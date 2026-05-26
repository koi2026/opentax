"""
L2 — Fact Completeness Check

LLM 호출 전에 실행. 결정적 규칙으로 사실관계 완전성을 검사.
크리티컬 항목이 빠지면 LLM을 호출하지 않고 조기 반환.

설계 원칙:
- RAGQueryInput(typed schema)을 받아 semantic completeness를 검사
- 문자열 비교 없음 — date 객체와 enum 직접 비교
- "모르면 위험한 쪽으로" 원칙: 불확실 시 danger_flag 추가, can_proceed=False
- missing_facts는 LLM 프롬프트에도 전달해 "이 정보가 없어서 불확실합니다"를 안내
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional

from .query_input import (
    AcquisitionReason,
    PropertyType,
    RAGQueryInput,
)


@dataclass
class MissingFact:
    """
    누락된 사실관계 1건.
    is_critical=True이면 이 항목 없이는 LLM 호출을 차단.
    """
    field_name: str        # 누락 필드명 (사용자에게 재질문용)
    reason: str            # 왜 필요한지 — 상담 화면에 노출
    article_hint: str      # 관련 조문 (LLM 프롬프트에 삽입)
    is_critical: bool = True


@dataclass
class FactCheckResult:
    can_proceed: bool                         # False면 LLM 호출 차단
    missing_facts: List[MissingFact] = field(default_factory=list)
    danger_flags: List[str] = field(default_factory=list)  # L3 키워드 주입용
    forced_verdict: Optional[str] = None     # "needs_verification" 등

    @property
    def critical_missing(self) -> List[MissingFact]:
        return [f for f in self.missing_facts if f.is_critical]

    def missing_fact_texts(self) -> List[str]:
        """LLM 프롬프트 삽입용 텍스트 목록"""
        return [f"{f.field_name}: {f.reason}" for f in self.missing_facts]


def check_facts(query: RAGQueryInput) -> FactCheckResult:
    """
    RAGQueryInput을 받아 사실관계 완전성 검사.
    순서가 중요: 크리티컬 순서대로 체크.
    """
    missing: List[MissingFact] = []
    danger: List[str] = []
    fv = query.fact_vector
    sc = fv.special_cases
    db = query.date_bundle

    # ── 1. 고가주택 판단 불가 (모든 케이스에 영향) ──────────────────────
    if fv.transfer_price is None:
        missing.append(MissingFact(
            field_name="transfer_price",
            reason="양도가액 미확인 — 12억 초과 고가주택 여부를 알 수 없으면 비과세 범위 계산 불가",
            article_hint="소득세법 §89①3호, 시행령 §156의2",
            is_critical=True,
        ))
        danger.append("고가주택_미확인")
    elif fv.is_high_value_house:
        danger.append("고가주택")  # 12억 초과 확인 → L3에서 §89/§156의2 키워드 주입

    # ── 2. 이월과세 (가장 위험: 조용히 틀린 결과) ───────────────────────
    is_gift_acquisition = fv.acquisition_reason in (
        AcquisitionReason.GIFT, AcquisitionReason.BURDEN_GIFT
    )
    if is_gift_acquisition:
        danger.append("이월과세")
        rt = sc.rollover_taxation
        if rt is None or not rt.is_gift_from_spouse_or_lineal:
            # 증여 취득인데 배우자/직계 여부 미확인 → 이월과세 적용 가능성 있음
            missing.append(MissingFact(
                field_name="is_gift_from_spouse_or_lineal",
                reason="증여자가 배우자/직계존비속인지 확인 필요 — 해당 시 이월과세 적용으로 취득가액·취득일 기산점이 바뀜",
                article_hint="소득세법 §97의2",
                is_critical=True,
            ))
        elif rt.is_gift_from_spouse_or_lineal:
            # 배우자/직계 증여 확인 — 이월과세 기간 내인지 체크
            years_elapsed = _years_between(rt.gift_date, db.transfer_date)
            if years_elapsed < rt.iota_period_years:
                danger.append(f"이월과세_{rt.iota_period_years}년이내")
                if not rt.original_donor_acquisition_date or rt.original_donor_acquisition_price == 0:
                    missing.append(MissingFact(
                        field_name="original_donor_acquisition_date / original_donor_acquisition_price",
                        reason=(
                            f"배우자/직계존비속 증여 후 {rt.iota_period_years}년 이내 양도 — "
                            "이월과세 적용 시 증여자 원취득일과 원취득가액으로 계산됨. "
                            "이 정보 없이는 취득가액 계산 불가"
                        ),
                        article_hint="소득세법 §97의2",
                        is_critical=True,
                    ))

    # ── 3. 상속주택 — 피상속인 원취득일 없음 ────────────────────────────
    # 경로 A(일반주택 양도) 포함 — acquisition_reason이 PURCHASE여도 sc.is_inherited_house로 감지
    if fv.acquisition_reason == AcquisitionReason.INHERITANCE or sc.is_inherited_house:
        danger.append("상속주택")
        inh = sc.inheritance
        if inh is None:
            missing.append(MissingFact(
                field_name="death_date",
                reason="상속개시일(사망일) 필요 — 5년 이내 상속주택 주택 수 제외 기간 기산점",
                article_hint="소득세법 시행령 §155②",
                is_critical=True,
            ))
        else:
            # InheritanceDetail이 있더라도 경로 B(상속주택 자체 양도) 시 피상속인 원취득일 필수
            if inh.selling_inherited_house:
                danger.append("상속주택_자체양도")
                donor_acq = getattr(inh, "donor_acquisition_date", None)
                if donor_acq is None:
                    missing.append(MissingFact(
                        field_name="donor_acquisition_date",
                        reason="상속주택 자체 양도 시 피상속인 원취득일 필요 — 보유기간 합산 여부 판단 불가",
                        article_hint="소득세법 시행령 §155③",
                        is_critical=True,
                    ))

    # ── 4. 일시적 2주택 — 신규주택 취득일 없음 ──────────────────────────
    if sc.is_temporary_two_house:
        danger.append("일시적2주택")
        td = sc.temp_two_house
        if td is None or not getattr(td, "new_acquisition_date", None):
            missing.append(MissingFact(
                field_name="temp_two_house.new_acquisition_date",
                reason="신규주택 취득일 필요 — 종전주택 3년 이내 양도 기한 계산 불가",
                article_hint="소득세법 시행령 §155①",
                is_critical=True,
            ))

    # ── 5. 재건축/재개발 — 관리처분계획인가일 없음 ──────────────────────
    if fv.property_type == PropertyType.ASSOCIATION_RIGHT:
        danger.append("조합원입주권")
        rc = sc.reconstruction
        if rc is None:
            missing.append(MissingFact(
                field_name="management_disposal_date",
                reason="관리처분계획인가일 필요 — 조합원입주권 보유기간 기산점, 1세대1주택 특례 판단 불가",
                article_hint="소득세법 시행령 §156의2",
                is_critical=True,
            ))
        elif not rc.original_house_acquisition_date:
            missing.append(MissingFact(
                field_name="reconstruction.original_house_acquisition_date",
                reason="종전주택 취득일 필요 — 원조합원 보유기간 기산점",
                article_hint="소득세법 시행령 §156의2①",
                is_critical=True,
            ))

    # ── 6. 분양권 — 2021년 기준 주택 수 산입 여부 ───────────────────────
    if fv.property_type == PropertyType.SUBSCRIPTION_RIGHT:
        danger.append("분양권")
        before = sc.bunyang_acquired_before_2021
        if before is None:
            # 취득일 있으면 자동 판단되어야 하는데 None이면 데이터 누락
            missing.append(MissingFact(
                field_name="acquisition_date (분양권)",
                reason="분양권 취득일 필요 — 2021.01.01 이후 취득분만 주택 수에 산입됨",
                article_hint="소득세법 §88⑦",
                is_critical=False,  # 주의 수준 (비과세 계산에 영향)
            ))
            danger.append("분양권_기준불명")
        elif before:
            danger.append("분양권_2021전_주택수미산입")
        else:
            danger.append("분양권_2021후_주택수산입")

    # ── 7. 조정대상지역 취득 + 거주요건 미충족 경고 ──────────────────────
    # 취득 당시 조정대상지역이었으면 거주기간 2년 이상 필요 (소령 §154①)
    # 미충족 시 §89 비과세 불가 → L3 키워드 주입으로 §154 조문 검색 유도
    if fv.adjustment_area_at_acquisition and (fv.residence_period_years or 0.0) < 2.0:
        danger.append("조정지역_거주요건")

    # ── 7-2. 다주택 중과 가능 여부 ───────────────────────────────────────
    if fv.household_house_count >= 2:
        if fv.adjustment_area_at_transfer:
            # 한시적 중과배제 기간(2022.5.10~) 확인 — 기간 내면 조정지역이어도 일반세율
            _transfer_dt = query.date_bundle.transfer_date
            from .tax_constants import TaxConstantsRegistry
            _suspension_start: date = TaxConstantsRegistry.get("HEAVY_TAX_SUSPENSION_START", _transfer_dt)
            _suspension_end: date = TaxConstantsRegistry.get("HEAVY_TAX_SUSPENSION_END", _transfer_dt)

            if _suspension_start <= _transfer_dt <= _suspension_end:
                danger.append("중과한시면세")  # 면세 기간 중 → 조정지역이어도 일반세율
            else:
                danger.append("다주택중과")   # 조정지역 다주택 → §104 중과 검색 유도
        else:
            danger.append("다주택비조정")   # 비조정지역 → 중과 비해당 명시

    # ── 8. 상생임대 — 조정대상지역 여부 미확인 ──────────────────────────
    if sc.sangsaeng_rental and sc.sangsaeng_rental.residence_requirement_waived:
        danger.append("상생임대")
        if not fv.adjustment_area_at_transfer:
            # 상생임대는 조정대상지역이어야 거주요건 면제 의미가 있음
            # 비조정지역이면 원래 거주요건 없음 — 상생임대 적용 의미 없음
            missing.append(MissingFact(
                field_name="adjustment_area_at_transfer",
                reason="상생임대 거주요건 면제는 조정대상지역 주택에만 적용 — 비조정지역이면 원래 거주요건 없음",
                article_hint="소득세법 시행령 §155의3",
                is_critical=False,
            ))

    # ── 9. 공동명의 — 지분 정보 없음 ────────────────────────────────────
    if fv.joint_ownership_yn:
        danger.append("공동명의")
        # joint_owner_info는 FactVector에 없고 user_property에서 오므로
        # 여기서는 danger flag만 추가

    # ── 10. 특수관계자간 거래 — 부당행위계산부인 위험 ─────────────────────
    # 차단하지 않음(비크리티컬) — 경고 후 진행. L5에서 expert_review_signal 생성.
    if fv.is_related_party_transaction:
        danger.append("특수관계자거래")
        missing.append(MissingFact(
            field_name="related_party_transaction_details",
            reason=(
                "특수관계자 거래 확인 — 소득세법 §101 부당행위계산부인 적용 시 "
                "양도가액이 시가로 재계산되어 양도차익·비과세 범위가 달라질 수 있음"
            ),
            article_hint="소득세법 §101",
            is_critical=False,
        ))

    # ── 11. 비거주자 — §121 비과세 배제 ─────────────────────────────────
    if sc.is_non_resident:
        danger.append("비거주자")

    # ── 12. 동거봉양합가 — §155④ 10년 이내 비과세 ──────────────────────
    if sc.is_cohabitation_care:
        danger.append("동거봉양합가")

    # ── 13. 농어촌주택 보유 — 조특법 §99의4 주택 수 제외 ────────────────
    if sc.is_rural_house:
        danger.append("농어촌주택")

    # ── 14. 공익사업 수용 — 조특법 §77 감면 ──────────────────────────────
    if sc.expropriation:
        danger.append("공익수용감면")

    # ── 15. 장기임대주택 감면 — 조특법 §97의3 ───────────────────────────
    if sc.is_long_term_rental_registered and sc.long_term_rental:
        if sc.long_term_rental.mandatory_period_fulfilled:
            danger.append("장기임대감면")

    # ── 결정 ─────────────────────────────────────────────────────────────
    critical_count = sum(1 for m in missing if m.is_critical)
    can_proceed = critical_count == 0

    return FactCheckResult(
        can_proceed=can_proceed,
        missing_facts=missing,
        danger_flags=danger,
        forced_verdict="needs_verification" if not can_proceed else None,
    )


def _years_between(earlier: date, later: date) -> float:
    """두 날짜 사이 경과 연수. 불확실 시 0 반환(위험한 쪽으로 판단하지 않음 — 호출부에서 처리)."""
    try:
        return (later - earlier).days / 365.25
    except (TypeError, AttributeError):
        return 0.0
