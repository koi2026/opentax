"""
유형2 시뮬레이션 엔진 — 양도 / 증여 / 부담부증여 세금 비교.

컨설팅 모드(query_mode="consulting")에서 호출된다.

계산 범위:
  양도: 양도소득세 + 지방소득세 (TaxCalculator 직접 연동)
  증여: 증여세 (배우자/직계/기타 공제 적용) + 수증자 취득세 추산
  부담부증여: 채무 부분 양도소득세 + 순증여 부분 증여세 + 취득세

미계산 항목 (전문가 상담 필요):
  수증자의 추후 양도세, 이월과세 손익 정밀 분석, 지방세 특례
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from src.calculator.tax_calculator import (
    TaxCalculationInput,
    TaxCalculation,
    calculate_transfer_tax,
    compute_ltshd_rate,
    _apply_basic_brackets,
)
from src.domain.tax_answer import TaxVerdict

# ── 증여세율표 (상속세 및 증여세법 §56) ──────────────────────────────────────
_GIFT_TAX_BRACKETS: list[tuple] = [
    (100_000_000,     0.10,          0),
    (500_000_000,     0.20,   10_000_000),
    (1_000_000_000,   0.30,   60_000_000),
    (3_000_000_000,   0.40,  160_000_000),
    (float("inf"),    0.50,  460_000_000),
]

# 증여재산공제 10년 합산 기준 (상증법 §53)
_GIFT_DEDUCTIONS: dict[str, int] = {
    "배우자":              600_000_000,  # 6억
    "직계존비속":           50_000_000,  # 5천만 (성년)
    "직계존비속_미성년":     20_000_000,  # 2천만
    "기타":                10_000_000,  # 1천만
}


@dataclass
class ScenarioResult:
    """처분 시나리오 1개의 계산 결과."""
    scenario_type: str              # "양도" | "증여" | "부담부증여"
    description: str
    transfer_income_tax: int = 0   # 양도소득세 (국세)
    gift_tax: int = 0              # 증여세
    local_income_tax: int = 0      # 지방소득세 (양도소득세×10%)
    acquisition_tax_estimate: int = 0  # 수증자 취득세 추산 (참고용)
    total_tax: int = 0             # 납부세 합계 (취득세 제외)
    effective_rate: float = 0.0    # 실효세율 (총세액 / 시가)
    notes: List[str] = field(default_factory=list)
    is_calculable: bool = True     # False이면 세액 미산출, 전문가 상담 필요
    detail: Optional[dict] = None  # 세부 계산 내역 (디버그/표시용)

    def to_dict(self) -> dict:
        return {
            "scenario_type": self.scenario_type,
            "description": self.description,
            "transfer_income_tax": self.transfer_income_tax,
            "gift_tax": self.gift_tax,
            "local_income_tax": self.local_income_tax,
            "acquisition_tax_estimate": self.acquisition_tax_estimate,
            "total_tax": self.total_tax,
            "effective_rate": round(self.effective_rate, 4),
            "notes": self.notes,
            "is_calculable": self.is_calculable,
            "detail": self.detail,
        }


@dataclass
class SimulationResult:
    """3개 시나리오 비교 최종 결과."""
    scenarios: List[ScenarioResult]
    optimal_type: str              # 세금 최소 시나리오 타입
    optimal_saving: int            # 양도 대비 절세액
    recommendation_reason: str
    expert_review_needed: bool = True
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "scenarios": [s.to_dict() for s in self.scenarios],
            "optimal_type": self.optimal_type,
            "optimal_saving": self.optimal_saving,
            "recommendation_reason": self.recommendation_reason,
            "expert_review_needed": self.expert_review_needed,
            "warnings": self.warnings,
        }


# ── 세부 계산 함수 ──────────────────────────────────────────────────────────


def _calc_gift_tax(gift_value: int, recipient: str, is_adult: bool) -> int:
    """증여세 산출세액 계산 (누진공제 방식)."""
    key = "직계존비속_미성년" if (recipient == "직계존비속" and not is_adult) else recipient
    deduction = _GIFT_DEDUCTIONS.get(key, _GIFT_DEDUCTIONS["기타"])
    taxable = max(0, gift_value - deduction)
    for upper, rate, prog_ded in _GIFT_TAX_BRACKETS:
        if taxable <= upper:
            return max(0, int(taxable * rate - prog_ded))
    return max(0, int(taxable * 0.50 - 460_000_000))


def _estimate_acquisition_tax(value: int, *, is_gift: bool = True) -> int:
    """수증자 취득세 추산 — 증여 3.5%, 유상 4% (지방세법 §15 기준, 감면 미포함)."""
    return int(value * (0.035 if is_gift else 0.04))


def build_transfer_scenario(
    *,
    market_value: int,
    acquisition_price: int,
    holding_years: float,
    residence_years: float,
    household_house_count: int,
    verdict: str,
    necessary_expenses: int = 0,
    heavy_tax_suspended: bool = False,
    is_non_resident: bool = False,
) -> ScenarioResult:
    """양도 시나리오 — TaxCalculator 직접 연동."""
    from datetime import date as _date

    is_one_house = verdict in (TaxVerdict.EXEMPT, TaxVerdict.PARTIALLY_EXEMPT)
    is_high_value = verdict == TaxVerdict.PARTIALLY_EXEMPT
    is_heavy = verdict == TaxVerdict.HEAVY_TAX
    short_term = holding_years < 2.0

    ltd_rate = compute_ltshd_rate(holding_years, residence_years, is_one_house)
    today = _date.today()

    inp = TaxCalculationInput(
        transfer_price=market_value,
        acquisition_price=acquisition_price,
        transfer_date=today,
        acquisition_date=today,
        holding_years=holding_years,
        residence_years=residence_years,
        household_house_count=household_house_count,
        is_one_house_exemption=is_one_house,
        is_high_value_house=is_high_value,
        is_heavy_tax=is_heavy,
        heavy_tax_suspended=heavy_tax_suspended,
        is_short_term=short_term,
        is_non_resident=is_non_resident,
        necessary_expenses=necessary_expenses,
        long_term_deduction_rate=ltd_rate,
    )
    calc: TaxCalculation = calculate_transfer_tax(inp)

    notes: list[str] = []
    if verdict == TaxVerdict.NEEDS_VERIFICATION:
        notes.append("비과세 요건 미확정 — 별도 확인 필요")
    if is_heavy:
        notes.append(f"다주택 중과세율 적용 ({household_house_count}주택)")
    if short_term:
        notes.append("단기보유(2년 미만) 세율 적용")
    if verdict in (TaxVerdict.EXEMPT,) and not is_high_value:
        notes.append("1세대1주택 비과세 — 세액 0원")

    return ScenarioResult(
        scenario_type="양도",
        description="현재 시세로 매도",
        transfer_income_tax=calc.calculated_tax,
        local_income_tax=calc.local_income_tax,
        total_tax=calc.total_tax,
        effective_rate=calc.total_tax / market_value if market_value else 0.0,
        notes=notes,
        detail={
            "gross_gain": calc.gross_gain,
            "long_term_deduction": calc.long_term_deduction,
            "ltd_rate": round(ltd_rate, 4),
            "taxable_income": calc.taxable_income,
            "rate_type": calc.rate_type,
            "applied_rate": calc.applied_rate,
            "deduction_summary": calc.deduction_summary,
        },
    )


def build_gift_scenario(
    *,
    market_value: int,
    gift_recipient: str,
    recipient_is_adult: bool = True,
) -> ScenarioResult:
    """증여 시나리오 — 증여세 + 수증자 취득세 추산."""
    gift_tax = _calc_gift_tax(market_value, gift_recipient, recipient_is_adult)
    acquisition_tax = _estimate_acquisition_tax(market_value)
    total = gift_tax + acquisition_tax

    key = "직계존비속_미성년" if (gift_recipient == "직계존비속" and not recipient_is_adult) else gift_recipient
    deduction = _GIFT_DEDUCTIONS.get(key, _GIFT_DEDUCTIONS["기타"])

    notes = [
        "수증자 취득세 추산 포함 (시가 × 3.5%, 감면 미적용)",
        "수증자 추후 양도 시 이월과세 위험 별도 검토 필요",
    ]
    if gift_recipient == "배우자":
        notes.append("배우자 증여 후 5년 내 양도 시 이월과세(§97의2) 의무 확인")

    return ScenarioResult(
        scenario_type="증여",
        description=f"{gift_recipient}에게 무상증여",
        gift_tax=gift_tax,
        acquisition_tax_estimate=acquisition_tax,
        total_tax=total,
        effective_rate=total / market_value if market_value else 0.0,
        notes=notes,
        detail={
            "market_value": market_value,
            "deduction": deduction,
            "taxable_gift": max(0, market_value - deduction),
            "gift_tax": gift_tax,
            "acquisition_tax_estimate": acquisition_tax,
        },
    )


def build_burden_gift_scenario(
    *,
    market_value: int,
    acquisition_price: int,
    encumbrance: int,
    holding_years: float,
    gift_recipient: str,
    recipient_is_adult: bool = True,
    is_heavy_tax: bool = False,
    necessary_expenses: int = 0,
) -> ScenarioResult:
    """부담부증여 — 채무 비율 양도세 + 순증여 증여세.

    채무비율 = 채무액 / 시가
    양도세 과세: 채무액을 양도가액으로, 취득가액 × 채무비율
    증여세 과세: 시가 - 채무액 (순증여액)
    """
    if encumbrance <= 0 or encumbrance >= market_value:
        return ScenarioResult(
            scenario_type="부담부증여",
            description="채무액 없음 또는 초과 — 계산 불가",
            is_calculable=False,
            notes=["채무액(담보대출·임대보증금)이 0이거나 시가 초과 시 순증여로 처리"],
        )

    ratio = encumbrance / market_value
    enc_acquisition = int(acquisition_price * ratio)
    enc_expenses = int(necessary_expenses * ratio)
    gain_on_debt = max(0, encumbrance - enc_acquisition - enc_expenses)

    ltd_rate = compute_ltshd_rate(holding_years, 0.0, False)  # 부담부증여는 표1 적용
    short_term = holding_years < 2.0

    if gain_on_debt > 0:
        ltd = int(gain_on_debt * ltd_rate) if not short_term and not is_heavy_tax else 0
        taxable = max(0, gain_on_debt - ltd - 2_500_000)  # 기본공제 250만
        if short_term:
            rate = 0.70 if holding_years < 1.0 else 0.60
            debt_tax = int(taxable * rate)
        elif is_heavy_tax:
            base_tax, base_rate = _apply_basic_brackets(taxable)
            debt_tax = base_tax + int(taxable * 0.30)  # +30% 추산 (3주택 기준)
        else:
            debt_tax, _ = _apply_basic_brackets(taxable)
        debt_local = int(debt_tax * 0.10)
    else:
        debt_tax = debt_local = 0

    net_gift = market_value - encumbrance
    gift_tax = _calc_gift_tax(net_gift, gift_recipient, recipient_is_adult)
    acquisition_tax = _estimate_acquisition_tax(market_value)
    total = debt_tax + debt_local + gift_tax + acquisition_tax

    notes = [
        f"채무비율 {ratio:.1%} 부분 양도세 과세",
        "수증자 취득세 추산 포함 (시가 × 3.5%)",
    ]
    if is_heavy_tax:
        notes.append("다주택 중과 — 채무 부분 세액은 3주택 기준 추산, 실제와 다를 수 있음")
    if short_term:
        notes.append("단기보유 단일세율 적용")

    return ScenarioResult(
        scenario_type="부담부증여",
        description=f"채무({encumbrance:,}원) 부담부증여 / 순증여({net_gift:,}원)",
        transfer_income_tax=debt_tax,
        gift_tax=gift_tax,
        local_income_tax=debt_local,
        acquisition_tax_estimate=acquisition_tax,
        total_tax=total,
        effective_rate=total / market_value if market_value else 0.0,
        notes=notes,
        detail={
            "encumbrance": encumbrance,
            "encumbrance_ratio": round(ratio, 4),
            "debt_gain": gain_on_debt,
            "debt_transfer_tax": debt_tax,
            "net_gift": net_gift,
            "gift_tax": gift_tax,
            "acquisition_tax_estimate": acquisition_tax,
        },
    )


# ── 진입점 ───────────────────────────────────────────────────────────────────


def run_simulation(
    *,
    market_value: int,
    acquisition_price: int,
    holding_years: float,
    residence_years: float,
    household_house_count: int,
    verdict: str,
    encumbrance: int = 0,
    gift_recipient: str = "직계존비속",
    recipient_is_adult: bool = True,
    necessary_expenses: int = 0,
    heavy_tax_suspended: bool = False,
    is_non_resident: bool = False,
) -> SimulationResult:
    """
    양도 / 증여 / 부담부증여 3개 시나리오 세금 비교.

    verdict: RAG 파이프라인이 산출한 TaxVerdict 문자열 — 양도 시나리오 세율 결정에 사용.
    encumbrance: 채무총액(담보대출+임대보증금) — 0이면 부담부증여 시나리오 생략.
    """
    is_heavy = verdict == TaxVerdict.HEAVY_TAX

    scenarios: list[ScenarioResult] = []

    transfer_s = build_transfer_scenario(
        market_value=market_value,
        acquisition_price=acquisition_price,
        holding_years=holding_years,
        residence_years=residence_years,
        household_house_count=household_house_count,
        verdict=verdict,
        necessary_expenses=necessary_expenses,
        heavy_tax_suspended=heavy_tax_suspended,
        is_non_resident=is_non_resident,
    )
    scenarios.append(transfer_s)

    gift_s = build_gift_scenario(
        market_value=market_value,
        gift_recipient=gift_recipient,
        recipient_is_adult=recipient_is_adult,
    )
    scenarios.append(gift_s)

    if encumbrance > 0:
        burden_s = build_burden_gift_scenario(
            market_value=market_value,
            acquisition_price=acquisition_price,
            encumbrance=encumbrance,
            holding_years=holding_years,
            gift_recipient=gift_recipient,
            recipient_is_adult=recipient_is_adult,
            is_heavy_tax=is_heavy,
            necessary_expenses=necessary_expenses,
        )
        scenarios.append(burden_s)

    calculable = [s for s in scenarios if s.is_calculable]
    optimal = min(calculable, key=lambda s: s.total_tax) if calculable else scenarios[0]

    saving = max(0, transfer_s.total_tax - optimal.total_tax)
    saving_pct = saving / market_value * 100 if market_value else 0

    if optimal.scenario_type == "양도":
        reason = "현재 비과세·감면 요건이 충족되어 양도가 가장 유리합니다."
    elif optimal.scenario_type == "증여":
        reason = (
            f"증여 시 세 부담이 양도 대비 {saving:,}원 ({saving_pct:.1f}%) 절감됩니다. "
            "수증자 추후 양도세·이월과세 기간을 반드시 확인하세요."
        )
    else:
        reason = (
            f"부담부증여 시 양도 대비 {saving:,}원 절감됩니다. "
            "채무 부분 양도세 및 수증자 취득세를 합산한 결과입니다."
        )

    warnings: list[str] = []
    if market_value < 100_000_000:
        warnings.append("시가 1억 미만 — 증여세 계산은 참고값입니다.")
    if is_non_resident:
        warnings.append("비거주자 양도 — 증여·부담부증여 적용 가능 여부 별도 검토 필요")
    if verdict == TaxVerdict.NEEDS_VERIFICATION:
        warnings.append("비과세 요건 미확정 상태의 추산입니다.")

    return SimulationResult(
        scenarios=scenarios,
        optimal_type=optimal.scenario_type,
        optimal_saving=saving,
        recommendation_reason=reason,
        expert_review_needed=True,
        warnings=warnings,
    )
