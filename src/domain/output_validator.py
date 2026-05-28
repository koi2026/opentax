"""
L5 — Output Validator

LLM 출력이 나온 후 실행. 두 종류의 오류를 방어:

- 조용한 오류: 이월과세 무시하고 "비과세" → L2가 잡아야 하지만 통과된 경우 최후 방어
- 자신감 있는 오류: 고가주택 확인 없이 "100% 비과세" → 신뢰도 강제 하향

원칙: confidence가 높아도 missing_facts가 있으면 하향.
     인용 chunk가 검색 결과에 없으면(phantom citation) 신뢰도 0.3 이하.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional, Set

from .tax_answer import ExpertReviewSignal, TaxAnswer, TaxVerdict

if TYPE_CHECKING:
    from .query_input import RAGQueryInput, ResidenceExemptionType

# 신뢰도 상한 — missing_facts 있을 때
CONFIDENCE_CAP_WITH_MISSING = 0.75

# phantom citation 발견 시 신뢰도 강제 상한
CONFIDENCE_CAP_PHANTOM_CITATION = 0.3

# "비과세" verdict인데 고가주택 미확인 시 신뢰도 상한
CONFIDENCE_CAP_UNCHECKED_HIGH_VALUE = 0.6


# 예규/판례 의존도가 높은 danger_flag → 세무사 전문 검토 기회 신호
# 에러가 아니라 아이템 발굴 신호 — 탐지될수록 전문가 상담 가치 증가
EXPERT_REVIEW_TRIGGERS: dict[str, dict] = {
    "이월과세": {
        "category": "해석다툼",
        "description": "이월과세(§97의2) vs 부당행위계산부인(§101) 선택 적용은 예규·판례에 따라 달라집니다.",
        "opportunity": "배우자 증여 후 양도 시 두 규정의 교차 적용 — 세액 차이가 크므로 세무사 검토 아이템",
        "related_article": "소득세법 제97조의2, 제101조",
    },
    "상속주택": {
        "category": "해석다툼",
        "description": "공동상속 지정보유자 요건, 동거봉양 합산 판단 등은 예규·판례 의존 영역입니다.",
        "opportunity": "최대지분·거주자·최연장자 기준 지정 분쟁, 피상속인 보유기간 합산 범위 — 세무사 검토 아이템",
        "related_article": "소득세법 시행령 제155조 제2항",
    },
    "상생임대": {
        "category": "예규공백",
        "description": "상생임대 직전 임대차계약 범위, 보증금-월세 전환 시 5% 계산 방식이 예규로 구체화됩니다.",
        "opportunity": "신규 임차인 vs 갱신 계약 경계 분쟁 — 5% 증액 요건 충족 여부 설계 아이템",
        "related_article": "소득세법 시행령 제155조의3",
    },
    "공동명의": {
        "category": "해석다툼",
        "description": "공동명의 지분별 주택 수 산정 방식, 1주택 취급 기준은 예규 의존 영역입니다.",
        "opportunity": "지분율 기준 vs 1주택 취급 — 공동명의 절세 구조 설계 아이템",
        "related_article": "소득세법 시행령 제154조",
    },
    "재건축재개발원조합원": {
        "category": "예규공백",
        "description": "청산금 납부·수령 시 비례 과세 계산, 원조합원 보유기간 통산 방식은 예규로 구체화됩니다.",
        "opportunity": "청산금 수령분 비례 과세 분기, 멸실 후 신축 입주권 보유기간 기산 — 세무사 검토 아이템",
        "related_article": "소득세법 시행령 제156조의2",
    },
    "특수관계자거래": {
        "category": "조세불복가능",
        "description": "특수관계자 저가양도 시 부당행위계산부인 적용 여부는 시가 입증 방법에 따라 다투어질 수 있습니다.",
        "opportunity": "시가 vs 양도가액 입증 전략, 조세심판 선례 활용 — 세무사 절세·불복 아이템",
        "related_article": "소득세법 제101조",
    },
    "동거봉양합가": {
        "category": "해석다툼",
        "description": "동거봉양 합가 요건(60세·중증질환) 충족 여부 및 10년 기산점이 예규 쟁점입니다.",
        "opportunity": "합가일 기준 입증, 별거 후 재합가 처리 — 세무사 요건 충족 검토 아이템",
        "related_article": "소득세법 시행령 제155조 제4항",
    },
}


def validate_output(
    answer: TaxAnswer,
    retrieved_chunk_ids: Set[str],
    danger_flags: Optional[List[str]] = None,
    query: Optional["RAGQueryInput"] = None,
) -> TaxAnswer:
    """
    TaxAnswer를 검증하고 필요 시 confidence를 하향 조정.

    Args:
        answer: LLM이 생성한 TaxAnswer
        retrieved_chunk_ids: Stage 1+2 검색에서 실제로 반환된 chunk ID 집합
        danger_flags: L2 fact_checker에서 탐지된 위험 플래그 목록 (예규 신호 탐지용)

    Returns:
        warnings, expert_review_signals 추가 및 confidence 조정된 TaxAnswer
    """
    warnings = list(answer.warnings)
    confidence = answer.confidence
    verdict = answer.verdict
    active_flags = set(danger_flags or [])

    # ── 1. Phantom Citation 검사 ─────────────────────────────────────────
    # LLM이 인용한 chunk가 실제 검색 결과에 없으면 hallucination 의심
    cited_ids = {c.chunk_id for c in answer.citations}
    phantom = cited_ids - retrieved_chunk_ids
    if phantom:
        warnings.append(
            f"⚠ 인용 {len(phantom)}개 청크가 검색 결과에 없음 — "
            f"환각 인용 가능성: {', '.join(sorted(phantom))}"
        )
        confidence = min(confidence, CONFIDENCE_CAP_PHANTOM_CITATION)

    # ── 2. Missing Facts → 신뢰도 상한 ──────────────────────────────────
    if answer.missing_facts and confidence > CONFIDENCE_CAP_WITH_MISSING:
        warnings.append(
            f"추가 확인 필요 항목 {len(answer.missing_facts)}건 — "
            f"신뢰도 {confidence:.0%} → {CONFIDENCE_CAP_WITH_MISSING:.0%}로 조정"
        )
        confidence = CONFIDENCE_CAP_WITH_MISSING

    # ── 3. 비과세 verdict + 고가주택 미확인 ─────────────────────────────
    # "비과세"라고 했는데 양도가액을 확인하지 않은 경우
    # 12억 초과이면 초과분은 과세 → 완전 비과세가 아님
    is_exemption_verdict = answer.verdict in ("비과세", "조건부비과세")
    high_value_unchecked = any(
        "양도가액" in f or "고가주택" in f
        for f in answer.missing_facts
    )
    if is_exemption_verdict and high_value_unchecked:
        warnings.append(
            "⚠ 양도가액 미확인 — 고가주택(12억 초과) 해당 시 초과분 과세됨. "
            "비과세 판단은 양도가액 확인 후 재검토 필요"
        )
        confidence = min(confidence, CONFIDENCE_CAP_UNCHECKED_HIGH_VALUE)

    # ── 4. 이월과세 경고 통과 여부 ──────────────────────────────────────
    # L2에서 이월과세 크리티컬 항목이 빠졌는데 여기까지 왔다면
    # (can_proceed=True인데 이월과세 관련 missing_facts가 있는 경우)
    iota_missing = any("이월과세" in f or "원취득일" in f or "원취득가액" in f for f in answer.missing_facts)
    if iota_missing and is_exemption_verdict:
        warnings.append(
            "⚠ 이월과세 적용 여부 미확인 — 배우자/직계 증여 후 기간 내 양도 시 "
            "취득가액이 증여자 원가로 바뀌어 세액이 크게 달라질 수 있음"
        )
        confidence = min(confidence, 0.5)

    # ── 5. 예규/판례 의존 영역 → 세무사 전문 검토 기회 신호 ─────────────
    # 에러 신호가 아니라 아이템 발굴 신호 — confidence 조정 없음
    expert_signals: List[ExpertReviewSignal] = list(answer.expert_review_signals)
    already_categories = {s.category + s.related_article for s in expert_signals}

    for flag in active_flags:
        trigger = EXPERT_REVIEW_TRIGGERS.get(flag)
        if not trigger:
            continue
        key = trigger["category"] + (trigger.get("related_article") or "")
        if key in already_categories:
            continue
        expert_signals.append(ExpertReviewSignal(
            category=trigger["category"],
            description=trigger["description"],
            opportunity=trigger["opportunity"],
            related_article=trigger.get("related_article"),
        ))
        already_categories.add(key)

    # ── 6. 결정론적 Verdict 오버라이드 ──────────────────────────────────
    # LLM이 틀린 경우를 후처리로 교정. 사실관계 기반이라 회귀 위험 낮음.

    # 6-1. 12억 경계값: 고가주택 판정인데 transfer_price ≤ 비과세 한도 → 비과세
    if verdict == TaxVerdict.PARTIALLY_EXEMPT and query is not None:
        _tp = query.fact_vector.transfer_price
        if _tp is not None:
            from .tax_constants import TaxConstantsRegistry
            _threshold_int = int(TaxConstantsRegistry.get(
                "HIGH_VALUE_THRESHOLD", query.date_bundle.transfer_date
            ))
            if _tp <= _threshold_int:
                verdict = TaxVerdict.EXEMPT
                warnings.append(
                    f"[L5 수정] 양도가액 {_tp:,}원 ≤ 비과세 한도 {_threshold_int:,}원 "
                    "→ 고가주택 판정 오류 수정, 비과세로 변경"
                )

    # 6-2. 중과 한시면세: danger_flag 존재 + 중과 판정 → 일반과세
    if verdict == TaxVerdict.HEAVY_TAX and "중과한시면세" in active_flags:
        verdict = TaxVerdict.GENERAL
        warnings.append(
            "[L5 수정] 중과 한시적 배제 기간(2022.5.10~2026.5.9) 내 양도 "
            "→ 중과 판정 오류 수정, 일반과세로 변경"
        )

    # 6-3. 조정지역 거주요건 미충족 + 비과세 판정 → 일반과세
    #      단, 상생임대·공익수용 등 거주요건 면제 특례가 있으면 유지
    _residence_waiver_flags = {"상생임대", "수용_compulsory_거주요건면제", "수용_negotiated_거주요건면제"}
    if (
        verdict == TaxVerdict.EXEMPT
        and "조정지역_거주요건" in active_flags
        and not (active_flags & _residence_waiver_flags)
    ):
        verdict = TaxVerdict.GENERAL
        warnings.append(
            "[L5 수정] 조정대상지역 취득 주택: 거주기간 2년 미충족 (소령 §154①) "
            "→ 비과세 요건 불충족, 일반과세로 변경"
        )

    # ── 6-4. 장기임대 감면 취소 → 비과세 차단 ──────────────────────────────
    # 의무기간 미충족 또는 증액제한 위반 → 감면 취소 → 일반과세
    # 등록 임대주택은 임대기간 중 거주주택 아님 → §89 비과세 불가
    if "장기임대감면취소" in active_flags and verdict == TaxVerdict.EXEMPT:
        verdict = TaxVerdict.GENERAL
        warnings.append(
            "[L5 수정] 장기임대 감면 취소(의무기간 미충족 또는 증액제한 위반) "
            "→ 등록 임대주택은 §89 비과세 불가, 일반과세"
        )

    # ── 6-5. 장기임대 감면 요건 충족 + 사실관계부족/일반과세 오판 → 감면 오버라이드 ──
    # danger_flag '장기임대감면' = fulfilled AND complied 모두 True → verdict='감면'
    if "장기임대감면" in active_flags and verdict in (
        TaxVerdict.NEEDS_VERIFICATION, TaxVerdict.GENERAL
    ):
        verdict = TaxVerdict.REDUCED
        warnings.append(
            "[L5 수정] 장기임대 의무기간·증액 요건 모두 충족 → §97의3 감면 적용"
        )

    # ── 6-6. 공익수용 감면/비과세 → 일반과세 차단 ────────────────────────────
    # 공익사업 수용(§77)은 감면이 기본 — 일반과세 판정은 오류.
    # 단, 실거주 주택(is_main_residence=True) + 1주택 + §89 요건 충족 시 §77 감면보다 §89 비과세 우선.
    if (
        ("공익수용감면" in active_flags or "수용_조특77감면" in active_flags)
        and verdict == TaxVerdict.GENERAL
    ):
        _exempt_applies6 = False
        if query is not None:
            from .tax_constants import TaxConstantsRegistry as _TCR6
            _exp6 = query.fact_vector.special_cases.expropriation
            _tp6 = query.fact_vector.transfer_price
            _hp6 = query.fact_vector.holding_period_years or 0.0
            _hc6 = query.fact_vector.household_house_count
            _threshold6 = int(_TCR6.get("HIGH_VALUE_THRESHOLD", query.date_bundle.transfer_date))
            _exempt_applies6 = (
                _exp6 is not None
                and getattr(_exp6, "residence_exemption_applies", False)
                and _hc6 == 1
                and _hp6 >= 2.0
                and _tp6 is not None
                and _tp6 <= _threshold6
            )
        if _exempt_applies6:
            verdict = TaxVerdict.EXEMPT
            warnings.append(
                "[L5 수정] 공익수용 실거주 1주택(§154①단서 거주요건면제) — §89 비과세 우선 적용, 일반과세 수정"
            )
        else:
            verdict = TaxVerdict.REDUCED
            warnings.append(
                "[L5 수정] 공익사업 수용(조특§77) — 일반과세 판정 오류 수정, 감면 적용"
            )

    # ── 6-8. 다주택 중과세율 적용 → 일반/고가/사실관계부족 판정 보정 ────────────────
    # 조정대상지역 다주택 + 한시면세 종료 → 중과세율 필수 (소득세법 §104)
    # fact_checker가 "다주택중과" 플래그를 세운 경우 LLM 오판(일반·고가·사실관계부족) 보정
    # Note: "중과한시면세" 기간 중에는 이 플래그가 설정되지 않으므로 안전
    if "다주택중과" in active_flags and verdict in (
        TaxVerdict.GENERAL,
        TaxVerdict.PARTIALLY_EXEMPT,
        TaxVerdict.NEEDS_VERIFICATION,
    ):
        verdict = TaxVerdict.HEAVY_TAX
        warnings.append(
            "[L5 수정] 조정대상지역 다주택 + 한시면세 기간 종료 — 일반/고가주택/사실관계부족 판정 오류, 중과세율 적용"
        )

    # ── 6-9. 공동상속 비지정보유자 → 비과세 차단 ─────────────────────────────────
    # 소령 §155②: 공동상속 시 지정보유자가 아닌 경우(동등지분·최연장자 아님) 상속주택 주택수 산입
    # → 1세대1주택 비과세(§89) 적용 불가, LLM이 보유기간·거주기간만 보고 비과세 오판 시 보정
    if (
        "상속주택" in active_flags
        and verdict == TaxVerdict.EXEMPT
        and query is not None
    ):
        inh = query.fact_vector.special_cases.inheritance
        if inh is not None and not inh.inherited_as_only_house:
            verdict = TaxVerdict.GENERAL
            warnings.append(
                "[L5 수정] 공동상속 비지정보유자 — 상속주택 주택수 산입(소령§155②), §89 비과세 불가 → 일반과세"
            )

    # ── 6-10. 비조정지역 취득 + 거주요건 없음 → NEEDS_VERIFICATION 해제 ─────────────
    # 소령§154①: 취득 당시 비조정지역이면 거주2년 불요 → 보유2년+1주택+12억이하 → §89 비과세
    # fact_checker가 "조정지역_거주요건" 미설정인 상태에서 LLM이 거주기간 누락 이유로 오판 시 보정
    if (
        verdict == TaxVerdict.NEEDS_VERIFICATION
        and "조정지역_거주요건" not in active_flags
        and query is not None
        and not query.fact_vector.adjustment_area_at_acquisition
        and query.fact_vector.household_house_count == 1
        and (query.fact_vector.holding_period_years or 0.0) >= 2.0
    ):
        from .tax_constants import TaxConstantsRegistry as _TCR10
        _threshold10 = int(_TCR10.get("HIGH_VALUE_THRESHOLD", query.date_bundle.transfer_date))
        _tp10 = query.fact_vector.transfer_price
        if _tp10 is not None and _tp10 <= _threshold10:
            verdict = TaxVerdict.EXEMPT
            warnings.append(
                "[L5 수정] 취득시 비조정지역 — 소령§154① 거주요건 불적용, NEEDS_VERIFICATION → §89 비과세"
            )

    # ── 6-11. 혼인합가 5년이내 → 1주택 간주 (비과세/고가주택 보정) ──────────────────
    # 소령§155③: 혼인 전 각자 1주택 + 혼인신고일부터 5년이내 양도 → 1세대1주택 간주
    # LLM이 세대 합산 2주택만 보고 일반과세/사실관계부족 반환 시 보정
    if (
        verdict in (TaxVerdict.GENERAL, TaxVerdict.NEEDS_VERIFICATION)
        and "조정지역_거주요건" not in active_flags
        and query is not None
        and query.fact_vector.special_cases.is_marriage_merge
    ):
        _mm11 = query.fact_vector.special_cases.marriage_merge
        if _mm11 is not None:
            from .tax_constants import TaxConstantsRegistry as _TCR11
            _mm_limit11 = int(_TCR11.get("MARRIAGE_MERGE_EXEMPT_YEARS", query.date_bundle.transfer_date))
            _elapsed11 = (query.date_bundle.transfer_date - _mm11.marriage_date).days / 365.25
            if _elapsed11 <= _mm_limit11:
                _threshold11 = int(_TCR11.get("HIGH_VALUE_THRESHOLD", query.date_bundle.transfer_date))
                _tp11 = query.fact_vector.transfer_price
                if _tp11 is not None and _tp11 > _threshold11:
                    verdict = TaxVerdict.PARTIALLY_EXEMPT
                    warnings.append(
                        f"[L5 수정] 혼인합가 {_elapsed11:.1f}년이내(§155③) — 1주택 간주, 고가주택(12억 초과분 과세)"
                    )
                elif _tp11 is not None:
                    verdict = TaxVerdict.EXEMPT
                    warnings.append(
                        f"[L5 수정] 혼인합가 {_elapsed11:.1f}년이내(§155③) — 1주택 간주, §89 비과세"
                    )

    # ── 6-7. 해외이주 1주택 비거주자 → 비과세 보정 ───────────────────────────────
    # §154①2호: 해외이주자는 비거주자이더라도 1주택 출국일로부터 2년 이내 양도 시 §89 비과세 적용
    # LLM이 "비거주자 = 일반과세" 기본 원칙에 빠져 특례를 놓칠 때 보정
    if (
        query is not None
        and verdict == TaxVerdict.GENERAL
        and query.fact_vector.household_house_count == 1
        and query.fact_vector.special_cases.residence_requirement_exempted
    ):
        from .query_input import ResidenceExemptionType as _RET
        if query.fact_vector.special_cases.residence_exemption_type == _RET.OVERSEAS_EMIGRATION:
            verdict = TaxVerdict.EXEMPT
            warnings.append(
                "[L5 수정] 해외이주 1주택자 — §154①2호 거주요건 면제 → §89 비과세 적용"
            )

    # ── 6-8b. 비거주자 단기보유 → 단기세율 확정 ────────────────────────────────
    # 비거주자는 §89 비과세 불가. 보유 2년 미만이면 §104 단기세율(60%/70%) 확정.
    # LLM이 §121 조문 부재를 이유로 NEEDS_VERIFICATION 반환 시 보정.
    if (
        query is not None
        and verdict == TaxVerdict.NEEDS_VERIFICATION
        and (query.fact_vector.overseas_residence_yn or query.fact_vector.special_cases.is_non_resident)
        and 0 < (query.fact_vector.holding_period_years or 0.0) < 2.0
    ):
        verdict = TaxVerdict.SHORT_TERM
        warnings.append(
            "[L5 수정] 비거주자 단기보유(§89 비과세 불가) — §104 단기세율 적용"
        )

    # ── 7. 최종 반환 ─────────────────────────────────────────────────────
    changed = (
        verdict != answer.verdict
        or confidence != answer.confidence
        or warnings != answer.warnings
        or expert_signals != answer.expert_review_signals
    )
    if changed:
        return answer.with_update(
            verdict=verdict,
            confidence=confidence,
            warnings=warnings,
            expert_review_signals=expert_signals,
        )
    return answer
