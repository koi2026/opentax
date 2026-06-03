"""MCP server for tax-rag retrieval tools."""
from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from src.config import MCP_HOST, MCP_PORT
from src.domain.query_enrichment import enrich_raw_query_text
from src.mcp.tools.retrieval import retrieve_tax_context_payload
from src.retrieval.tax_law_search import retrieve_tax_law

mcp = FastMCP(
    name="tax-rag",
    instructions=(
        "한국 양도소득세 비과세·감면·중과 여부 판단을 위한 RAG 검색 서버입니다. "
        "API 서버가 이 MCP 도구를 호출해 검색된 chunk_id 기반으로만 판단합니다."
    ),
    host=MCP_HOST,
    port=MCP_PORT,
)


@mcp.tool()
def retrieve_tax_context(
    fact_json: dict[str, Any],
    query_text: str = "",
    top_k: int = 20,
    rerank_top_n: int = 7,
    include_buchik: bool = True,
) -> dict[str, Any]:
    """RAG 파이프라인 전용 법령·유권해석 검색 tool."""
    return retrieve_tax_context_payload(
        fact_json=fact_json,
        query_text=query_text,
        top_k=top_k,
        rerank_top_n=rerank_top_n,
        include_buchik=include_buchik,
    )


@mcp.tool()
def search_tax_law(
    query: str,
    top_k: int = 20,
    rerank_top_n: int = 5,
    as_of_date: str = "",
) -> str:
    """Human-facing 법령 검색 tool."""
    enriched_query = enrich_raw_query_text(query)
    chunks = retrieve_tax_law(
        enriched_query,
        top_k=top_k,
        rerank_top_n=rerank_top_n,
        as_of_date=as_of_date or None,
    )
    if not chunks:
        return "관련 법령 조문을 찾을 수 없습니다."

    lines = []
    for i, chunk in enumerate(chunks, 1):
        lines.append(
            f"[{i}] {chunk.law_name} 제{chunk.article_number}조 {chunk.article_title}\n"
            f"    chunk_id: {chunk.id} | rerank_score: {chunk.score:.4f}\n"
            f"    {chunk.full_text[:500]}"
        )
    return "\n\n".join(lines)


@mcp.tool()
def retrieve_article(law_name: str, article_number: str) -> str:
    """Human-facing 특정 조문 조회 tool."""
    query = f"{law_name} 제{article_number}조"
    chunks = retrieve_tax_law(query, top_k=20, rerank_top_n=10)
    matched = [
        c for c in chunks
        if c.law_name == law_name and c.article_number == article_number
    ]
    if not matched:
        return f"{law_name} 제{article_number}조를 찾을 수 없습니다."
    return "\n\n---\n\n".join(
        f"{chunk.law_name} 제{chunk.article_number}조 {chunk.article_title}\n"
        f"chunk_id: {chunk.id}\n\n{chunk.full_text}"
        for chunk in matched
    )


@mcp.tool()
def verify_citations(question: str, chunk_ids: list[str]) -> str:
    """검색 결과에 존재하는 chunk_id인지 검증합니다."""
    chunks = retrieve_tax_law(question, top_k=20, rerank_top_n=10)
    retrieved_ids = {c.id for c in chunks}
    verified = [cid for cid in chunk_ids if cid in retrieved_ids]
    unverified = [cid for cid in chunk_ids if cid not in retrieved_ids]
    return json.dumps(
        {
            "verified_chunk_ids": verified,
            "unverified_chunk_ids": unverified,
            "warning": (
                f"{len(unverified)}개 chunk_id가 검색 결과에 없습니다. 인용 금지."
                if unverified
                else "모든 chunk_id 검증 완료"
            ),
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
async def calculate_tax(
    transfer_price: int,
    acquisition_price: int,
    transfer_date: str,
    acquisition_date: str,
    household_house_count: int = 1,
    residence_years: float = 0.0,
    is_adjustment_area_at_transfer: bool = False,
) -> dict:
    """양도소득세 결정론 계산 tool."""
    from datetime import date as _date

    from src.calculator.tax_calculator import (
        TaxCalculationInput,
        calculate_transfer_tax,
        compute_ltshd_rate,
    )
    from src.domain.tax_constants import TaxConstantsRegistry

    t_date = _date(int(transfer_date[:4]), int(transfer_date[4:6]), int(transfer_date[6:8]))
    a_date = _date(int(acquisition_date[:4]), int(acquisition_date[4:6]), int(acquisition_date[6:8]))
    holding_years = (t_date - a_date).days / 365.25
    high_value_threshold = TaxConstantsRegistry.get("HIGH_VALUE_THRESHOLD", t_date)
    is_high_value = transfer_price > high_value_threshold
    is_one_house = household_house_count == 1
    ltshd_rate = compute_ltshd_rate(holding_years, residence_years, is_one_house, as_of=t_date)

    result = calculate_transfer_tax(
        TaxCalculationInput(
            transfer_price=transfer_price,
            acquisition_price=acquisition_price,
            transfer_date=t_date,
            acquisition_date=a_date,
            holding_years=holding_years,
            residence_years=residence_years,
            household_house_count=household_house_count,
            is_one_house_exemption=is_one_house and not is_high_value,
            is_high_value_house=is_high_value,
            is_heavy_tax=household_house_count >= 2 and is_adjustment_area_at_transfer,
            is_short_term=holding_years < 2.0,
            long_term_deduction_rate=ltshd_rate,
        )
    )
    return {
        "gross_gain": result.gross_gain,
        "long_term_deduction": result.long_term_deduction,
        "taxable_income": result.taxable_income,
        "applied_rate": f"{result.applied_rate:.1%}",
        "rate_type": result.rate_type,
        "calculated_tax": result.calculated_tax,
        "local_income_tax": result.local_income_tax,
        "total_tax": result.total_tax,
        "deduction_summary": result.deduction_summary,
        "warnings": result.warnings,
    }


@mcp.tool()
async def check_area_designation(
    region: str,
    target_date: str,
    area_type: str = "조정대상지역",
) -> dict:
    """특정 날짜의 규제지역 지정 여부 조회 tool."""
    from datetime import date as _date

    from src.ingestion.admin_notices import load_manual_table, resolve_area_status

    t_date = _date(int(target_date[:4]), int(target_date[4:6]), int(target_date[6:8]))
    records = load_manual_table()
    return {
        "region": region,
        "target_date": target_date,
        "area_type": area_type,
        "is_designated": resolve_area_status(region, t_date, area_type, records),
        "source": "manual_table",
    }


@mcp.tool()
async def lookup_ruling(
    query: str,
    ruling_type: str = "all",
    top_k: int = 5,
) -> str:
    """유권해석 DB 검색 tool."""
    namespaces: dict[str, list[str]] = {
        "ntis": ["tax-ruling-nts", "tax-ruling-nts-interp"],
        "moef": ["tax-ruling-moef"],
        "tt": ["tax-ruling-decisions"],
        "court": ["tax-ruling-pdf"],
        "all": [
            "tax-ruling-moef",
            "tax-ruling-nts",
            "tax-ruling-nts-interp",
            "tax-ruling-decisions",
            "tax-ruling-pdf",
        ],
    }
    if ruling_type not in namespaces:
        return json.dumps(
            {"error": f"ruling_type 오류: '{ruling_type}'. 허용 값: ntis | moef | tt | court | all"},
            ensure_ascii=False,
            indent=2,
        )

    try:
        from src.infra.embedder import embed_query
        from src.infra.pinecone_client import get_pinecone_index

        index = get_pinecone_index()
        query_vector = embed_query(query)
    except Exception as exc:
        return json.dumps(
            {
                "status": "유권해석 DB 미수집",
                "message": "유권해석 DB 또는 임베딩 환경을 초기화할 수 없습니다.",
                "detail": str(exc),
            },
            ensure_ascii=False,
            indent=2,
        )

    results: list[dict[str, Any]] = []
    for namespace in namespaces[ruling_type]:
        try:
            response = index.query(
                vector=query_vector,
                top_k=top_k,
                namespace=namespace,
                include_metadata=True,
            )
        except Exception:
            continue
        for match in response.get("matches", []):
            meta = match.get("metadata", {})
            results.append(
                {
                    "ruling_id": meta.get("ruling_id", match["id"]),
                    "ruling_type": meta.get("ruling_type", namespace.replace("tax-ruling-", "")),
                    "title": meta.get("title", ""),
                    "issue_date": meta.get("issue_date", ""),
                    "summary": meta.get("summary", "")[:500],
                    "related_articles": meta.get("related_articles", []),
                    "score": round(match.get("score", 0.0), 4),
                    "namespace": namespace,
                }
            )

    results.sort(key=lambda item: item["score"], reverse=True)
    return json.dumps(
        {
            "status": "ok" if results else "유권해석 DB 미수집",
            "query": query,
            "ruling_type": ruling_type,
            "total": min(len(results), top_k),
            "results": results[:top_k],
        },
        ensure_ascii=False,
        indent=2,
    )


if __name__ == "__main__":
    import sys

    if "--sse" in sys.argv:
        mcp.run(transport="sse")
    else:
        mcp.run(transport="stdio")
