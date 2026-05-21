"""
취득일 결정론 모듈.

법적 취득일(잔금일 vs 등기일 선후 판단)을 결정적으로 계산.
LLM 없음 — 순수 결정론 코드.
"""
from __future__ import annotations

from datetime import date
from typing import Optional


def resolve_acquisition_date(
    balance_payment_date: Optional[date],
    registration_date: Optional[date],
    contract_date: Optional[date] = None,
) -> Optional[date]:
    """
    소득세법상 취득일 = min(잔금일, 등기접수일).
    둘 다 없으면 계약일 반환 (fallback — 보수적 처리).
    셋 다 없으면 None.

    근거: 소득세법 시행령 §162①1호
    """
    candidates = [d for d in (balance_payment_date, registration_date) if d is not None]
    if candidates:
        return min(candidates)
    return contract_date  # fallback


def resolve_transfer_date(
    balance_payment_date: Optional[date],
    registration_date: Optional[date],
    contract_date: Optional[date] = None,
) -> Optional[date]:
    """
    양도일도 동일 규칙: min(잔금일, 등기접수일).
    근거: 소득세법 시행령 §162①1호
    """
    return resolve_acquisition_date(balance_payment_date, registration_date, contract_date)
