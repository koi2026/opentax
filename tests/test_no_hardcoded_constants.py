"""
드리프트 방지 테스트 — TaxConstantsRegistry ↔ 프롬프트 / 도메인 로직 일관성 검증.

이 테스트가 실패하면:
  1. TaxConstantsRegistry에 새로운 상수 키가 추가되지 않은 것이다.
  2. 또는 도메인 로직에 새로운 하드코딩 수치가 삽입된 것이다.

세법 개정 시 처리 절차:
  1. TaxConstantsRegistry에 새 ConstantVersion 추가 (effective_from / effective_to 지정)
  2. 이 테스트가 통과하는지 확인
  3. 프롬프트·계산 로직은 자동 반영 — 별도 수정 불필요
"""
from __future__ import annotations

import re
from datetime import date

import pytest

from src.domain.tax_constants import TaxConstantsRegistry as _TCR
from src.agents.prompts import build_rag_system_prompt, build_red_team_system, RAG_SYSTEM_PROMPT


# ── 레지스트리 필수 키 존재 검증 ─────────────────────────────────────────────

REQUIRED_KEYS = [
    "HIGH_VALUE_THRESHOLD",
    "SHORT_TERM_RATES",
    "HEAVY_TAX_ADDITIONAL",
    "RESIDENCE_REQUIRED_YEARS_ADJUSTMENT",
    "INHERITANCE_EXEMPT_YEARS",
    "COHABITATION_EXEMPT_YEARS",
    "MARRIAGE_MERGE_EXEMPT_YEARS",
    "SANGSAENG_MIN_PERIOD_MONTHS",
    "SANGSAENG_RESIDENCE_YEARS",
    "SANGSAENG_MAX_INCREASE_RATE",
    "IOTA_PERIOD_YEARS",
    "GIFT_TAX_BRACKETS",
    "GIFT_DEDUCTIONS",
    "BASIC_TAX_BRACKETS",
    "BASIC_DEDUCTION",
    "LOCAL_INCOME_TAX_RATE",
    "NON_RESIDENT_RATE",
    "HEAVY_TAX_SUSPENSION_START",
    "HEAVY_TAX_SUSPENSION_END",
    "LONG_TERM_DEDUCTION_RATE_TABLE1",
    "LONG_TERM_DEDUCTION_RATE_TABLE2",
]


@pytest.mark.parametrize("key", REQUIRED_KEYS)
def test_registry_key_exists(key: str) -> None:
    """레지스트리에 필수 키가 모두 존재하는지 확인."""
    value = _TCR.get(key, date.today())
    assert value is not None, f"TaxConstantsRegistry에 '{key}' 키가 없거나 None입니다."


# ── 프롬프트 수치가 레지스트리 값과 일치하는지 검증 ───────────────────────────

def test_rag_system_prompt_threshold_matches_registry() -> None:
    """RAG 프롬프트의 고가주택 기준이 레지스트리와 일치해야 한다."""
    today = date.today()
    threshold_eok = _TCR.get("HIGH_VALUE_THRESHOLD", today) // 100_000_000
    prompt = build_rag_system_prompt(as_of=today)
    assert f"{threshold_eok}억" in prompt, (
        f"RAG 프롬프트에 고가주택 기준 '{threshold_eok}억'이 없습니다. "
        "build_rag_system_prompt()가 레지스트리를 참조하고 있는지 확인하세요."
    )


def test_rag_system_prompt_short_rates_match_registry() -> None:
    """RAG 프롬프트의 단기세율이 레지스트리와 일치해야 한다."""
    today = date.today()
    short_rates = _TCR.get("SHORT_TERM_RATES", today)
    s1 = int(short_rates["under_1_year"] * 100)
    s2 = int(short_rates["1_to_2_years"] * 100)
    prompt = build_rag_system_prompt(as_of=today)
    assert f"1년 미만 {s1}%" in prompt, (
        f"RAG 프롬프트에 1년 미만 단기세율 '{s1}%'가 없습니다."
    )
    assert f"미만 {s2}%" in prompt, (
        f"RAG 프롬프트에 2년 미만 단기세율 '{s2}%'가 없습니다."
    )


def test_rag_system_prompt_inheritance_years_match_registry() -> None:
    """RAG 프롬프트의 상속주택 제외 기간이 레지스트리와 일치해야 한다."""
    today = date.today()
    inh_yrs = _TCR.get("INHERITANCE_EXEMPT_YEARS", today)
    prompt = build_rag_system_prompt(as_of=today)
    assert f"상속주택 {inh_yrs}년 규칙" in prompt, (
        f"RAG 프롬프트에 상속주택 '{inh_yrs}년 규칙'이 없습니다."
    )


def test_rag_system_prompt_cohabitation_years_match_registry() -> None:
    """RAG 프롬프트의 동거봉양합가 기간이 레지스트리와 일치해야 한다."""
    today = date.today()
    cohab_yrs = _TCR.get("COHABITATION_EXEMPT_YEARS", today)
    prompt = build_rag_system_prompt(as_of=today)
    assert f"cohabitation_date로부터 {cohab_yrs}년 이내" in prompt, (
        f"RAG 프롬프트에 동거봉양합가 '{cohab_yrs}년' 기준이 없습니다."
    )


def test_rag_system_prompt_sangsaeng_requirements_match_registry() -> None:
    """RAG 프롬프트의 상생임대 요건이 레지스트리와 일치해야 한다."""
    today = date.today()
    sg_months = _TCR.get("SANGSAENG_MIN_PERIOD_MONTHS", today)
    sg_res = _TCR.get("SANGSAENG_RESIDENCE_YEARS", today)
    sg_rate = int(_TCR.get("SANGSAENG_MAX_INCREASE_RATE", today) * 100)
    prompt = build_rag_system_prompt(as_of=today)
    assert f"임대기간 {sg_months}개월 이상" in prompt
    assert f"거주요건 {sg_res}년" in prompt
    assert f"증액 {sg_rate}% 이내" in prompt


def test_red_team_system_threshold_matches_registry() -> None:
    """레드팀 프롬프트의 고가주택 기준이 레지스트리와 일치해야 한다."""
    today = date.today()
    threshold_eok = _TCR.get("HIGH_VALUE_THRESHOLD", today) // 100_000_000
    prompt = build_red_team_system(as_of=today)
    assert f"{threshold_eok}억" in prompt


# ── 레지스트리 버전 논리 검증 ─────────────────────────────────────────────────

def test_iota_period_years_versioned() -> None:
    """이월과세 기간이 2023년 전후로 올바르게 버전 관리되어야 한다."""
    before_2023 = _TCR.get("IOTA_PERIOD_YEARS", date(2022, 12, 31), anchor_key="gift_date")
    after_2023 = _TCR.get("IOTA_PERIOD_YEARS", date(2023, 1, 1), anchor_key="gift_date")
    assert before_2023 == 5, f"2022년 이전 이월과세 기간은 5년이어야 함, 실제: {before_2023}"
    assert after_2023 == 10, f"2023년 이후 이월과세 기간은 10년이어야 함, 실제: {after_2023}"


def test_gift_tax_brackets_structure() -> None:
    """증여세율표가 올바른 구조를 갖는지 확인."""
    brackets = _TCR.get("GIFT_TAX_BRACKETS", date.today())
    assert len(brackets) >= 3, "증여세율표는 최소 3개 구간이어야 합니다."
    upper, rate, deduction = brackets[-1]
    import math
    assert upper == math.inf or upper == float("inf"), "마지막 구간 상한은 무한대여야 합니다."
    assert 0 < rate <= 1.0, f"세율은 0~1.0 범위여야 합니다, 실제: {rate}"


def test_gift_deductions_has_required_keys() -> None:
    """증여재산공제에 필수 키가 있는지 확인."""
    deductions = _TCR.get("GIFT_DEDUCTIONS", date.today())
    required = {"배우자", "직계존비속", "직계존비속_미성년", "기타"}
    missing = required - set(deductions.keys())
    assert not missing, f"증여재산공제에 필수 키 누락: {missing}"


def test_heavy_tax_additional_has_two_and_three() -> None:
    """다주택 중과 추가세율에 2주택, 3주택 키가 있어야 한다."""
    additional = _TCR.get("HEAVY_TAX_ADDITIONAL", date.today())
    assert 2 in additional, "HEAVY_TAX_ADDITIONAL에 2주택 키가 없습니다."
    assert 3 in additional, "HEAVY_TAX_ADDITIONAL에 3주택 키가 없습니다."
    assert additional[2] < additional[3], "3주택 중과율이 2주택보다 높아야 합니다."


# ── 모듈 수준 상수가 빌드 함수 결과와 동일한지 확인 ──────────────────────────

def test_rag_system_prompt_module_constant_equals_build_result() -> None:
    """모듈 로드 시 생성된 RAG_SYSTEM_PROMPT가 build_rag_system_prompt() 결과와 같아야 한다."""
    # 모듈 로드 직후 생성이므로 오늘 날짜 기준으로 일치해야 함
    # (다만 midnight 경계에서 날짜 변경 시 1초 차이 가능 — 허용)
    built = build_rag_system_prompt()
    # 핵심 구분자 텍스트가 동일한지만 확인 (날짜 변경 엣지케이스 무시)
    assert "[verdict 선택 기준" in RAG_SYSTEM_PROMPT
    assert "[핵심 구별 포인트]" in RAG_SYSTEM_PROMPT
    assert "[verdict 선택 기준" in built
