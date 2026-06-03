"""Compare retrieval quality before and after a simple retrieval gate.

The gate does not call Claude and does not change the product pipeline. It runs
the existing retriever on golden cases, checks required legal article coverage,
then tries a conservative repair step: directly search for missing required
articles and merge those article references into the evidence set.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.domain.fact_checker import check_facts
from src.domain.query_enrichment import build_rag_query
from src.domain.query_input import RAGQueryInput
from src.domain.retrieval_quality import (
    ArticleRef,
    RetrievalQuality,
    article_refs_from_chunks,
    assess_retrieval_quality,
    assess_retrieval_quality_from_refs,
)
from src.retrieval.retriever_impl import PineconeTaxLawRetriever
from tests.rag_golden_cases import RAG_GOLDEN_CASES


@dataclass
class GateEvalCase:
    case_id: str
    title: str
    blocked_at_l2: bool
    base_quality: Optional[dict]
    enhanced_query_quality: Optional[dict]
    gated_quality: Optional[dict]
    enhanced_query_improved: bool
    metadata_improved: bool
    added_articles: List[str]
    elapsed_s: float
    error: Optional[str] = None


def _build_query(case: dict[str, Any]) -> RAGQueryInput:
    return RAGQueryInput.from_fact_ledger(
        fact_ledger=case["fact_ledger"],
        owner_profile=case["owner_profile"],
        user_property=case["user_property"],
    )


def _article_ref_from_label(label: str) -> ArticleRef:
    law_name, article = label.rsplit(" 제", 1)
    return ArticleRef(law_name=law_name, article_number=article.removesuffix("조"))


def _legacy_article_refs_for_missing(labels: list[str], top_k: int, rerank_top_n: int) -> tuple[list[ArticleRef], list[float]]:
    from src.infra.embedder import embed_query
    from src.infra.pinecone_client import query_pinecone

    refs: list[ArticleRef] = []
    scores: list[float] = []

    for label in labels:
        ref = _article_ref_from_label(label)
        vector = embed_query(label)
        matches = query_pinecone(
            vector=vector,
            top_k=top_k,
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
        refs.append(ArticleRef(meta.get("law_name", ref.law_name), meta.get("article_number", ref.article_number)))
        scores.append(float(best.get("score", 0.0)))

    return refs, scores


def _merge_refs(base_refs: list[ArticleRef], added_refs: list[ArticleRef]) -> list[ArticleRef]:
    seen: set[tuple[str, str]] = set()
    merged: list[ArticleRef] = []
    for ref in base_refs + added_refs:
        key = (ref.law_name.replace(" ", ""), ref.article_number.replace(" ", ""))
        if key in seen:
            continue
        seen.add(key)
        merged.append(ref)
    return merged


def _retrieve_with_text(
    retriever: PineconeTaxLawRetriever,
    query: RAGQueryInput,
    query_text: str,
) -> list:
    """Run the main Pinecone+BGE retrieval path using an explicit query text."""

    from src.infra.embedder import bm25_sparse_vector, embed_query
    from src.infra.pinecone_client import query_pinecone
    from src.infra.reranker import rerank
    from src.retrieval.retriever_impl import (
        _HYBRID_ALPHA,
        _cheap_prefilter,
        _pinecone_meta_to_chunk_metadata,
        _select_anchor_date,
    )
    from src.domain.retriever import RetrievedChunk

    vector = embed_query(query_text)
    top_k = getattr(query, "top_k", None) or retriever.top_k

    sparse_vec = None
    hybrid_alpha = None
    if _HYBRID_ALPHA is not None:
        hybrid_alpha = _HYBRID_ALPHA
        sparse_vec = bm25_sparse_vector(query_text)

    anchor_date = _select_anchor_date(query)
    as_of_int = int(anchor_date.strftime("%Y%m%d"))
    pinecone_filter = {
        "$and": [
            {"effective_date": {"$lte": as_of_int}},
            {"expiration_date": {"$gte": as_of_int}},
        ]
    }

    matches = query_pinecone(
        vector=vector,
        top_k=top_k,
        namespace=retriever.namespace,
        filter_dict=pinecone_filter,
        sparse_vector=sparse_vec,
        alpha=hybrid_alpha,
    )
    if not matches:
        matches = query_pinecone(
            vector=vector,
            top_k=top_k,
            namespace=retriever.namespace,
            sparse_vector=sparse_vec,
            alpha=hybrid_alpha,
        )
    if not matches:
        return []

    scope_val = query.entity_scope.value
    if scope_val:
        filtered = [
            m for m in matches
            if not m.get("metadata", {}).get("entity_scopes")
            or scope_val in m["metadata"]["entity_scopes"]
        ]
        matches = filtered if filtered else matches

    ranked = rerank(query_text, _cheap_prefilter(matches, query_text), retriever.rerank_top_n)
    chunks = []
    for score, match in ranked:
        meta = match["metadata"]
        chunks.append(
            RetrievedChunk(
                metadata=_pinecone_meta_to_chunk_metadata(match["id"], meta),
                content=meta.get("full_text", ""),
                score=float(score),
            )
        )
    return chunks


def _run_case(
    case: dict[str, Any],
    retriever: PineconeTaxLawRetriever,
    threshold: float,
    repair_top_k: int,
    repair_rerank_top_n: int,
) -> GateEvalCase:
    started = time.monotonic()
    case_id = case["case_id"]
    title = case.get("title", "")

    query = _build_query(case)
    fact_check = check_facts(query)
    if not fact_check.can_proceed:
        return GateEvalCase(
            case_id=case_id,
            title=title,
            blocked_at_l2=True,
            base_quality=None,
            enhanced_query_quality=None,
            gated_quality=None,
            enhanced_query_improved=False,
            metadata_improved=False,
            added_articles=[],
            elapsed_s=round(time.monotonic() - started, 2),
        )

    chunks = retriever.retrieve_with_buchik(query)
    base_quality = assess_retrieval_quality(query, chunks, fact_check.danger_flags)

    enriched_query = build_rag_query(query, fact_check.danger_flags)
    enhanced_chunks = _retrieve_with_text(retriever, query, enriched_query)
    enhanced_quality = assess_retrieval_quality(query, enhanced_chunks, fact_check.danger_flags)

    added_refs: list[ArticleRef] = []
    added_scores: list[float] = []
    if enhanced_quality.confidence < threshold and enhanced_quality.missing_required_articles:
        added_refs, added_scores = _legacy_article_refs_for_missing(
            enhanced_quality.missing_required_articles,
            top_k=repair_top_k,
            rerank_top_n=repair_rerank_top_n,
        )

    enhanced_refs = article_refs_from_chunks(enhanced_chunks)
    gated_refs = _merge_refs(enhanced_refs, added_refs)
    gated_quality: RetrievalQuality = assess_retrieval_quality_from_refs(
        query=query,
        article_refs=gated_refs,
        scores=[chunk.score for chunk in enhanced_chunks] + added_scores,
        danger_flags=fact_check.danger_flags,
        result_count=len(enhanced_chunks) + len(added_refs),
        has_date_filter_signal=bool(enhanced_chunks),
        has_scope_signal=bool(enhanced_chunks),
        has_buchik=any(chunk.included_as_linked_buchik for chunk in enhanced_chunks),
    )

    return GateEvalCase(
        case_id=case_id,
        title=title,
        blocked_at_l2=False,
        base_quality=asdict(base_quality),
        enhanced_query_quality=asdict(enhanced_quality),
        gated_quality=asdict(gated_quality),
        enhanced_query_improved=enhanced_quality.confidence > base_quality.confidence,
        metadata_improved=gated_quality.confidence > enhanced_quality.confidence,
        added_articles=[ref.label for ref in added_refs],
        elapsed_s=round(time.monotonic() - started, 2),
    )


def _summarize(results: list[GateEvalCase]) -> dict[str, Any]:
    runnable = [r for r in results if not r.blocked_at_l2 and not r.error]
    blocked = [r for r in results if r.blocked_at_l2]
    errors = [r for r in results if r.error]

    def avg(values: list[float]) -> float:
        return round(sum(values) / len(values), 4) if values else 0.0

    base_conf = [r.base_quality["confidence"] for r in runnable if r.base_quality]
    enhanced_conf = [r.enhanced_query_quality["confidence"] for r in runnable if r.enhanced_query_quality]
    gated_conf = [r.gated_quality["confidence"] for r in runnable if r.gated_quality]
    base_cov = [r.base_quality["coverage_score"] for r in runnable if r.base_quality]
    enhanced_cov = [r.enhanced_query_quality["coverage_score"] for r in runnable if r.enhanced_query_quality]
    gated_cov = [r.gated_quality["coverage_score"] for r in runnable if r.gated_quality]
    base_missing = [len(r.base_quality["missing_required_articles"]) for r in runnable if r.base_quality]
    enhanced_missing = [
        len(r.enhanced_query_quality["missing_required_articles"])
        for r in runnable
        if r.enhanced_query_quality
    ]
    gated_missing = [len(r.gated_quality["missing_required_articles"]) for r in runnable if r.gated_quality]

    return {
        "total": len(results),
        "runnable": len(runnable),
        "blocked_at_l2": len(blocked),
        "errors": len(errors),
        "enhanced_query_improved_cases": sum(1 for r in runnable if r.enhanced_query_improved),
        "metadata_improved_cases": sum(1 for r in runnable if r.metadata_improved),
        "avg_base_confidence": avg(base_conf),
        "avg_enhanced_query_confidence": avg(enhanced_conf),
        "avg_gated_confidence": avg(gated_conf),
        "avg_enhanced_query_confidence_delta": round(avg(enhanced_conf) - avg(base_conf), 4),
        "avg_metadata_confidence_delta": round(avg(gated_conf) - avg(enhanced_conf), 4),
        "avg_total_confidence_delta": round(avg(gated_conf) - avg(base_conf), 4),
        "avg_base_coverage": avg(base_cov),
        "avg_enhanced_query_coverage": avg(enhanced_cov),
        "avg_gated_coverage": avg(gated_cov),
        "avg_enhanced_query_coverage_delta": round(avg(enhanced_cov) - avg(base_cov), 4),
        "avg_metadata_coverage_delta": round(avg(gated_cov) - avg(enhanced_cov), 4),
        "avg_total_coverage_delta": round(avg(gated_cov) - avg(base_cov), 4),
        "avg_base_missing_required": avg(base_missing),
        "avg_enhanced_query_missing_required": avg(enhanced_missing),
        "avg_gated_missing_required": avg(gated_missing),
        "avg_enhanced_query_missing_delta": round(avg(enhanced_missing) - avg(base_missing), 4),
        "avg_metadata_missing_delta": round(avg(gated_missing) - avg(enhanced_missing), 4),
        "avg_total_missing_required_delta": round(avg(gated_missing) - avg(base_missing), 4),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--threshold", type=float, default=0.75)
    parser.add_argument("--repair-top-k", type=int, default=15)
    parser.add_argument("--repair-rerank-top-n", type=int, default=5)
    parser.add_argument("--output", type=Path, default=Path("data/eval_results/retrieval_gate_eval.json"))
    args = parser.parse_args()

    cases = RAG_GOLDEN_CASES[: args.limit] if args.limit else RAG_GOLDEN_CASES
    retriever = PineconeTaxLawRetriever()
    results: list[GateEvalCase] = []

    for idx, case in enumerate(cases, 1):
        try:
            result = _run_case(
                case=case,
                retriever=retriever,
                threshold=args.threshold,
                repair_top_k=args.repair_top_k,
                repair_rerank_top_n=args.repair_rerank_top_n,
            )
        except Exception as exc:
            result = GateEvalCase(
                case_id=case.get("case_id", "unknown"),
                title=case.get("title", ""),
                blocked_at_l2=False,
                base_quality=None,
                enhanced_query_quality=None,
                gated_quality=None,
                enhanced_query_improved=False,
                metadata_improved=False,
                added_articles=[],
                elapsed_s=0.0,
                error=str(exc),
            )
        results.append(result)

        if result.error:
            print(f"[{idx:02d}/{len(cases)}] ERR {result.case_id}: {result.error}")
        elif result.blocked_at_l2:
            print(f"[{idx:02d}/{len(cases)}] L2  {result.case_id}: blocked")
        else:
            base = result.base_quality or {}
            enhanced = result.enhanced_query_quality or {}
            gated = result.gated_quality or {}
            print(
                f"[{idx:02d}/{len(cases)}] {result.case_id}: "
                f"conf {base.get('confidence', 0):.2f} -> "
                f"{enhanced.get('confidence', 0):.2f} -> "
                f"{gated.get('confidence', 0):.2f}, "
                f"missing {len(base.get('missing_required_articles', []))} -> "
                f"{len(enhanced.get('missing_required_articles', []))} -> "
                f"{len(gated.get('missing_required_articles', []))}"
            )

    summary = _summarize(results)
    payload = {
        "threshold": args.threshold,
        "repair_top_k": args.repair_top_k,
        "repair_rerank_top_n": args.repair_rerank_top_n,
        "summary": summary,
        "results": [asdict(r) for r in results],
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== Retrieval Gate Eval Summary ===")
    for key, value in summary.items():
        print(f"{key}: {value}")
    print(f"\nSaved: {args.output}")


if __name__ == "__main__":
    main()
