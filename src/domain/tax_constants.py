"""
세법 상수 레지스트리 — 연도별 버전 관리.

anchor_key 기준 날짜로 유효한 버전을 조회한다.
별표 이미지 등 기계 판독 불가 상수는 manual_review_required=True로 표시하고
사람이 직접 등록한 값을 사용한다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ConstantVersion:
    effective_from: date
    effective_to: date          # date.max for currently-active versions
    value: Any
    source_law: str             # e.g. "소득세법 §89①3호"
    anchor_key: str = "transfer_date"   # which date field to anchor on
    manual_review_required: bool = False  # True when sourced from 별표 image


_REGISTRY: Dict[str, List[ConstantVersion]] = {
    "HIGH_VALUE_THRESHOLD": [
        ConstantVersion(
            date(2021, 1, 1), date.max,
            1_200_000_000,
            "소득세법 §89①3호, 시행령 §156의2",
        ),
    ],
    "SANGSAENG_WINDOW_START": [
        ConstantVersion(
            date(2021, 12, 20), date.max,
            date(2021, 12, 20),
            "소득세법 시행령 §155의3",
        ),
    ],
    "SANGSAENG_WINDOW_END": [
        ConstantVersion(
            date(2021, 12, 20), date.max,
            date(2024, 12, 31),
            "소득세법 시행령 §155의3",
        ),
    ],
    "SANGSAENG_MAX_INCREASE_RATE": [
        ConstantVersion(
            date(2021, 12, 20), date.max,
            0.05,
            "소득세법 시행령 §155의3",
        ),
    ],
    "HEAVY_TAX_SUSPENSION_END": [
        ConstantVersion(
            date(2022, 5, 10), date.max,
            date(2026, 5, 9),
            "소득세법 §104①, 한시적 중과배제",
        ),
    ],
    # 이월과세 적용 기간 — 증여일 기준 앵커
    "IOTA_PERIOD_YEARS": [
        ConstantVersion(
            date(2023, 1, 1), date.max,
            10,
            "소득세법 §97의2 (2023년 개정: 5→10년)",
            anchor_key="gift_date",
        ),
        ConstantVersion(
            date(2000, 1, 1), date(2022, 12, 31),
            5,
            "소득세법 §97의2 (개정 전)",
            anchor_key="gift_date",
        ),
    ],
    # 기본세율 구간표 (소득세법 §55①) — list[(상한, 세율, 누진공제)]
    "BASIC_TAX_BRACKETS": [
        ConstantVersion(
            date(2021, 1, 1), date.max,
            [
                (14_000_000, 0.06, 0),
                (50_000_000, 0.15, 1_260_000),
                (88_000_000, 0.24, 5_760_000),
                (150_000_000, 0.35, 15_440_000),
                (300_000_000, 0.38, 19_940_000),
                (500_000_000, 0.40, 25_940_000),
                (1_000_000_000, 0.42, 35_940_000),
                (float("inf"), 0.45, 65_940_000),
            ],
            "소득세법 §55①",
        ),
    ],
    # 단기보유 세율 (소득세법 §104①)
    "SHORT_TERM_RATES": [
        ConstantVersion(
            date(2021, 6, 1), date.max,
            {"under_1_year": 0.70, "1_to_2_years": 0.60},
            "소득세법 §104①1호",
        ),
    ],
    # 다주택 중과 추가세율 (소득세법 §104①2,3호)
    "HEAVY_TAX_ADDITIONAL": [
        ConstantVersion(
            date(2018, 4, 1), date.max,
            {2: 0.20, 3: 0.30},
            "소득세법 §104①2호,3호",
        ),
    ],
    # 비거주자 단일세율 (소득세법 §121②)
    "NON_RESIDENT_RATE": [
        ConstantVersion(date(2000, 1, 1), date.max, 0.20, "소득세법 §121②"),
    ],
    # 기본공제 (소득세법 §103)
    "BASIC_DEDUCTION": [
        ConstantVersion(date(2000, 1, 1), date.max, 2_500_000, "소득세법 §103①"),
    ],
    # 지방소득세율 (지방세법 §92, 개인지방소득세)
    "LOCAL_INCOME_TAX_RATE": [
        ConstantVersion(date(2014, 1, 1), date.max, 0.10, "지방세법 §92"),
    ],
    # 한시적 중과배제 시작일
    "HEAVY_TAX_SUSPENSION_START": [
        ConstantVersion(
            date(2022, 5, 10), date.max,
            date(2022, 5, 10),
            "소득세법 §104①, 한시적 중과배제",
        ),
    ],
    # 조정대상지역 거주요건 제도 시행일 (소득세법 §154① 개정)
    "ADJUSTMENT_AREA_RESIDENCE_RULE_START": [
        ConstantVersion(
            date(2017, 8, 3), date.max,
            date(2017, 8, 3),
            "소득세법 §154①, 2017.8.3 취득분부터 적용",
        ),
    ],
    # 조정대상지역 취득 시 거주요건 연수 (소득세법 §154①)
    "RESIDENCE_REQUIRED_YEARS_ADJUSTMENT": [
        ConstantVersion(date(2017, 8, 3), date.max, 2.0, "소득세법 §154①"),
    ],
    # 상생임대 최소 임대기간 (소득세법 시행령 §155의3)
    "SANGSAENG_MIN_PERIOD_MONTHS": [
        ConstantVersion(
            date(2021, 12, 20), date.max,
            24,
            "소득세법 시행령 §155의3",
        ),
    ],
    # 비거주자 해외이주 후 비과세 예외 적용 기한 (소득세법 §89①4호)
    "NON_RESIDENT_DEPARTURE_EXEMPTION_MONTHS": [
        ConstantVersion(date(2000, 1, 1), date.max, 24, "소득세법 §89①4호"),
    ],
    # 취득세율 추산 — 시뮬레이션 전용 (지방세법 §15, 감면 미포함)
    "ACQUISITION_TAX_RATE_GIFT": [
        ConstantVersion(date(2020, 8, 12), date.max, 0.035, "지방세법 §15①1호 (증여)"),
    ],
    "ACQUISITION_TAX_RATE_GENERAL": [
        ConstantVersion(date(2020, 8, 12), date.max, 0.04, "지방세법 §15①2호 (유상취득)"),
    ],
    # 장기보유특별공제율 표1 — 일반 (소득세법 §95② 별표1)
    # 보유기간(년): 공제율
    "LONG_TERM_DEDUCTION_RATE_TABLE1": [
        ConstantVersion(
            date(2021, 1, 1), date.max,
            {
                3: 0.06, 4: 0.08, 5: 0.10, 6: 0.12, 7: 0.14,
                8: 0.16, 9: 0.18, 10: 0.20, 11: 0.22, 12: 0.24,
                13: 0.26, 14: 0.28, 15: 0.30,
            },
            "소득세법 §95②, 별표1",
            manual_review_required=False,
        ),
    ],
    # 장기보유특별공제율 표2 — 1세대1주택 (거주기간 포함)
    "LONG_TERM_DEDUCTION_RATE_TABLE2": [
        ConstantVersion(
            date(2021, 1, 1), date.max,
            {
                2: 0.08, 3: 0.12, 4: 0.16, 5: 0.20, 6: 0.24,
                7: 0.28, 8: 0.32, 9: 0.36, 10: 0.40, 11: 0.44,
                12: 0.48, 13: 0.52, 14: 0.56, 15: 0.60, 16: 0.64,
                17: 0.68, 18: 0.72, 19: 0.76, 20: 0.80,
            },
            "소득세법 §95②, 별표2 (1세대1주택: 거주기간 포함)",
            manual_review_required=False,
        ),
    ],
}


class TaxConstantsRegistry:
    @staticmethod
    def get(key: str, as_of: date, anchor_key: Optional[str] = None) -> Any:
        """
        Return the constant value effective on `as_of` date.

        Raises KeyError if key not found in registry.
        Falls back to oldest version when no version covers as_of
        (handles pre-history queries gracefully).
        """
        versions = _REGISTRY.get(key)
        if versions is None:
            raise KeyError(f"Unknown constant key: {key!r}")

        for v in sorted(versions, key=lambda x: x.effective_from, reverse=True):
            if v.effective_from <= as_of <= v.effective_to:
                if v.manual_review_required:
                    logger.warning(
                        "상수 %r (as_of=%s)는 별표 이미지 기반 수동 등록값입니다. "
                        "법령 개정 시 manual_review_required 항목을 확인하세요.",
                        key, as_of,
                    )
                return v.value

        # No version matched — fall back to oldest to avoid hard failure
        oldest = min(versions, key=lambda x: x.effective_from)
        logger.debug(
            "상수 %r에 대해 %s 기준 유효한 버전이 없습니다. "
            "가장 오래된 버전(%s)으로 대체합니다.",
            key, as_of, oldest.effective_from,
        )
        return oldest.value

    @staticmethod
    def get_version(key: str, as_of: date) -> Optional[ConstantVersion]:
        """Return the full ConstantVersion metadata effective on `as_of`, or None."""
        versions = _REGISTRY.get(key)
        if not versions:
            return None
        for v in sorted(versions, key=lambda x: x.effective_from, reverse=True):
            if v.effective_from <= as_of <= v.effective_to:
                return v
        return min(versions, key=lambda x: x.effective_from)

    @staticmethod
    def all_keys() -> List[str]:
        """Return all registered constant keys."""
        return list(_REGISTRY.keys())
