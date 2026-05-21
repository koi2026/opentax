"""
취득일·보유기간 기산점 결정 모듈.

보유기간 승계(날짜)와 취득가액 승계(금액)는 별도 규칙을 따른다.
이 모듈은 날짜/기간 결정만 담당한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass(frozen=True)
class AcquisitionTimelineResult:
    effective_acquisition_date: date          # 보유기간 기산점
    holding_period_base_date: date            # 보유기간 계산 시작일 (= effective_acquisition_date)
    is_successor_period: bool                 # True = 승계된 기간 포함
    rollover_applies: bool                    # True = 이월과세 적용 (취득가액도 영향받음)
    source_rule: str                          # 적용 근거 조문


def resolve_effective_acquisition_date(
    declared_acquisition_date: date,
    transfer_date: date,
    acquisition_reason: str,
    donor_acquisition_date: Optional[date] = None,
    gift_date: Optional[date] = None,
    is_gift_from_spouse_or_lineal: Optional[bool] = None,
    death_date: Optional[date] = None,
    deceased_original_acquisition_date: Optional[date] = None,
    original_house_acquisition_date: Optional[date] = None,
    management_disposal_date: Optional[date] = None,
    iota_period_years: int = 10,
) -> AcquisitionTimelineResult:
    """
    법적 보유기간 기산점을 결정.

    acquisition_reason: "매매" | "상속" | "증여" | "부담부증여" | "재건축" | "재개발" | ...
    """
    # ── 이월과세: 배우자/직계 증여 후 iota_period_years 이내 양도 ─────────
    is_gift = acquisition_reason in ("증여", "부담부증여")
    if (
        is_gift
        and is_gift_from_spouse_or_lineal
        and gift_date is not None
        and donor_acquisition_date is not None
    ):
        years_since_gift = (transfer_date - gift_date).days / 365.25
        if years_since_gift < iota_period_years:
            return AcquisitionTimelineResult(
                effective_acquisition_date=donor_acquisition_date,
                holding_period_base_date=donor_acquisition_date,
                is_successor_period=True,
                rollover_applies=True,
                source_rule="소득세법 §97의2 이월과세",
            )

    # ── 상속: 피상속인 원취득일 승계 (보유기간 합산) ─────────────────────
    if acquisition_reason == "상속" and deceased_original_acquisition_date is not None:
        # 피상속인 취득일부터 보유기간 계산 (보유기간 승계 적용 시)
        # 단, 취득가액 승계는 별도 (이 모듈 범위 밖)
        return AcquisitionTimelineResult(
            effective_acquisition_date=deceased_original_acquisition_date,
            holding_period_base_date=deceased_original_acquisition_date,
            is_successor_period=True,
            rollover_applies=False,
            source_rule="소득세법 시행령 §154③, §155② 상속주택 보유기간 승계",
        )

    # ── 재건축/재개발 입주권: 종전주택 취득일부터 기산 ─────────────────────
    if acquisition_reason in ("재건축", "재개발") and original_house_acquisition_date is not None:
        return AcquisitionTimelineResult(
            effective_acquisition_date=original_house_acquisition_date,
            holding_period_base_date=original_house_acquisition_date,
            is_successor_period=True,
            rollover_applies=False,
            source_rule="소득세법 시행령 §156의2 조합원입주권 보유기간",
        )

    # ── 기본: 신고된 취득일 사용 ──────────────────────────────────────────
    return AcquisitionTimelineResult(
        effective_acquisition_date=declared_acquisition_date,
        holding_period_base_date=declared_acquisition_date,
        is_successor_period=False,
        rollover_applies=False,
        source_rule="소득세법 시행령 §162 취득일 원칙",
    )


def resolve_holding_period_years(
    timeline: AcquisitionTimelineResult,
    transfer_date: date,
) -> float:
    """보유기간(년) = (양도일 - 보유기간기산점) / 365.25"""
    return (transfer_date - timeline.holding_period_base_date).days / 365.25


def is_rollover_period_active(
    gift_date: date,
    transfer_date: date,
    iota_period_years: int = 10,
) -> bool:
    """이월과세 기간 내 양도 여부."""
    return (transfer_date - gift_date).days / 365.25 < iota_period_years
