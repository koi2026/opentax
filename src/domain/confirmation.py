"""
L1.5 — Confirmation Gate

사실관계 완전성(L2)과 다른 레이어: 사용자의 명시적 확약을 요구.
4개 항목 중 하나라도 미확인이면 파이프라인 진입 차단.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


CONFIRMATION_ITEMS: Dict[str, str] = {
    "household_house_count_verified": (
        "세대 전체 주택 수를 정확히 파악했습니까? "
        "(본인 및 세대원 보유 주택 모두 포함)"
    ),
    "balance_or_registration_date_used": (
        "잔금 지급일과 등기접수일 중 먼저 도래한 날짜를 취득일/양도일로 사용했습니까?"
    ),
    "no_related_party": (
        "매수인/매도인이 특수관계인(배우자, 직계존비속, 형제자매, 경제적 연관관계)이 "
        "아님을 확인했습니까?"
    ),
    "actual_residence_verified": (
        "거주기간은 주민등록 전입 후 실제 거주한 기간만 포함했습니까? "
        "(주민등록만 이전하고 실제 거주하지 않은 기간 제외)"
    ),
}


@dataclass
class ConfirmationResult:
    can_proceed: bool
    unconfirmed_items: List[str] = field(default_factory=list)   # keys of unconfirmed items
    unconfirmed_questions: List[str] = field(default_factory=list)  # human-readable questions


def check_confirmation(confirmed: Optional[Dict[str, bool]]) -> ConfirmationResult:
    """
    Check whether the user has explicitly attested to all 4 confirmation items.

    Args:
        confirmed: dict mapping confirmation key -> True/False.
                   None = caller has not implemented confirmation yet (pass-through).
                   Empty dict or partial dict = actively blocks unconfirmed items.

    Returns:
        ConfirmationResult with can_proceed=True only when all 4 keys are True.
    """
    if confirmed is None:
        return ConfirmationResult(can_proceed=True)

    unconfirmed_keys: List[str] = []
    unconfirmed_questions: List[str] = []

    for key, question in CONFIRMATION_ITEMS.items():
        if not confirmed.get(key, False):
            unconfirmed_keys.append(key)
            unconfirmed_questions.append(question)

    return ConfirmationResult(
        can_proceed=len(unconfirmed_keys) == 0,
        unconfirmed_items=unconfirmed_keys,
        unconfirmed_questions=unconfirmed_questions,
    )
