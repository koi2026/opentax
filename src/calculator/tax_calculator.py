"""
양도소득세 결정론 계산기.

LLM 개입 없음 — 입력 사실관계가 올바르면 세액 오차 0원이 목표.
모든 세율·공제·기준값은 TaxConstantsRegistry에서 날짜 기준으로 조회한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional

from src.domain.tax_constants import TaxConstantsRegistry as _TCR


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
    transfer_price_exempt_threshold: Optional[int] = None  # None이면 레지스트리에서 자동 조회
    is_heavy_tax: bool = False                # 다주택 중과 적용 여부
    heavy_tax_suspended: bool = False         # 한시적 중과배제
    is_short_term: bool = False               # 단기 세율 적용 여부(1~2년 보유)
    is_non_resident: bool = False             # 비거주자
    necessary_expenses: int = 0              # 필요경비 (양도비용 등)
    long_term_deduction_rate: float = 0.0    # 장기보유특별공제율 (외부에서 계산하여 주입)
    is_burden_gift: bool = False              # 부담부증여 여부

    def __post_init__(self) -> None:
        if self.transfer_price_exempt_threshold is None:
            self.transfer_price_exempt_threshold = _TCR.get(
                "HIGH_VALUE_THRESHOLD", self.transfer_date
            )


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

    # ④ 기본공제
    basic_deduction: int = _TCR.get("BASIC_DEDUCTION", inp.transfer_date)
    taxable_income = max(0, taxable_income - basic_deduction)

    # ⑤ 세율 결정
    _brackets = _TCR.get("BASIC_TAX_BRACKETS", inp.transfer_date)
    _short_rates = _TCR.get("SHORT_TERM_RATES", inp.transfer_date)
    _heavy_additional = _TCR.get("HEAVY_TAX_ADDITIONAL", inp.transfer_date)

    if inp.is_non_resident:
        rate: float = _TCR.get("NON_RESIDENT_RATE", inp.transfer_date)
        rate_type = "비거주자"
        tax = int(taxable_income * rate)
    elif inp.is_short_term:
        years = inp.holding_years
        if years < 1.0:
            rate = _short_rates["under_1_year"]
            rate_type = "단기세율(1년미만)"
        else:
            rate = _short_rates["1_to_2_years"]
            rate_type = "단기세율(1~2년)"
        tax = int(taxable_income * rate)
    elif inp.is_heavy_tax and not inp.heavy_tax_suspended:
        base_tax, base_rate = _apply_basic_brackets(taxable_income, _brackets)
        _max_count_key = max(_heavy_additional.keys())
        additional = _heavy_additional.get(min(inp.household_house_count, _max_count_key),
                                           _heavy_additional[_max_count_key])
        rate = base_rate + additional
        rate_type = f"중과세율({inp.household_house_count}주택)"
        tax = base_tax + int(taxable_income * additional)
    else:
        tax, rate = _apply_basic_brackets(taxable_income, _brackets)
        rate_type = "기본세율"

    _local_rate: float = _TCR.get("LOCAL_INCOME_TAX_RATE", inp.transfer_date)
    local_tax = int(tax * _local_rate)
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


def compute_ltshd_rate(
    holding_years: float,
    residence_years: float,
    is_one_house: bool,
    as_of: Optional[date] = None,
) -> float:
    """
    장기보유특별공제율 계산.
    표1(일반): LONG_TERM_DEDUCTION_RATE_TABLE1 Registry 조회
    표2(1세대1주택): LONG_TERM_DEDUCTION_RATE_TABLE2 — 보유 4%/년 + 거주 4%/년, 최대 80%
    as_of가 None이면 오늘 날짜 기준으로 Registry를 조회한다.
    """
    if as_of is None:
        as_of = date.today()

    if holding_years < 3:
        return 0.0

    if is_one_house and residence_years >= 2:
        # 보유 4%/년(최대 40%) + 거주 4%/년(최대 40%), 합산 최대 80%
        # TABLE2 키는 연수, 값은 4%×연수 — 각 컴포넌트를 독립적으로 조회
        table2: dict = _TCR.get("LONG_TERM_DEDUCTION_RATE_TABLE2", as_of)
        max_key = max(table2)
        holding_rate = table2.get(min(int(holding_years), max_key), 0.0)
        residence_rate = table2.get(min(int(residence_years), max_key), 0.0)
        max_component = max(table2.values()) / 2  # 보유·거주 각 컴포넌트 상한 (전체 상한의 절반)
        return min(
            min(holding_rate, max_component) + min(residence_rate, max_component),
            max(table2.values()),
        )
    else:
        table1: dict = _TCR.get("LONG_TERM_DEDUCTION_RATE_TABLE1", as_of)
        capped_years = min(int(holding_years), max(table1))
        return table1.get(capped_years, 0.0)


def _apply_basic_brackets(taxable_income: int, brackets: list) -> tuple[int, float]:
    """기본세율 누진공제 방식으로 산출세액 계산. (세액, 한계세율) 반환."""
    for upper, rate, deduction in brackets:
        if taxable_income <= upper:
            return int(taxable_income * rate - deduction), rate
    # 최고구간 (brackets 마지막 항목)
    _, rate, deduction = brackets[-1]
    return int(taxable_income * rate - deduction), rate
