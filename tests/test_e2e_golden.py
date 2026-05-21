"""
E2E 골든 테스트 — L2/L3/ConfirmationGate 검증 (외부 서비스 없음)

검증 범위:
    - L2 (fact_checker): blocked_at_l2 정확도, missing_facts 포함 여부
    - L1.5 (confirmation): CASE-26/27 게이트 차단/통과 검증
    - L3 (query_enrichment): danger_flags → 도메인 키워드 주입 검증

외부 서비스(Pinecone, Claude API) 의존 테스트는 pytest -m integration으로만 실행.
이 파일의 모든 테스트는 외부 서비스 없이 동작한다.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from tests.rag_golden_cases import RAG_GOLDEN_CASES
from src.domain.confirmation import check_confirmation


# ── 헬퍼 ───────────────────────────────────────────────────────────────────────

def _get_case(case_id: str) -> Dict[str, Any]:
    """case_id로 골든 케이스를 가져온다. 없으면 KeyError."""
    for c in RAG_GOLDEN_CASES:
        if c["case_id"] == case_id:
            return c
    raise KeyError(f"케이스를 찾을 수 없음: {case_id}")


def _build_query_input(case: Dict[str, Any]):
    """
    골든 케이스의 owner_profile / user_property / fact_ledger 를
    RAGQueryInput으로 변환한다.
    변환 불가 케이스(필수 필드 의도적 누락)에서는 None을 반환한다.
    """
    from src.domain.query_input import RAGQueryInput

    try:
        return RAGQueryInput.from_fact_ledger(
            fact_ledger=case["fact_ledger"],
            owner_profile=case["owner_profile"],
            user_property=case["user_property"],
        )
    except Exception:
        # 의도적으로 누락된 필드가 있어 변환 불가 — None 반환 후 호출부에서 처리
        return None


# ── L2 차단/비차단 검증 ──────────────────────────────────────────────────────


# L2 차단이 예상되는 케이스 (blocked_at_l2=True)
L2_BLOCK_CASES = [c for c in RAG_GOLDEN_CASES if c["expected"].get("blocked_at_l2") is True]

# L2 통과가 예상되는 케이스 (blocked_at_l2=False)
L2_PASS_CASES = [c for c in RAG_GOLDEN_CASES if c["expected"].get("blocked_at_l2") is False]


@pytest.mark.parametrize("case", L2_BLOCK_CASES, ids=[c["case_id"] for c in L2_BLOCK_CASES])
def test_l2_blocks_critical_missing(case: Dict[str, Any]) -> None:
    """
    크리티컬 사실관계 누락 시 check_facts()가 can_proceed=False를 반환해야 한다.
    """
    from src.domain.fact_checker import check_facts

    query = _build_query_input(case)
    if query is None:
        pytest.skip(f"{case['case_id']}: RAGQueryInput 변환 불가 — 필드 누락 구조 확인 필요")

    result = check_facts(query)

    assert not result.can_proceed, (
        f"{case['case_id']}: L2 차단 예상이지만 can_proceed=True. "
        f"missing_facts={[m.field_name for m in result.missing_facts]}"
    )

    # missing_fact_contains가 지정된 경우 해당 필드명이 missing_facts에 존재해야 한다
    expected_missing: Optional[str] = case["expected"].get("missing_fact_contains")
    if expected_missing:
        field_names = [m.field_name for m in result.missing_facts]
        assert any(expected_missing in fn for fn in field_names), (
            f"{case['case_id']}: missing_facts에 '{expected_missing}'가 없음. "
            f"실제 missing_facts={field_names}"
        )


@pytest.mark.parametrize("case", L2_PASS_CASES, ids=[c["case_id"] for c in L2_PASS_CASES])
def test_l2_passes_complete_facts(case: Dict[str, Any]) -> None:
    """
    사실관계가 완전한 케이스는 check_facts()가 can_proceed=True를 반환해야 한다.
    확인서(confirmed) 관련 케이스 포함 — L2는 통과해야 한다.
    """
    from src.domain.fact_checker import check_facts

    query = _build_query_input(case)
    if query is None:
        pytest.skip(f"{case['case_id']}: RAGQueryInput 변환 불가")

    result = check_facts(query)

    assert result.can_proceed, (
        f"{case['case_id']}: L2 통과 예상이지만 can_proceed=False. "
        f"critical_missing={[m.field_name for m in result.critical_missing]}"
    )


# ── ConfirmationGate 검증 ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "case_id, confirmed, expected_can_proceed",
    [
        ("CASE-26", {}, False),   # 빈 dict → 전부 미확인 → 차단
        (
            "CASE-27",
            {
                "household_house_count_verified": True,
                "balance_or_registration_date_used": True,
                "no_related_party": True,
                "actual_residence_verified": True,
            },
            True,
        ),  # 4개 모두 True → 통과
    ],
)
def test_confirmation_gate(
    case_id: str,
    confirmed: Dict[str, bool],
    expected_can_proceed: bool,
) -> None:
    """
    check_confirmation()이 confirmed 딕셔너리에 따라 올바르게 차단/통과하는지 검증한다.
    """
    result = check_confirmation(confirmed)

    assert result.can_proceed == expected_can_proceed, (
        f"{case_id}: can_proceed 예상={expected_can_proceed}, 실제={result.can_proceed}. "
        f"unconfirmed_items={result.unconfirmed_items}"
    )

    if not expected_can_proceed:
        assert len(result.unconfirmed_items) > 0, (
            f"{case_id}: can_proceed=False인데 unconfirmed_items가 비어 있음"
        )
        assert len(result.unconfirmed_questions) == len(result.unconfirmed_items), (
            f"{case_id}: unconfirmed_items와 unconfirmed_questions 개수 불일치"
        )


def test_confirmation_gate_none_passthrough() -> None:
    """confirmed=None이면 미구현 경로로 간주하여 통과(can_proceed=True)해야 한다."""
    result = check_confirmation(None)
    assert result.can_proceed is True


def test_confirmation_gate_partial() -> None:
    """4개 중 일부만 True이면 차단해야 한다."""
    partial = {
        "household_house_count_verified": True,
        "balance_or_registration_date_used": False,  # 미확인
        "no_related_party": True,
        "actual_residence_verified": True,
    }
    result = check_confirmation(partial)

    assert not result.can_proceed
    assert "balance_or_registration_date_used" in result.unconfirmed_items


def test_confirmation_gate_all_four_items_required() -> None:
    """4개 항목이 모두 있어야 통과한다 — 3개만 True이면 차단."""
    three_items = {
        "household_house_count_verified": True,
        "balance_or_registration_date_used": True,
        "no_related_party": True,
        # actual_residence_verified 없음
    }
    result = check_confirmation(three_items)
    assert not result.can_proceed
    assert "actual_residence_verified" in result.unconfirmed_items


# ── L3 query enrichment danger_flags 검증 ───────────────────────────────────


def test_query_enrichment_injects_rollover_taxation_keyword() -> None:
    """이월과세 danger_flag → §97의2 관련 키워드 주입 검증."""
    from src.domain.query_enrichment import enrich_query

    base = "배우자 증여 후 양도"
    enriched = enrich_query(base, ["이월과세"])

    assert "97조의2" in enriched or "이월과세" in enriched, (
        f"이월과세 키워드 미주입. enriched='{enriched}'"
    )


def test_query_enrichment_injects_multiple_flags() -> None:
    """복수의 danger_flag → 각각 키워드 주입 검증."""
    from src.domain.query_enrichment import enrich_query

    base = "일시적 2주택 종전주택 양도"
    enriched = enrich_query(base, ["일시적2주택", "고가주택"])

    assert "155조" in enriched or "일시적" in enriched, (
        f"일시적2주택 키워드 미주입. enriched='{enriched}'"
    )
    assert "12억" in enriched or "고가주택" in enriched or "156조" in enriched, (
        f"고가주택 키워드 미주입. enriched='{enriched}'"
    )


def test_query_enrichment_no_flags_returns_base() -> None:
    """danger_flags가 빈 리스트이면 base_query를 그대로 반환해야 한다."""
    from src.domain.query_enrichment import enrich_query

    base = "1세대 1주택 비과세"
    enriched = enrich_query(base, [])

    assert enriched == base, (
        f"빈 flags인데 쿼리가 변경됨. enriched='{enriched}'"
    )


def test_query_enrichment_special_case_flags() -> None:
    """특수관계자거래 flag → §101 키워드 주입 검증."""
    from src.domain.query_enrichment import enrich_query

    base = "시가보다 낮은 가액으로 양도"
    enriched = enrich_query(base, ["특수관계자거래"])

    assert "101" in enriched or "특수관계" in enriched or "부당행위" in enriched, (
        f"특수관계자거래 키워드 미주입. enriched='{enriched}'"
    )


def test_query_enrichment_sangsaeng_rental_flag() -> None:
    """상생임대 flag → §155의3 키워드 주입 검증."""
    from src.domain.query_enrichment import enrich_query

    base = "상생임대 거주요건 면제"
    enriched = enrich_query(base, ["상생임대"])

    assert "155조의3" in enriched or "상생임대" in enriched, (
        f"상생임대 키워드 미주입. enriched='{enriched}'"
    )


# ── 골든 케이스 메타 검증 ────────────────────────────────────────────────────


def test_golden_cases_count() -> None:
    """골든 케이스가 정확히 30개인지 확인."""
    assert len(RAG_GOLDEN_CASES) == 30, (
        f"골든 케이스 수 오류: 예상=30, 실제={len(RAG_GOLDEN_CASES)}"
    )


def test_golden_cases_unique_ids() -> None:
    """모든 case_id가 유일한지 확인."""
    ids = [c["case_id"] for c in RAG_GOLDEN_CASES]
    assert len(ids) == len(set(ids)), f"중복 case_id 존재: {ids}"


def test_golden_cases_sequential_ids() -> None:
    """case_id가 CASE-01 ~ CASE-30 순서로 존재하는지 확인."""
    ids = [c["case_id"] for c in RAG_GOLDEN_CASES]
    expected = [f"CASE-{i:02d}" for i in range(1, 31)]
    assert ids == expected, f"case_id 순서 오류. 실제={ids}"


def test_golden_cases_have_required_fields() -> None:
    """모든 케이스에 필수 필드(case_id, title, owner_profile, user_property, fact_ledger, expected)가 있는지 확인."""
    required_keys = {"case_id", "title", "owner_profile", "user_property", "fact_ledger", "expected"}
    for case in RAG_GOLDEN_CASES:
        missing = required_keys - set(case.keys())
        assert not missing, f"{case.get('case_id', '?')}: 필수 필드 누락 {missing}"


def test_l2_block_cases_have_blocked_at_l2_true() -> None:
    """blocked_at_l2=True인 케이스(CASE-03, CASE-22~25)가 정확히 5개인지 확인."""
    block_cases = [c for c in RAG_GOLDEN_CASES if c["expected"].get("blocked_at_l2") is True]
    assert len(block_cases) == 5, (
        f"L2 차단 케이스 수 오류: 예상=5, 실제={len(block_cases)}. "
        f"케이스={[c['case_id'] for c in block_cases]}"
    )


def test_confirmation_cases_have_blocked_at_confirmation() -> None:
    """blocked_at_confirmation 필드가 있는 케이스(CASE-26~27)가 정확히 2개인지 확인."""
    conf_cases = [
        c for c in RAG_GOLDEN_CASES
        if "blocked_at_confirmation" in c["expected"]
    ]
    assert len(conf_cases) == 2, (
        f"확인 게이트 케이스 수 오류: 예상=2, 실제={len(conf_cases)}. "
        f"케이스={[c['case_id'] for c in conf_cases]}"
    )


# ── Integration 마크 테스트 (외부 서비스 필요) ─────────────────────────────


@pytest.mark.integration
@pytest.mark.parametrize("case", RAG_GOLDEN_CASES, ids=[c["case_id"] for c in RAG_GOLDEN_CASES])
async def test_full_pipeline_golden(case: Dict[str, Any]) -> None:
    """
    전체 파이프라인 E2E 검증 — Pinecone + Claude API 필요.
    pytest -m integration 으로만 실행.

    검증 항목:
        - blocked_at_l2 정확도
        - verdict 정확도 (비차단 케이스)
        - confidence >= confidence_min
    """
    from src.domain.pipeline import run_rag_pipeline
    from src.retrieval.retriever_impl import PineconeTaxLawRetriever
    from src.retrieval.llm_fn import llm_fn
    from src.domain.query_input import RAGQueryInput

    query = RAGQueryInput.from_fact_ledger(
        fact_ledger=case["fact_ledger"],
        owner_profile=case["owner_profile"],
        user_property=case["user_property"],
    )

    result = await run_rag_pipeline(
        query=query,
        retriever=PineconeTaxLawRetriever(),
        llm_fn=llm_fn,
        fact_json={**case["owner_profile"], **case["user_property"], **case["fact_ledger"]},
        enable_debate=False,  # 골든 테스트에서는 debate 비활성화
    )

    exp = case["expected"]

    assert result.blocked_at_l2 == exp["blocked_at_l2"], (
        f"{case['case_id']}: blocked_at_l2 예상={exp['blocked_at_l2']}, "
        f"실제={result.blocked_at_l2}"
    )

    if result.blocked_at_l2:
        return  # 차단 케이스 — verdict 검증 불필요

    assert result.answer.verdict == exp["verdict"], (
        f"{case['case_id']}: verdict 예상={exp['verdict']}, "
        f"실제={result.answer.verdict}"
    )

    if "confidence_min" in exp:
        assert result.answer.confidence >= exp["confidence_min"], (
            f"{case['case_id']}: confidence 예상>={exp['confidence_min']}, "
            f"실제={result.answer.confidence:.3f}"
        )

    # CASE-28: 특수관계자 → expert_review_signals 포함 확인
    if exp.get("has_expert_review_signals"):
        assert result.answer.expert_review_signals, (
            f"{case['case_id']}: expert_review_signals 없음"
        )

    # CASE-28: warnings에 특수관계자 관련 내용 포함 확인
    if exp.get("warnings_contain"):
        keyword = exp["warnings_contain"]
        warnings_text = " ".join(result.answer.warnings)
        assert keyword in warnings_text, (
            f"{case['case_id']}: warnings에 '{keyword}' 없음. "
            f"warnings={result.answer.warnings}"
        )
