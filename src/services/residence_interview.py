"""
실거주 요건 심층 인터뷰 플로우

주민등록 기준 거주기간 != 실질 거주기간일 때를 발굴하는 인터뷰.
비과세 요건 충족 여부가 바뀔 수 있는 고부가가치 특례 발굴.

- 조정대상지역 취득(2017.8.3 이후): 2년 거주 요건 (소득세법 §154①)
- 비조정지역 또는 2017.8.3 이전 취득: 거주 요건 없음
- 주민등록 전입/전출일 != 실제 이사/이사날 → 거주기간 재산정 필요
"""

from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional


# ── 상수 ─────────────────────────────────────────────────────────────────────

# 조정대상지역 거주요건 제도 시행일 (소득세법 §154① 개정, 2017.8.3 취득분부터)
_ADJUSTMENT_AREA_RESIDENCE_RULE_START = date(2017, 8, 3)

# 거주요건 충족 기준 연수
_REQUIRED_RESIDENCE_YEARS_ADJUSTMENT = 2.0  # 조정대상지역 취득
_REQUIRED_RESIDENCE_YEARS_NON_ADJUSTMENT = 0.0  # 비조정지역 (거주요건 없음)

# 경계값 판단 기준: 이 여유분 이내면 is_borderline=True
_BORDERLINE_MARGIN_YEARS = 0.5


# ── 데이터 클래스 ──────────────────────────────────────────────────────────────

@dataclass
class ResidenceEvidenceItem:
    """개별 거주 증빙 항목"""

    period_start: date
    period_end: date
    evidence_type: str  # "공과금" | "카드내역" | "재직증명" | "학교재학" | "주민등록" | "기타"
    description: str
    is_actual_residence: bool  # True=실거주, False=주민등록만/공백


@dataclass
class ResidenceInterviewResult:
    """실거주 인터뷰 결과"""

    declared_residence_years: float          # 사용자가 처음 신고한 거주기간
    verified_residence_years: float          # 인터뷰 후 실질 거주기간 (보수적 추정)
    evidence_items: List[ResidenceEvidenceItem]
    missing_evidence_warnings: List[str]     # 증빙 부족 항목
    interview_questions: List[str]           # 추가로 확인이 필요한 질문들
    can_verify: bool                         # 증빙으로 충분히 확인 가능한지
    potential_gain_years: float              # 추가 인정 가능 거주기간 상한 (낙관적 시나리오)
    needs_expert: bool                       # 세무사 면담 필요 여부


# ── 인터뷰 질문 목록 ──────────────────────────────────────────────────────────

RESIDENCE_INTERVIEW_QUESTIONS: List[dict] = [
    {
        "id": "R01",
        "question": "주민등록상 전입일과 실제 이사 들어간 날이 같습니까?",
        "followup_if_no": (
            "실제 이사한 날짜를 알 수 있습니까? "
            "(공과금 첫 납부일, 이사업체 영수증 등으로 확인 가능)"
        ),
        "impact": "high",  # 거주기간 기산일 변동
    },
    {
        "id": "R02",
        "question": (
            "전출 후 실제로 그 집을 비운 날짜가 있습니까? "
            "(전입신고만 하고 다른 곳에서 생활한 기간)"
        ),
        "followup_if_yes": (
            "그 기간 동안 어디서 거주하셨습니까? "
            "(직장, 학교, 가족 등 이유가 있으면 특례 인정 가능)"
        ),
        "impact": "high",  # 실질 거주기간 감소
    },
    {
        "id": "R03",
        "question": "해당 주택에서 전기/가스/수도를 직접 납부한 기간을 확인할 수 있습니까?",
        "followup_if_no": (
            "임차인이 납부했거나 관리비에 포함된 경우라도 본인이 실거주한 것으로 볼 수 있습니다. "
            "확인 가능한 증빙이 있습니까?"
        ),
        "impact": "medium",  # 증빙 보강
    },
    {
        "id": "R04",
        "question": (
            "직장이 해당 주택에서 통근 가능한 거리에 있었습니까? "
            "(왕복 3시간 이상이면 실거주 의심받을 수 있음)"
        ),
        "followup_if_no": (
            "직장이 멀었다면, 주말만 거주하거나 주중에는 다른 곳에서 지낸 기간이 있습니까?"
        ),
        "impact": "medium",
    },
    {
        "id": "R05",
        "question": "취학 자녀의 학교가 해당 주소지 기준으로 배정되었습니까?",
        "followup_if_yes": "학교 재학 증명서 등으로 거주 사실을 추가 입증할 수 있습니다.",
        "impact": "low",  # 보강 증거
    },
]

# 인터뷰 질문 중 고영향(high) 항목만 따로 참조
_HIGH_IMPACT_QUESTION_IDS: List[str] = [
    q["id"] for q in RESIDENCE_INTERVIEW_QUESTIONS if q["impact"] == "high"
]


# ── 핵심 함수 ─────────────────────────────────────────────────────────────────

def _years_between(start: date, end: date) -> float:
    """두 날짜 사이 경과 연수를 365.25일 기준으로 계산한다."""
    delta_days = (end - start).days
    return max(0.0, delta_days / 365.25)


def build_interview_from_facts(
    declared_residence_years: float,
    transfer_date: date,
    acquisition_date: date,
    adjustment_area_at_acquisition: bool,
) -> ResidenceInterviewResult:
    """
    사실관계에서 인터뷰 결과 초안을 생성한다.

    - 보유기간 전체를 주민등록 기준 거주로 가정한 최초 상태를 만든다.
    - 조정대상지역 취득 여부에 따라 필요 거주기간을 판별한다.
    - 거주기간이 경계값(±0.5년) 이내이면 고영향 질문을 우선 배치한다.
    - 증빙 확인이 필요한 항목을 missing_evidence_warnings에 담는다.

    Parameters
    ----------
    declared_residence_years:
        사용자가 신고한(또는 주민등록 기준) 거주기간(연수).
    transfer_date:
        양도일.
    acquisition_date:
        취득일.
    adjustment_area_at_acquisition:
        취득 당시 조정대상지역 여부.
        2017.8.3 이전 취득분은 호출 전에 False로 처리해야 한다.

    Returns
    -------
    ResidenceInterviewResult
    """
    holding_years = _years_between(acquisition_date, transfer_date)

    # 조정지역이라도 2017.8.3 이전 취득은 거주요건 없음
    is_rule_applicable = (
        adjustment_area_at_acquisition
        and acquisition_date >= _ADJUSTMENT_AREA_RESIDENCE_RULE_START
    )

    required_years = (
        _REQUIRED_RESIDENCE_YEARS_ADJUSTMENT
        if is_rule_applicable
        else _REQUIRED_RESIDENCE_YEARS_NON_ADJUSTMENT
    )

    # 선언 거주기간은 보유기간을 초과할 수 없다
    capped_declared = min(declared_residence_years, holding_years)

    # 초기 verified는 선언값과 동일하게 시작 (인터뷰 답변에 따라 조정)
    verified_residence_years = capped_declared

    # 잠재적 추가 인정 상한: 현재 선언값과 보유기간의 차이
    potential_gain_years = max(0.0, holding_years - capped_declared)

    # ── 증빙 경고 ──────────────────────────────────────────────────────────────
    missing_evidence_warnings: List[str] = []
    if is_rule_applicable and capped_declared < required_years:
        missing_evidence_warnings.append(
            f"조정대상지역 취득 주택은 2년 거주 요건이 필요합니다. "
            f"현재 신고 거주기간({capped_declared:.1f}년)이 미달입니다. "
            f"실질 거주기간을 증빙 자료로 보완해야 합니다."
        )
    if capped_declared < 1.0:
        missing_evidence_warnings.append(
            "거주기간이 1년 미만입니다. 공과금 납부 내역, 카드 사용 내역 등 "
            "실거주 증빙 자료가 필수입니다."
        )

    # ── 인터뷰 질문 선택 ───────────────────────────────────────────────────────
    # 거주요건 경계값 근처이거나 요건 미달이면 고영향 질문을 앞에 배치
    threshold_check = check_residence_exemption_threshold(
        verified_years=capped_declared,
        is_adjustment_area=is_rule_applicable,
    )

    ordered_questions: List[str] = []
    if not threshold_check["is_satisfied"] or threshold_check["is_borderline"]:
        # 고영향 질문 우선
        for q in RESIDENCE_INTERVIEW_QUESTIONS:
            if q["impact"] == "high":
                ordered_questions.append(q["question"])
                if "followup_if_no" in q:
                    ordered_questions.append(f"  → {q['followup_if_no']}")
        for q in RESIDENCE_INTERVIEW_QUESTIONS:
            if q["impact"] != "high":
                ordered_questions.append(q["question"])
    else:
        # 요건 충족 시 경량 인터뷰 (보강 증거 수집 목적)
        ordered_questions = [
            q["question"]
            for q in RESIDENCE_INTERVIEW_QUESTIONS
            if q["impact"] in ("medium", "low")
        ]

    # ── 종합 판단 ──────────────────────────────────────────────────────────────
    # 증빙으로 확인 가능 여부: 공과금·학교·재직 증빙이 있으면 True로 가정
    # (실제 증빙은 사용자가 답변해야 알 수 있으므로 초안은 보수적으로 False)
    can_verify = len(missing_evidence_warnings) == 0

    # 세무사 면담이 필요한 경우
    # ① 경계값 이내이고 요건 미충족, ② 잠재 이득이 크고(0.5년 이상) 고영향 질문에 답 필요
    needs_expert = (
        (threshold_check["is_borderline"] and not threshold_check["is_satisfied"])
        or (potential_gain_years >= 0.5 and not threshold_check["is_satisfied"])
    )

    # 초기 evidence_items: 주민등록 기준 전체 보유기간을 단일 항목으로 표현
    evidence_items: List[ResidenceEvidenceItem] = [
        ResidenceEvidenceItem(
            period_start=acquisition_date,
            period_end=transfer_date,
            evidence_type="주민등록",
            description=f"주민등록 기준 보유기간 전체 ({holding_years:.1f}년), 실질 거주 여부 미확인",
            is_actual_residence=False,  # 인터뷰 전이므로 미확인 상태
        )
    ]

    return ResidenceInterviewResult(
        declared_residence_years=capped_declared,
        verified_residence_years=verified_residence_years,
        evidence_items=evidence_items,
        missing_evidence_warnings=missing_evidence_warnings,
        interview_questions=ordered_questions,
        can_verify=can_verify,
        potential_gain_years=potential_gain_years,
        needs_expert=needs_expert,
    )


def check_residence_exemption_threshold(
    verified_years: float,
    is_adjustment_area: bool,
) -> dict:
    """
    거주기간이 비과세 요건(2년)을 충족하는지 + 경계값을 분석한다.

    - 조정대상지역(2017.8.3 이후 취득): 2년 거주 필요 (소득세법 §154①)
    - 비조정지역 또는 2017.8.3 이전 취득: 거주 요건 없음 → 자동 충족

    Parameters
    ----------
    verified_years:
        인터뷰 또는 증빙으로 확인된 실질 거주기간(연수).
    is_adjustment_area:
        취득 당시 조정대상지역 여부 (2017.8.3 이전 취득분은 False로 호출).

    Returns
    -------
    dict with keys:
        required_years (float): 필요 거주연수 (0.0 또는 2.0)
        is_satisfied (bool): 거주요건 충족 여부
        margin_years (float): 충족 시 여유연수, 미충족 시 부족연수 (항상 양수)
        is_borderline (bool): 충족/미충족 경계값 ±0.5년 이내
    """
    required_years = (
        _REQUIRED_RESIDENCE_YEARS_ADJUSTMENT
        if is_adjustment_area
        else _REQUIRED_RESIDENCE_YEARS_NON_ADJUSTMENT
    )

    if required_years == 0.0:
        # 거주 요건 없음 — 무조건 충족
        return {
            "required_years": 0.0,
            "is_satisfied": True,
            "margin_years": 0.0,
            "is_borderline": False,
        }

    is_satisfied = verified_years >= required_years
    margin_years = abs(verified_years - required_years)
    is_borderline = margin_years <= _BORDERLINE_MARGIN_YEARS

    return {
        "required_years": required_years,
        "is_satisfied": is_satisfied,
        "margin_years": margin_years,
        "is_borderline": is_borderline,
    }


def generate_expert_referral_message(result: ResidenceInterviewResult) -> str:
    """
    세무사 연결이 필요한 경우 전달할 요약 메시지를 생성한다.

    Parameters
    ----------
    result:
        build_interview_from_facts()로 생성한 인터뷰 결과.

    Returns
    -------
    str: 세무사에게 전달할 요약 메시지 (한국어)
    """
    if not result.needs_expert:
        return (
            "현재 사실관계에서는 세무사 면담 없이도 거주요건 판단이 가능합니다. "
            "증빙 자료를 갖추고 신고를 진행하시기 바랍니다."
        )

    lines: List[str] = [
        "[실거주 요건 세무사 검토 요청]",
        "",
        f"신고 거주기간: {result.declared_residence_years:.1f}년",
        f"검증된 거주기간: {result.verified_residence_years:.1f}년",
        f"추가 인정 가능 상한: {result.potential_gain_years:.1f}년",
        "",
    ]

    if result.missing_evidence_warnings:
        lines.append("[증빙 부족 항목]")
        for w in result.missing_evidence_warnings:
            lines.append(f"  - {w}")
        lines.append("")

    if result.evidence_items:
        lines.append("[수집된 증빙 항목]")
        for item in result.evidence_items:
            status = "실거주" if item.is_actual_residence else "미확인"
            lines.append(
                f"  - {item.period_start} ~ {item.period_end} "
                f"[{item.evidence_type}] {item.description} ({status})"
            )
        lines.append("")

    lines.append("[추가 확인 필요 사항]")
    for q in result.interview_questions:
        lines.append(f"  Q. {q}")
    lines.append("")

    lines.append(
        "실거주 여부는 주민등록 외에 공과금 납부 내역, 카드 사용 내역, "
        "학교 재학 증명서, 직장 재직 증명서 등 객관적 증빙으로 입증해야 합니다. "
        "세무 전문가와 함께 증빙 자료를 정리하시기 바랍니다."
    )

    return "\n".join(lines)
