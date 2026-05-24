"""
골든셋 → L4 few-shot 주입기.

debate.py가 blue_won/no_contest 케이스를 data/golden/qa_pairs.json에 쌓으면,
이 모듈이 현재 질문과 유사한 케이스를 골라 L4 프롬프트에 예시로 주입한다.

유사도 기준:
  1. property_type 일치
  2. acquisition_reason 일치
  3. household_house_count 일치
  4. 특례 플래그 겹침 수
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

GOLDEN_FILE = Path("data/golden/qa_pairs.json")
MAX_SHOTS = 2        # 프롬프트에 주입할 최대 예시 수
MIN_GOLDEN = 5       # 골든셋 최소 크기 (이하면 주입 안 함)


def _load_golden() -> list[dict]:
    if not GOLDEN_FILE.exists():
        return []
    with GOLDEN_FILE.open(encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []


def _score_similarity(fact_json: dict, golden_fact: dict) -> int:
    """두 fact_json의 유사도 점수 (높을수록 유사)."""
    score = 0
    for key in ("property_type", "acquisition_reason"):
        if fact_json.get(key) == golden_fact.get(key):
            score += 3
    if fact_json.get("household_house_count") == golden_fact.get("household_house_count"):
        score += 2

    # 특례 플래그 겹침
    sc1 = set((fact_json.get("special_cases") or {}).keys())
    sc2 = set((golden_fact.get("special_cases") or {}).keys())
    score += len(sc1 & sc2)

    return score


def find_similar_cases(fact_json: dict, top_n: int = MAX_SHOTS) -> list[dict]:
    """fact_json과 가장 유사한 골든 케이스 top_n개 반환."""
    golden = _load_golden()
    if len(golden) < MIN_GOLDEN:
        return []

    usable = [g for g in golden if g.get("source") == "debate" and g.get("verdict")]
    if len(usable) < MIN_GOLDEN:
        return []
    scored = [(g, _score_similarity(fact_json, g.get("fact_json", {}))) for g in usable]
    scored.sort(key=lambda x: -x[1])
    return [g for g, s in scored[:top_n] if s > 0]


def build_few_shot_block(fact_json: dict) -> str:
    """
    L4 프롬프트에 삽입할 few-shot 블록 생성.
    유사 케이스가 없으면 빈 문자열 반환.
    """
    cases = find_similar_cases(fact_json)
    if not cases:
        return ""

    lines = ["[참고 — 유사 케이스 검증 사례]"]
    for i, case in enumerate(cases, 1):
        lines.append(
            f"\n예시 {i}. {case.get('fact_json', {}).get('property_type', '')} "
            f"/ {case.get('fact_json', {}).get('acquisition_reason', '')} "
            f"/ {case.get('fact_json', {}).get('household_house_count', '')}주택"
        )
        lines.append(f"  판단: {case.get('verdict', '')}")
        answer_preview = (case.get("answer") or "")[:200]
        lines.append(f"  근거: {answer_preview}")
        if case.get("citations"):
            lines.append(f"  인용: {', '.join(case['citations'][:3])}")

    return "\n".join(lines)


def golden_summary() -> dict:
    """골든셋 현황."""
    golden = _load_golden()
    debate_cases = [g for g in golden if g.get("source") == "debate"]
    verdicts: dict[str, int] = {}
    for g in debate_cases:
        v = g.get("verdict", "unknown")
        verdicts[v] = verdicts.get(v, 0) + 1
    return {
        "total_golden": len(golden),
        "debate_sourced": len(debate_cases),
        "verdict_distribution": verdicts,
    }
