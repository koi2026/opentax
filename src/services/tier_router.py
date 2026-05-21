"""
3-티어 상담 라우터.

Bot    : 필수 서식 미제출 → 자료 재요청 (무료, 세무사 연결 없음)
Quick  : 사실관계 불명·특례 애매 → 세무사 채팅 1~2 질문 (5~10만원)
Premium: 3주택 이상·예규 공백·조세불복 가능 → 대면/전화 풀패키지 (30~50만원)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Literal, Optional

from src.domain.pipeline import PipelineResult
from src.domain.tax_answer import ExpertReviewSignal


TierType = Literal["bot", "quick", "premium"]


@dataclass
class TierDecision:
    tier: TierType
    reason: str
    triggers: List[str]              # 어떤 조건이 티어를 결정했는지
    cta_message: str                  # 사용자 화면에 노출할 행동 유도 문구
    estimated_fee_range: Optional[str] = None  # "5~10만원" 등


def route_tier(result: PipelineResult) -> TierDecision:
    """
    파이프라인 결과를 보고 상담 티어를 결정.

    우선순위: Premium > Quick > Bot
    """
    answer = result.answer

    # ── Premium 트리거 ─────────────────────────────────────────────────────
    premium_triggers = _check_premium_triggers(answer.expert_review_signals, answer.warnings, result)
    if premium_triggers:
        return TierDecision(
            tier="premium",
            reason="전문가 검토가 필요한 고난도 케이스입니다.",
            triggers=premium_triggers,
            cta_message=(
                "이 케이스는 예규·판례 해석이 필요하거나 세액 규모가 큽니다. "
                "세무사와 직접 상담하시면 절세 기회를 최대한 찾을 수 있습니다."
            ),
            estimated_fee_range="30~50만원",
        )

    # ── Quick 트리거 ────────────────────────────────────────────────────────
    quick_triggers = _check_quick_triggers(answer, result)
    if quick_triggers:
        return TierDecision(
            tier="quick",
            reason="추가 확인이 필요한 사항이 있습니다.",
            triggers=quick_triggers,
            cta_message=(
                "1~2가지 추가 질문으로 정확한 판단이 가능합니다. "
                "세무사 채팅 상담을 통해 빠르게 확인해 드립니다."
            ),
            estimated_fee_range="5~10만원",
        )

    # ── Bot (자료 재요청) ───────────────────────────────────────────────────
    return TierDecision(
        tier="bot",
        reason="자동 처리 완료",
        triggers=["사실관계 완비", "자동 판단 가능"],
        cta_message="판단이 완료되었습니다. 추가 서류가 필요한 경우 아래 목록을 확인해 주세요.",
        estimated_fee_range=None,
    )


def _check_premium_triggers(
    signals: List[ExpertReviewSignal],
    warnings: List[str],
    result: PipelineResult,
) -> List[str]:
    triggers = []

    for sig in signals:
        if sig.category in ("예규공백", "조세불복가능", "판례의존"):
            triggers.append(f"{sig.category}: {sig.description[:50]}")

    # 3주택 이상
    fc = result.fact_check
    if fc and any("3주택" in f or "다주택" in f for f in fc.danger_flags):
        triggers.append("3주택 이상 다주택자")

    # confidence 낮음 + 고가주택
    if result.answer.confidence < 0.7 and any("고가주택" in w for w in warnings):
        triggers.append("저신뢰도 + 고가주택 복합")

    return triggers


def _check_quick_triggers(answer, result: PipelineResult) -> List[str]:
    triggers = []

    # missing_facts 있지만 critical 아닌 경우
    if answer.missing_facts:
        triggers.append(f"추가 확인 필요 사항 {len(answer.missing_facts)}건")

    # 해석다툼 signal
    for sig in answer.expert_review_signals:
        if sig.category == "해석다툼":
            triggers.append(f"해석 불명확: {sig.description[:40]}")

    # 신뢰도 0.7~0.85 구간
    if 0.7 <= answer.confidence < 0.85:
        triggers.append(f"신뢰도 {answer.confidence:.0%} — 전문가 확인 권장")

    return triggers
