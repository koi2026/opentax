"""
Phase A 베이스라인 평가 배치 실행기.

현행법 기준 종합 케이스를 debate 없이 실행하여 현재 파이프라인의 verdict 분포를
측정하고, 추후 fine-tuning을 위한 red_win 데이터를 확보한다.

사용법:
    python -m scripts.eval.run_baseline_eval                   # 전체 실행
    python -m scripts.eval.run_baseline_eval --resume          # 이어서 실행
    python -m scripts.eval.run_baseline_eval --cases-file <path>  # 외부 케이스 파일
    python -m scripts.eval.run_baseline_eval --limit 20        # 처음 N건만
    python -m scripts.eval.run_baseline_eval --debate          # debate 포함 (비용 증가)
    python -m scripts.eval.run_baseline_eval --report-only     # 기존 결과만 요약
"""
from __future__ import annotations

import argparse
import asyncio
import io
import json
import re
import subprocess
import sys
import time

# Windows cp949 콘솔에서 한글/유니코드 문자 인코딩 오류 방지
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

CHECKPOINT_PATH = Path("data/eval_results/baseline_checkpoint.json")
RESULTS_DIR = Path("data/eval_results")
RED_WINS_DIR = Path("data/red_wins")
TRAINING_STATE_PATH = Path("data/models/bge-reranker-tax-rag/training_state.json")
MIN_TOTAL_DEBATES_FOR_TRAIN = 50   # 총 debate 수가 이 미만이면 학습 건너뜀 (초기 품질 보장)
MIN_NEW_DEBATES_FOR_RETRAIN = 20   # 마지막 학습 이후 신규 debate >= 이 수일 때 재학습 트리거
ACCURACY_TARGET = 0.85             # 이 미만이면 다음 eval 사이클 자동 권고

# Claude Sonnet 4.6 기준 비용 추정 (입력 3$/MTok, 출력 15$/MTok)
_COST_PER_CASE_NO_DEBATE = 0.018   # ~$0.018/케이스 (debate 없음)
_COST_PER_CASE_WITH_DEBATE = 0.12  # ~$0.12/케이스 (debate 포함)


@dataclass
class EvalResult:
    case_id: str
    description: str
    boundary_type: str
    tags: List[str]
    verdict: str
    confidence: float
    expected_verdict: Optional[str]
    match: Optional[bool]        # None이면 expected_verdict 없음
    blocked: bool
    missing_facts: List[str]
    warnings: List[str]
    has_debate: bool
    elapsed_s: float
    error: Optional[str] = None


@dataclass
class CheckpointState:
    total: int = 0
    completed: int = 0
    results: List[dict] = field(default_factory=list)
    started_at: str = ""
    last_updated: str = ""


def _load_checkpoint() -> CheckpointState:
    if not CHECKPOINT_PATH.exists():
        return CheckpointState()
    try:
        raw = json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
        state = CheckpointState(
            total=raw.get("total", 0),
            completed=raw.get("completed", 0),
            results=raw.get("results", []),
            started_at=raw.get("started_at", ""),
            last_updated=raw.get("last_updated", ""),
        )
        return state
    except Exception:
        return CheckpointState()


def _save_checkpoint(state: CheckpointState) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    state.last_updated = datetime.now().isoformat()
    CHECKPOINT_PATH.write_text(
        json.dumps(asdict(state), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _completed_ids(state: CheckpointState) -> set[str]:
    return {r["case_id"] for r in state.results}


async def _run_single(
    case: dict,
    enable_debate: bool,
) -> EvalResult:
    from src.application.chat_service import run_chat as chat_turn

    t0 = time.monotonic()
    error: Optional[str] = None
    verdict = ""
    confidence = 0.0
    blocked = False
    missing_facts: List[str] = []
    warnings: List[str] = []
    has_debate = False

    try:
        result = await chat_turn(
            fact_json=case["fact_json"],
            enable_debate=enable_debate,
        )
        verdict = result.get("verdict", "")
        confidence = result.get("confidence", 0.0)
        blocked = result.get("blocked", False)
        missing_facts = result.get("missing_facts", [])
        warnings = result.get("warnings", [])
        has_debate = bool(result.get("debate_record"))
    except Exception as e:
        error = str(e)
        verdict = "오류"
        confidence = 0.0

    elapsed = time.monotonic() - t0
    expected = case.get("expected_verdict")
    match: Optional[bool] = None
    if expected and verdict and verdict != "오류":
        from src.eval.verdict_matcher import compute_reward
        signal = compute_reward(
            case_id=case.get("case_id", ""),
            expected_verdict=expected,
            actual_verdict=verdict,
            confidence=confidence,
        )
        match = signal.verdict_match

    return EvalResult(
        case_id=case["case_id"],
        description=case["description"],
        boundary_type=case.get("boundary_type", ""),
        tags=case.get("tags", []),
        verdict=verdict,
        confidence=confidence,
        expected_verdict=expected,
        match=match,
        blocked=blocked,
        missing_facts=missing_facts,
        warnings=warnings,
        has_debate=has_debate,
        elapsed_s=round(elapsed, 2),
        error=error,
    )


def _print_progress(
    idx: int,
    total: int,
    result: EvalResult,
    elapsed_total: float,
    cost_per_case: float,
) -> None:
    pct = (idx + 1) / total * 100
    est_remaining_cost = (total - idx - 1) * cost_per_case
    if result.match is True:
        match_str = "OK"
    elif result.match is False:
        match_str = "NG"
    elif result.error:
        match_str = "ER"
    else:
        match_str = " -"

    verdict_short = result.verdict[:4] if result.verdict else "오류"
    print(
        f"  [{idx+1:3d}/{total}] {pct:5.1f}% "
        f"{match_str} {verdict_short:<4s} "
        f"({result.confidence:.2f}) "
        f"{result.elapsed_s:.1f}s | "
        f"남은 예상비용 ~${est_remaining_cost:.2f} | "
        f"{result.description[:35]}"
    )


def _count_red_wins() -> int:
    if not RED_WINS_DIR.exists():
        return 0
    return len(list(RED_WINS_DIR.glob("*.json")))


def _load_training_state() -> dict:
    if not TRAINING_STATE_PATH.exists():
        return {}
    try:
        return json.loads(TRAINING_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_training_state(state: dict) -> None:
    TRAINING_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    TRAINING_STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _read_finetune_accuracy(output_dir: Path) -> float | None:
    """파인튜닝 결과 CSV에서 최고 Accuracy 값을 읽어 반환. 파일 없으면 None."""
    csv_path = output_dir / "eval" / "CrossEncoderClassificationEvaluator_tax-rag-eval_results.csv"
    if not csv_path.exists():
        # finetune_reranker.py 기본 output_dir 외부에 저장된 경우 fallback
        csv_path = Path("checkpoints") / "model" / "eval" / "CrossEncoderClassificationEvaluator_tax-rag-eval_results.csv"
    if not csv_path.exists():
        return None
    try:
        import csv as _csv
        rows = list(_csv.DictReader(csv_path.open(encoding="utf-8")))
        if not rows:
            return None
        # 마지막 epoch 행 기준 (best model 저장 시 마지막 행이 최고 성능)
        accuracies = [float(r["Accuracy"]) for r in rows if r.get("Accuracy")]
        return max(accuracies) if accuracies else None
    except Exception:
        return None


def _update_env_model_path(model_path: str) -> None:
    env_path = Path(".env")
    if not env_path.exists():
        return
    content = env_path.read_text(encoding="utf-8")
    if "BGE_RERANKER_MODEL=" in content:
        content = re.sub(r"BGE_RERANKER_MODEL=.*", f"BGE_RERANKER_MODEL={model_path}", content)
    else:
        content += f"\nBGE_RERANKER_MODEL={model_path}\n"
    env_path.write_text(content, encoding="utf-8")


def _maybe_trigger_finetune() -> None:
    current = _count_red_wins()
    last_state = _load_training_state()
    last_count = last_state.get("debate_count", 0)
    delta = current - last_count

    print(f"\n[auto-finetune] red_wins 현재={current}건 / 마지막학습시={last_count}건 / 신규={delta}건")

    if current < MIN_TOTAL_DEBATES_FOR_TRAIN:
        print(f"[auto-finetune] 총 {current}건 < 최소 {MIN_TOTAL_DEBATES_FOR_TRAIN}건 → 데이터 부족, 스킵")
        return

    if delta < MIN_NEW_DEBATES_FOR_RETRAIN:
        print(f"[auto-finetune] 신규 {delta}건 < 임계값 {MIN_NEW_DEBATES_FOR_RETRAIN}건 → 스킵")
        return

    print(f"[auto-finetune] 임계값 초과 → 자동 파인튜닝 시작\n")

    try:
        # 1. pair 추출
        print("=== [1/3] reranker pair 추출 ===")
        subprocess.run(
            [sys.executable, "scripts/training/extract_reranker_pairs.py"],
            check=True,
        )

        # 2. 파인튜닝
        print("\n=== [2/3] BGE 파인튜닝 ===")
        subprocess.run(
            [sys.executable, "scripts/training/finetune_reranker.py"],
            check=True,
        )

        # 3. 정확도 확인 + 학습 상태 저장 + .env 업데이트
        model_path = "data/models/bge-reranker-tax-rag"
        accuracy = _read_finetune_accuracy(Path(model_path))

        print(f"\n=== [3/3] 품질 게이트 확인 ===")

        if accuracy is not None:
            acc_pct = accuracy * 100
            if accuracy >= ACCURACY_TARGET:
                # 품질 통과 → 모델 프로모션
                _save_training_state({
                    "debate_count": current,
                    "trained_at": datetime.now().isoformat(),
                    "model_path": model_path,
                    "accuracy": accuracy,
                    "promoted": True,
                })
                _update_env_model_path(model_path)
                print(f"  정확도: {acc_pct:.1f}% ✓ (목표 {ACCURACY_TARGET*100:.0f}% 달성)")
                print(f"  BGE_RERANKER_MODEL={model_path} (.env 반영)")
                print(f"  다음 파인튜닝 트리거: {current + MIN_NEW_DEBATES_FOR_RETRAIN}건 도달 시")
            else:
                # 품질 미달 → 프로모션 보류 (base model 유지)
                _save_training_state({
                    "debate_count": current,
                    "trained_at": datetime.now().isoformat(),
                    "model_path": model_path,
                    "accuracy": accuracy,
                    "promoted": False,
                })
                print(f"  정확도: {acc_pct:.1f}% ✗ (목표 {ACCURACY_TARGET*100:.0f}% 미달)")
                print(f"  ⚠️  모델 프로모션 보류 — base model 유지 (.env 미변경)")
                print(f"  → 다음 eval 사이클을 실행해 debate를 더 수집하세요.")
                print(f"  → 권장 명령: python -m scripts.eval.run_baseline_eval --debate --auto-finetune --workers 3")
        else:
            _save_training_state({
                "debate_count": current,
                "trained_at": datetime.now().isoformat(),
                "model_path": model_path,
                "accuracy": None,
                "promoted": False,
            })
            print(f"  정확도 CSV 없음 — 프로모션 보류 (수동 확인 필요)")
            print(f"  → python -m scripts.training.finetune_reranker --eval-only 로 재평가하세요.")
            print(f"  다음 파인튜닝 트리거: {current + MIN_NEW_DEBATES_FOR_RETRAIN}건 도달 시")

    except subprocess.CalledProcessError as e:
        print(f"[auto-finetune] 오류 발생: {e} — 수동으로 스크립트를 실행하세요.")


def _print_report(state: CheckpointState) -> None:
    results = state.results
    if not results:
        print("결과 없음.")
        return

    total = len(results)
    has_expected = [r for r in results if r.get("expected_verdict")]
    correct = [r for r in has_expected if r.get("match") is True]
    errors = [r for r in results if r.get("error")]
    blocked = [r for r in results if r.get("blocked")]

    verdict_dist: dict[str, int] = {}
    for r in results:
        v = r.get("verdict", "알수없음")
        verdict_dist[v] = verdict_dist.get(v, 0) + 1

    avg_conf = sum(r.get("confidence", 0) for r in results) / total if total else 0
    avg_elapsed = sum(r.get("elapsed_s", 0) for r in results) / total if total else 0

    print("\n" + "=" * 60)
    print(f"  베이스라인 평가 결과 ({datetime.now().strftime('%Y-%m-%d %H:%M')})")
    print("=" * 60)
    print(f"  총 케이스: {total}건")
    print(f"  정답 비교 가능: {len(has_expected)}건")
    if has_expected:
        acc = len(correct) / len(has_expected) * 100
        print(f"  정확도: {len(correct)}/{len(has_expected)} = {acc:.1f}%")
    print(f"  L2 차단(사실관계부족): {len(blocked)}건")
    print(f"  오류: {len(errors)}건")
    print(f"  평균 신뢰도: {avg_conf:.3f}")
    print(f"  평균 응답시간: {avg_elapsed:.1f}초")
    print(f"\n  Verdict 분포:")
    for v, cnt in sorted(verdict_dist.items(), key=lambda x: -x[1]):
        bar = "█" * cnt
        print(f"    {v:<10s} {cnt:3d}건  {bar}")

    # 정답 있는데 틀린 케이스
    wrong = [r for r in has_expected if r.get("match") is False]
    if wrong:
        print(f"\n  [NG] 오답 {len(wrong)}건:")
        for r in wrong:
            print(
                f"    [{r['case_id']}] 예상={r['expected_verdict']} 실제={r['verdict']}"
                f" ({r['confidence']:.2f}) — {r['description'][:40]}"
            )

    # 신뢰도 낮은 케이스 (0.6 이하)
    low_conf = [r for r in results if r.get("confidence", 1) <= 0.6 and not r.get("error")]
    if low_conf:
        print(f"\n  [!] 낮은 신뢰도 케이스 ({len(low_conf)}건):")
        for r in sorted(low_conf, key=lambda x: x.get("confidence", 0))[:10]:
            print(
                f"    [{r['case_id']}] conf={r['confidence']:.2f} "
                f"verdict={r['verdict']} — {r['description'][:40]}"
            )

    print("=" * 60)


def _load_cases_from_file(path: Path) -> List[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


async def main_async(args: argparse.Namespace) -> None:
    from src.eval.case_generator import generate_all_comprehensive_cases, SyntheticCase
    from dataclasses import asdict as dc_asdict

    cost_per_case = _COST_PER_CASE_WITH_DEBATE if args.debate else _COST_PER_CASE_NO_DEBATE

    # 케이스 로드
    if args.cases_file:
        raw_cases = _load_cases_from_file(Path(args.cases_file))
    else:
        synthetic = generate_all_comprehensive_cases()
        raw_cases = [dc_asdict(c) for c in synthetic]

    if args.limit:
        raw_cases = raw_cases[: args.limit]

    total = len(raw_cases)
    est_cost = total * cost_per_case
    est_min = total * (8 if args.debate else 3) / 60 / args.workers

    # 보고서만 출력
    if args.report_only:
        state = _load_checkpoint()
        _print_report(state)
        return

    print(f"=== Phase A 베이스라인 평가 ===")
    print(f"케이스: {total}건 | debate: {'켜짐' if args.debate else '꺼짐'}")
    print(f"예상 비용: ~${est_cost:.2f} | 예상 시간: ~{est_min:.0f}분")
    print()

    # 체크포인트 로드
    if args.resume:
        state = _load_checkpoint()
        done_ids = _completed_ids(state)
        print(f"이어서 실행: {state.completed}/{state.total}건 완료")
    else:
        state = CheckpointState(
            total=total,
            started_at=datetime.now().isoformat(),
        )
        done_ids: set[str] = set()

    state.total = total
    pending = [c for c in raw_cases if c["case_id"] not in done_ids]
    print(f"남은 케이스: {len(pending)}건\n")

    t_start = time.monotonic()
    semaphore = asyncio.Semaphore(args.workers)
    lock = asyncio.Lock()
    abs_idx_counter = [state.completed]  # mutable counter for parallel progress

    async def _run_with_sem(case: dict) -> EvalResult:
        async with semaphore:
            return await _run_single(case, enable_debate=args.debate)

    tasks = [asyncio.create_task(_run_with_sem(c)) for c in pending]
    for task in asyncio.as_completed(tasks):
        result = await task
        async with lock:
            state.results.append(asdict(result))
            state.completed += 1
            abs_idx = abs_idx_counter[0]
            abs_idx_counter[0] += 1
            _print_progress(abs_idx, total, result, time.monotonic() - t_start, cost_per_case)
            _save_checkpoint(state)

    elapsed_total = time.monotonic() - t_start
    print(f"\n완료: {state.completed}건 / {elapsed_total:.0f}초 소요")
    _print_report(state)

    # 최종 결과 파일 저장
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    final_path = RESULTS_DIR / f"baseline_final_{ts}.json"
    final_path.write_text(
        json.dumps(asdict(state), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n최종 결과 저장: {final_path}")

    if args.debate and args.auto_finetune:
        _maybe_trigger_finetune()


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase A 베이스라인 평가 실행기")
    parser.add_argument("--resume", action="store_true", help="이전 체크포인트에서 이어서 실행")
    parser.add_argument("--debate", action="store_true", help="debate 활성화 (비용 증가)")
    parser.add_argument("--limit", type=int, default=0, help="처음 N건만 실행 (0=전체)")
    parser.add_argument("--workers", type=int, default=3, help="병렬 처리 워커 수 (기본 3)")
    parser.add_argument("--cases-file", type=str, default="", help="외부 케이스 JSON 파일 경로")
    parser.add_argument("--report-only", action="store_true", help="기존 체크포인트 결과만 요약")
    parser.add_argument(
        "--auto-finetune", action="store_true",
        help=(
            f"debate 완료 후 총 >= {MIN_TOTAL_DEBATES_FOR_TRAIN}건 AND "
            f"신규 >= {MIN_NEW_DEBATES_FOR_RETRAIN}건이면 자동 파인튜닝 실행"
        ),
    )
    args = parser.parse_args()

    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
