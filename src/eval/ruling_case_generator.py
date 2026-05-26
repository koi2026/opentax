"""
예규·해석 기반 합성 케이스 생성기 — 세무사급 판단이 필요한 특례 시나리오.

법령 조문만으로 판단이 어렵고 유권해석(질의회신·심판결정례·세법해석례)이
결정적인 케이스를 대상으로 한다.  이 케이스들은:

1. 파이프라인이 오판하기 쉬운 영역 (감면, 복합특례)  →  debate 유발
2. debate 결과로 예규 청크가 positive 샘플로 등록    →  BGE RVRL 학습
3. 골든셋 Recall@K 측정                              →  예규 namespace 검색 품질 추적

카테고리별 케이스 수:
  ① 상생임대      §155의3         6건
  ② 동거봉양합가  §155④           5건
  ③ 농어촌주택    조특§99의4       4건
  ④ 비거주자 심화 §121/§118의2    4건
  ⑤ 분양권 심화   §88/§156의3     5건
  ⑥ 조합원입주권  §156의2         6건
  ⑦ 장기임대 감면 조특§97의3      5건
  ⑧ 공익수용 감면 조특§77         4건
  ⑨ 상속주택 심화 §155②③        6건
  ⑩ 혼인합가      §155③          4건
  합계: 49건
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date, timedelta
from pathlib import Path
from typing import Iterator, List, Optional
import json
import uuid

from src.eval.case_generator import SyntheticCase, _capture_snapshot, _get_heavy_tax_suspension_end


# ── ① 상생임대 (소득세법 시행령 §155의3) ─────────────────────────────────────
def generate_sangsaeng_rental_deep(
    transfer_date: date = date(2026, 5, 1),
) -> Iterator[SyntheticCase]:
    """
    상생임대 특례 심화. 핵심 예규:
    - 사전-2022-법령해석재산-0836 : 묵시적 갱신 인정 여부
    - 기준-2023-법령해석재산-0017 : 조기퇴거 후 재계약
    - 사전-2023-법령해석재산-1231 : 기준시가 요건 (개정 전/후)
    """
    _adj_acq_date = "20200101"   # 조정대상지역 취득 → 거주 2년 필요
    _base_fact = {
        "transfer_date": transfer_date.strftime("%Y%m%d"),
        "acquisition_date": _adj_acq_date,
        "property_type": "아파트",
        "acquisition_reason": "매매",
        "household_house_count": 1,
        "transfer_price": 900_000_000,
        "acquisition_price": 500_000_000,
        "residence_years": 1.5,   # 2년 미달 → 상생임대 특례 없으면 일반과세
        "is_adjustment_area_at_transfer": True,
        "is_adjustment_area_at_acquisition": True,
    }

    cases = [
        {
            "desc": "상생임대 — 5개 요건 모두 충족 (거주요건 면제, 비과세)",
            "contract_date": "20220601",
            "period": 24,
            "prev_rent": 1_000_000,
            "new_rent": 1_040_000,    # 4% 인상 ≤ 5% ✓
            "prior": True,
            "expected": "비과세",
            "tags": ["상생임대", "요건충족", "비과세"],
        },
        {
            "desc": "상생임대 — 임대기간 23개월 (24개월 미달, 특례 불적용)",
            "contract_date": "20220601",
            "period": 23,
            "prev_rent": 1_000_000,
            "new_rent": 1_040_000,
            "prior": True,
            "expected": "일반과세",
            "tags": ["상생임대", "기간미달", "일반과세"],
        },
        {
            "desc": "상생임대 — 임대료 6% 인상 (5% 초과, 특례 박탈)",
            "contract_date": "20220601",
            "period": 24,
            "prev_rent": 1_000_000,
            "new_rent": 1_060_000,    # 6% > 5% ✗
            "prior": True,
            "expected": "일반과세",
            "tags": ["상생임대", "임대료초과", "일반과세"],
        },
        {
            "desc": "상생임대 — 직전 임대차계약 없음 (신규 임차인, 특례 불가)",
            "contract_date": "20221201",
            "period": 24,
            "prev_rent": 0,
            "new_rent": 1_000_000,
            "prior": False,   # 직전 계약 없음 ✗
            "expected": "일반과세",
            "tags": ["상생임대", "직전계약없음", "일반과세"],
        },
        {
            "desc": "상생임대 창문 전 계약 (2021-12-20 이전 체결, 특례 미적용)",
            "contract_date": "20211201",  # 2021-12-19 이전
            "period": 24,
            "prev_rent": 1_000_000,
            "new_rent": 1_040_000,
            "prior": True,
            "expected": "일반과세",
            "tags": ["상생임대", "창문전계약", "일반과세"],
        },
        {
            "desc": "상생임대 + 고가주택 12억 초과 — 거주요건 면제, 고가주택 과세",
            "contract_date": "20220601",
            "period": 24,
            "prev_rent": 1_000_000,
            "new_rent": 1_040_000,
            "prior": True,
            "transfer_price": 1_400_000_000,   # 12억 초과
            "expected": "고가주택",
            "tags": ["상생임대", "고가주택", "복합"],
        },
    ]

    for c in cases:
        fj = dict(_base_fact)
        fj["special_cases"] = {
            "sangsaeng_rental": {
                "contract_date": c["contract_date"],
                "contract_period_months": c["period"],
                "previous_monthly_rent": c["prev_rent"],
                "new_monthly_rent": c["new_rent"],
                "has_prior_contract": c["prior"],
            }
        }
        if "transfer_price" in c:
            fj["transfer_price"] = c["transfer_price"]
        yield SyntheticCase(
            description=c["desc"],
            fact_json=fj,
            expected_verdict=c["expected"],
            boundary_type="ruling_sangsaeng",
            tags=c["tags"],
        )


# ── ② 동거봉양합가 (소득세법 시행령 §155④) ───────────────────────────────────
def generate_cohabitation_deep(
    transfer_date: date = date(2026, 5, 1),
) -> Iterator[SyntheticCase]:
    """
    동거봉양합가 심화. 합가일 기준 10년 경계, 복합 특례.
    핵심 예규: 사전-2021-법령해석재산-0579 (합가 후 주택 추가 취득)
    """
    _suspension_end = _get_heavy_tax_suspension_end(transfer_date)
    _after_suspension = transfer_date > _suspension_end

    scenarios = [
        {
            "desc": "동거봉양합가 — 합가 후 9년 11개월 양도 (10년 이내, 1주택 간주 → 비과세)",
            "merge": "20160601",   # 합가 후 ~9년 11개월 → 10년 이내
            "expected": "비과세",
            "tags": ["동거봉양", "10년이내", "비과세"],
        },
        {
            "desc": "동거봉양합가 — 합가 후 10년 1개월 양도 (10년 초과, 다주택 취급)",
            "merge": "20160201",   # 합가 후 ~10년 3개월 → 10년 초과
            "expected": "중과" if _after_suspension else "일반과세",
            "tags": ["동거봉양", "10년초과", "다주택"],
        },
        {
            "desc": "동거봉양합가 — 합가 당시 부모 60세 이상 요건 충족 후 10년 이내",
            "merge": "20180301",
            "parent_age": 62,
            "expected": "비과세",
            "tags": ["동거봉양", "부모60세", "비과세"],
        },
        {
            "desc": "동거봉양합가 — 부모 중증질환 (연령 미달 대체 요건) 10년 이내",
            "merge": "20190601",
            "parent_age": 55,
            "severe_illness": True,
            "expected": "비과세",
            "tags": ["동거봉양", "중증질환", "비과세"],
        },
        {
            "desc": "동거봉양합가 + 합가 후 신규주택 취득 — 일시적2주택+동거봉양 중첩",
            "merge": "20210601",
            "temp_two_house": True,
            "expected": "비과세",
            "tags": ["동거봉양", "일시적2주택", "복합"],
        },
    ]

    for s in scenarios:
        sc_inner: dict = {
            "cohabitation_care": {
                "cohabitation_date": s["merge"],
                "parent_age_at_merge": s.get("parent_age", 65),
                "parent_has_severe_illness": s.get("severe_illness", False),
            }
        }
        if s.get("temp_two_house"):
            sc_inner["temp_two_house"] = {
                "new_acquisition_date": "20230601",
                "old_house_must_sell_by": "20280601",
                "new_is_adjustment_area": False,
            }
        yield SyntheticCase(
            description=s["desc"],
            fact_json={
                "transfer_date": transfer_date.strftime("%Y%m%d"),
                "acquisition_date": "20150101",
                "property_type": "아파트",
                "acquisition_reason": "매매",
                "household_house_count": 2,
                "transfer_price": 900_000_000,
                "acquisition_price": 500_000_000,
                "residence_years": 3.0,
                "is_adjustment_area_at_transfer": False,
                "special_cases": sc_inner,
            },
            expected_verdict=s["expected"],
            boundary_type="ruling_cohabitation",
            tags=s["tags"],
        )


# ── ③ 농어촌주택 (조세특례제한법 §99의4) ─────────────────────────────────────
def generate_rural_house_deep(
    transfer_date: date = date(2026, 5, 1),
) -> Iterator[SyntheticCase]:
    """
    농어촌주택 특례 심화.
    수도권·조정대상지역 아닌 읍·면 소재 3억 이하 주택은 주택 수에서 제외.
    """
    scenarios = [
        {
            "desc": "농어촌주택 보유 중 일반주택 양도 — 1세대1주택 비과세 유지",
            "expected": "비과세",
            "tags": ["농어촌주택", "1세대1주택유지"],
        },
        {
            "desc": "농어촌주택이 도시지역으로 편입 — 비과세 특례 소멸, 일반과세",
            "expected": "일반과세",
            "tags": ["농어촌주택", "도시편입", "특례소멸"],
        },
        {
            "desc": "농어촌주택 + 일반주택 모두 고가주택 — 조특§99의4 적용 한도 초과",
            "transfer_price": 1_500_000_000,
            "expected": "고가주택",
            "tags": ["농어촌주택", "고가주택"],
        },
        {
            "desc": "수도권 소재 농어촌주택 — 조특§99의4 적용 제외 지역",
            "expected": "일반과세",   # 수도권 소재는 특례 적용 불가
            "rural_eligible": False,
            "tags": ["농어촌주택", "수도권제외"],
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
                "transfer_price": s.get("transfer_price", 900_000_000),
                "acquisition_price": 500_000_000,
                "residence_years": 3.0,
                "is_adjustment_area_at_transfer": False,
                "special_cases": {
                    "rural_house": {
                        "is_eligible": s.get("rural_eligible", True),
                        "region": "강원도 홍천군" if s.get("rural_eligible", True) else "경기도 성남시",
                    }
                },
            },
            expected_verdict=s["expected"],
            boundary_type="ruling_rural",
            tags=s["tags"],
        )


# ── ④ 비거주자 심화 (소득세법 §121, §118의2) ────────────────────────────────
def generate_non_resident_deep(
    transfer_date: date = date(2026, 5, 1),
) -> Iterator[SyntheticCase]:
    """
    비거주자 과세 심화.
    핵심 예규: 비거주자 국내 1주택 비과세 불가, 해외이주 특례.
    """
    _suspension_end = _get_heavy_tax_suspension_end(transfer_date)
    _after_suspension = transfer_date > _suspension_end

    scenarios = [
        {
            "desc": "비거주자 — 국내 1주택 5년 보유, 비과세 불가 (일반과세)",
            "acq": "20210101",
            "residence": 0.0,
            "non_res": True,
            "house_count": 1,
            "adj_trf": False,
            "exemption": None,
            "expected": "일반과세",
            "tags": ["비거주자", "비과세불가"],
        },
        {
            "desc": "비거주자 — 단기보유 (1년 미만, 70% 단기세율)",
            "acq": (transfer_date - timedelta(days=300)).strftime("%Y%m%d"),
            "residence": 0.0,
            "non_res": True,
            "house_count": 1,
            "adj_trf": False,
            "exemption": None,
            "expected": "단기세율",
            "tags": ["비거주자", "단기세율"],
        },
        {
            "desc": "해외이주 출국 — 거주요건 면제 특례 (§154④), 1년 이상 거주 후 출국",
            "acq": "20180101",
            "residence": 1.2,    # 1년 이상 거주 후 출국 → 거주요건 면제
            "non_res": True,
            "house_count": 1,
            "adj_trf": True,
            "exemption": "해외이주",
            "expected": "비과세",
            "tags": ["비거주자", "해외이주", "거주면제"],
        },
        {
            "desc": "비거주자 + 조정대상지역 2주택 — 중과 적용",
            "acq": "20180101",
            "residence": 0.0,
            "non_res": True,
            "house_count": 2,
            "adj_trf": True,
            "exemption": None,
            "expected": "중과" if _after_suspension else "일반과세",
            "tags": ["비거주자", "중과", "조정지역"],
        },
    ]

    for s in scenarios:
        fj: dict = {
            "transfer_date": transfer_date.strftime("%Y%m%d"),
            "acquisition_date": s["acq"],
            "property_type": "아파트",
            "acquisition_reason": "매매",
            "household_house_count": s["house_count"],
            "transfer_price": 800_000_000,
            "acquisition_price": 500_000_000,
            "residence_years": s["residence"],
            "is_adjustment_area_at_transfer": s["adj_trf"],
            "is_non_resident": s["non_res"],
        }
        if s["exemption"]:
            fj["special_cases"] = {"residence_exemption_reason": s["exemption"]}
        yield SyntheticCase(
            description=s["desc"],
            fact_json=fj,
            expected_verdict=s["expected"],
            boundary_type="ruling_non_resident",
            tags=s["tags"],
        )


# ── ⑤ 분양권 심화 (소득세법 §88, §104, §156의3) ────────────────────────────
def generate_bunyang_deep(
    transfer_date: date = date(2026, 5, 1),
) -> Iterator[SyntheticCase]:
    """분양권 양도 심화. 2021년 법 개정 전후 주택 수 포함 여부."""
    _lt1y = (transfer_date - timedelta(days=300)).strftime("%Y%m%d")   # 10개월
    _1to2y = (transfer_date - timedelta(days=500)).strftime("%Y%m%d")  # 16개월
    _gt2y = (transfer_date - timedelta(days=800)).strftime("%Y%m%d")   # 26개월

    scenarios = [
        {
            "desc": "분양권 — 2021년 이후 취득 + 1년 미만 보유 (70% 단기세율)",
            "acq": _lt1y,
            "prop": "분양권",
            "acq_reason": "분양",
            "count": 1,
            "expected": "단기세율",
            "tags": ["분양권", "1년미만", "70%"],
        },
        {
            "desc": "분양권 — 2021년 이후 취득 + 1~2년 보유 (60% 단기세율)",
            "acq": _1to2y,
            "prop": "분양권",
            "acq_reason": "분양",
            "count": 1,
            "expected": "단기세율",
            "tags": ["분양권", "1~2년", "60%"],
        },
        {
            "desc": "분양권 + 기존주택 일시적2주택 특례 — 기한 내 종전주택 양도 (비과세)",
            "acq": "20170101",
            "prop": "아파트",
            "acq_reason": "매매",
            "count": 2,
            "temp_two_house": {
                "new_acquisition_date": "20230601",   # 분양권 취득
                "old_house_must_sell_by": "20270601",  # 3년 내 양도 기한
                "new_is_adjustment_area": False,
            },
            "expected": "비과세",
            "tags": ["분양권", "일시적2주택", "비과세"],
        },
        {
            "desc": "분양권 2개 + 기존주택 — 분양권 주택수 포함 시 3주택 중과",
            "acq": "20170101",
            "prop": "아파트",
            "acq_reason": "매매",
            "count": 3,   # 주택1 + 분양권2 포함 3주택
            "adj_trf": True,
            "expected": "중과",
            "tags": ["분양권", "주택수포함", "중과"],
        },
        {
            "desc": "배우자로부터 증여받은 분양권 + 이월과세 10년 내",
            "acq": "20200601",
            "prop": "분양권",
            "acq_reason": "증여",
            "count": 1,
            "gift": {
                "is_gift_from_spouse_or_lineal": True,
                "gift_date": "20200601",
                "donor_acquisition_date": "20190101",
                "donor_acquisition_price": 350_000_000,
            },
            "expected": None,   # 이월과세 적용 여부가 사실관계에 따라 달라짐
            "tags": ["분양권", "배우자증여", "이월과세"],
        },
    ]

    for s in scenarios:
        fj: dict = {
            "transfer_date": transfer_date.strftime("%Y%m%d"),
            "acquisition_date": s["acq"],
            "property_type": s["prop"],
            "acquisition_reason": s["acq_reason"],
            "household_house_count": s["count"],
            "transfer_price": 700_000_000,
            "acquisition_price": 400_000_000,
            "residence_years": 0.0,
            "is_adjustment_area_at_transfer": s.get("adj_trf", False),
        }
        sc_inner: dict = {}
        if s.get("temp_two_house"):
            sc_inner["temp_two_house"] = s["temp_two_house"]
        if s.get("gift"):
            sc_inner["gift"] = s["gift"]
        if sc_inner:
            fj["special_cases"] = sc_inner
        yield SyntheticCase(
            description=s["desc"],
            fact_json=fj,
            expected_verdict=s["expected"],
            boundary_type="ruling_bunyang",
            tags=s["tags"],
        )


# ── ⑥ 조합원입주권 심화 (소득세법 §156의2) ──────────────────────────────────
def generate_reconstruction_deep(
    transfer_date: date = date(2026, 5, 1),
) -> Iterator[SyntheticCase]:
    """
    조합원입주권 심화.
    핵심 예규: 원조합원·승계조합원 구분, 대체주택, 청산금 과세.
    """
    _suspension_end = _get_heavy_tax_suspension_end(transfer_date)
    _after_suspension = transfer_date > _suspension_end

    cases = [
        {
            "desc": "원조합원 입주권 — 비조정지역 10년 이상 보유, 비과세",
            "acq": "20130101",
            "is_original": True,
            "adj": False,
            "expected": "비과세",
            "tags": ["입주권", "원조합원", "비과세"],
        },
        {
            "desc": "원조합원 입주권 — 조정지역 + 거주요건 2년 미충족",
            "acq": "20180101",
            "is_original": True,
            "adj": True,
            "residence": 0.5,
            "expected": "일반과세",
            "tags": ["입주권", "원조합원", "조정지역거주미달"],
        },
        {
            "desc": "승계조합원 입주권 — 1년 미만 보유 (70% 단기세율)",
            "acq": (transfer_date - timedelta(days=300)).strftime("%Y%m%d"),
            "is_original": False,
            "adj": False,
            "expected": "단기세율",
            "tags": ["입주권", "승계조합원", "1년미만"],
        },
        {
            "desc": "승계조합원 입주권 — 2년 이상 보유 (일반과세, §156의2 비과세 불가)",
            "acq": "20230101",
            "is_original": False,
            "adj": False,
            "expected": "일반과세",
            "tags": ["입주권", "승계조합원", "2년이상"],
        },
        {
            "desc": "원조합원 + 일반주택 1채 — 입주권 일시적2주택 특례 (비과세)",
            "acq": "20160101",
            "is_original": True,
            "adj": False,
            "temp_two_house": {
                "new_acquisition_date": "20240101",
                "old_house_must_sell_by": "20280101",
                "new_is_adjustment_area": False,
            },
            "expected": "비과세",
            "tags": ["입주권", "원조합원", "일시적2주택"],
        },
        {
            "desc": "대체주택 — 재건축 기간 중 취득한 주택 양도, 비과세 적용",
            "acq": "20210601",   # 관리처분 후 취득 대체주택
            "prop": "아파트",
            "acq_reason": "매매",
            "is_original": True,
            "adj": False,
            "residence": 2.5,
            "expected": "비과세",
            "tags": ["입주권", "대체주택", "비과세"],
        },
    ]

    for c in cases:
        prop = c.get("prop", "입주권")
        reason = c.get("acq_reason", "재건축" if prop == "입주권" else "매매")
        sc_inner: dict = {}
        if prop == "입주권":
            sc_inner["reconstruction"] = {
                "management_disposal_date": "20220601",
                "is_original_member": c["is_original"],
            }
        if c.get("temp_two_house"):
            sc_inner["temp_two_house"] = c["temp_two_house"]
        fj: dict = {
            "transfer_date": transfer_date.strftime("%Y%m%d"),
            "acquisition_date": c["acq"],
            "property_type": prop,
            "acquisition_reason": reason,
            "household_house_count": 2 if c.get("temp_two_house") else 1,
            "transfer_price": 700_000_000,
            "acquisition_price": 300_000_000,
            "residence_years": c.get("residence", 0.0 if prop == "입주권" else 2.5),
            "is_adjustment_area_at_transfer": c.get("adj", False),
            "is_adjustment_area_at_acquisition": c.get("adj", False),
        }
        if sc_inner:
            fj["special_cases"] = sc_inner
        yield SyntheticCase(
            description=c["desc"],
            fact_json=fj,
            expected_verdict=c["expected"],
            boundary_type="ruling_reconstruction",
            tags=c["tags"],
        )


# ── ⑦ 장기임대주택 감면 (조세특례제한법 §97의3) ────────────────────────────
def generate_long_term_rental_deep(
    transfer_date: date = date(2026, 5, 1),
) -> Iterator[SyntheticCase]:
    """
    민간임대주택법 등록 + 의무임대기간 충족 시 양도세 감면.
    핵심 예규: 의무기간 중 수용, 5% 증액제한 위반 시 감면 취소.
    """
    scenarios = [
        {
            "desc": "장기일반민간임대 8년 + 의무기간 충족 — 50% 감면 (조특§97의3①)",
            "reg": "20170101",
            "years": 8,
            "fulfilled": True,
            "increase_ok": True,
            "expected": "감면",
            "tags": ["장기임대", "8년감면", "50%"],
        },
        {
            "desc": "장기일반민간임대 10년 + 의무기간 충족 — 70% 감면 (조특§97의3①)",
            "reg": "20150101",
            "years": 10,
            "fulfilled": True,
            "increase_ok": True,
            "expected": "감면",
            "tags": ["장기임대", "10년감면", "70%"],
        },
        {
            "desc": "장기임대 의무기간 중 공익수용 — 감면 유지 (의무기간 면제)",
            "reg": "20180101",
            "years": 8,
            "fulfilled": True,    # 수용으로 의무기간 충족 간주
            "increase_ok": True,
            "expropriation": True,
            "expected": "감면",
            "tags": ["장기임대", "공익수용", "감면유지"],
        },
        {
            "desc": "장기임대 의무기간 미충족 자진 말소 — 감면 취소, 일반과세",
            "reg": "20180101",
            "years": 8,
            "fulfilled": False,   # 6년만 임대 후 자진 말소
            "increase_ok": True,
            "expected": "일반과세",
            "tags": ["장기임대", "의무기간미달", "감면취소"],
        },
        {
            "desc": "장기임대 5% 증액제한 위반 — 감면 취소, 일반과세",
            "reg": "20170101",
            "years": 8,
            "fulfilled": True,
            "increase_ok": False,  # 5% 초과 인상 → 감면 취소
            "expected": "일반과세",
            "tags": ["장기임대", "증액위반", "감면취소"],
        },
    ]

    for s in scenarios:
        sc_inner: dict = {
            "long_term_rental": {
                "registration_date": s["reg"],
                "mandatory_period_years": s["years"],
                "mandatory_period_fulfilled": s["fulfilled"],
                "rent_increase_limit_complied": s["increase_ok"],
            }
        }
        if s.get("expropriation"):
            sc_inner["expropriation"] = {
                "compensation_type": "현금",
                "is_main_residence": False,
            }
        yield SyntheticCase(
            description=s["desc"],
            fact_json={
                "transfer_date": transfer_date.strftime("%Y%m%d"),
                "acquisition_date": "20150101",
                "property_type": "아파트",
                "acquisition_reason": "매매",
                "household_house_count": 1,
                "transfer_price": 800_000_000,
                "acquisition_price": 400_000_000,
                "residence_years": 0.0,
                "is_adjustment_area_at_transfer": False,
                "special_cases": sc_inner,
            },
            expected_verdict=s["expected"],
            boundary_type="ruling_long_term_rental",
            tags=s["tags"],
        )


# ── ⑧ 공익사업 수용 감면 (조세특례제한법 §77) ────────────────────────────────
def generate_expropriation_deep(
    transfer_date: date = date(2026, 5, 1),
) -> Iterator[SyntheticCase]:
    """
    공익사업 수용 감면 심화.
    현금보상: 10%, 채권보상: 15%, 채권 3년 이상 보유 시 30%.
    핵심 예규: 사업인정 고시 전·후 자진 협의 취득 여부.
    """
    scenarios = [
        {
            "desc": "공익수용 — 현금보상 감면 (조특§77①, 10%)",
            "comp": "현금",
            "expected": "감면",
            "tags": ["공익수용", "현금보상", "감면"],
        },
        {
            "desc": "공익수용 — 채권보상 감면 (조특§77①, 15~30%)",
            "comp": "채권",
            "expected": "감면",
            "tags": ["공익수용", "채권보상", "감면"],
        },
        {
            "desc": "공익수용 — 2년 이상 거주 주택 + 채권보상 (추가 감면)",
            "comp": "채권",
            "main_res": True,
            "expected": "감면",
            "tags": ["공익수용", "거주주택", "추가감면"],
        },
        {
            "desc": "공익수용 — 비조정지역, 보유 5년 이상, 비과세 요건 미충족 → 감면",
            "comp": "현금",
            "main_res": False,
            "residence": 0.0,   # 거주 0년, §89 비과세 불가 → §77 감면
            "expected": "감면",
            "tags": ["공익수용", "거주미달", "§77감면"],
        },
    ]

    for s in scenarios:
        yield SyntheticCase(
            description=s["desc"],
            fact_json={
                "transfer_date": transfer_date.strftime("%Y%m%d"),
                "acquisition_date": "20180101",
                "property_type": "아파트",
                "acquisition_reason": "수용",
                "household_house_count": 1,
                "transfer_price": 800_000_000,
                "acquisition_price": 400_000_000,
                "residence_years": s.get("residence", 0.0),
                "is_adjustment_area_at_acquisition": True,
                "is_adjustment_area_at_transfer": False,
                "special_cases": {
                    "expropriation": {
                        "compensation_type": s["comp"],
                        "is_main_residence": s.get("main_res", False),
                    }
                },
            },
            expected_verdict=s["expected"],
            boundary_type="ruling_expropriation",
            tags=s["tags"],
        )


# ── ⑨ 상속주택 심화 (소득세법 §155②③, §89③) ────────────────────────────────
def generate_inheritance_deep(
    transfer_date: date = date(2026, 5, 1),
) -> Iterator[SyntheticCase]:
    """
    상속주택 심화.
    핵심 예규: 공동상속 지분, 피상속인 보유기간 합산, 상속+일시적2주택.
    """
    scenarios = [
        {
            "desc": "상속주택 — 상속개시 후 5년 이내, 일반주택 1채 함께 보유 (비과세)",
            "death": "20230101",
            "selling_inherited": False,    # 일반주택 양도
            "same_hh": True,
            "only_house": True,
            "expected": "비과세",
            "tags": ["상속주택", "5년이내", "일반주택양도"],
        },
        {
            "desc": "상속주택 — 상속주택 직접 양도, 취득가액=상속세 과세가액",
            "death": "20200601",
            "selling_inherited": True,
            "same_hh": False,
            "only_house": False,
            "expected": "일반과세",
            "tags": ["상속주택", "직접양도", "취득가액"],
        },
        {
            "desc": "공동상속 — 최대지분자(상속주택 1채로 간주), 일반주택 비과세",
            "death": "20230101",
            "selling_inherited": False,
            "same_hh": False,
            "only_house": True,  # 최대지분 = 1주택 간주
            "expected": "비과세",
            "tags": ["상속주택", "공동상속", "최대지분"],
        },
        {
            "desc": "공동상속 — 동등지분 (최연장자가 아님), 상속주택 제외 불가",
            "death": "20220101",
            "selling_inherited": False,
            "same_hh": False,
            "only_house": False,  # 동등지분 최연장자 아님 → 2주택
            "expected": "일반과세",
            "tags": ["상속주택", "공동상속", "동등지분"],
        },
        {
            "desc": "상속주택 + 일시적2주택 — 3년 내 일반주택 양도 (비과세)",
            "death": "20230101",
            "selling_inherited": False,
            "same_hh": False,
            "only_house": True,
            "temp_two_house": {
                "new_acquisition_date": "20230601",
                "old_house_must_sell_by": "20280601",
                "new_is_adjustment_area": False,
            },
            "expected": "비과세",
            "tags": ["상속주택", "일시적2주택", "복합"],
        },
        {
            "desc": "피상속인 장기 보유 주택 — 보유기간 합산 후 비과세 여부",
            "death": "20240101",
            "selling_inherited": True,
            "same_hh": True,    # 동일 세대 거주 → 피상속인 보유기간 합산 가능
            "only_house": True,
            "donor_acq": "20050101",  # 피상속인 20년 보유 → 장기보유특별공제 최대
            "expected": "비과세",
            "tags": ["상속주택", "보유기간합산", "장기공제"],
        },
    ]

    for s in scenarios:
        inh_inner: dict = {
            "death_date": s["death"],
            "same_household_at_death": s["same_hh"],
            "inherited_as_only_house": s["only_house"],
            "selling_inherited_house": s["selling_inherited"],
        }
        if s.get("donor_acq"):
            inh_inner["donor_acquisition_date"] = s["donor_acq"]

        sc_inner: dict = {"inheritance": inh_inner}
        if s.get("temp_two_house"):
            sc_inner["temp_two_house"] = s["temp_two_house"]

        yield SyntheticCase(
            description=s["desc"],
            fact_json={
                "transfer_date": transfer_date.strftime("%Y%m%d"),
                "acquisition_date": s["death"] if s["selling_inherited"] else "20180101",
                "property_type": "아파트",
                "acquisition_reason": "상속" if s["selling_inherited"] else "매매",
                "household_house_count": 2 if s.get("temp_two_house") else (1 if s["only_house"] else 2),
                "transfer_price": 900_000_000,
                "acquisition_price": 400_000_000,
                "residence_years": 3.0 if not s["selling_inherited"] else 0.0,
                "is_adjustment_area_at_transfer": False,
                "special_cases": sc_inner,
            },
            expected_verdict=s["expected"],
            boundary_type="ruling_inheritance",
            tags=s["tags"],
        )


# ── ⑩ 혼인합가 (소득세법 §155③) ─────────────────────────────────────────────
def generate_marriage_merge_deep(
    transfer_date: date = date(2026, 5, 1),
) -> Iterator[SyntheticCase]:
    """혼인합가 심화. 합산 후 5년 이내/초과 경계."""
    _suspension_end = _get_heavy_tax_suspension_end(transfer_date)
    _after_suspension = transfer_date > _suspension_end

    scenarios = [
        {
            "desc": "혼인합가 — 합가 후 4년 이내 양도 (1주택 간주, 비과세)",
            "marriage": "20220601",
            "expected": "비과세",
            "tags": ["혼인합가", "5년이내", "비과세"],
        },
        {
            "desc": "혼인합가 — 합가 후 5년 초과 양도 (다주택 취급)",
            "marriage": "20180601",
            "expected": "중과" if _after_suspension else "일반과세",
            "tags": ["혼인합가", "5년초과", "다주택"],
        },
        {
            "desc": "혼인합가 + 고가주택 12억 초과 — 합가 내 양도, 고가주택 과세",
            "marriage": "20230601",
            "transfer_price": 1_400_000_000,
            "expected": "고가주택",
            "tags": ["혼인합가", "고가주택", "복합"],
        },
        {
            "desc": "혼인합가 + 일시적2주택 중첩 — 3년 내 종전주택 양도 (비과세)",
            "marriage": "20230101",
            "temp_two_house": {
                "new_acquisition_date": "20231201",
                "old_house_must_sell_by": "20271201",
                "new_is_adjustment_area": False,
            },
            "expected": "비과세",
            "tags": ["혼인합가", "일시적2주택", "복합"],
        },
    ]

    for s in scenarios:
        sc_inner: dict = {
            "marriage_merge": {
                "marriage_date": s["marriage"],
                "spouse_house_count_before_marriage": 1,
                "own_house_count_before_marriage": 1,
            }
        }
        if s.get("temp_two_house"):
            sc_inner["temp_two_house"] = s["temp_two_house"]

        fj: dict = {
            "transfer_date": transfer_date.strftime("%Y%m%d"),
            "acquisition_date": "20180101",
            "property_type": "아파트",
            "acquisition_reason": "혼인합가",
            "household_house_count": 2,
            "transfer_price": s.get("transfer_price", 900_000_000),
            "acquisition_price": 500_000_000,
            "residence_years": 3.0,
            "is_adjustment_area_at_transfer": False,
            "special_cases": sc_inner,
        }
        yield SyntheticCase(
            description=s["desc"],
            fact_json=fj,
            expected_verdict=s["expected"],
            boundary_type="ruling_marriage_merge",
            tags=s["tags"],
        )


# ── 전체 취합 ─────────────────────────────────────────────────────────────────
def generate_all_ruling_cases(
    as_of: Optional[date] = None,
) -> List[SyntheticCase]:
    """
    예규·해석 기반 케이스 전체 생성.
    generate_all_comprehensive_cases()에 추가로 호출하면 골든셋이 확장된다.
    """
    today = as_of or date.today()
    cases: List[SyntheticCase] = []

    cases.extend(generate_sangsaeng_rental_deep(today))
    cases.extend(generate_cohabitation_deep(today))
    cases.extend(generate_rural_house_deep(today))
    cases.extend(generate_non_resident_deep(today))
    cases.extend(generate_bunyang_deep(today))
    cases.extend(generate_reconstruction_deep(today))
    cases.extend(generate_long_term_rental_deep(today))
    cases.extend(generate_expropriation_deep(today))
    cases.extend(generate_inheritance_deep(today))
    cases.extend(generate_marriage_merge_deep(today))

    # case_id 고유성 보장
    seen: set[str] = set()
    for c in cases:
        while c.case_id in seen:
            c.case_id = str(uuid.uuid4())[:8]
        seen.add(c.case_id)

    return cases


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="예규·해석 기반 케이스 생성")
    parser.add_argument("--output", default="data/golden/ruling_cases.json")
    args = parser.parse_args()

    cases = generate_all_ruling_cases()
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps([asdict(c) for c in cases], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"예규 케이스 생성: {len(cases)}건 → {out}")

    # 카테고리별 요약
    from collections import Counter
    cats = Counter(c.boundary_type for c in cases)
    for cat, n in sorted(cats.items()):
        print(f"  {cat}: {n}건")
