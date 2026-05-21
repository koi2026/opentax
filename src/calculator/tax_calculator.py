"""
양도소득세 결정론 계산기.

LLM 개입 없음 — 입력 사실관계가 올바르면 세액 오차 0원이 목표.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional


# ── 세율표 ───────────────────────────────────────────────────────────────────

# 기본세율 (소득세법 §55①, 양도소득세 기본세율 적용)
_BASIC_TAX_BRACKETS = [
    (14_000_000, 0.06, 0),
    (50_000_000, 0.15, 1_260_000),
    (88_000_000, 0.24, 5_760_000),
    (150_000_000, 0.35, 15_440_000),
    (300_000_000, 0.38, 19_940_000),
    (500_000_000, 0.40, 25_940_000),
    (1_000_000_000, 0.42, 35_940_000),
    (float("inf"), 0.45, 65_940_000),
]

# 단기세율 (소득세법 §104①)
_SHORT_TERM_RATES = {
    "under_1_year": 0.70,
    "1_to_2_years": 0.60,
}

# 다주택 중과 추가세율 (소득세법 §104①2,3호)
_HEAVY_TAX_ADDITIONAL = {
    2: 0.20,   # 2주택: +20%p
    3: 0.30,   # 3주택 이상: +30%p
}

# 비거주자 단일세율
_NON_RESIDENT_RATE = 0.20  # 소득세법 §121②


@dataclass
class TaxCalculationInput:
    """세액 계산에 필요한 최소 입력."""
    transfer_price: int
    acquisition_price: int
    transfer_date: date
    acquisition_date: date                    # 보유기간 기산점 (acquisition_timeline 결과 사용)
    holding_years: float
    residence_years: float = 0.0
    household_house_count: int = 1
    is_one_house_exemption: bool = False      # 1세대1주택 비과세 해당 여부
    is_high_value_house: bool = False         # 12억 초과 고가주택
    transfer_price_exempt_threshold: int = 1_200_000_000  # 비과세 한도 (TaxConstantsRegistry에서)
    is_heavy_tax: bool = False                # 다주택 중과 적용 여부
    heavy_tax_suspended: bool = False         # 한시적 중과배제
    is_short_term: bool = False               # 단기 세율 적용 여부(1~2년 보유)
    is_non_resident: bool = False             # 비거주자
    necessary_expenses: int = 0              # 필요경비 (양도비용 등)
    long_term_deduction_rate: float = 0.0    # 장기보유특별공제율 (외부에서 계산하여 주입)
    is_burden_gift: bool = False              # 부담부증여 여부


@dataclass
class TaxCalculation:
    """세액 계산 결과."""
    # 과세 대상 부분 (고가주택의 경우 12억 초과분만)
    taxable_transfer_price: int
    taxable_acquisition_price: int

    # 양도차익 계산
    gross_gain: int                          # 양도차익 (양도가액 - 취득가액 - 필요경비)
    long_term_deduction: int                 # 장기보유특별공제
    taxable_income: int                      # 과세표준 (양도차익 - 장특공)

    # 세율 적용
    applied_rate: float                      # 적용 세율
    rate_type: str                           # "기본세율" | "단기세율" | "중과세율" | "비거주자"

    # 세액
    calculated_tax: int                      # 산출세액
    local_income_tax: int                    # 지방소득세 (산출세액 × 10%)
    total_tax: int                           # 납부세액 합계

    # 비과세·감면 요약
    exempt_amount: int = 0                   # 비과세된 이익 금액
    deduction_summary: str = ""              # 적용된 공제 요약 (사용자 표시용)
    warnings: List[str] = field(default_factory=list)


def calculate_transfer_tax(inp: TaxCalculationInput) -> TaxCalculation:
    """
    양도소득세 결정론 계산.

    순서: 과세대상 산정 → 양도차익 → 장특공 → 과세표준 → 세율 → 산출세액 → 지방소득세
    """
    warnings: List[str] = []

    # ① 과세 대상 산정 (고가주택 12억 초과분)
    if inp.is_one_house_exemption and inp.is_high_value_house:
        ratio = (inp.transfer_price - inp.transfer_price_exempt_threshold) / inp.transfer_price
        ratio = max(0.0, min(1.0, ratio))
        taxable_tp = int(inp.transfer_price * ratio)
        taxable_ap = int(inp.acquisition_price * ratio)
        exempt_amount = inp.transfer_price - taxable_tp
    elif inp.is_one_house_exemption and not inp.is_high_value_house:
        # 완전 비과세
        return TaxCalculation(
            taxable_transfer_price=0,
            taxable_acquisition_price=0,
            gross_gain=0,
            long_term_deduction=0,
            taxable_income=0,
            applied_rate=0.0,
            rate_type="비과세",
            calculated_tax=0,
            local_income_tax=0,
            total_tax=0,
            exempt_amount=inp.transfer_price - inp.acquisition_price,
            deduction_summary="1세대1주택 비과세",
        )
    else:
        taxable_tp = inp.transfer_price
        taxable_ap = inp.acquisition_price
        exempt_amount = 0

    # ② 양도차익
    gross_gain = taxable_tp - taxable_ap - inp.necessary_expenses
    if gross_gain <= 0:
        return TaxCalculation(
            taxable_transfer_price=taxable_tp,
            taxable_acquisition_price=taxable_ap,
            gross_gain=gross_gain,
            long_term_deduction=0,
            taxable_income=0,
            applied_rate=0.0,
            rate_type="양도차손",
            calculated_tax=0,
            local_income_tax=0,
            total_tax=0,
            exempt_amount=exempt_amount,
            deduction_summary="양도차손 — 세액 없음",
        )

    # ③ 장기보유특별공제 (단기/중과 시 미적용)
    ltd = 0
    if inp.long_term_deduction_rate > 0 and not inp.is_short_term and not (inp.is_heavy_tax and not inp.heavy_tax_suspended):
        ltd = int(gross_gain * inp.long_term_deduction_rate)

    taxable_income = max(0, gross_gain - ltd)

    # ④ 기본공제 (250만원)
    basic_deduction = 2_500_000
    taxable_income = max(0, taxable_income - basic_deduction)

    # ⑤ 세율 결정
    if inp.is_non_resident:
        rate = _NON_RESIDENT_RATE
        rate_type = "비거주자"
        tax = int(taxable_income * rate)
    elif inp.is_short_term:
        years = inp.holding_years
        if years < 1.0:
            rate = _SHORT_TERM_RATES["under_1_year"]
            rate_type = "단기세율(1년미만)"
        else:
            rate = _SHORT_TERM_RATES["1_to_2_years"]
            rate_type = "단기세율(1~2년)"
        tax = int(taxable_income * rate)
    elif inp.is_heavy_tax and not inp.heavy_tax_suspended:
        # 중과: 기본세율 + 추가
        base_tax, base_rate = _apply_basic_brackets(taxable_income)
        additional = _HEAVY_TAX_ADDITIONAL.get(min(inp.household_house_count, 3), 0.30)
        rate = base_rate + additional
        rate_type = f"중과세율({inp.household_house_count}주택)"
        tax = base_tax + int(taxable_income * additional)
    else:
        tax, rate = _apply_basic_brackets(taxable_income)
        rate_type = "기본세율"

    local_tax = int(tax * 0.10)
    total_tax = tax + local_tax

    deduction_parts = []
    if ltd > 0:
        deduction_parts.append(f"장기보유특별공제 {ltd:,}원 ({inp.long_term_deduction_rate:.0%})")
    deduction_parts.append(f"기본공제 {basic_deduction:,}원")

    return TaxCalculation(
        taxable_transfer_price=taxable_tp,
        taxable_acquisition_price=taxable_ap,
        gross_gain=gross_gain,
        long_term_deduction=ltd,
        taxable_income=taxable_income,
        applied_rate=rate,
        rate_type=rate_type,
        calculated_tax=tax,
        local_income_tax=local_tax,
        total_tax=total_tax,
        exempt_amount=exempt_amount,
        deduction_summary=" / ".join(deduction_parts),
        warnings=warnings,
    )


def compute_ltshd_rate(holding_years: float, residence_years: float, is_one_house: bool) -> float:
    """
    장기보유특별공제율 계산.
    표1: 일반 (보유기간만)
    표2: 1세대1주택 (보유 4%/년 + 거주 4%/년, 최대 80%)
    """
    if holding_years < 3:
        return 0.0

    if is_one_house and residence_years >= 2:
        holding_rate = min(int(holding_years) * 0.04, 0.40)
        residence_rate = min(int(residence_years) * 0.04, 0.40)
        return min(holding_rate + residence_rate, 0.80)
    else:
        capped_years = min(int(holding_years), 15)
        # 표1: 3년 6%, 이후 2%씩 증가
        return min(0.06 + (capped_years - 3) * 0.02, 0.30)


def _apply_basic_brackets(taxable_income: int) -> tuple[int, float]:
    """기본세율 누진공제 방식으로 산출세액 계산. (세액, 한계세율) 반환."""
    for upper, rate, deduction in _BASIC_TAX_BRACKETS:
        if taxable_income <= upper:
            return int(taxable_income * rate - deduction), rate
    # 최고구간
    rate = 0.45
    return int(taxable_income * rate - 65_940_000), rate
