"""
골든셋 자동 평가 실행기.

qa_pairs.json의 모든 케이스를 현재 파이프라인으로 실행하고,
각 케이스의 last_eval 필드를 갱신한 뒤 전체 리포트를 저장한다.

사용법:
    python -m scripts.run_golden_eval                  # 전체 실행
    python -m scripts.run_golden_eval --limit 10       # 처음 N건만
    python -m scripts.run_golden_eval --workers 2      # 병렬 수 (기본 2)
    python -m scripts.run_golden_eval --report-only    # 기존 결과 요약만

법령 개정 후 자동 실행:
    detect_law_changes.py → flag_for_review() → 이 스크립트로 재평가
"""
from __future__ import annotations

import argparse
import asyncio
import io
import json
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

# Windows 콘솔 UTF-8
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent.parent))

GOLDEN_FILE = Path("data/golden/qa_pairs.json")
RESULTS_DIR = Path("data/eval_results")
LATEST_FILE = RESULTS_DIR / "golden_eval_latest.json"

# expected_verdict 정규화 테이블 (영문↔한글 별칭)
_VERDICT_NORM: dict[str, str] = {
    "exempt": "비과세",
    "taxable": "일반과세",
    "uncertain": "사실관계부족",
    "heavy": "중과",
    "short": "단기세율",
    "reduced": "감면",
    "expensive": "고가주택",
}


def _normalize_verdict(v: str) -> str:
    return _VERDICT_NORM.get(v, v)


@dataclass
class CaseEvalResult:
    case_id: str
    description: str
    expected_verdict: Optional[str]
    actual_verdict: str
    match: Optional[bool]
    confidence: float
    blocked: bool
    invalidated: bool
    elapsed_s: float
    run_at: str
    error: Optional[str] = None


def _load_golden() -> list[dict]:
    if not GOLDEN_FILE.exists():
        return []
    return json.loads(GOLDEN_FILE.read_text(encoding="utf-8"))


def _save_golden(cases: list[dict]) -> None:
    GOLDEN_FILE.write_text(
        json.dumps(cases, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


async def _run_case(case: dict) -> CaseEvalResult:
    from src.api.chat_api import chat_turn

    t0 = time.monotonic()
    run_at = datetime.now().strftime("%Y%m%d_%H%M%S")
    case_id = case.get("id") or case.get("case_id", "unknown")
    invalidated = bool(case.get("invalidated", False))

    # 예상 판결 — debate 케이스는 'verdict', 수동 케이스는 'expected_verdict'
    expected_raw = case.get("expected_verdict") or case.get("verdict")
    expected = _normalize_verdict(expected_raw) if expected_raw else None

    try:
        fact_json = case.get("fact_json")
        question = case.get("question") if not fact_json else None

        result = await chat_turn(
            fact_json=fact_json,
            question=question,
            enable_debate=False,
        )
        actual = _normalize_verdict(result.get("verdict", ""))
        confidence = result.get("confidence", 0.0)
        blocked = result.get("blocked", False)
        error = None
    except Exception as e:
        actual = "오류"
        confidence = 0.0
        blocked = False
        error = str(e)

    elapsed = time.monotonic() - t0

    match: Optional[bool] = None
    if expected and actual not in ("오류",):
        match = expected == actual

    return CaseEvalResult(
        case_id=case_id,
        description=case.get("description", ""),
        expected_verdict=expected,
        actual_verdict=actual,
        match=match,
        confidence=confidence,
        blocked=blocked,
        invalidated=invalidated,
        elapsed_s=round(elapsed, 2),
        run_at=run_at,
        error=error,
    )


def _print_report(report: dict) -> None:
    results = report.get("results", [])
    total = len(results)
    if not total:
        print("결과 없음")
        return

    has_expected = [r for r in results if r.get("expected_verdict")]
    passed = [r for r in has_expected if r.get("match") is True]
    failed = [r for r in has_expected if r.get("match") is False]
    errors = [r for r in results if r.get("error")]
    blocked = [r for r in results if r.get("blocked")]
    invalidated = [r for r in results if r.get("invalidated")]

    acc = len(passed) / len(has_expected) * 100 if has_expected else 0
    run_at = report.get("run_at", "")[:16]

    print(f"\n{'='*60}")
    print(f"  골든셋 평가 리포트  ({run_at})")
    print(f"{'='*60}")
    print(f"  총 케이스  : {total}건")
    print(f"  정답 비교  : {len(has_expected)}건")
    if has_expected:
        print(f"  ✅ 통과    : {len(passed)}건")
        print(f"  ❌ 실패    : {len(failed)}건")
        print(f"  정확도     : {acc:.1f}%")
    print(f"  차단(L2)   : {len(blocked)}건")
    print(f"  오류       : {len(errors)}건")
    print(f"  재검토 필요: {len(invalidated)}건 (법령 개정 영향)")

    if failed:
        print(f"\n  [실패 케이스]")
        for r in failed:
            print(
                f"    {r['case_id'][:8]}  "
                f"예상={r['expected_verdict']}  실제={r['actual_verdict']}  "
                f"({r.get('confidence', 0):.2f})  — {r['description'][:40]}"
            )

    if errors:
        print(f"\n  [오류 케이스]")
        for r in errors:
            print(f"    {r['case_id'][:8]}  {r.get('error', '')[:60]}")

    print(f"{'='*60}")


async def main_async(args: argparse.Namespace) -> None:
    if args.report_only:
        if LATEST_FILE.exists():
            _print_report(json.loads(LATEST_FILE.read_text(encoding="utf-8")))
        else:
            print("평가 결과 없음. 먼저 평가를 실행하세요.")
        return

    cases = _load_golden()
    if not cases:
        print("골든셋이 비어 있습니다.")
        return

    target = cases[: args.limit] if args.limit else cases
    total = len(target)

    print(f"=== 골든셋 평가 ===")
    print(f"케이스: {total}건 | workers: {args.workers}")
    print()

    results: list[dict] = []
    semaphore = asyncio.Semaphore(args.workers)
    lock = asyncio.Lock()
    counter = [0]

    # case_id → index in `cases` for in-place update
    id_to_idx: dict[str, int] = {
        (c.get("id") or c.get("case_id", "")): i for i, c in enumerate(cases)
    }

    async def _run_with_sem(case: dict) -> tuple[dict, CaseEvalResult]:
        async with semaphore:
            res = await _run_case(case)
            return case, res

    tasks = [asyncio.create_task(_run_with_sem(c)) for c in target]
    for task in asyncio.as_completed(tasks):
        case, res = await task
        async with lock:
            counter[0] += 1
            idx = counter[0]
            match_str = "✅" if res.match is True else ("❌" if res.match is False else "—")
            inv_str = " ⚠️재검토" if res.invalidated else ""
            print(
                f"  [{idx:3d}/{total}] {match_str} {res.actual_verdict:<10s} "
                f"({res.confidence:.2f}){inv_str}  {res.description[:35]}"
            )

            # qa_pairs.json 업데이트
            orig_idx = id_to_idx.get(res.case_id)
            if orig_idx is not None:
                cases[orig_idx]["last_eval"] = {
                    "verdict": res.actual_verdict,
                    "match": res.match,
                    "confidence": res.confidence,
                    "blocked": res.blocked,
                    "run_at": res.run_at,
                    "error": res.error,
                }
                if not cases[orig_idx].get("validated_at"):
                    cases[orig_idx]["validated_at"] = datetime.now().strftime("%Y%m%d")

            results.append(asdict(res))

    # 갱신된 golden 저장
    _save_golden(cases)

    now_str = datetime.now().isoformat()
    report = {"run_at": now_str, "total": total, "results": results}

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    LATEST_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    archived = RESULTS_DIR / f"golden_eval_{ts}.json"
    archived.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    _print_report(report)
    print(f"\n결과 저장: {LATEST_FILE}")
    print(f"이력 저장: {archived}")


def main() -> None:
    parser = argparse.ArgumentParser(description="골든셋 자동 평가 실행기")
    parser.add_argument("--limit", type=int, default=0, help="처음 N건만 실행 (0=전체)")
    parser.add_argument("--workers", type=int, default=2, help="병렬 워커 수")
    parser.add_argument("--report-only", action="store_true", help="기존 결과 요약만 출력")
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
