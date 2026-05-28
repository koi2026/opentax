"""
특례 발굴 엔진 — 모든 조특법·소득세법 특례를 망라하여 적용 가능성을 판단.

설계 원칙:
- 확정: verdict에 반영
- 가능·검토_필요: warnings에만 추가 (verdict 변경 금지)
- 미구현 특례 없음 — 새 특례는 _DETECTORS 목록에 추가
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Callable, List, Literal, Optional

from .query_input import (
    AcquisitionReason,
    FactVector,
    PropertyType,
    ResidenceExemptionType,
)
from .tax_constants import TaxConstantsRegistry as _TCR


@dataclass
class ApplicableSpecialCase:
    name: str                                      # 특례명 ("농어촌주택 비과세" 등)
    certainty: Literal["확정", "가능", "검토_필요"]
    article_ref: str                               # 근거 조문 ("조특법 §99의4")
    missing_evidence: List[str] = field(default_factory=list)  # 확정에 필요한 추가 정보
    estimated_tax_delta: Optional[int] = None     # 절세 효과 추정액 (원, None=미계산)
    description: str = ""                         # 사용자 노출 설명


# ── 개별 검출 함수 ─────────────────────────────────────────────────────────────


def _detect_temp_two_house(fv: FactVector, transfer_date: date) -> Optional[ApplicableSpecialCase]:
    """일시적 2주택 비과세 (소득세법 시행령 §155①)"""
    sc = fv.special_cases
    if not sc.is_temporary_two_house:
        return None

    if sc.temp_two_house is not None:
        detail = sc.temp_two_house
        within_deadline = transfer_date <= detail.old_house_must_sell_by
        certainty: Literal["확정", "가능", "검토_필요"] = "확정" if within_deadline else "가능"
        missing: List[str] = [] if within_deadline else ["종전주택 양도 기한 초과 여부 재확인"]
        desc = (
            f"신규주택 취득 후 종전주택을 {detail.old_house_must_sell_by} 이전에 양도해야 비과세."
            + (" (기한 내 양도 확인됨)" if within_deadline else " (기한 초과 가능 — 재확인 필요)")
        )
    else:
        certainty = "가능"
        missing = ["신규주택 취득일", "종전주택 양도 기한"]
        desc = "일시적 2주택 비과세 가능 — 상세 일정 확인 필요"

    return ApplicableSpecialCase(
        name="일시적 2주택 비과세",
        certainty=certainty,
        article_ref="소득세법 시행령 §155①",
        missing_evidence=missing,
        description=desc,
    )


def _detect_inheritance(fv: FactVector, transfer_date: date) -> Optional[ApplicableSpecialCase]:
    """상속주택 비과세 (소득세법 시행령 §155②③)"""
    sc = fv.special_cases
    if not sc.is_inherited_house:
        return None

    if sc.inheritance is not None:
        certainty: Literal["확정", "가능", "검토_필요"] = "확정"
        missing: List[str] = []
        detail = sc.inheritance
        if detail.selling_inherited_house:
            desc = "상속주택 자체 양도 — 피상속인 보유기간 합산 적용 (소령 §155③)"
            if detail.donor_acquisition_date is None:
                certainty = "가능"
                missing = ["피상속인 원취득일"]
        else:
            desc = "상속주택 외 일반주택 양도 시 1세대 1주택 비과세 적용 가능 (소령 §155②)"
    else:
        certainty = "가능"
        missing = ["상속개시일(사망일)", "피상속인과의 동일세대 여부", "상속 당시 상속인의 주택 보유 여부"]
        desc = "상속주택 특례 가능 — 상세 정보 확인 필요"

    return ApplicableSpecialCase(
        name="상속주택 비과세 특례",
        certainty=certainty,
        article_ref="소득세법 시행령 §155②③",
        missing_evidence=missing,
        description=desc,
    )


def _detect_rollover_taxation(fv: FactVector, transfer_date: date) -> Optional[ApplicableSpecialCase]:
    """이월과세 (소득세법 §97의2) — 납세자 불리 케이스"""
    sc = fv.special_cases
    rt = sc.rollover_taxation
    if rt is None or not rt.iota_applies:
        return None

    cutoff = rt.gift_date.replace(year=rt.gift_date.year + rt.iota_period_years)
    within_period = transfer_date <= cutoff

    if not within_period:
        return None

    missing: List[str] = []
    if rt.original_donor_acquisition_date is None:
        missing.append("증여자 원취득일")
    if rt.original_donor_acquisition_price is None:
        missing.append("증여자 원취득가액")

    desc = (
        f"이월과세 적용 시 취득가액이 증여자 원취득가액으로 계산됩니다. "
        f"납세자에게 불리한 경우가 많습니다. "
        f"(증여일: {rt.gift_date}, 적용기간: {rt.iota_period_years}년)"
    )

    return ApplicableSpecialCase(
        name="이월과세 적용 위험",
        certainty="검토_필요",
        article_ref="소득세법 §97의2",
        missing_evidence=missing,
        description=desc,
    )


def _detect_sangsaeng_rental(fv: FactVector, transfer_date: date) -> Optional[ApplicableSpecialCase]:
    """상생임대 거주요건 면제 (소득세법 시행령 §155의3)"""
    sc = fv.special_cases
    sr = sc.sangsaeng_rental
    if sr is None:
        return None

    if sr.residence_requirement_waived:
        certainty: Literal["확정", "가능", "검토_필요"] = "확정"
        missing: List[str] = []
        desc = "상생임대 5개 요건 충족 — 조정대상지역 거주요건 2년 면제 적용"
    else:
        certainty = "가능"
        missing = []
        if not sr.contract_in_window:
            missing.append(f"상생임대차계약 체결일 기준 확인 (계약일: {sr.contract_date})")
        if not sr.has_prior_contract:
            missing.append("직전 임대차계약 존재 여부 확인")
        if sr.increase_rate > 0.05:
            missing.append(f"임대료 인상률 5% 초과 ({sr.increase_rate:.1%}) — 요건 미충족")
        _min_months: int = _TCR.get("SANGSAENG_MIN_PERIOD_MONTHS", transfer_date)
        if sr.contract_period_months < _min_months:
            missing.append(f"실제 임대기간 2년 미만 ({sr.contract_period_months}개월)")
        desc = "상생임대 요건 일부 미충족 — 추가 확인 후 적용 가능 여부 판단 필요"

    return ApplicableSpecialCase(
        name="상생임대 거주요건 면제",
        certainty=certainty,
        article_ref="소득세법 시행령 §155의3",
        missing_evidence=missing,
        description=desc,
    )


def _detect_cohabitation_care(fv: FactVector, transfer_date: date) -> Optional[ApplicableSpecialCase]:
    """동거봉양 합가 비과세 (소득세법 시행령 §155④)"""
    sc = fv.special_cases
    if not getattr(sc, "is_cohabitation_care", False):
        return None

    cc = getattr(sc, "cohabitation_care", None)
    missing: List[str] = ["동거봉양 합가일", "직계존속 연령/건강 정보"]

    if cc is not None:
        if cc.age_requirement_met:
            years_since_merge = (transfer_date - cc.cohabitation_start_date).days / 365.25
            _cohab_limit: int = _TCR.get("COHABITATION_EXEMPT_YEARS", transfer_date)
            if years_since_merge <= _cohab_limit:
                certainty: Literal["확정", "가능", "검토_필요"] = "확정"
                missing = []
                desc = (
                    f"동거봉양 합가일({cc.cohabitation_start_date})부터 {_cohab_limit}년 이내 양도 — "
                    "먼저 양도하는 주택 비과세 적용"
                )
            else:
                certainty = "가능"
                missing = [f"합가 후 {_cohab_limit}년 초과 여부 재확인 ({_cohab_limit}년 경과 시 특례 소멸)"]
                desc = f"동거봉양 합가 후 {_cohab_limit}년 초과 가능 — 비과세 특례 소멸 위험"
        else:
            certainty = "가능"
            missing = ["직계존속 나이 60세 이상 또는 중증질환 해당 여부 확인"]
            desc = "동거봉양 요건 미충족 가능 — 직계존속 연령/질환 요건 확인 필요"
    else:
        certainty = "가능"
        desc = "동거봉양 합가 특례 가능 — 상세 정보 확인 필요"

    return ApplicableSpecialCase(
        name="동거봉양 합가 비과세",
        certainty=certainty,
        article_ref="소득세법 시행령 §155④",
        missing_evidence=missing,
        description=desc,
    )


def _detect_marriage_merge(fv: FactVector, transfer_date: date) -> Optional[ApplicableSpecialCase]:
    """혼인합가 비과세 (소득세법 시행령 §155⑤)"""
    sc = fv.special_cases
    if not sc.is_marriage_merge:
        return None

    mm = sc.marriage_merge
    missing: List[str] = []

    if mm is not None:
        years_since_marriage = (transfer_date - mm.marriage_date).days / 365.25
        _marriage_limit: int = _TCR.get("MARRIAGE_MERGE_EXEMPT_YEARS", transfer_date)
        if years_since_marriage <= _marriage_limit:
            certainty: Literal["확정", "가능", "검토_필요"] = "확정"
            desc = (
                f"혼인신고일({mm.marriage_date})부터 {_marriage_limit}년 이내 양도 — "
                "혼인 전 각자 보유 1주택 비과세 적용"
            )
        else:
            certainty = "가능"
            missing = [f"혼인 후 {_marriage_limit}년 초과 여부 재확인 ({_marriage_limit}년 경과 시 특례 소멸)"]
            desc = f"혼인합가 후 {_marriage_limit}년 초과 가능 — 비과세 특례 소멸 위험"
    else:
        certainty = "가능"
        missing = ["혼인신고일", "합가 전 각자 보유주택 수"]
        desc = "혼인합가 비과세 특례 가능 — 상세 정보 확인 필요"

    return ApplicableSpecialCase(
        name="혼인합가 비과세",
        certainty=certainty,
        article_ref="소득세법 시행령 §155⑤",
        missing_evidence=missing,
        description=desc,
    )


def _detect_rural_house(fv: FactVector, transfer_date: date) -> Optional[ApplicableSpecialCase]:
    """농어촌주택 비과세 (조세특례제한법 §99의4)"""
    sc = fv.special_cases
    is_rural = sc.is_rural_house or fv.property_type == PropertyType.RURAL_HOUSE

    if not is_rural:
        return None

    return ApplicableSpecialCase(
        name="농어촌주택 비과세",
        certainty="가능",
        article_ref="조세특례제한법 §99의4",
        missing_evidence=[
            "농어촌주택 소재지 행정구역 확인",
            "취득 당시 농어촌지역 해당 여부",
            "수도권·도시지역 이외 지역 소재 확인",
        ],
        description="농어촌주택 보유 시 일반주택 양도 시 비과세 — 소재지 요건 확인 필요",
    )


def _detect_long_term_rental(fv: FactVector, transfer_date: date) -> Optional[ApplicableSpecialCase]:
    """장기임대주택 감면 (조세특례제한법 §97의3~§97의5)"""
    sc = fv.special_cases
    if not sc.is_long_term_rental_registered:
        return None

    lt = sc.long_term_rental
    if lt is not None and lt.mandatory_period_fulfilled and lt.rent_increase_limit_complied:
        certainty: Literal["확정", "가능", "검토_필요"] = "확정"
        missing: List[str] = []
        desc = (
            f"장기임대주택 의무임대기간 {lt.mandatory_period_years}년 충족 및 "
            "임대료 5% 증액 제한 준수 — 양도소득세 감면 적용"
        )
    else:
        certainty = "가능"
        missing = []
        if lt is not None:
            if not lt.mandatory_period_fulfilled:
                missing.append(f"의무임대기간 {lt.mandatory_period_years}년 충족 여부 재확인")
            if not lt.rent_increase_limit_complied:
                missing.append("임대료 5% 증액 제한 준수 여부 확인")
        else:
            missing = ["임대사업자 등록일", "의무임대기간(4/8/10년) 충족 여부", "임대료 증액 제한 준수 여부"]
        desc = "장기임대주택 감면 가능 — 요건 충족 여부 확인 필요"

    return ApplicableSpecialCase(
        name="장기임대주택 양도소득세 감면",
        certainty=certainty,
        article_ref="조세특례제한법 §97의3~§97의5",
        missing_evidence=missing,
        description=desc,
    )


def _detect_expropriation(fv: FactVector, transfer_date: date) -> Optional[ApplicableSpecialCase]:
    """공익수용 비과세·감면 (조세특례제한법 §77)"""
    sc = fv.special_cases
    exp = sc.expropriation

    is_expropriation_reason = fv.acquisition_reason == AcquisitionReason.EXPROPRIATION
    has_expropriation_detail = exp is not None

    if not is_expropriation_reason and not has_expropriation_detail:
        return None

    if exp is not None and exp.residence_exemption_applies:
        certainty: Literal["확정", "가능", "검토_필요"] = "확정"
        desc = (
            f"공익사업 수용({exp.acquisition_type}) — 양도소득세 10~40% 감면. "
            "대체취득 기간 조건 있음. 보상 유형에 따라 추가 특례 가능 (채권·대토)."
        )
        missing: List[str] = []
    else:
        certainty = "가능"
        missing = ["공익수용 유형 확인 (강제수용/협의취득/자진매각)", "보상 유형 확인 (현금/채권/대토)"]
        desc = "공익사업 수용 시 양도소득세 10~40% 감면 — 수용 유형 확인 필요"

    return ApplicableSpecialCase(
        name="공익수용 양도소득세 감면",
        certainty=certainty,
        article_ref="조세특례제한법 §77",
        missing_evidence=missing,
        description=desc,
    )


def _detect_small_reconstruction(fv: FactVector, transfer_date: date) -> Optional[ApplicableSpecialCase]:
    """소규모재건축 감면 (조세특례제한법 §99의2)"""
    sc = fv.special_cases
    is_reconstruction_type = fv.property_type == PropertyType.ASSOCIATION_RIGHT
    has_reconstruction = sc.reconstruction is not None

    if not (is_reconstruction_type and has_reconstruction):
        return None

    return ApplicableSpecialCase(
        name="소규모재건축 양도소득세 감면",
        certainty="검토_필요",
        article_ref="조세특례제한법 §99의2",
        missing_evidence=[
            "소규모재건축 해당 여부 (가로주택정비사업·소규모재건축사업)",
            "사업승인 규모 확인 (1만㎡ 미만 등 요건)",
        ],
        description="소규모재건축 해당 시 양도소득세 감면 가능 — 사업 규모 요건 전문가 확인 필요",
    )


def _detect_unavoidable_relocation(fv: FactVector, transfer_date: date) -> Optional[ApplicableSpecialCase]:
    """직장이전·취학·질병 거주요건 면제 (소득세법 시행령 §154①6호)"""
    sc = fv.special_cases
    exemption_type = sc.residence_exemption_type

    if exemption_type not in (
        ResidenceExemptionType.UNAVOIDABLE_RELOCATION,
        ResidenceExemptionType.OVERSEAS_EMIGRATION,
    ):
        return None

    type_label = {
        ResidenceExemptionType.UNAVOIDABLE_RELOCATION: "직장이전·취학·질병",
        ResidenceExemptionType.OVERSEAS_EMIGRATION: "해외이주",
    }.get(exemption_type, "부득이한 사유")

    article_ref = {
        ResidenceExemptionType.UNAVOIDABLE_RELOCATION: "소득세법 시행령 §154①6호",
        ResidenceExemptionType.OVERSEAS_EMIGRATION: "소득세법 시행령 §154①2호",
    }.get(exemption_type, "소득세법 시행령 §154")

    return ApplicableSpecialCase(
        name=f"{type_label} 거주요건 면제",
        certainty="가능",
        article_ref=article_ref,
        missing_evidence=[],
        description=f"거주요건 면제 사유: {type_label}. 사유 증빙 서류 보유 필요",
    )


def _detect_association_right_exemption(fv: FactVector, transfer_date: date) -> Optional[ApplicableSpecialCase]:
    """조합원입주권 비과세 (소득세법 시행령 §156의2)"""
    sc = fv.special_cases
    if fv.property_type != PropertyType.ASSOCIATION_RIGHT:
        return None
    if sc.reconstruction is None:
        return None

    rc = sc.reconstruction

    if not rc.is_original_member:
        # 승계조합원(관리처분 후 취득)은 §156의2 비과세 특례 적용 불가.
        # 입주권 자체 양도 시 보유기간에 따라 단기세율 또는 일반과세 적용.
        return None

    desc = (
        f"원조합원 입주권 — 종전주택 취득일({rc.original_house_acquisition_date})부터 "
        "보유기간 합산 인정 가능"
    )

    return ApplicableSpecialCase(
        name="조합원입주권 1세대1주택 특례",
        certainty="가능",
        article_ref="소득세법 시행령 §156의2",
        missing_evidence=[],
        description=desc,
    )


def _detect_subscription_right_exemption(fv: FactVector, transfer_date: date) -> Optional[ApplicableSpecialCase]:
    """분양권 1세대1주택 특례 (소득세법 §88⑦)"""
    if fv.property_type != PropertyType.SUBSCRIPTION_RIGHT:
        return None

    sc = fv.special_cases
    before_2021 = sc.bunyang_acquired_before_2021

    missing: List[str] = []
    if before_2021 is None:
        missing = ["분양권 취득일 (2021.01.01 전후 구분)", "세대 전체 주택 수"]
    elif not before_2021:
        missing = ["세대 전체 주택 수 (분양권 2021.01.01 이후 취득 — 주택 수 산입)"]

    return ApplicableSpecialCase(
        name="분양권 1세대1주택 특례",
        certainty="검토_필요",
        article_ref="소득세법 §88⑦",
        missing_evidence=missing,
        description=(
            "분양권 2021.01.01 이후 취득분은 세대 주택 수에 산입됨. "
            "이전 취득분은 주택 수 미산입 — 취득일 기준 확인 필요"
        ),
    )


def _detect_non_resident_exemption(fv: FactVector, transfer_date: date) -> Optional[ApplicableSpecialCase]:
    """비거주자 국내부동산 과세 특례 (소득세법 §121 등)"""
    sc = fv.special_cases
    if not (fv.overseas_residence_yn or sc.is_non_resident):
        return None

    nr = sc.non_resident
    missing: List[str] = ["비거주자 해당 기간", "조세조약 적용 여부"]

    if nr is not None and nr.emigration_exemption_possible:
        months_since_departure = (transfer_date - nr.departure_date).days / 30.44
        _exemption_months: int = _TCR.get("NON_RESIDENT_DEPARTURE_EXEMPTION_MONTHS", transfer_date)
        if months_since_departure <= _exemption_months:
            missing = ["해외이주 후 2년 이내 양도 — 비과세 예외 적용 가능 여부 확인"]
            desc = f"해외이주 후 {months_since_departure:.0f}개월 경과 — 2년 이내 양도 비과세 예외 검토"
        else:
            desc = "해외이주 후 2년 초과 양도 — 비거주자 과세 원칙 적용, 조세조약 검토 필요"
    else:
        desc = "비거주자는 원칙적으로 1세대1주택 비과세 불가 — 조세조약·예외 규정 전문가 확인 필요"

    return ApplicableSpecialCase(
        name="비거주자 국내부동산 과세 특례",
        certainty="검토_필요",
        article_ref="소득세법 §121의2",
        missing_evidence=missing,
        description=desc,
    )


def _detect_high_value_house(fv: FactVector, transfer_date: date) -> Optional[ApplicableSpecialCase]:
    """고가주택 12억 초과분 과세 (소득세법 §89①3호, 소득세법 시행령 §156의2)"""
    if not fv.is_high_value_house:
        return None

    price = fv.transfer_price or 0
    desc = (
        f"양도가액 {price:,}원 — 12억 초과분에 대해서만 양도소득세 과세. "
        "비과세 적용 시에도 초과분은 과세됩니다."
    )

    return ApplicableSpecialCase(
        name="고가주택 12억 초과분 과세",
        certainty="확정",
        article_ref="소득세법 §89①3호",
        missing_evidence=[],
        description=desc,
    )


# ── 검출 함수 목록 ─────────────────────────────────────────────────────────────

_DetectorFn = Callable[[FactVector, date], Optional[ApplicableSpecialCase]]

_DETECTORS: List[_DetectorFn] = [
    _detect_temp_two_house,
    _detect_inheritance,
    _detect_rollover_taxation,
    _detect_sangsaeng_rental,
    _detect_cohabitation_care,
    _detect_marriage_merge,
    _detect_rural_house,
    _detect_long_term_rental,
    _detect_expropriation,
    _detect_small_reconstruction,
    _detect_unavoidable_relocation,
    _detect_association_right_exemption,
    _detect_subscription_right_exemption,
    _detect_non_resident_exemption,
    _detect_high_value_house,
]


# ── 공개 API ──────────────────────────────────────────────────────────────────


def find_special_cases(fv: FactVector, transfer_date: date) -> List[ApplicableSpecialCase]:
    """
    FactVector에서 적용 가능한 모든 세법 특례를 검출한다.

    Args:
        fv: 사실관계 벡터 (주택유형, 특례 플래그, 보유기간 등 포함)
        transfer_date: 양도일 (기한 계산 기준)

    Returns:
        발견된 특례 목록. 확정·가능·검토_필요 순으로 정렬.
    """
    results: List[ApplicableSpecialCase] = []
    for detector in _DETECTORS:
        case = detector(fv, transfer_date)
        if case is not None:
            results.append(case)

    # 확정 → 가능 → 검토_필요 순으로 정렬
    order = {"확정": 0, "가능": 1, "검토_필요": 2}
    results.sort(key=lambda c: order[c.certainty])
    return results


def format_special_cases_summary(cases: List[ApplicableSpecialCase]) -> str:
    """
    "AI가 N개의 절세 기회를 발견했습니다" 형식 메시지.
    verdict 말미에 첨부.

    Args:
        cases: find_special_cases() 반환값

    Returns:
        요약 메시지 문자열. 발견된 특례가 없으면 빈 문자열 반환.
    """
    confirmed = [c for c in cases if c.certainty == "확정"]
    possible = [c for c in cases if c.certainty == "가능"]
    review = [c for c in cases if c.certainty == "검토_필요"]

    parts: List[str] = []
    if confirmed:
        parts.append(f"확정 {len(confirmed)}건")
    if possible:
        parts.append(f"검토 가능 {len(possible)}건")
    if review:
        parts.append(f"전문가 검토 필요 {len(review)}건")

    if not parts:
        return ""
    return f"AI가 {len(cases)}개의 절세 기회를 발견했습니다 ({', '.join(parts)})"
