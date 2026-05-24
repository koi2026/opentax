"""
Verdict matcher — binary reward(1/0) 자동 계산.

골든셋(qa_pairs.json)과 파이프라인 출력을 비교하여 reward 산출.
RLVR 루프에서 BGE reranker 파인튜닝 신호로 사용.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
from typing import List, Optional


VERDICT_ALIASES: dict[str, list[str]] = {
    "비과세": ["비과세", "exempt"],
    "감면": ["감면", "reduced"],
    "중과": ["중과", "heavy_tax"],
    "일반과세": ["일반과세", "general", "taxable", "과세"],
    "단기세율": ["단기세율", "short_term"],
    "고가주택": ["고가주택", "partially_exempt"],
    "사실관계부족": ["사실관계부족", "needs_verification", "uncertain"],
}


@dataclass
class RewardSignal:
    case_id: str
    expected_verdict: str
    actual_verdict: str
    reward: int                  # 1 = 정답, 0 = 오답
    verdict_match: bool
    confidence: float
    chunk_ids: List[str]
    notes: str = ""


def compute_reward(
    case_id: str,
    expected_verdict: str,
    actual_verdict: str,
    confidence: float,
    chunk_ids: Optional[List[str]] = None,
) -> RewardSignal:
    """
    Binary reward: verdict 일치 = 1, 불일치 = 0.

    verdict 비교는 alias 정규화 후 수행 (한글/영문 혼용 대응).
    """
    def _normalize(v: str) -> str:
        v = v.strip().lower()
        for canonical, aliases in VERDICT_ALIASES.items():
            if v in [a.lower() for a in aliases]:
                return canonical
        return v

    norm_expected = _normalize(expected_verdict)
    norm_actual = _normalize(actual_verdict)
    match = norm_expected == norm_actual

    return RewardSignal(
        case_id=case_id,
        expected_verdict=expected_verdict,
        actual_verdict=actual_verdict,
        reward=1 if match else 0,
        verdict_match=match,
        confidence=confidence,
        chunk_ids=chunk_ids or [],
        notes="" if match else f"Expected {norm_expected!r}, got {norm_actual!r}",
    )


def batch_evaluate(
    golden_path: Path,
    predictions: List[dict],
) -> List[RewardSignal]:
    """
    golden_path: data/golden/qa_pairs.json
    predictions: [{"case_id", "verdict", "confidence", "chunk_ids"}, ...]
    """
    golden = json.loads(golden_path.read_text(encoding="utf-8"))
    golden_by_id = {g["case_id"]: g for g in golden if "case_id" in g}

    signals = []
    for pred in predictions:
        case_id = pred.get("case_id", "unknown")
        expected = golden_by_id.get(case_id, {}).get("verdict", "")
        if not expected:
            continue
        signal = compute_reward(
            case_id=case_id,
            expected_verdict=expected,
            actual_verdict=pred.get("verdict", ""),
            confidence=pred.get("confidence", 0.0),
            chunk_ids=pred.get("chunk_ids", []),
        )
        signals.append(signal)

    return signals


def compute_accuracy(signals: List[RewardSignal]) -> float:
    """전체 정확도 계산."""
    if not signals:
        return 0.0
    return sum(s.reward for s in signals) / len(signals)
