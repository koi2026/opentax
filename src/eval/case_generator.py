"""
합성 케이스 생성기 — 경계 케이스 자동 생성.

골든셋 확충 및 RLVR 학습 데이터 생성용.
경계 조건(날짜 기준일, 금액 임계값, 주택 수 변경)에서 케이스 자동 생성.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import date, timedelta
from pathlib import Path
from typing import Iterator, List, Optional


@dataclass
class SyntheticCase:
    case_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    description: str = ""
    fact_json: dict = field(default_factory=dict)
    expected_verdict: Optional[str] = None   # 생성 시 알 수 없으면 None
    boundary_type: str = ""                  # "date_boundary" | "price_boundary" | "house_count"
    tags: List[str] = field(default_factory=list)


def generate_date_boundary_cases(
    base_transfer_date: date,
    acquisition_date: date,
    acquisition_price: int = 500_000_000,
) -> Iterator[SyntheticCase]:
    """
    날짜 경계 케이스 생성:
    - 보유기간 1년/2년/3년 경계
    - 상생임대 기간 경계 (2021-12-20 / 2024-12-31)
    - 중과배제 기간 경계 (2026-05-09)
    """
    holding_boundaries = [
        timedelta(days=364),   # 1년 미만
        timedelta(days=365),   # 정확히 1년
        timedelta(days=366),   # 1년 초과
        timedelta(days=729),   # 2년 미만
        timedelta(days=730),   # 정확히 2년
        timedelta(days=1095),  # 3년
    ]

    for delta in holding_boundaries:
        acq = base_transfer_date - delta
        yield SyntheticCase(
            description=f"보유기간 {delta.days}일 경계 케이스",
            fact_json={
                "transfer_date": base_transfer_date.strftime("%Y%m%d"),
                "acquisition_date": acq.strftime("%Y%m%d"),
                "property_type": "아파트",
                "acquisition_reason": "매매",
                "household_house_count": 1,
                "transfer_price": 900_000_000,
                "acquisition_price": acquisition_price,
                "is_adjustment_area_at_transfer": False,
                "residence_years": delta.days / 365.25,
            },
            boundary_type="date_boundary",
            tags=["보유기간경계", f"{delta.days}일"],
        )


def generate_price_boundary_cases(
    transfer_date: date = date(2025, 6, 1),
    acquisition_date: date = date(2020, 1, 1),
) -> Iterator[SyntheticCase]:
    """
    금액 경계 케이스 — 12억 전후:
    - 11.9억, 12억, 12.1억, 15억
    """
    prices = [
        (1_190_000_000, "11.9억 비과세"),
        (1_200_000_000, "12억 정확히 비과세한도"),
        (1_210_000_000, "12.1억 고가주택"),
        (1_500_000_000, "15억 고가주택"),
    ]
    for price, description in prices:
        yield SyntheticCase(
            description=description,
            fact_json={
                "transfer_date": transfer_date.strftime("%Y%m%d"),
                "acquisition_date": acquisition_date.strftime("%Y%m%d"),
                "property_type": "아파트",
                "acquisition_reason": "매매",
                "household_house_count": 1,
                "transfer_price": price,
                "acquisition_price": 500_000_000,
                "residence_years": 3.0,
                "is_adjustment_area_at_transfer": False,
            },
            expected_verdict="고가주택" if price > 1_200_000_000 else "비과세",
            boundary_type="price_boundary",
            tags=["12억경계", "고가주택"],
        )


def generate_house_count_cases(
    transfer_date: date = date(2025, 6, 1),
) -> Iterator[SyntheticCase]:
    """주택 수 경계 케이스 — 1주택/2주택/3주택."""
    for count in [1, 2, 3]:
        yield SyntheticCase(
            description=f"세대 내 {count}주택 케이스",
            fact_json={
                "transfer_date": transfer_date.strftime("%Y%m%d"),
                "acquisition_date": "20180101",
                "property_type": "아파트",
                "acquisition_reason": "매매",
                "household_house_count": count,
                "transfer_price": 1_000_000_000,
                "acquisition_price": 600_000_000,
                "residence_years": 3.0,
                "is_adjustment_area_at_transfer": True,
            },
            boundary_type="house_count",
            tags=["주택수경계", f"{count}주택"],
        )


def generate_all_boundary_cases(n_per_type: int = 10) -> List[SyntheticCase]:
    """전체 경계 케이스 생성."""
    cases: List[SyntheticCase] = []
    today = date(2025, 6, 1)

    cases.extend(list(generate_date_boundary_cases(today, date(2018, 1, 1)))[:n_per_type])
    cases.extend(list(generate_price_boundary_cases(today))[:n_per_type])
    cases.extend(list(generate_house_count_cases(today))[:n_per_type])

    return cases


def save_cases(cases: List[SyntheticCase], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = [asdict(c) for c in cases]
    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    cases = generate_all_boundary_cases()
    save_cases(cases, Path("data/golden/synthetic_cases.json"))
    print(f"생성된 경계 케이스: {len(cases)}건")
