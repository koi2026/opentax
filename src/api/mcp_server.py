"""
MCP 서버 — tax-rag
FastMCP 기반: stdio(Claude Desktop) + SSE(HTTP 클라이언트) 양쪽 지원
"""
import json
from mcp.server.fastmcp import FastMCP

from src.config import MCP_HOST, MCP_PORT
from src.rag import retrieve_tax_law
from src.domain.query_enrichment import enrich_raw_query_text

mcp = FastMCP(
    name="tax-rag",
    instructions=(
        "한국 양도소득세 비과세·감면·중과 여부를 판단하는 법령 RAG 서버입니다. "
        "모든 답변은 law.go.kr 법령 조문 검색 결과에만 근거합니다."
    ),
    host=MCP_HOST,
    port=MCP_PORT,
)


# ── Tool 1: 법령 벡터 검색 ────────────────────────────────────────────────────

@mcp.tool()
def search_tax_law(
    query: str,
    top_k: int = 20,
    rerank_top_n: int = 5,
    as_of_date: str = "",
) -> str:
    """
    한국 양도소득세 관련 법령 조문을 벡터 검색 + BGE reranking으로 검색합니다.

    Args:
        query: 검색할 법령 키워드 또는 질문
        top_k: 벡터 검색 후보 수 (기본 20)
        rerank_top_n: BGE reranking 후 반환할 조문 수 (기본 5)
        as_of_date: 기준일자 YYYYMMDD (예: "20220101"). 비워두면 전체 버전 검색.
    """
    enriched_query = enrich_raw_query_text(query)
    chunks = retrieve_tax_law(
        enriched_query, top_k=top_k, rerank_top_n=rerank_top_n,
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


# ── Tool 2: 특정 조문 직접 조회 ───────────────────────────────────────────────

@mcp.tool()
def retrieve_article(law_name: str, article_number: str) -> str:
    """
    특정 법령의 조문 번호로 직접 조회합니다.

    Args:
        law_name: 법령명 (예: "소득세법", "소득세법 시행령")
        article_number: 조문 번호 (예: "89", "154")
    """
    query = f"{law_name} 제{article_number}조"
    chunks = retrieve_tax_law(query, top_k=20, rerank_top_n=10)

    matched = [
        c for c in chunks
        if c.law_name == law_name and c.article_number == article_number
    ]

    if not matched:
        return f"{law_name} 제{article_number}조를 찾을 수 없습니다."

    lines = []
    for chunk in matched:
        lines.append(
            f"{chunk.law_name} 제{chunk.article_number}조 {chunk.article_title}\n"
            f"chunk_id: {chunk.id}\n\n"
            f"{chunk.full_text}"
        )
    return "\n\n---\n\n".join(lines)


# ── Tool 3: 비과세 요건 분석 (RAG + LLM) ─────────────────────────────────────

@mcp.tool()
async def analyze_exemption(question: str, as_of_date: str = "") -> str:
    """
    양도소득세 비과세·감면·중과 여부를 RAG 검색 후 Claude로 분석합니다.
    검색된 법령 조문에만 근거하며, 불확실한 사실관계는 추가 확인 항목으로 표시합니다.

    Args:
        question: 사실관계가 포함된 질문
                  (예: "2019년 취득, 2024년 양도, 보유 5년, 거주 3년, 1세대 1주택")
        as_of_date: 기준일자 YYYYMMDD (예: "20220101"). 취득일 또는 양도일 기준.
    """
    from src.api.chat_api import chat_turn

    result = await chat_turn(
        question=question,
        enable_debate=False,
    )
    return json.dumps(
        {
            "verdict": result.get("verdict"),
            "answer": result.get("answer"),
            "confidence": result.get("confidence"),
            "citations": result.get("citations", []),
            "chunk_ids": result.get("chunk_ids", []),
            "missing_facts": result.get("missing_facts", []),
            "warnings": result.get("warnings", []),
            "blocked": result.get("blocked", False),
        },
        ensure_ascii=False,
        indent=2,
    )


# ── Tool 4: 인용 조문 검증 ────────────────────────────────────────────────────

@mcp.tool()
def verify_citations(question: str, chunk_ids: list[str]) -> str:
    """
    인용된 chunk_id가 실제 검색 결과에 존재하는지 검증합니다.
    존재하지 않는 chunk_id를 인용하는 것은 허용되지 않습니다.

    Args:
        question: 원래 질문 (재검색에 사용)
        chunk_ids: 검증할 chunk_id 목록
    """
    chunks = retrieve_tax_law(question, top_k=20, rerank_top_n=10)
    retrieved_ids = {c.id for c in chunks}

    verified = [cid for cid in chunk_ids if cid in retrieved_ids]
    unverified = [cid for cid in chunk_ids if cid not in retrieved_ids]

    result = {
        "verified_chunk_ids": verified,
        "unverified_chunk_ids": unverified,
        "warning": (
            f"{len(unverified)}개 chunk_id가 검색 결과에 없습니다. 인용 금지."
            if unverified else "모든 chunk_id 검증 완료"
        ),
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


# ── Tool 5: 양도소득세 결정론 계산 ────────────────────────────────────────────

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
    """
    양도소득세 결정론 계산.
    입력 사실관계에서 세액을 직접 계산합니다 (LLM 없음).

    Args:
        transfer_price: 양도가액 (원)
        acquisition_price: 취득가액 (원)
        transfer_date: 양도일 YYYYMMDD (예: "20240601")
        acquisition_date: 취득일 YYYYMMDD (예: "20190101")
        household_house_count: 세대 보유 주택 수 (기본 1)
        residence_years: 거주기간 연수 (기본 0.0)
        is_adjustment_area_at_transfer: 양도 시점 조정대상지역 여부 (기본 False)
    """
    from datetime import date as _date
    from src.calculator.tax_calculator import (
        TaxCalculationInput, calculate_transfer_tax, compute_ltshd_rate,
    )

    t_date = _date(int(transfer_date[:4]), int(transfer_date[4:6]), int(transfer_date[6:8]))
    a_date = _date(int(acquisition_date[:4]), int(acquisition_date[4:6]), int(acquisition_date[6:8]))
    holding_years = (t_date - a_date).days / 365.25

    from src.domain.tax_constants import TaxConstantsRegistry
    high_value_threshold = TaxConstantsRegistry.get("HIGH_VALUE_THRESHOLD", t_date)
    is_high_value = transfer_price > high_value_threshold
    is_one_house = household_house_count == 1
    ltshd_rate = compute_ltshd_rate(holding_years, residence_years, is_one_house)
    is_short_term = holding_years < 2.0
    is_heavy = household_house_count >= 2 and is_adjustment_area_at_transfer

    inp = TaxCalculationInput(
        transfer_price=transfer_price,
        acquisition_price=acquisition_price,
        transfer_date=t_date,
        acquisition_date=a_date,
        holding_years=holding_years,
        residence_years=residence_years,
        household_house_count=household_house_count,
        is_one_house_exemption=is_one_house and not is_high_value,
        is_high_value_house=is_high_value,
        is_heavy_tax=is_heavy,
        is_short_term=is_short_term,
        long_term_deduction_rate=ltshd_rate,
    )
    result = calculate_transfer_tax(inp)
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


# ── Tool 6: 지역 지정 여부 조회 ───────────────────────────────────────────────

@mcp.tool()
async def check_area_designation(
    region: str,
    target_date: str,
    area_type: str = "조정대상지역",
) -> dict:
    """
    특정 날짜에 해당 지역이 area_type으로 지정되어 있었는지 조회.
    수동 기준표 + API 결합 조회.

    Args:
        region: 지역명 (예: "서울특별시 강남구", "용인시 수지구")
        target_date: 기준일 YYYYMMDD (예: "20220801")
        area_type: 지정 유형 — "조정대상지역" | "투기과열지구" | "토지거래허가구역" (기본 "조정대상지역")
    """
    from datetime import date as _date
    from src.ingestion.admin_notices import load_manual_table, resolve_area_status

    t_date = _date(int(target_date[:4]), int(target_date[4:6]), int(target_date[6:8]))
    records = load_manual_table()
    is_designated = resolve_area_status(region, t_date, area_type, records)

    return {
        "region": region,
        "target_date": target_date,
        "area_type": area_type,
        "is_designated": is_designated,
        "source": "manual_table",
        "note": "수동 기준표 기반 조회 (API 연동 전)",
    }


# ── Tool 7: 유권해석 DB 검색 ──────────────────────────────────────────────────

@mcp.tool()
async def lookup_ruling(
    query: str,
    ruling_type: str = "all",
    top_k: int = 5,
) -> str:
    """
    유권해석 DB에서 관련 해석례를 검색합니다.

    Args:
        query: 검색 키워드 또는 질문
               (예: "배우자 증여 이월과세 적용 요건", "일시적 2주택 3년 이내 양도")
        ruling_type: 검색 대상 DB — "ntis" | "tt" | "court" | "all" (기본 "all")
                     ntis: 국세청 예규·질의회신 (ntis.go.kr)
                     tt: 조세심판원 결정례 (tt.go.kr)
                     court: 대법원 판결
        top_k: 반환할 최대 결과 수 (기본 5)

    Returns:
        검색된 해석례 목록 (JSON 문자열).
        데이터가 없으면 "유권해석 DB 미수집" 메시지를 반환합니다 (에러 아님).
    """
    # Pinecone 네임스페이스 매핑
    RULING_NAMESPACES: dict = {
        "ntis": ["tax-ruling-nts"],
        "tt": ["tax-ruling-decisions"],
        "court": ["tax-ruling-pdf"],
        "all": ["tax-ruling-nts", "tax-ruling-decisions", "tax-ruling-pdf"],
    }

    if ruling_type not in RULING_NAMESPACES:
        return json.dumps(
            {
                "error": f"ruling_type 오류: '{ruling_type}'. "
                         "허용 값: ntis | tt | court | all",
            },
            ensure_ascii=False,
            indent=2,
        )

    target_namespaces = RULING_NAMESPACES[ruling_type]

    # Pinecone 클라이언트 초기화 및 네임스페이스별 검색
    try:
        from src.infra.pinecone_client import get_pinecone_index
        from src.infra.embedder import embed_query

        index = get_pinecone_index()
        query_vector = embed_query(query)
    except Exception as exc:
        return json.dumps(
            {
                "status": "유권해석 DB 미수집",
                "message": (
                    "유권해석 DB가 아직 수집되지 않았습니다. "
                    "Phase 5 — 유권해석 DB 1단계 완료 후 검색 가능합니다."
                ),
                "detail": str(exc),
            },
            ensure_ascii=False,
            indent=2,
        )

    results = []
    for ns in target_namespaces:
        try:
            response = index.query(
                vector=query_vector,
                top_k=top_k,
                namespace=ns,
                include_metadata=True,
            )
            for match in response.get("matches", []):
                meta = match.get("metadata", {})
                results.append(
                    {
                        "ruling_id": meta.get("ruling_id", match["id"]),
                        "ruling_type": meta.get("ruling_type", ns.replace("tax-ruling-", "")),
                        "title": meta.get("title", ""),
                        "issue_date": meta.get("issue_date", ""),
                        "summary": meta.get("summary", "")[:500],   # 500자 이하 요약
                        "related_articles": meta.get("related_articles", []),
                        "score": round(match.get("score", 0.0), 4),
                        "namespace": ns,
                    }
                )
        except Exception:
            # 네임스페이스 미존재 등 → 해당 DB 건너뜀
            continue

    if not results:
        return json.dumps(
            {
                "status": "유권해석 DB 미수집",
                "message": (
                    "유권해석 DB가 아직 수집되지 않았습니다. "
                    "Phase 5 — 유권해석 DB 1단계 완료 후 검색 가능합니다."
                ),
                "query": query,
                "ruling_type": ruling_type,
            },
            ensure_ascii=False,
            indent=2,
        )

    # 점수 내림차순 정렬 후 top_k 제한
    results.sort(key=lambda r: r["score"], reverse=True)
    results = results[:top_k]

    return json.dumps(
        {
            "status": "ok",
            "query": query,
            "ruling_type": ruling_type,
            "total": len(results),
            "results": results,
        },
        ensure_ascii=False,
        indent=2,
    )


# ── 실행 ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    # 인자 없으면 stdio (Claude Desktop), --sse 이면 HTTP SSE
    if "--sse" in sys.argv:
        mcp.run(transport="sse")
    else:
        mcp.run(transport="stdio")
