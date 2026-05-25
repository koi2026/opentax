"""Compare final pipeline verdicts with and without metadata retrieval repair.

This is an evaluation-only script. It does not modify the application pipeline.
It runs the normal pipeline once, then runs it again with a wrapper retriever
that adds missing required legal anchor articles by Pinecone metadata filter
before the LLM sees the context.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.domain.fact_checker import check_facts
from src.domain.pipeline import run_rag_pipeline
from src.domain.query_input import RAGQueryInput
from src.domain.retrieval_quality import (
    ArticleRef,
    assess_retrieval_quality,
    required_articles_for_query,
)
from src.domain.retriever import RetrievedChunk
from src.eval.verdict_matcher import compute_reward
from src.retrieval.llm_fn import llm_fn
from src.retrieval.retriever_impl import PineconeTaxLawRetriever
from tests.rag_golden_cases import RAG_GOLDEN_CASES


@dataclass
class VerdictRun:
    verdict: str
    answer: str
    confidence: float
    blocked: bool
    retrieval_confidence: float
    missing_required_articles: List[str]
    retrieved_articles: List[str]
    retrieved_chunk_ids: List[str]
    citations: List[str]
    warnings: List[str]
    error: Optional[str] = None


@dataclass
class VerdictEvalCase:
    case_id: str
    title: str
    expected_verdict: Optional[str]
    base: VerdictRun
    repaired: VerdictRun
    expanded: VerdictRun
    base_match: Optional[bool]
    repaired_match: Optional[bool]
    expanded_match: Optional[bool]
    metadata_verdict_changed: bool
    expanded_verdict_changed: bool
    elapsed_s: float


def _build_query(case: dict[str, Any]) -> RAGQueryInput:
    return RAGQueryInput.from_fact_ledger(
        fact_ledger=case["fact_ledger"],
        owner_profile=case["owner_profile"],
        user_property=case["user_property"],
    )


def _article_ref_from_label(label: str) -> ArticleRef:
    law_name, article = label.rsplit(" 제", 1)
    return ArticleRef(law_name=law_name, article_number=article.removesuffix("조"))


def _fetch_required_articles(labels: list[str], namespace: str) -> list[RetrievedChunk]:
    from src.infra.embedder import embed_query
    from src.infra.pinecone_client import query_pinecone
    from src.retrieval.retriever_impl import _pinecone_meta_to_chunk_metadata

    chunks: list[RetrievedChunk] = []
    for label in labels:
        ref = _article_ref_from_label(label)
        vector = embed_query(label)
        matches = query_pinecone(
            vector=vector,
            top_k=5,
            namespace=namespace,
            filter_dict={
                "$and": [
                    {"law_name": {"$eq": ref.law_name}},
                    {"article_number": {"$eq": ref.article_number}},
                ]
            },
        )
        if not matches:
            continue
        best = max(matches, key=lambda m: float(m.get("score", 0.0)))
        meta = best.get("metadata", {})
        chunks.append(
            RetrievedChunk(
                metadata=_pinecone_meta_to_chunk_metadata(best["id"], meta),
                content=meta.get("full_text", ""),
                score=float(best.get("score", 0.0)),
            )
        )
    return chunks


def _dedupe_chunks(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    seen: set[str] = set()
    result: list[RetrievedChunk] = []
    for chunk in chunks:
        if chunk.metadata.chunk_id in seen:
            continue
        seen.add(chunk.metadata.chunk_id)
        result.append(chunk)
    return result


def _secondary_query_for_anchor(chunk: RetrievedChunk) -> str:
    label = f"{chunk.metadata.law_name} 제{chunk.metadata.article_number}조"
    content = " ".join(chunk.content.split())[:700]
    return f"{label} {content}"


def _secondary_retrieve_for_anchors(
    retriever: PineconeTaxLawRetriever,
    query: RAGQueryInput,
    anchors: list[RetrievedChunk],
    max_total: int = 5,
) -> list[RetrievedChunk]:
    from src.infra.embedder import bm25_sparse_vector, embed_query
    from src.infra.pinecone_client import query_pinecone
    from src.infra.reranker import rerank
    from src.retrieval.retriever_impl import (
        _HYBRID_ALPHA,
        _cheap_prefilter,
        _pinecone_meta_to_chunk_metadata,
        _select_anchor_date,
    )

    results: list[RetrievedChunk] = []
    anchor_date = _select_anchor_date(query)
    as_of_int = int(anchor_date.strftime("%Y%m%d"))
    for anchor in anchors:
        query_text = _secondary_query_for_anchor(anchor)
        pinecone_filter = {
            "$and": [
                {"effective_date": {"$lte": as_of_int}},
                {"expiration_date": {"$gte": as_of_int}},
                {"law_name": {"$eq": anchor.metadata.law_name}},
            ]
        }
        sparse_vec = None
        hybrid_alpha = None
        if _HYBRID_ALPHA is not None:
            hybrid_alpha = _HYBRID_ALPHA
            sparse_vec = bm25_sparse_vector(query_text)

        matches = query_pinecone(
            vector=embed_query(query_text),
            top_k=8,
            namespace=retriever.namespace,
            filter_dict=pinecone_filter,
            sparse_vector=sparse_vec,
            alpha=hybrid_alpha,
        )
        if not matches:
            continue

        scope_val = query.entity_scope.value
        if scope_val:
            scoped = [
                m for m in matches
                if not m.get("metadata", {}).get("entity_scopes")
                or scope_val in m["metadata"]["entity_scopes"]
            ]
            matches = scoped if scoped else matches

        for score, match in rerank(query_text, _cheap_prefilter(matches, query_text), top_n=3):
            meta = match["metadata"]
            results.append(
                RetrievedChunk(
                    metadata=_pinecone_meta_to_chunk_metadata(match["id"], meta),
                    content=meta.get("full_text", ""),
                    score=float(score),
                )
            )
            if len(_dedupe_chunks(results)) >= max_total:
                return _dedupe_chunks(results)[:max_total]

    return _dedupe_chunks(results)[:max_total]


class MetadataRepairRetriever(PineconeTaxLawRetriever):
    """Evaluation wrapper that repairs missing required articles after retrieval."""

    def retrieve_with_buchik(self, query: RAGQueryInput) -> List[RetrievedChunk]:
        chunks = super().retrieve_with_buchik(query)
        fact_check = check_facts(query)
        quality = assess_retrieval_quality(query, chunks, fact_check.danger_flags)
        if not quality.missing_required_articles:
            return chunks

        extras = _fetch_required_articles(quality.missing_required_articles, self.namespace)
        seen = {chunk.metadata.chunk_id for chunk in chunks}
        for extra in extras:
            if extra.metadata.chunk_id in seen:
                continue
            chunks.append(extra)
            seen.add(extra.metadata.chunk_id)
        return chunks


class ExpandedMetadataRepairRetriever(PineconeTaxLawRetriever):
    """Metadata repair plus linked-buchik expansion, without secondary search."""

    def _expand_buchik_for(self, chunks: list[RetrievedChunk], query: RAGQueryInput) -> list[RetrievedChunk]:
        expanded: list[RetrievedChunk] = []
        for chunk in chunks:
            for buchik_id in chunk.metadata.linked_buchik_ids:
                buchik_meta = self._get_chunk_by_id(buchik_id)
                if buchik_meta is None:
                    continue
                buchik_chunk = RetrievedChunk(
                    metadata=buchik_meta,
                    content=self._get_content(buchik_id),
                    score=chunk.score,
                    included_as_linked_buchik=True,
                )
                if not self._is_buchik_applicable(buchik_chunk, query):
                    continue
                expanded.append(buchik_chunk)
        return expanded

    def retrieve_with_buchik(self, query: RAGQueryInput) -> List[RetrievedChunk]:
        chunks = super().retrieve_with_buchik(query)
        fact_check = check_facts(query)
        quality = assess_retrieval_quality(query, chunks, fact_check.danger_flags)
        if not quality.missing_required_articles:
            return chunks

        anchors = _fetch_required_articles(quality.missing_required_articles, self.namespace)
        linked_buchik = self._expand_buchik_for(anchors, query)
        return _dedupe_chunks(chunks + anchors + linked_buchik)


class MetadataOnlyRetriever(ExpandedMetadataRepairRetriever):
    """Use only rule-derived metadata anchors plus linked buchik, no base embedding retrieval."""

    def retrieve_with_buchik(self, query: RAGQueryInput) -> List[RetrievedChunk]:
        fact_check = check_facts(query)
        required = required_articles_for_query(query, fact_check.danger_flags)
        anchors = _fetch_required_articles([req.label for req in required], self.namespace)
        linked_buchik = self._expand_buchik_for(anchors, query)
        return _dedupe_chunks(anchors + linked_buchik)


async def _run_pipeline_once(query: RAGQueryInput, retriever: PineconeTaxLawRetriever) -> VerdictRun:
    try:
        result = await run_rag_pipeline(
            query=query,
            retriever=retriever,
            llm_fn=llm_fn,
            enable_debate=False,
            confirmed=None,
        )
        quality = assess_retrieval_quality(
            query,
            result.retrieved_chunks,
            result.fact_check.danger_flags,
        )
        return VerdictRun(
            verdict=result.answer.verdict,
            answer=result.answer.answer,
            confidence=result.answer.confidence,
            blocked=result.blocked_at_l2 or result.blocked_at_confirmation,
            retrieval_confidence=quality.confidence,
            missing_required_articles=quality.missing_required_articles,
            retrieved_articles=[
                f"{chunk.metadata.law_name} 제{chunk.metadata.article_number}조"
                for chunk in result.retrieved_chunks
            ],
            retrieved_chunk_ids=[chunk.metadata.chunk_id for chunk in result.retrieved_chunks],
            citations=[
                citation.article if hasattr(citation, "article") else str(citation)
                for citation in result.answer.citations
            ],
            warnings=result.answer.warnings,
        )
    except Exception as exc:
        return VerdictRun(
            verdict="오류",
            answer="",
            confidence=0.0,
            blocked=False,
            retrieval_confidence=0.0,
            missing_required_articles=[],
            retrieved_articles=[],
            retrieved_chunk_ids=[],
            citations=[],
            warnings=[],
            error=str(exc),
        )


def _match(expected: Optional[str], actual: str, case_id: str) -> Optional[bool]:
    if not expected or actual == "오류":
        return None
    return compute_reward(
        case_id=case_id,
        expected_verdict=expected,
        actual_verdict=actual,
        confidence=0.0,
    ).verdict_match


async def _run_case(case: dict[str, Any]) -> VerdictEvalCase:
    started = time.monotonic()
    query = _build_query(case)
    expected = case.get("expected", {}).get("verdict")

    base = await _run_pipeline_once(query, PineconeTaxLawRetriever())
    repaired = await _run_pipeline_once(query, MetadataRepairRetriever())
    expanded = await _run_pipeline_once(query, ExpandedMetadataRepairRetriever())

    return VerdictEvalCase(
        case_id=case["case_id"],
        title=case.get("title", ""),
        expected_verdict=expected,
        base=base,
        repaired=repaired,
        expanded=expanded,
        base_match=_match(expected, base.verdict, case["case_id"]),
        repaired_match=_match(expected, repaired.verdict, case["case_id"]),
        expanded_match=_match(expected, expanded.verdict, case["case_id"]),
        metadata_verdict_changed=base.verdict != repaired.verdict,
        expanded_verdict_changed=repaired.verdict != expanded.verdict,
        elapsed_s=round(time.monotonic() - started, 2),
    )


def _summarize(results: list[VerdictEvalCase]) -> dict[str, Any]:
    comparable = [
        r for r in results
        if r.base_match is not None and r.repaired_match is not None and r.expanded_match is not None
    ]
    metadata_changed = [r for r in results if r.metadata_verdict_changed]
    expanded_changed = [r for r in results if r.expanded_verdict_changed]
    errors = [r for r in results if r.base.error or r.repaired.error or r.expanded.error]

    def acc(which: str) -> float:
        if not comparable:
            return 0.0
        return round(
            sum(1 for r in comparable if getattr(r, which + "_match") is True) / len(comparable),
            4,
        )

    def avg(vals: list[float]) -> float:
        return round(sum(vals) / len(vals), 4) if vals else 0.0

    return {
        "total": len(results),
        "comparable": len(comparable),
        "errors": len(errors),
        "metadata_verdict_changed": len(metadata_changed),
        "expanded_verdict_changed": len(expanded_changed),
        "base_accuracy": acc("base"),
        "repaired_accuracy": acc("repaired"),
        "expanded_accuracy": acc("expanded"),
        "metadata_accuracy_delta": round(acc("repaired") - acc("base"), 4),
        "expanded_accuracy_delta": round(acc("expanded") - acc("repaired"), 4),
        "total_accuracy_delta": round(acc("expanded") - acc("base"), 4),
        "avg_base_answer_confidence": avg([r.base.confidence for r in results if not r.base.error]),
        "avg_repaired_answer_confidence": avg([r.repaired.confidence for r in results if not r.repaired.error]),
        "avg_expanded_answer_confidence": avg([r.expanded.confidence for r in results if not r.expanded.error]),
        "avg_base_retrieval_confidence": avg([r.base.retrieval_confidence for r in results if not r.base.error]),
        "avg_repaired_retrieval_confidence": avg([r.repaired.retrieval_confidence for r in results if not r.repaired.error]),
        "avg_expanded_retrieval_confidence": avg([r.expanded.retrieval_confidence for r in results if not r.expanded.error]),
    }


async def main_async() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--only-expanded",
        action="store_true",
        help="Run only the expanded retriever for cases whose base/metadata results are already known.",
    )
    parser.add_argument(
        "--only-metadata-source",
        action="store_true",
        help="Run only rule-derived metadata anchors plus linked buchik, without base embedding retrieval.",
    )
    parser.add_argument(
        "--case-ids",
        type=str,
        default="",
        help="Comma-separated case IDs to run, e.g. CASE-04,CASE-05.",
    )
    parser.add_argument("--output", type=Path, default=Path("data/eval_results/metadata_retrieval_verdict_eval.json"))
    args = parser.parse_args()

    cases = RAG_GOLDEN_CASES[: args.limit] if args.limit else RAG_GOLDEN_CASES
    if args.case_ids:
        wanted = {case_id.strip() for case_id in args.case_ids.split(",") if case_id.strip()}
        cases = [case for case in cases if case["case_id"] in wanted]
        missing = wanted - {case["case_id"] for case in cases}
        if missing:
            raise ValueError(f"Unknown case IDs: {', '.join(sorted(missing))}")

    if args.only_expanded or args.only_metadata_source:
        mode_name = "metadata_source_only" if args.only_metadata_source else "expanded_only"
        retriever_cls = MetadataOnlyRetriever if args.only_metadata_source else ExpandedMetadataRepairRetriever
        results = []
        for idx, case in enumerate(cases, 1):
            started = time.monotonic()
            query = _build_query(case)
            expected = case.get("expected", {}).get("verdict")
            expanded = await _run_pipeline_once(query, retriever_cls())
            match = _match(expected, expanded.verdict, case["case_id"])
            row = {
                "case_id": case["case_id"],
                "title": case.get("title", ""),
                "expected_verdict": expected,
                "expanded": asdict(expanded),
                "expanded_match": match,
                "elapsed_s": round(time.monotonic() - started, 2),
            }
            results.append(row)
            print(
                f"[{idx:02d}/{len(cases)}] {case['case_id']}: "
                f"{expanded.verdict}({expanded.confidence:.2f}, r={expanded.retrieval_confidence:.2f}) "
                f"expected={expected}"
            )
            if expanded.error:
                print(f"  error expanded={expanded.error}")

        comparable = [r for r in results if r["expanded_match"] is not None]
        summary = {
            "total": len(results),
            "comparable": len(comparable),
            "errors": sum(1 for r in results if r["expanded"]["error"]),
            "expanded_accuracy": round(
                sum(1 for r in comparable if r["expanded_match"] is True) / len(comparable),
                4,
            ) if comparable else 0.0,
            "avg_expanded_answer_confidence": round(
                sum(r["expanded"]["confidence"] for r in results if not r["expanded"]["error"])
                / max(1, sum(1 for r in results if not r["expanded"]["error"])),
                4,
            ),
            "avg_expanded_retrieval_confidence": round(
                sum(r["expanded"]["retrieval_confidence"] for r in results if not r["expanded"]["error"])
                / max(1, sum(1 for r in results if not r["expanded"]["error"])),
                4,
            ),
        }
        payload = {
            "mode": mode_name,
            "summary": summary,
            "results": results,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n=== {mode_name} Eval Summary ===")
        for key, value in summary.items():
            print(f"{key}: {value}")
        print(f"\nSaved: {args.output}")
        return

    results: list[VerdictEvalCase] = []
    for idx, case in enumerate(cases, 1):
        result = await _run_case(case)
        results.append(result)
        print(
            f"[{idx:02d}/{len(cases)}] {result.case_id}: "
            f"{result.base.verdict}({result.base.confidence:.2f}, r={result.base.retrieval_confidence:.2f}) -> "
            f"{result.repaired.verdict}({result.repaired.confidence:.2f}, r={result.repaired.retrieval_confidence:.2f}) -> "
            f"{result.expanded.verdict}({result.expanded.confidence:.2f}, r={result.expanded.retrieval_confidence:.2f}) "
            f"expected={result.expected_verdict}"
        )
        if result.base.error or result.repaired.error or result.expanded.error:
            print(
                f"  error base={result.base.error} "
                f"repaired={result.repaired.error} expanded={result.expanded.error}"
            )

    payload = {
        "summary": _summarize(results),
        "results": [asdict(r) for r in results],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== Metadata Retrieval Verdict Eval Summary ===")
    for key, value in payload["summary"].items():
        print(f"{key}: {value}")
    print(f"\nSaved: {args.output}")


if __name__ == "__main__":
    asyncio.run(main_async())
