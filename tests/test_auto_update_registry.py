"""
auto_update_registry.py 단위 테스트.

실제 파일 쓰기·git·gh 호출 없이 핵심 로직(매핑, 변환, 패치)만 검증.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from scripts.auto_update_registry import (
    convert_value,
    match_registry_key,
    patch_registry_source,
)

# ── 레지스트리 소스 픽스처 ─────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def registry_source() -> str:
    return Path("src/domain/tax_constants.py").read_text(encoding="utf-8")


# ── match_registry_key ────────────────────────────────────────────────────────

@pytest.mark.parametrize("threshold,expected_key,expected_type", [
    (
        {"article": "89", "description": "고가주택 비과세 기준가격", "type": "price",
         "value": 1_500_000_000, "unit": "원", "verdict_affected": "비과세"},
        "HIGH_VALUE_THRESHOLD", "price_won",
    ),
    (
        {"article": "104", "description": "중과배제 일몰기한", "type": "date",
         "value": "20261231", "unit": "YYYYMMDD", "verdict_affected": "중과"},
        "HEAVY_TAX_SUSPENSION_END", "date_yyyymmdd",
    ),
    (
        {"article": "97의2", "description": "이월과세 기간", "type": "period",
         "value": 10, "unit": "년", "verdict_affected": "비과세"},
        "IOTA_PERIOD_YEARS", "period_years",
    ),
    (
        {"article": "155의3", "description": "상생임대 임대기간", "type": "period",
         "value": 24, "unit": "개월", "verdict_affected": "비과세"},
        "SANGSAENG_MIN_PERIOD_MONTHS", "period_months",
    ),
    (
        {"article": "155의3", "description": "상생임대 증액 상한", "type": "rate",
         "value": 5, "unit": "%", "verdict_affected": "비과세"},
        "SANGSAENG_MAX_INCREASE_RATE", "rate_decimal",
    ),
    (
        {"article": "155의3", "description": "상생임대 거주요건 단축", "type": "period",
         "value": 1.5, "unit": "년", "verdict_affected": "비과세"},
        "SANGSAENG_RESIDENCE_YEARS", "period_years",
    ),
    (
        {"article": "154", "description": "조정대상지역 거주 요건 연수", "type": "period",
         "value": 2, "unit": "년", "verdict_affected": "비과세"},
        "RESIDENCE_REQUIRED_YEARS_ADJUSTMENT", "period_years",
    ),
    (
        {"article": "155②", "description": "상속주택 기간 제외", "type": "period",
         "value": 5, "unit": "년", "verdict_affected": "비과세"},
        "INHERITANCE_EXEMPT_YEARS", "period_years",
    ),
    (
        {"article": "155④", "description": "동거봉양합가 특례", "type": "period",
         "value": 10, "unit": "년", "verdict_affected": "비과세"},
        "COHABITATION_EXEMPT_YEARS", "period_years",
    ),
    (
        {"article": "155⑤", "description": "혼인합가 특례", "type": "period",
         "value": 5, "unit": "년", "verdict_affected": "비과세"},
        "MARRIAGE_MERGE_EXEMPT_YEARS", "period_years",
    ),
    # manual_review 케이스
    (
        {"article": "95", "description": "장기보유특별공제율 표1", "type": "rate",
         "value": 0.10, "unit": "%", "verdict_affected": "일반과세"},
        "LONG_TERM_DEDUCTION_RATE_TABLE1", "manual",
    ),
])
def test_match_registry_key(threshold, expected_key, expected_type):
    key, vtype = match_registry_key(threshold)
    assert key == expected_key, f"Expected key={expected_key!r}, got {key!r}"
    assert vtype == expected_type, f"Expected type={expected_type!r}, got {vtype!r}"


def test_match_registry_key_unknown_returns_none():
    th = {"article": "999", "description": "알 수 없는 조항", "type": "rate", "value": 1}
    key, vtype = match_registry_key(th)
    assert key is None
    assert vtype is None


# ── convert_value ─────────────────────────────────────────────────────────────

def test_convert_price_won():
    v, ok = convert_value({"value": 1_500_000_000, "unit": "원"}, "price_won")
    assert ok and v == 1_500_000_000


def test_convert_period_years_int():
    v, ok = convert_value({"value": 10, "unit": "년"}, "period_years")
    assert ok and v == 10 and isinstance(v, int)


def test_convert_period_years_float():
    v, ok = convert_value({"value": 1.5, "unit": "년"}, "period_years")
    assert ok and v == 1.5 and isinstance(v, float)


def test_convert_period_months():
    v, ok = convert_value({"value": 24, "unit": "개월"}, "period_months")
    assert ok and v == 24


def test_convert_rate_decimal_percent():
    v, ok = convert_value({"value": 5, "unit": "%"}, "rate_decimal")
    assert ok and abs(v - 0.05) < 1e-9


def test_convert_rate_decimal_already_decimal():
    v, ok = convert_value({"value": 0.05, "unit": ""}, "rate_decimal")
    assert ok and abs(v - 0.05) < 1e-9


def test_convert_date_yyyymmdd():
    v, ok = convert_value({"value": "20261231", "unit": "YYYYMMDD"}, "date_yyyymmdd")
    assert ok and v == date(2026, 12, 31)


def test_convert_manual_returns_none():
    v, ok = convert_value({"value": 0.10, "unit": "%"}, "manual")
    assert not ok and v is None


# ── patch_registry_source ────────────────────────────────────────────────────

NEW_FROM = date(2027, 1, 1)
OLD_TO = NEW_FROM - timedelta(days=1)


def test_patch_int_scalar(registry_source):
    patched = patch_registry_source(
        registry_source, "HIGH_VALUE_THRESHOLD", 1_500_000_000, NEW_FROM
    )
    # 신규 버전 삽입
    assert f"date({NEW_FROM.year}, {NEW_FROM.month}, {NEW_FROM.day}), date.max" in patched
    assert "1_500_000_000" in patched
    # 구버전 effective_to 갱신
    assert f"date(2021, 1, 1), date({OLD_TO.year}, {OLD_TO.month}, {OLD_TO.day})" in patched
    # 구버전 값 보존
    assert "1_200_000_000" in patched
    # 구문 유효성
    compile(patched, "patched.py", "exec")


def test_patch_date_scalar(registry_source):
    new_sunset = date(2028, 5, 9)
    new_from = date(2026, 5, 10)
    patched = patch_registry_source(
        registry_source, "HEAVY_TAX_SUSPENSION_END", new_sunset, new_from
    )
    assert f"date({new_from.year}, {new_from.month}, {new_from.day}), date.max" in patched
    assert "date(2028, 5, 9)" in patched
    compile(patched, "patched.py", "exec")


def test_patch_iota_period_with_anchor_key(registry_source):
    """anchor_key 있는 ConstantVersion도 올바르게 패치되어야 한다."""
    patched = patch_registry_source(
        registry_source, "IOTA_PERIOD_YEARS", 15, NEW_FROM
    )
    assert f"date({NEW_FROM.year}, {NEW_FROM.month}, {NEW_FROM.day}), date.max" in patched
    assert "\n            15," in patched
    # anchor_key 유지
    assert 'anchor_key="gift_date"' in patched
    compile(patched, "patched.py", "exec")


def test_patch_preserves_other_keys(registry_source):
    """패치 시 다른 레지스트리 키는 변경되지 않아야 한다."""
    patched = patch_registry_source(
        registry_source, "HIGH_VALUE_THRESHOLD", 1_500_000_000, NEW_FROM
    )
    # 다른 키의 값들이 그대로 존재하는지 확인
    assert '"SANGSAENG_MIN_PERIOD_MONTHS"' in patched
    assert '"IOTA_PERIOD_YEARS"' in patched
    assert '"SHORT_TERM_RATES"' in patched


def test_patch_unknown_key_raises(registry_source):
    with pytest.raises(ValueError, match="not found"):
        patch_registry_source(registry_source, "NONEXISTENT_KEY", 0, NEW_FROM)
