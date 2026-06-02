"""
골든셋 gold_chunk_ids 자동 부트스트랩.

synthetic_comprehensive.json + qa_pairs.json의 케이스를 파이프라인으로 실행하여,
verdict가 일치하고 confidence >= 0.7인 경우 chunk_ids를 gold_chunk_ids로 등록.

한 번만 실행하면 됨. 이후 eval.py가 Recall@K를 의미 있는 값으로 리포트.

사용법:
    python -m scripts.bootstrap_gold_chunks
    python -m scripts.bootstrap_gold_chunks --min-confidence 0.8
    python -m scripts.bootstrap_gold_chunks --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import io
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from src.eval.verdict_matcher import compute_reward

GOLDEN_FILES = [
    Path("data/golden/synthetic_comprehensive.json"),
    Path("data/golden/qa_pairs.json"),
    Path("data/golden/synthetic_cases.json"),
]
MIN_CONFIDENCE_DEFAULT = 0.7


async def _run_case(case: dict) -> dict:
    """케이스를 파이프라인으로 실행하여 verdict + chunk_ids 반환."""
    from src.api.chat_api import chat_turn
    fact_json = case.get("fact_json")
    if not fact_json:
        return {"verdict": "", "confidence": 0.0, "chunk_ids": []}
    try:
        result = await chat_turn(fact_json=fact_json, enable_debate=False)
        return {
            "verdict": result.get("verdict", ""),
            "confidence": result.get("confidence", 0.0),
            "chunk_ids": result.get("chunk_ids", []),
        }
    except Exception as e:
        return {"verdict": "", "confidence": 0.0, "chunk_ids": [], "error": str(e)}


def _load_cases(path: Path) -> list[dict]:
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return raw
    return raw.get("cases", [])


def _save_cases(path: Path, cases: list[dict]) -> None:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        path.write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        raw["cases"] = cases
        path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")


async def bootstrap(min_confidence: float, dry_run: bool) -> None:
    total_updated = 0
    total_skipped_no_verdict = 0
    total_skipped_mismatch = 0
    total_already_done = 0
    total_no_fact_json = 0

    for file_path in GOLDEN_FILES:
        cases = _load_cases(file_path)
        if not cases:
            continue

        print(f"\n── {file_path.name} ({len(cases)}건) ──")
        updated_in_file = 0

        for i, case in enumerate(cases):
            expected_verdict = case.get("expected_verdict")
            case_id = case.get("case_id") or case.get("id") or f"idx_{i}"

            if not case.get("fact_json"):
                total_no_fact_json += 1
                continue

            if not expected_verdict:
                total_skipped_no_verdict += 1
                continue

            if case.get("gold_chunk_ids"):
                total_already_done += 1
                continue

            print(f"  [{i+1:03d}] {case.get('description', '')[:50]}...", flush=True)

            result = await _run_case(case)
            actual_verdict = result["verdict"]
            confidence = result["confidence"]
            chunk_ids = result["chunk_ids"]

            if not actual_verdict:
                print("→ verdict 없음 스킵")
                total_skipped_mismatch += 1
                continue

            signal = compute_reward(
                case_id=case_id,
                expected_verdict=expected_verdict,
                actual_verdict=actual_verdict,
                confidence=confidence,
                chunk_ids=chunk_ids,
            )

            if signal.verdict_match and confidence >= min_confidence and chunk_ids:
                print(f"→ ✓ {actual_verdict} (conf={confidence:.2f}) → {len(chunk_ids)}개 청크 등록")
                if not dry_run:
                    case["gold_chunk_ids"] = chunk_ids
                    case["gold_confidence"] = confidence
                updated_in_file += 1
                total_updated += 1
            else:
                reason = f"verdict불일치({actual_verdict}≠{expected_verdict})" if not signal.verdict_match else f"confidence낮음({confidence:.2f}<{min_confidence})"
                print(f"→ ✗ {reason}")
                total_skipped_mismatch += 1

        if updated_in_file > 0 and not dry_run:
            _save_cases(file_path, cases)
            print(f"  저장 완료: {file_path.name} ({updated_in_file}건 업데이트)")

    print(f"\n=== 결과 ===")
    print(f"  gold_chunk_ids 신규 등록 : {total_updated}건")
    print(f"  이미 등록된 케이스       : {total_already_done}건")
    print(f"  expected_verdict 없음    : {total_skipped_no_verdict}건")
    print(f"  fact_json 없음           : {total_no_fact_json}건")
    print(f"  verdict 불일치/confidence낮음: {total_skipped_mismatch}건")
    if dry_run:
        print("\n[dry-run] 실제 저장 안 함. --dry-run 없이 재실행하면 저장됩니다.")


def main() -> None:
    parser = argparse.ArgumentParser(description="골든셋 gold_chunk_ids 자동 부트스트랩")
    parser.add_argument("--min-confidence", type=float, default=MIN_CONFIDENCE_DEFAULT,
                        help=f"gold 등록 최소 confidence (기본: {MIN_CONFIDENCE_DEFAULT})")
    parser.add_argument("--dry-run", action="store_true",
                        help="저장하지 않고 결과만 확인")
    args = parser.parse_args()

    print(f"gold_chunk_ids 부트스트랩 시작 (min_confidence={args.min_confidence})")
    if args.dry_run:
        print("[dry-run 모드]")

    asyncio.run(bootstrap(args.min_confidence, args.dry_run))


if __name__ == "__main__":
    main()
