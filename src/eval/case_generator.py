"""
합성 케이스 생성기 — 경계 케이스 자동 생성.

골든셋 확충 및 RLVR 학습 데이터 생성용.
경계 조건(날짜 기준일, 금액 임계값, 주택 수 변경)에서 케이스 자동 생성.

특례 유형별 시나리오:
  - 일시적2주택, 상속주택, 이월과세(배우자증여), 상생임대
  - 재건축/입주권, 농어촌주택, 동거봉양합가
  - 비거주자, 분양권
  - 중과(현행 2026-05-09 이후 부활), 단기세율, L2 차단
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import date, timedelta
from pathlib import Path
from typing import Iterator, List, Optional

def _get_heavy_tax_suspension_end(as_of: Optional[date] = None) -> date:
    """TaxConstantsRegistry에서 읽어 법령 개정 시 자동 반영."""
    try:
        from src.domain.tax_constants import TaxConstantsRegistry
        v = TaxConstantsRegistry.get("HEAVY_TAX_SUSPENSION_END", as_of or date.today())
        return v if isinstance(v, date) else date.fromisoformat(str(v))
    except Exception:
        return date(2026, 5, 9)  # fallback


@dataclass
class SyntheticCase:
    case_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    description: str = ""
    fact_json: dict = field(default_factory=dict)
    expected_verdict: Optional[str] = None   # 생성 시 알 수 없으면 None
    boundary_type: str = ""                  # "date_boundary" | "price_boundary" | "house_count"
    tags: List[str] = field(default_factory=list)
    registry_deps: List[str] = field(default_factory=list)
    # 이 케이스의 expected_verdict가 의존하는 TaxConstantsRegistry 키 목록.
    # 개정 감지 시 해당 키가 바뀌면 이 케이스를 자동 stale 처리.


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
    금액 경계 케이스 — HIGH_VALUE_THRESHOLD(TaxConstantsRegistry) 기준.
    하드코딩 대신 레지스트리에서 기준금액을 읽어 법령 개정 시 자동 반영.
    """
    try:
        from src.domain.tax_constants import TaxConstantsRegistry
        threshold = TaxConstantsRegistry.get("HIGH_VALUE_THRESHOLD", transfer_date)
    except Exception:
        threshold = 1_200_000_000  # 레지스트리 미접근 시 fallback

    margin = 10_000_000  # ±1천만원 경계
    threshold_label = f"{threshold // 100_000_000}억"

    prices = [
        (threshold - margin, f"{threshold_label} 미달 비과세"),
        (threshold, f"{threshold_label} 정확히 비과세한도"),
        (threshold + margin, f"{threshold_label} 초과 고가주택"),
        (threshold + 300_000_000, f"{threshold_label} +3억 고가주택"),
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
            expected_verdict="고가주택" if price > threshold else "비과세",
            boundary_type="price_boundary",
            tags=[f"{threshold_label}경계", "고가주택"],
            registry_deps=["HIGH_VALUE_THRESHOLD"],
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


def generate_temp_two_house_cases(
    transfer_date: date = date(2026, 4, 1),
) -> Iterator[SyntheticCase]:
    """일시적2주택 특례 — 소득세법 §155①."""
    _suspension_end = _get_heavy_tax_suspension_end(transfer_date)
    _after_suspension = transfer_date > _suspension_end
    scenarios = [
        {
            "desc": "일시적2주택 — 3년 내 종전주택 양도 (비과세)",
            "new_acq": "20230901",
            "expected": "비과세",
            "tags": ["일시적2주택", "3년이내"],
        },
        {
            "desc": "일시적2주택 — 3년 초과 후 양도 (일반과세)" if not _after_suspension else "일시적2주택 — 3년 초과 후 양도 (중과)",
            "new_acq": "20221201",
            "expected": "중과" if _after_suspension else "일반과세",
            "tags": ["일시적2주택", "3년초과"],
        },
        {
            "desc": "일시적2주택 — 신규주택 취득 후 1일 경과 (비과세 여부)",
            "new_acq": "20260331",
            "expected": None,
            "tags": ["일시적2주택", "경계"],
        },
        {
            "desc": "일시적2주택 — 조정→조정 2년거주 충족",
            "new_acq": "20231001",
            "expected": "비과세",
            "tags": ["일시적2주택", "조정대상지역"],
        },
    ]
    def _add_3years(yyyymmdd: str) -> str:
        """YYYYMMDD 날짜에 3년 추가."""
        from datetime import date as _d
        d = _d(int(yyyymmdd[:4]), int(yyyymmdd[4:6]), int(yyyymmdd[6:8]))
        try:
            return _d(d.year + 3, d.month, d.day).strftime("%Y%m%d")
        except ValueError:
            return _d(d.year + 3, d.month, d.day - 1).strftime("%Y%m%d")

    for s in scenarios:
        yield SyntheticCase(
            description=s["desc"],
            fact_json={
                "transfer_date": transfer_date.strftime("%Y%m%d"),
                "acquisition_date": "20180601",
                "property_type": "아파트",
                "acquisition_reason": "매매",
                "household_house_count": 2,
                "transfer_price": 900_000_000,
                "acquisition_price": 500_000_000,
                "residence_years": 3.0,
                "is_adjustment_area_at_transfer": True,
                "special_cases": {
                    "temp_two_house": {
                        "new_acquisition_date": s["new_acq"],
                        "old_house_must_sell_by": _add_3years(s["new_acq"]),
                        "new_is_adjustment_area": True,
                    }
                },
            },
            expected_verdict=s["expected"],
            boundary_type="special_case",
            tags=s["tags"],
        )


def generate_inheritance_cases(
    transfer_date: date = date(2026, 4, 1),
) -> Iterator[SyntheticCase]:
    """상속주택 특례 — 소득세법 §155②."""
    scenarios = [
        {
            "desc": "상속주택 — 상속 후 5년 이내 양도 (1주택 간주)",
            "death_date": "20210601",
            "expected": "비과세",
            "tags": ["상속주택", "5년이내"],
        },
        {
            "desc": "상속주택 — 상속 후 5년 초과 양도 (다주택 취급)",
            "death_date": "20190601",
            "expected": "일반과세",
            "tags": ["상속주택", "5년초과"],
        },
        {
            "desc": "상속주택 — 협의분할 취득일 기산 (취득일 경계)",
            "death_date": "20210101",
            "expected": None,
            "tags": ["상속주택", "협의분할"],
        },
    ]
    for s in scenarios:
        yield SyntheticCase(
            description=s["desc"],
            fact_json={
                "transfer_date": transfer_date.strftime("%Y%m%d"),
                "acquisition_date": "20180101",
                "property_type": "아파트",
                "acquisition_reason": "매매",
                "household_house_count": 2,
                "transfer_price": 800_000_000,
                "acquisition_price": 400_000_000,
                "residence_years": 2.0,
                "is_adjustment_area_at_transfer": False,
                "special_cases": {
                    "inheritance": {
                        "death_date": s["death_date"],
                        "selling_inherited_house": False,
                        "inherited_acquisition_date": s["death_date"],
                    }
                },
            },
            expected_verdict=s["expected"],
            boundary_type="special_case",
            tags=s["tags"],
        )


def generate_gift_rollover_cases(
    transfer_date: date = date(2026, 4, 1),
) -> Iterator[SyntheticCase]:
    """배우자/직계존비속 증여 이월과세 — 소득세법 §97의2."""
    try:
        from src.domain.tax_constants import TaxConstantsRegistry
        iota_years = TaxConstantsRegistry.get("IOTA_PERIOD_YEARS", transfer_date)
    except Exception:
        iota_years = 10

    scenarios = [
        {
            "desc": f"이월과세 — 증여 후 {iota_years}년 이내 양도 (원취득가액 적용)",
            "gift_date": (transfer_date - timedelta(days=iota_years * 365 - 30)).strftime("%Y%m%d"),
            "expected": None,
            "tags": ["이월과세", f"{iota_years}년이내"],
        },
        {
            "desc": f"이월과세 — 증여 후 {iota_years}년 초과 양도 (증여받은 가액 적용)",
            "gift_date": (transfer_date - timedelta(days=iota_years * 365 + 30)).strftime("%Y%m%d"),
            "expected": None,
            "tags": ["이월과세", f"{iota_years}년초과"],
        },
        {
            "desc": "이월과세 — 직계존속 증여, 시가보다 저가 취득",
            "gift_date": "20150101",
            "expected": None,
            "tags": ["이월과세", "직계존속", "저가증여"],
        },
    ]
    for s in scenarios:
        yield SyntheticCase(
            description=s["desc"],
            fact_json={
                "transfer_date": transfer_date.strftime("%Y%m%d"),
                "acquisition_date": s["gift_date"],
                "property_type": "아파트",
                "acquisition_reason": "증여",
                "household_house_count": 1,
                "transfer_price": 1_000_000_000,
                "acquisition_price": 300_000_000,
                "residence_years": 3.0,
                "is_adjustment_area_at_transfer": False,
                "special_cases": {
                    "gift": {
                        "is_gift_from_spouse_or_lineal": True,
                        "gift_date": s["gift_date"],
                        "donor_acquisition_price": 200_000_000,
                        "donor_acquisition_date": "20100101",
                    }
                },
            },
            expected_verdict=s["expected"],
            boundary_type="special_case",
            tags=s["tags"],
        )


def generate_sangsaeng_rental_cases(
    transfer_date: date = date(2026, 4, 1),
) -> Iterator[SyntheticCase]:
    """상생임대 특례 — 소득세법 §155의3. 2021-12-20~2026-12-31 체결 임대차."""
    scenarios = [
        {
            "desc": "상생임대 — 거주요건 2년 대신 1년6개월로 비과세",
            "contract_date": "20230101",
            "prev_rent": 1_000_000,
            "new_rent": 1_040_000,   # 4% 인상 (5% 이내 충족)
            "expected": "비과세",
            "tags": ["상생임대", "거주요건완화"],
        },
        {
            "desc": "상생임대 — 2021-12-20 이전 계약 (특례 미적용)",
            "contract_date": "20211201",
            "prev_rent": 1_000_000,
            "new_rent": 1_040_000,
            "expected": None,
            "tags": ["상생임대", "기간외계약"],
        },
        {
            "desc": "상생임대 — 임대료 5% 초과 인상 (특례 박탈)",
            "contract_date": "20220601",
            "prev_rent": 1_000_000,
            "new_rent": 1_060_000,   # 6% 인상 → 특례 박탈
            "expected": None,
            "tags": ["상생임대", "임대료초과"],
        },
    ]
    for s in scenarios:
        yield SyntheticCase(
            description=s["desc"],
            fact_json={
                "transfer_date": transfer_date.strftime("%Y%m%d"),
                "acquisition_date": "20200101",
                "property_type": "아파트",
                "acquisition_reason": "매매",
                "household_house_count": 1,
                "transfer_price": 900_000_000,
                "acquisition_price": 500_000_000,
                "residence_years": 1.5,
                "is_adjustment_area_at_transfer": True,
                "is_adjustment_area_at_acquisition": True,
                "special_cases": {
                    "sangsaeng_rental": {
                        "contract_date": s["contract_date"],
                        "contract_period_months": 24,
                        "previous_monthly_rent": s["prev_rent"],
                        "new_monthly_rent": s["new_rent"],
                        "has_prior_contract": True,
                    }
                },
            },
            expected_verdict=s["expected"],
            boundary_type="special_case",
            tags=s["tags"],
        )


def generate_reconstruction_cases(
    transfer_date: date = date(2026, 4, 1),
) -> Iterator[SyntheticCase]:
    """재건축/입주권 — 소득세법 §156의2."""
    # 원조합원: 비조정 + 2년 이상 보유 → §156의2 비과세
    yield SyntheticCase(
        description="원조합원 입주권 양도 — 비조정지역 + 10년 보유 (비과세)",
        fact_json={
            "transfer_date": transfer_date.strftime("%Y%m%d"),
            "acquisition_date": "20150101",
            "property_type": "입주권",
            "acquisition_reason": "재건축",
            "household_house_count": 1,
            "transfer_price": 700_000_000,
            "acquisition_price": 300_000_000,
            "residence_years": 3.0,
            "is_adjustment_area_at_acquisition": False,
            "is_adjustment_area_at_transfer": False,
            "special_cases": {
                "reconstruction": {
                    "management_disposal_date": "20220301",
                    "is_original_member": True,
                }
            },
        },
        expected_verdict="비과세",
        boundary_type="special_case",
        tags=["입주권", "원조합원", "비과세"],
    )

    # 승계조합원: 관리처분 후 입주권 매수, 1년 6개월 보유 → 단기세율 60%
    yield SyntheticCase(
        description="승계조합원 입주권 양도 — 1년6개월 보유 (60% 단기세율)",
        fact_json={
            "transfer_date": transfer_date.strftime("%Y%m%d"),
            "acquisition_date": (transfer_date - timedelta(days=548)).strftime("%Y%m%d"),  # ~1.5년
            "property_type": "입주권",
            "acquisition_reason": "매매",
            "household_house_count": 1,
            "transfer_price": 700_000_000,
            "acquisition_price": 500_000_000,
            "residence_years": 0.0,
            "is_adjustment_area_at_transfer": False,
            "special_cases": {
                "reconstruction": {
                    "management_disposal_date": "20230101",
                    "is_original_member": False,
                }
            },
        },
        expected_verdict="단기세율",
        boundary_type="special_case",
        tags=["입주권", "승계조합원", "단기세율"],
    )

    # 승계조합원: 2년 이상 보유 → 일반과세
    yield SyntheticCase(
        description="승계조합원 입주권 — 3년 보유 (일반과세)",
        fact_json={
            "transfer_date": transfer_date.strftime("%Y%m%d"),
            "acquisition_date": "20230101",
            "property_type": "입주권",
            "acquisition_reason": "매매",
            "household_house_count": 1,
            "transfer_price": 700_000_000,
            "acquisition_price": 400_000_000,
            "residence_years": 0.0,
            "is_adjustment_area_at_transfer": False,
            "special_cases": {
                "reconstruction": {
                    "management_disposal_date": "20220601",
                    "is_original_member": False,
                }
            },
        },
        expected_verdict="일반과세",
        boundary_type="special_case",
        tags=["입주권", "승계조합원", "일반과세"],
    )


def generate_rural_house_cases(
    transfer_date: date = date(2026, 4, 1),
) -> Iterator[SyntheticCase]:
    """농어촌주택 특례 — 소득세법 §155의2."""
    scenarios = [
        {
            "desc": "농어촌주택 보유 — 일반주택 1세대1주택 비과세 인정",
            "expected": "비과세",
            "tags": ["농어촌주택", "비과세유지"],
        },
        {
            "desc": "농어촌주택 본인 취득 후 3년 미경과 — 특례 미적용",
            "expected": "일반과세",
            "tags": ["농어촌주택", "3년미경과"],
        },
    ]
    expected_verdicts = ["비과세", None]  # 3년 미경과 case: RuralHouseInput이 취득일 미전달 → LLM 판단불가
    for s, ev in zip(scenarios, expected_verdicts):
        yield SyntheticCase(
            description=s["desc"],
            fact_json={
                "transfer_date": transfer_date.strftime("%Y%m%d"),
                "acquisition_date": "20170101",
                "property_type": "아파트",
                "acquisition_reason": "매매",
                "household_house_count": 2,
                "transfer_price": 800_000_000,
                "acquisition_price": 400_000_000,
                "residence_years": 3.0,
                "is_adjustment_area_at_transfer": False,
                "special_cases": {
                    # RuralHouseInput은 is_eligible + region만 지원 — 농어촌주택 취득일 전달 불가
                    "rural_house": {"is_eligible": True}
                },
            },
            expected_verdict=ev,
            boundary_type="special_case",
            tags=s["tags"],
        )


def generate_donggo_cases(
    transfer_date: date = date(2026, 4, 1),
) -> Iterator[SyntheticCase]:
    """동거봉양합가 특례 — 소득세법 §155③."""
    scenarios = [
        {
            "desc": "동거봉양합가 — 합가 후 10년 이내 양도 (1주택 간주)",
            "merge_date": "20200101",
            "expected": "비과세",
            "tags": ["동거봉양", "10년이내"],
        },
        {
            "desc": "동거봉양합가 — 합가 후 10년 초과 양도",
            "merge_date": "20130101",
            "expected": "일반과세",
            "tags": ["동거봉양", "10년초과"],
        },
    ]
    for s in scenarios:
        yield SyntheticCase(
            description=s["desc"],
            fact_json={
                "transfer_date": transfer_date.strftime("%Y%m%d"),
                "acquisition_date": "20150101",
                "property_type": "아파트",
                "acquisition_reason": "매매",
                "household_house_count": 2,
                "transfer_price": 900_000_000,
                "acquisition_price": 450_000_000,
                "residence_years": 2.0,
                "is_adjustment_area_at_transfer": False,
                "special_cases": {
                    "cohabitation_care": {
                        "cohabitation_date": s["merge_date"],
                        "parent_age_at_merge": 65,
                    }
                },
            },
            expected_verdict=s["expected"],
            boundary_type="special_case",
            tags=s["tags"],
        )


def generate_non_resident_cases(
    transfer_date: date = date(2026, 4, 1),
) -> Iterator[SyntheticCase]:
    """비거주자 양도 — 소득세법 §118의2, 거주요건 불충족."""
    scenarios = [
        {
            "desc": "비거주자 — 국내 1주택 양도 (비과세 불가)",
            "expected": "일반과세",
            "tags": ["비거주자", "비과세불가"],
        },
        {
            "desc": "비거주자 — 단기보유 국내주택 (단기세율)",
            "acq": "20250101",
            "expected": "단기세율",
            "tags": ["비거주자", "단기"],
        },
    ]
    acqs = ["20180101", "20250101"]
    for s, acq in zip(scenarios, acqs):
        yield SyntheticCase(
            description=s["desc"],
            fact_json={
                "transfer_date": transfer_date.strftime("%Y%m%d"),
                "acquisition_date": acq,
                "property_type": "아파트",
                "acquisition_reason": "매매",
                "household_house_count": 1,
                "transfer_price": 800_000_000,
                "acquisition_price": 500_000_000,
                "residence_years": 0.0,
                "is_adjustment_area_at_transfer": False,
                "is_non_resident": True,
            },
            expected_verdict=s["expected"],
            boundary_type="special_case",
            tags=s["tags"],
        )


def generate_bunyang_right_cases(
    transfer_date: date = date(2026, 4, 1),
) -> Iterator[SyntheticCase]:
    """분양권 양도 — 소득세법 §88, §104."""
    # 분양권 취득일은 transfer_date 기준 상대적으로 계산해야 정확한 보유기간 테스트가 가능
    _acq_lt1y = (transfer_date - timedelta(days=300)).strftime("%Y%m%d")   # 10개월 전 → 1년 미만
    _acq_gt1y = (transfer_date - timedelta(days=500)).strftime("%Y%m%d")   # 16개월 전 → 1년 이상
    scenarios = [
        {
            "desc": "분양권 — 2021-01-01 이후 취득, 1년 미만 보유 (70% 세율)",
            "acq": _acq_lt1y,
            "acq_price": 400_000_000,
            "transfer": 600_000_000,
            "expected": "단기세율",
            "tags": ["분양권", "1년미만", "70%"],
        },
        {
            "desc": "분양권 — 2021-01-01 이후 취득, 1년 이상 보유 (60% 세율)",
            "acq": _acq_gt1y,
            "acq_price": 400_000_000,
            "transfer": 550_000_000,
            "expected": "단기세율",
            "tags": ["분양권", "1년이상", "60%"],
        },
        {
            "desc": "분양권 — 1세대 1분양권 비과세 요건 (완공 후 이전)",
            "acq": "20210601",
            "acq_price": 500_000_000,
            "transfer": 700_000_000,
            "expected": None,
            "tags": ["분양권", "1세대1분양권"],
        },
    ]
    for s in scenarios:
        yield SyntheticCase(
            description=s["desc"],
            fact_json={
                "transfer_date": transfer_date.strftime("%Y%m%d"),
                "acquisition_date": s["acq"],
                "property_type": "분양권",
                "acquisition_reason": "매매",
                "household_house_count": 1,
                "transfer_price": s["transfer"],
                "acquisition_price": s["acq_price"],
                "residence_years": 0.0,
                "is_adjustment_area_at_transfer": False,
            },
            expected_verdict=s["expected"],
            boundary_type="special_case",
            tags=s["tags"],
        )


def generate_heavy_tax_cases(
    transfer_date: date = date(2026, 5, 20),
) -> Iterator[SyntheticCase]:
    """다주택 중과세 — 소득세법 §104.
    2026-05-09 이후: 중과 부활 (조정대상지역 2주택 +20%p, 3주택 +30%p).
    TaxConstantsRegistry['HEAVY_TAX_SUSPENSION_END'] 연동.
    """
    suspension_end = _get_heavy_tax_suspension_end(transfer_date)
    after_suspension = transfer_date > suspension_end

    scenarios = [
        {
            "desc": f"{'[중과부활]' if after_suspension else '[중과배제중]'} 조정지역 2주택 양도",
            "count": 2,
            "is_adj": True,
            "expected": "중과" if after_suspension else "일반과세",
            "tags": ["중과", "2주택", "조정대상지역"],
        },
        {
            "desc": f"{'[중과부활]' if after_suspension else '[중과배제중]'} 조정지역 3주택 양도",
            "count": 3,
            "is_adj": True,
            "expected": "중과" if after_suspension else "일반과세",
            "tags": ["중과", "3주택", "조정대상지역"],
        },
        {
            "desc": "비조정지역 2주택 — 기본세율 (중과 비해당)",
            "count": 2,
            "is_adj": False,
            "expected": "일반과세",
            "tags": ["중과", "2주택", "비조정지역"],
        },
        {
            "desc": "조정지역 2주택 — 장기보유특별공제 배제 여부",
            "count": 2,
            "is_adj": True,
            "expected": "중과" if after_suspension else "일반과세",
            "tags": ["중과", "장기보유공제배제"],
        },
    ]
    for s in scenarios:
        yield SyntheticCase(
            description=s["desc"],
            fact_json={
                "transfer_date": transfer_date.strftime("%Y%m%d"),
                "acquisition_date": "20170101",
                "property_type": "아파트",
                "acquisition_reason": "매매",
                "household_house_count": s["count"],
                "transfer_price": 1_200_000_000,
                "acquisition_price": 700_000_000,
                "residence_years": 1.0,
                "is_adjustment_area_at_transfer": s["is_adj"],
                "is_adjustment_area_at_acquisition": s["is_adj"],
            },
            expected_verdict=s["expected"],
            boundary_type="heavy_tax",
            tags=s["tags"],
            registry_deps=["HEAVY_TAX_SUSPENSION_END"],
        )


def generate_short_term_cases(
    transfer_date: date = date(2026, 4, 1),
) -> Iterator[SyntheticCase]:
    """단기세율 — 소득세법 §104. 1년미만 70%, 1~2년 60%."""
    scenarios = [
        {
            "desc": "1년 미만 보유 아파트 양도 (70% 세율)",
            "acq": (transfer_date - timedelta(days=300)).strftime("%Y%m%d"),
            "expected": "단기세율",
            "tags": ["단기세율", "1년미만", "70%"],
        },
        {
            "desc": "1년 ~ 2년 보유 아파트 양도 (60% 세율)",
            "acq": (transfer_date - timedelta(days=500)).strftime("%Y%m%d"),
            "expected": "단기세율",
            "tags": ["단기세율", "1~2년", "60%"],
        },
        {
            "desc": "정확히 1년 보유 경계 (365일)",
            "acq": (transfer_date - timedelta(days=365)).strftime("%Y%m%d"),
            "expected": "단기세율",
            "tags": ["단기세율", "365일경계"],
        },
        {
            "desc": "정확히 2년 보유 경계 (730일) — 단기세율 탈출",
            "acq": (transfer_date - timedelta(days=730)).strftime("%Y%m%d"),
            "expected": "비과세",   # 1주택 비조정 2년 보유 → 비과세 (거주요건 불필요)
            "tags": ["단기세율", "730일경계"],
        },
    ]
    for s in scenarios:
        yield SyntheticCase(
            description=s["desc"],
            fact_json={
                "transfer_date": transfer_date.strftime("%Y%m%d"),
                "acquisition_date": s["acq"],
                "property_type": "아파트",
                "acquisition_reason": "매매",
                "household_house_count": 1,
                "transfer_price": 700_000_000,
                "acquisition_price": 500_000_000,
                "residence_years": 0.0,
                "is_adjustment_area_at_transfer": False,
            },
            expected_verdict=s["expected"],
            boundary_type="short_term",
            tags=s["tags"],
        )


def generate_l2_block_cases() -> Iterator[SyntheticCase]:
    """L2 차단 검증 케이스 — 크리티컬 필드 누락 시 사실관계부족 반환."""
    scenarios = [
        {
            "desc": "transfer_price 누락 → L2 차단",
            "fact": {
                "transfer_date": "20260401",
                "acquisition_date": "20180101",
                "property_type": "아파트",
                "acquisition_reason": "매매",
                "household_house_count": 1,
                "acquisition_price": 500_000_000,
                "residence_years": 3.0,
                "is_adjustment_area_at_transfer": False,
            },
            "tags": ["L2차단", "transfer_price누락"],
        },
        {
            # acquisition_date는 transfer_date 기준 5년 이내여야 이월과세 iota 체크가 발동함
            # 5년 초과 시 L2가 "years_elapsed < iota_period_years" 조건 불충족으로 차단 안 함
            "desc": "배우자증여 + original_acquisition_price 누락 → L2 차단",
            "fact": {
                "transfer_date": "20260401",
                "acquisition_date": "20230101",   # 증여일 = 취득일 = 3.25년 전 (5년 이내)
                "property_type": "아파트",
                "acquisition_reason": "증여",
                "household_house_count": 1,
                "transfer_price": 900_000_000,
                "acquisition_price": 600_000_000,
                "residence_years": 2.0,
                "is_adjustment_area_at_transfer": False,
                "special_cases": {
                    # donor_acquisition_price 미제공 → original_donor_acquisition_price=0 → L2 차단
                    "gift": {"is_gift_from_spouse_or_lineal": True}
                },
            },
            "tags": ["L2차단", "이월과세누락"],
        },
        {
            "desc": "상속주택 death_date 누락 → L2 차단",
            "fact": {
                "transfer_date": "20260401",
                "acquisition_date": "20180101",
                "property_type": "아파트",
                "acquisition_reason": "상속",
                "household_house_count": 2,
                "transfer_price": 800_000_000,
                "acquisition_price": 400_000_000,
                "residence_years": 0.0,
                "is_adjustment_area_at_transfer": False,
            },
            "tags": ["L2차단", "death_date누락"],
        },
        {
            # TempTwoHouseInput은 new_acquisition_date를 필수로 요구하므로
            # FactInput을 통해 "신규취득일 누락" L2 차단을 재현할 수 없음.
            # 대신 is_gift_from_spouse_or_lineal=None인 증여 취득 → L2 차단 테스트로 대체
            "desc": "증여 취득 + is_gift_from_spouse_or_lineal 미확인 → L2 차단",
            "fact": {
                "transfer_date": "20260401",
                "acquisition_date": "20230601",
                "property_type": "아파트",
                "acquisition_reason": "증여",
                "household_house_count": 1,
                "transfer_price": 700_000_000,
                "acquisition_price": 500_000_000,
                "residence_years": 1.5,
                "is_adjustment_area_at_transfer": False,
                # special_cases.gift 미제공 → rollover_taxation.is_gift_from_spouse_or_lineal=None → L2 차단
            },
            "tags": ["L2차단", "이월과세_배우자여부미확인"],
        },
    ]
    for s in scenarios:
        yield SyntheticCase(
            description=s["desc"],
            fact_json=s["fact"],
            expected_verdict="사실관계부족",
            boundary_type="l2_block",
            tags=s["tags"],
        )


def generate_high_value_exempt_cases(
    transfer_date: date = date(2026, 4, 1),
) -> Iterator[SyntheticCase]:
    """고가주택 + 1세대1주택 복합 케이스."""
    try:
        from src.domain.tax_constants import TaxConstantsRegistry
        threshold = TaxConstantsRegistry.get("HIGH_VALUE_THRESHOLD", transfer_date)
    except Exception:
        threshold = 1_200_000_000

    suspension_end = _get_heavy_tax_suspension_end(transfer_date)
    label = f"{threshold // 100_000_000}억"
    scenarios = [
        {
            "desc": f"고가주택 1세대1주택 — {label} 이상 (초과분만 과세)",
            "price": threshold + 500_000_000,
            "expected": "고가주택",
            "tags": ["고가주택", "1세대1주택"],
        },
        {
            "desc": f"고가주택 — {label} 정확히 (비과세 한도)",
            "price": threshold,
            "expected": "비과세",
            "tags": ["고가주택", "한도정확"],
        },
        {
            "desc": f"고가주택 — 다주택 중과 + {label} 초과",
            "price": threshold + 300_000_000,
            "expected": "중과" if transfer_date > suspension_end else "고가주택",
            "tags": ["고가주택", "다주택중과"],
        },
    ]
    for s in scenarios:
        is_multi_house = "다주택" in s["desc"]
        yield SyntheticCase(
            description=s["desc"],
            fact_json={
                "transfer_date": transfer_date.strftime("%Y%m%d"),
                "acquisition_date": "20150101",
                "property_type": "아파트",
                "acquisition_reason": "매매",
                "household_house_count": 2 if is_multi_house else 1,
                "transfer_price": s["price"],
                "acquisition_price": 600_000_000,
                "residence_years": 3.0,
                # 다주택 중과는 조정대상지역이어야 +20% 적용
                "is_adjustment_area_at_transfer": is_multi_house,
            },
            expected_verdict=s["expected"],
            boundary_type="price_boundary",
            tags=s["tags"],
        )


def generate_long_term_deduction_cases(
    transfer_date: date = date(2026, 4, 1),
) -> Iterator[SyntheticCase]:
    """장기보유특별공제율 구간별 케이스 — 소득세법 §95, 별표1/별표2."""
    # 보유기간: 3/4/5/6/7/8/9/10년 + 거주 병행
    holding_years = [3, 4, 5, 6, 7, 8, 9, 10]
    for yr in holding_years:
        acq = date(transfer_date.year - yr, transfer_date.month, transfer_date.day)
        yield SyntheticCase(
            description=f"장기보유특별공제 — 보유{yr}년 거주{min(yr,2)}년 (1세대1주택)",
            fact_json={
                "transfer_date": transfer_date.strftime("%Y%m%d"),
                "acquisition_date": acq.strftime("%Y%m%d"),
                "property_type": "아파트",
                "acquisition_reason": "매매",
                "household_house_count": 1,
                "transfer_price": 1_500_000_000,
                "acquisition_price": 600_000_000,
                "residence_years": float(min(yr, 2)),
                "is_adjustment_area_at_transfer": False,
            },
            expected_verdict="고가주택",
            boundary_type="long_term_deduction",
            tags=["장기보유특별공제", f"보유{yr}년"],
        )

    # 1세대1주택 + 거주요건 미충족 케이스
    yield SyntheticCase(
        description="장기보유특별공제 — 보유10년 거주0년 (표2 아닌 표1 적용)",
        fact_json={
            "transfer_date": transfer_date.strftime("%Y%m%d"),
            "acquisition_date": date(transfer_date.year - 10, transfer_date.month, transfer_date.day).strftime("%Y%m%d"),
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 1,
            "transfer_price": 1_500_000_000,
            "acquisition_price": 600_000_000,
            "residence_years": 0.0,
            "is_adjustment_area_at_transfer": False,
        },
        expected_verdict="고가주택",
        boundary_type="long_term_deduction",
        tags=["장기보유특별공제", "거주0년", "표1"],
    )


def generate_special_tax_reduction_cases(
    transfer_date: date = date(2026, 4, 1),
) -> Iterator[SyntheticCase]:
    """조특법 감면 케이스 — 조세특례제한법."""
    # 자경농지 감면 §69 — FactInput에 자경 기간 필드 없음 → expected_verdict=None (판단 불가)
    yield SyntheticCase(
        description="8년 자경농지 양도소득세 감면 (§69)",
        fact_json={
            "transfer_date": transfer_date.strftime("%Y%m%d"),
            "acquisition_date": "20160101",
            "property_type": "토지",
            "acquisition_reason": "매매",
            "household_house_count": 1,
            "transfer_price": 800_000_000,
            "acquisition_price": 400_000_000,
            "residence_years": 0.0,
            "is_adjustment_area_at_transfer": False,
        },
        expected_verdict=None,   # FactInput에 자경 여부·기간 필드 없어 감면 판단 불가
        boundary_type="special_tax_reduction",
        tags=["조특법", "자경농지", "8년감면"],
    )

    # 장기임대주택 감면 §97의3
    # 2주택(거주주택 + 임대주택) 보유자가 임대주택 양도 → §89 1주택 비과세 불가, §97의3 감면
    yield SyntheticCase(
        description="장기임대주택 양도세 감면 — 10년 이상 임대 (§97의3)",
        fact_json={
            "transfer_date": transfer_date.strftime("%Y%m%d"),
            "acquisition_date": "20130101",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 2,   # 거주주택 + 임대주택 → §89 비과세 불가
            "transfer_price": 800_000_000,
            "acquisition_price": 400_000_000,
            "residence_years": 0.0,
            "is_adjustment_area_at_transfer": False,
            "special_cases": {
                "long_term_rental": {
                    "registration_date": "20130601",
                    "mandatory_period_years": 10,
                    "mandatory_period_fulfilled": True,
                    "rent_increase_limit_complied": True,
                }
            },
        },
        expected_verdict="감면",
        boundary_type="special_tax_reduction",
        tags=["조특법", "장기임대주택"],
    )

    # 미분양주택 감면 §98의2 — FactInput에 미분양 지위 필드 없음 → expected_verdict=None
    yield SyntheticCase(
        description="미분양주택 취득 감면 (§98의2) — 5년 이내 양도",
        fact_json={
            "transfer_date": transfer_date.strftime("%Y%m%d"),
            "acquisition_date": "20210101",
            "property_type": "아파트",
            "acquisition_reason": "분양",
            "household_house_count": 1,
            "transfer_price": 800_000_000,
            "acquisition_price": 400_000_000,
            "residence_years": 0.0,
            "is_adjustment_area_at_acquisition": True,
            "is_adjustment_area_at_transfer": False,
        },
        expected_verdict=None,   # 미분양 지위를 FactInput으로 전달할 방법 없음
        boundary_type="special_tax_reduction",
        tags=["조특법", "미분양주택"],
    )

    # 신축주택 감면 §99의3 — FactInput에 신축주택 여부 필드 없음 → expected_verdict=None
    yield SyntheticCase(
        description="신축주택 취득 감면 (§99의3) — 요건 충족",
        fact_json={
            "transfer_date": transfer_date.strftime("%Y%m%d"),
            "acquisition_date": "20220601",
            "property_type": "아파트",
            "acquisition_reason": "분양",
            "household_house_count": 1,
            "transfer_price": 800_000_000,
            "acquisition_price": 400_000_000,
            "residence_years": 0.0,
            "is_adjustment_area_at_acquisition": True,
            "is_adjustment_area_at_transfer": False,
        },
        expected_verdict=None,   # 신축주택 여부를 FactInput으로 전달할 방법 없음
        boundary_type="special_tax_reduction",
        tags=["조특법", "신축주택"],
    )

    # 공익수용 감면 §77
    # 조정지역 취득 + 거주 0년 → §89 비과세 거주요건 미충족, §77 채권보상 감면(30%) 적용
    yield SyntheticCase(
        description="공익사업 수용 감면 (§77) — 채권보상",
        fact_json={
            "transfer_date": transfer_date.strftime("%Y%m%d"),
            "acquisition_date": "20180101",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 1,
            "transfer_price": 800_000_000,
            "acquisition_price": 400_000_000,
            "residence_years": 0.0,
            "is_adjustment_area_at_acquisition": True,  # 조정지역 취득 → 거주 2년 필요
            "is_adjustment_area_at_transfer": False,
            "special_cases": {
                "expropriation": {
                    "compensation_type": "채권",
                    "is_main_residence": False,
                }
            },
        },
        expected_verdict="감면",
        boundary_type="special_tax_reduction",
        tags=["조특법", "공익수용"],
    )


def generate_combination_cases(
    transfer_date: date = date(2026, 4, 1),
) -> Iterator[SyntheticCase]:
    """복합 특례 케이스 — 2개 이상 특례가 동시에 적용되는 경계 케이스."""
    # 일시적2주택 + 고가주택
    try:
        from src.domain.tax_constants import TaxConstantsRegistry
        threshold = TaxConstantsRegistry.get("HIGH_VALUE_THRESHOLD", transfer_date)
    except Exception:
        threshold = 1_200_000_000

    yield SyntheticCase(
        description="일시적2주택 + 고가주택 — 12억 초과, 3년 이내 양도",
        fact_json={
            "transfer_date": transfer_date.strftime("%Y%m%d"),
            "acquisition_date": "20180101",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 2,
            "transfer_price": threshold + 500_000_000,
            "acquisition_price": 600_000_000,
            "residence_years": 3.0,
            "is_adjustment_area_at_transfer": False,
            "special_cases": {
                "temp_two_house": {
                    "new_acquisition_date": "20240101",
                    "old_house_must_sell_by": "20270101",
                    "new_is_adjustment_area": False,
                }
            },
        },
        expected_verdict="고가주택",
        boundary_type="combination",
        tags=["일시적2주택", "고가주택"],
    )

    # 상속주택 + 이월과세
    yield SyntheticCase(
        description="상속주택 보유 + 일반주택 배우자증여 후 이월과세 쟁점",
        fact_json={
            "transfer_date": transfer_date.strftime("%Y%m%d"),
            "acquisition_date": "20200101",
            "property_type": "아파트",
            "acquisition_reason": "증여",
            "household_house_count": 2,
            "transfer_price": 900_000_000,
            "acquisition_price": 500_000_000,
            "residence_years": 2.0,
            "is_adjustment_area_at_transfer": False,
            "special_cases": {
                "gift": {
                    "is_gift_from_spouse_or_lineal": True,
                    "gift_date": "20200101",
                    "donor_acquisition_price": 300_000_000,
                    "donor_acquisition_date": "20100101",
                },
                "inheritance": {
                    "death_date": "20220601",
                    "selling_inherited_house": False,
                },
            },
        },
        expected_verdict=None,
        boundary_type="combination",
        tags=["이월과세", "상속주택", "복합"],
    )

    # 동거봉양 + 일시적2주택
    yield SyntheticCase(
        description="동거봉양합가 + 신규주택 취득으로 3주택 → 1주택 간주 여부",
        fact_json={
            "transfer_date": transfer_date.strftime("%Y%m%d"),
            "acquisition_date": "20150101",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 3,
            "transfer_price": 900_000_000,
            "acquisition_price": 450_000_000,
            "residence_years": 2.0,
            "is_adjustment_area_at_transfer": False,
            "special_cases": {
                "cohabitation_care": {
                    "cohabitation_date": "20200101",
                    "parent_age_at_merge": 70,
                },
                "temp_two_house": {
                    "new_acquisition_date": "20241001",
                    "old_house_must_sell_by": "20271001",
                    "new_is_adjustment_area": False,
                },
            },
        },
        expected_verdict=None,
        boundary_type="combination",
        tags=["동거봉양", "일시적2주택", "3주택"],
    )

    # 비거주자 + 중과
    yield SyntheticCase(
        description="비거주자 + 조정지역 2주택 — 중과 여부",
        fact_json={
            "transfer_date": transfer_date.strftime("%Y%m%d"),
            "acquisition_date": "20180101",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 2,
            "transfer_price": 1_000_000_000,
            "acquisition_price": 600_000_000,
            "residence_years": 0.0,
            "is_adjustment_area_at_transfer": True,
            "is_non_resident": True,
        },
        expected_verdict="중과" if transfer_date > _get_heavy_tax_suspension_end(transfer_date) else "일반과세",
        boundary_type="combination",
        tags=["비거주자", "중과", "조정대상지역"],
    )

    # 분양권 보유 중 기존주택 양도 — 일시적2주택 특례 (기한 내)
    yield SyntheticCase(
        description="분양권 보유 + 기존주택 양도 (일시적2주택 특례 적용 여부)",
        fact_json={
            "transfer_date": transfer_date.strftime("%Y%m%d"),
            "acquisition_date": "20170101",
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": 2,
            "transfer_price": 900_000_000,
            "acquisition_price": 500_000_000,
            "residence_years": 3.0,
            "is_adjustment_area_at_transfer": False,
            "special_cases": {
                "temp_two_house": {
                    "new_acquisition_date": "20230101",
                    "old_house_must_sell_by": "20261201",  # transfer_date(20260401) 이후 → 기한 내
                    "new_is_adjustment_area": False,
                }
            },
        },
        expected_verdict="비과세",
        boundary_type="combination",
        tags=["분양권", "일시적2주택"],
    )


def generate_related_party_cases(
    transfer_date: date = date(2026, 4, 1),
) -> Iterator[SyntheticCase]:
    """특수관계자 거래 — 소득세법 §101 부당행위계산부인."""
    scenarios = [
        {
            "desc": "특수관계자 저가양도 — 시가의 70% 이하 (부당행위 추정)",
            "transfer_price": 500_000_000,
            "market_price": 900_000_000,
            "expected": None,
            "tags": ["특수관계자", "저가양도", "부당행위"],
        },
        {
            "desc": "특수관계자 고가양수 → 양도자 입장 (부당행위 비해당)",
            "transfer_price": 1_000_000_000,
            "market_price": 900_000_000,
            "expected": None,
            "tags": ["특수관계자", "고가양수"],
        },
        {
            "desc": "특수관계자 거래 + 1세대1주택 — 비과세 배제 여부",
            "transfer_price": 700_000_000,
            "market_price": 1_100_000_000,
            "expected": None,
            "tags": ["특수관계자", "비과세", "§101"],
        },
    ]
    for s in scenarios:
        yield SyntheticCase(
            description=s["desc"],
            fact_json={
                "transfer_date": transfer_date.strftime("%Y%m%d"),
                "acquisition_date": "20180101",
                "property_type": "아파트",
                "acquisition_reason": "매매",
                "household_house_count": 1,
                "transfer_price": s["transfer_price"],
                "acquisition_price": 400_000_000,
                "residence_years": 3.0,
                "is_adjustment_area_at_transfer": False,
                "is_related_party_transaction": True,
                "market_price": s["market_price"],
            },
            expected_verdict=s["expected"],
            boundary_type="related_party",
            tags=s["tags"],
        )


def generate_adjustment_area_boundary_cases(
    transfer_date: date = date(2026, 4, 1),
) -> Iterator[SyntheticCase]:
    """조정대상지역 지정/해제 경계 케이스."""
    scenarios = [
        {
            "desc": "조정지역 취득 + 조정지역 양도 — 거주요건 2년 필요",
            "acq_adj": True, "trf_adj": True,
            "residence": 2.0,
            "expected": "비과세",
            "tags": ["조정대상지역", "거주2년충족"],
        },
        {
            "desc": "조정지역 취득 + 조정지역 양도 — 거주요건 1년 미달",
            "acq_adj": True, "trf_adj": True,
            "residence": 1.0,
            "expected": "일반과세",
            "tags": ["조정대상지역", "거주요건미달"],
        },
        {
            "desc": "비조정지역 취득 + 이후 조정지역 편입 — 거주요건 불요",
            "acq_adj": False, "trf_adj": True,
            "residence": 0.0,
            "expected": "비과세",
            "tags": ["조정대상지역", "취득시비조정"],
        },
        {
            "desc": "조정지역 취득 + 이후 해제 후 양도 — 거주요건",
            "acq_adj": True, "trf_adj": False,
            "residence": 0.5,
            "expected": None,
            "tags": ["조정대상지역", "해제후양도"],
        },
    ]
    for s in scenarios:
        yield SyntheticCase(
            description=s["desc"],
            fact_json={
                "transfer_date": transfer_date.strftime("%Y%m%d"),
                "acquisition_date": "20190101",
                "property_type": "아파트",
                "acquisition_reason": "매매",
                "household_house_count": 1,
                "transfer_price": 900_000_000,
                "acquisition_price": 500_000_000,
                "residence_years": s["residence"],
                "is_adjustment_area_at_transfer": s["trf_adj"],
                "is_adjustment_area_at_acquisition": s["acq_adj"],
            },
            expected_verdict=s["expected"],
            boundary_type="adjustment_area",
            tags=s["tags"],
        )


def generate_one_house_exempt_variations(
    transfer_date: date = date(2026, 4, 1),
) -> Iterator[SyntheticCase]:
    """1세대1주택 비과세 — §89 다양한 변형 케이스."""
    scenarios = [
        {
            "desc": "1주택 — 보유2년+거주2년 충족, 비조정지역 (비과세)",
            "count": 1, "adj_acq": False, "adj_trf": False, "residence": 2.5,
            "acq": "20210101", "price": 900_000_000, "expected": "비과세",
            "tags": ["1세대1주택", "비조정", "비과세"],
        },
        {
            "desc": "1주택 — 거주요건 충족 + 12억 이하 (비과세)",
            "count": 1, "adj_acq": True, "adj_trf": True, "residence": 2.1,
            "acq": "20190101", "price": 1_100_000_000, "expected": "비과세",
            "tags": ["1세대1주택", "12억이하"],
        },
        {
            "desc": "1주택 — 보유2년 미달 (비과세 불가)",
            "count": 1, "adj_acq": False, "adj_trf": False, "residence": 0.5,
            "acq": (transfer_date - timedelta(days=700)).strftime("%Y%m%d"), "price": 900_000_000, "expected": "단기세율",  # 700일=1.92년 → 60%
            "tags": ["1세대1주택", "보유2년미달"],
        },
        {
            "desc": "1주택 — 직전 1년 거주 + 해외출국 (§154④ 특례)",
            "count": 1, "adj_acq": True, "adj_trf": True, "residence": 1.2,
            "acq": "20180101", "price": 900_000_000, "expected": None,
            "tags": ["1세대1주택", "해외출국특례"],
        },
        {
            "desc": "1주택 — 미등기 전매 (70% 세율, 비과세 배제)",
            "count": 1, "adj_acq": False, "adj_trf": False, "residence": 3.0,
            "acq": "20200101", "price": 700_000_000, "expected": None,  # 미등기 플래그 없어 자동판단 불가
            "tags": ["미등기전매"],
        },
        {
            "desc": "1주택 + 상가 동시 보유 — 주택 비과세 여부",
            "count": 1, "adj_acq": False, "adj_trf": False, "residence": 2.0,
            "acq": "20190101", "price": 800_000_000, "expected": "비과세",
            "tags": ["1세대1주택", "상가겸용"],
        },
    ]
    for s in scenarios:
        acq = s.get("acq", "20190101") if isinstance(s.get("acq"), str) else s["acq"]
        yield SyntheticCase(
            description=s["desc"],
            fact_json={
                "transfer_date": transfer_date.strftime("%Y%m%d"),
                "acquisition_date": acq,
                "property_type": "아파트",
                "acquisition_reason": "매매",
                "household_house_count": s["count"],
                "transfer_price": s["price"],
                "acquisition_price": 500_000_000,
                "residence_years": s["residence"],
                "is_adjustment_area_at_transfer": s["adj_trf"],
                "is_adjustment_area_at_acquisition": s["adj_acq"],
            },
            expected_verdict=s["expected"],
            boundary_type="one_house_exempt",
            tags=s["tags"],
        )


def generate_general_tax_baseline_cases(
    transfer_date: date = date(2026, 4, 1),
) -> Iterator[SyntheticCase]:
    """일반과세 기준 케이스 — 특례 없는 단순 양도."""
    scenarios = [
        {
            "desc": "2주택 비조정지역 — 일반세율 적용",
            "count": 2, "adj": False, "acq": "20180101", "price": 1_000_000_000,
            "expected": "일반과세", "tags": ["일반과세", "2주택", "비조정"],
        },
        {
            "desc": "1주택 보유2년 미달 (730일 미만) + 비조정 — 단기세율",
            "count": 1, "adj": False,
            "acq": (transfer_date - timedelta(days=700)).strftime("%Y%m%d"),
            "price": 700_000_000,
            "expected": "단기세율", "tags": ["단기세율", "2년미달"],  # 700일=1.92년 → 60%
        },
        {
            "desc": "1주택 — 조정지역 거주요건 미충족 (일반과세)",
            "count": 1, "adj": True, "acq": "20200101", "price": 800_000_000,
            "expected": "일반과세", "tags": ["일반과세", "조정", "거주미달"],
            "adj_acq": True,  # 취득 시도 조정지역 → 거주 2년 필요
        },
        {
            "desc": "토지(나대지) 5년 이상 보유 — 일반과세",
            "count": 0, "adj": False, "acq": "20170101", "price": 600_000_000,
            "expected": "일반과세", "tags": ["일반과세", "토지"],
        },
        {
            "desc": "상가 양도 — 일반과세 (비과세 불가)",
            "count": 0, "adj": False, "acq": "20160101", "price": 900_000_000,
            "expected": "일반과세", "tags": ["일반과세", "상가"],
        },
    ]
    for s in scenarios:
        acq = s["acq"] if isinstance(s["acq"], str) else s["acq"]
        yield SyntheticCase(
            description=s["desc"],
            fact_json={
                "transfer_date": transfer_date.strftime("%Y%m%d"),
                "acquisition_date": acq,
                "property_type": "아파트" if s["count"] > 0 else ("토지" if "토지" in s["desc"] else "상가"),
                "acquisition_reason": "매매",
                "household_house_count": s["count"],
                "transfer_price": s["price"],
                "acquisition_price": 400_000_000,
                "residence_years": 0.0,
                "is_adjustment_area_at_acquisition": s.get("adj_acq", s["adj"]),
                "is_adjustment_area_at_transfer": s["adj"],
            },
            expected_verdict=s["expected"],
            boundary_type="general_tax",
            tags=s["tags"],
        )


def generate_additional_l2_block_cases() -> Iterator[SyntheticCase]:
    """추가 L2 차단 케이스."""
    scenarios = [
        {
            "desc": "전체 필드 누락 — fact_json 비어있음",
            "fact": {},
            "tags": ["L2차단", "전체누락"],
        },
        {
            "desc": "transfer_date 없음 — 날짜 기준 판단 불가",
            "fact": {
                "property_type": "아파트",
                "household_house_count": 1,
                "transfer_price": 900_000_000,
                "acquisition_price": 500_000_000,
            },
            "tags": ["L2차단", "transfer_date누락"],
        },
        {
            "desc": "household_house_count 없음 — 다주택 여부 판단 불가",
            "fact": {
                "transfer_date": "20260401",
                "acquisition_date": "20180101",
                "property_type": "아파트",
                "transfer_price": 900_000_000,
                "acquisition_price": 500_000_000,
                "residence_years": 2.0,
                "is_adjustment_area_at_transfer": False,
            },
            "tags": ["L2차단", "household_house_count누락"],
        },
    ]
    for s in scenarios:
        yield SyntheticCase(
            description=s["desc"],
            fact_json=s["fact"],
            expected_verdict="사실관계부족",
            boundary_type="l2_block",
            tags=s["tags"],
        )


def generate_all_boundary_cases(n_per_type: int = 10) -> List[SyntheticCase]:
    """전체 경계 케이스 생성 (기존 호환용)."""
    cases: List[SyntheticCase] = []
    today = date(2025, 6, 1)

    cases.extend(list(generate_date_boundary_cases(today, date(2018, 1, 1)))[:n_per_type])
    cases.extend(list(generate_price_boundary_cases(today))[:n_per_type])
    cases.extend(list(generate_house_count_cases(today))[:n_per_type])

    return cases


def generate_all_comprehensive_cases(as_of: Optional[date] = None) -> List[SyntheticCase]:
    """
    현행법 기준 종합 케이스 생성 (~130건).

    카테고리:
    - 기본 보유기간 경계 (6)
    - 금액 경계 (4)
    - 주택 수 경계 (3)
    - 고가주택 복합 (3)
    - 일시적2주택 (4)
    - 상속주택 (3)
    - 이월과세 (3)
    - 상생임대 (3)
    - 재건축/입주권 (3)
    - 농어촌주택 (2)
    - 동거봉양합가 (2)
    - 비거주자 (2)
    - 분양권 (3)
    - 중과세 (4)
    - 단기세율 (4)
    - L2 차단 (4)
    - 장기보유특별공제 구간 (9)
    - 조특법 감면 (5)
    - 복합 특례 (5)
    - 특수관계자 거래 (3)
    - 조정대상지역 경계 (4)
    합계: ~약 90-130건
    """
    today = as_of or date.today()
    cases: List[SyntheticCase] = []

    cases.extend(generate_date_boundary_cases(today, date(2018, 1, 1)))
    cases.extend(generate_price_boundary_cases(today))
    cases.extend(generate_house_count_cases(today))
    cases.extend(generate_high_value_exempt_cases(today))
    cases.extend(generate_temp_two_house_cases(today))
    cases.extend(generate_inheritance_cases(today))
    cases.extend(generate_gift_rollover_cases(today))
    cases.extend(generate_sangsaeng_rental_cases(today))
    cases.extend(generate_reconstruction_cases(today))
    cases.extend(generate_rural_house_cases(today))
    cases.extend(generate_donggo_cases(today))
    cases.extend(generate_non_resident_cases(today))
    cases.extend(generate_bunyang_right_cases(today))
    cases.extend(generate_heavy_tax_cases(today))
    cases.extend(generate_short_term_cases(today))
    cases.extend(generate_l2_block_cases())
    cases.extend(generate_long_term_deduction_cases(today))
    cases.extend(generate_special_tax_reduction_cases(today))
    cases.extend(generate_combination_cases(today))
    cases.extend(generate_related_party_cases(today))
    cases.extend(generate_adjustment_area_boundary_cases(today))
    cases.extend(generate_one_house_exempt_variations(today))
    cases.extend(generate_general_tax_baseline_cases(today))
    cases.extend(generate_additional_l2_block_cases())

    return cases


def save_cases(cases: List[SyntheticCase], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = [asdict(c) for c in cases]
    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--comprehensive", action="store_true", help="전체 종합 케이스 생성")
    parser.add_argument("--output", default="data/golden/synthetic_cases.json")
    args = parser.parse_args()

    if args.comprehensive:
        cases = generate_all_comprehensive_cases()
        out = Path(args.output).parent / "synthetic_comprehensive.json"
    else:
        cases = generate_all_boundary_cases()
        out = Path(args.output)

    save_cases(cases, out)
    print(f"생성된 케이스: {len(cases)}건 → {out}")
