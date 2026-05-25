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
    base_match: Optional[bool]
    repaired_match: Optional[bool]
    verdict_changed: bool
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

    return VerdictEvalCase(
        case_id=case["case_id"],
        title=case.get("title", ""),
        expected_verdict=expected,
        base=base,
        repaired=repaired,
        base_match=_match(expected, base.verdict, case["case_id"]),
        repaired_match=_match(expected, repaired.verdict, case["case_id"]),
        verdict_changed=base.verdict != repaired.verdict,
        elapsed_s=round(time.monotonic() - started, 2),
    )


def _summarize(results: list[VerdictEvalCase]) -> dict[str, Any]:
    comparable = [r for r in results if r.base_match is not None and r.repaired_match is not None]
    changed = [r for r in results if r.verdict_changed]
    errors = [r for r in results if r.base.error or r.repaired.error]

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
        "verdict_changed": len(changed),
        "base_accuracy": acc("base"),
        "repaired_accuracy": acc("repaired"),
        "accuracy_delta": round(acc("repaired") - acc("base"), 4),
        "avg_base_answer_confidence": avg([r.base.confidence for r in results if not r.base.error]),
        "avg_repaired_answer_confidence": avg([r.repaired.confidence for r in results if not r.repaired.error]),
        "avg_base_retrieval_confidence": avg([r.base.retrieval_confidence for r in results if not r.base.error]),
        "avg_repaired_retrieval_confidence": avg([r.repaired.retrieval_confidence for r in results if not r.repaired.error]),
    }


async def main_async() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
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

    results: list[VerdictEvalCase] = []
    for idx, case in enumerate(cases, 1):
        result = await _run_case(case)
        results.append(result)
        print(
            f"[{idx:02d}/{len(cases)}] {result.case_id}: "
            f"{result.base.verdict}({result.base.confidence:.2f}, r={result.base.retrieval_confidence:.2f}) -> "
            f"{result.repaired.verdict}({result.repaired.confidence:.2f}, r={result.repaired.retrieval_confidence:.2f}) "
            f"expected={result.expected_verdict}"
        )
        if result.base.error or result.repaired.error:
            print(f"  error base={result.base.error} repaired={result.repaired.error}")

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
