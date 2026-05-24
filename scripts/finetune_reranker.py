"""
BGE Reranker 파인튜닝 스크립트.

data/reranker_pairs.jsonl (extract_reranker_pairs.py 출력)을 읽어
BAAI/bge-reranker-v2-m3 CrossEncoder를 fine-tune한 후
data/models/bge-reranker-tax-rag/ 에 저장한다.

사용법:
    # Step 1: pair 추출 (red_wins/blue_wins → JSONL)
    python scripts/extract_reranker_pairs.py

    # Step 2: 파인튜닝
    python -m scripts.finetune_reranker

    # Step 3: .env 업데이트
    BGE_RERANKER_MODEL=data/models/bge-reranker-tax-rag

필요 패키지:
    pip install sentence-transformers torch

권장 환경:
    GPU (VRAM 6GB+) — CPU 가능하나 에폭당 5~10분 소요
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

MIN_COMPLETE_PAIRS = 20   # 완전 triplet 최소 요건 (positive + negative 모두 있음)
EVAL_RATIO = 0.15         # 평가셋 비율
DEFAULT_PAIRS_PATH = Path("data/reranker_pairs.jsonl")
DEFAULT_OUTPUT_DIR = Path("data/models/bge-reranker-tax-rag")


# ── 데이터 로드 ───────────────────────────────────────────────────────────────

def load_pairs(path: Path) -> tuple[list[dict], list[dict]]:
    """
    JSONL 로드 후 완전 triplet과 positive-only로 분리.
    반환: (complete_pairs, positive_only_pairs)
    """
    if not path.exists():
        print(f"[오류] {path} 없음 — 먼저 extract_reranker_pairs.py 실행 필요")
        sys.exit(1)

    complete, pos_only = [], []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("positive") and rec.get("negative"):
                complete.append(rec)
            elif rec.get("positive"):
                pos_only.append(rec)

    return complete, pos_only


# ── 학습 데이터 빌드 ──────────────────────────────────────────────────────────

def build_input_examples(complete: list[dict], pos_only: list[dict]):
    """
    CrossEncoder.fit()용 InputExample 목록 생성.
    - complete triplet: (query, positive, 1.0) + (query, negative, 0.0)
    - positive-only: (query, positive, 1.0) — in-batch negative로 활용
    """
    from sentence_transformers import InputExample

    samples = []
    for rec in complete:
        samples.append(InputExample(texts=[rec["query"], rec["positive"]], label=1.0))
        samples.append(InputExample(texts=[rec["query"], rec["negative"]], label=0.0))

    for rec in pos_only:
        samples.append(InputExample(texts=[rec["query"], rec["positive"]], label=1.0))

    return samples


# ── 학습/평가 분할 ────────────────────────────────────────────────────────────

def split_train_eval(
    complete: list[dict],
    eval_ratio: float = EVAL_RATIO,
    seed: int = 42,
) -> tuple[list[dict], list[dict]]:
    """complete pairs를 학습/평가로 분할."""
    shuffled = complete.copy()
    random.seed(seed)
    random.shuffle(shuffled)
    n_eval = max(1, int(len(shuffled) * eval_ratio))
    return shuffled[n_eval:], shuffled[:n_eval]


# ── 파인튜닝 ──────────────────────────────────────────────────────────────────

def run_finetune(
    pairs_path: Path,
    output_dir: Path,
    base_model: str,
    epochs: int,
    batch_size: int,
    lr: float,
    warmup_ratio: float,
) -> None:
    """CrossEncoder 파인튜닝 메인."""
    from sentence_transformers import CrossEncoder, InputExample
    from sentence_transformers.cross_encoder.evaluation import CEBinaryAccuracyEvaluator
    from torch.utils.data import DataLoader

    print(f"=== BGE Reranker 파인튜닝 ===")
    print(f"  base model : {base_model}")
    print(f"  pairs file : {pairs_path}")
    print(f"  output dir : {output_dir}")

    # 1. 데이터 로드
    complete, pos_only = load_pairs(pairs_path)
    print(f"\n데이터:")
    print(f"  완전 triplet  : {len(complete)}건")
    print(f"  positive-only : {len(pos_only)}건")

    if len(complete) < MIN_COMPLETE_PAIRS:
        print(f"\n[경고] 완전 triplet {len(complete)}건 — 권장 최소 {MIN_COMPLETE_PAIRS}건")
        print("  red_win 케이스가 부족합니다. accumulate_red_wins.py 추가 실행 후 재시도 권장.")
        if len(complete) == 0:
            print("  완전 triplet 0건 — 파인튜닝 불가. 종료합니다.")
            sys.exit(1)
        print("  데이터 부족 상태로 계속 진행합니다...\n")

    # 2. 학습/평가 분할
    train_complete, eval_complete = split_train_eval(complete)
    print(f"  학습 triplet  : {len(train_complete)}건")
    print(f"  평가 triplet  : {len(eval_complete)}건")

    # 3. InputExample 생성
    train_samples = build_input_examples(train_complete, pos_only)
    eval_samples_raw = build_input_examples(eval_complete, [])
    print(f"  학습 샘플     : {len(train_samples)}개 (각 triplet = 2개 샘플)")

    # 4. 모델 로드
    print(f"\n모델 로드 중: {base_model}")
    model = CrossEncoder(base_model, num_labels=1, max_length=256)

    # 5. DataLoader
    train_dataloader = DataLoader(
        train_samples,
        shuffle=True,
        batch_size=batch_size,
    )
    warmup_steps = int(len(train_dataloader) * epochs * warmup_ratio)

    # 6. Evaluator (평가셋이 있을 때만)
    evaluator = None
    if eval_samples_raw:
        eval_texts = [(s.texts[0], s.texts[1]) for s in eval_samples_raw]
        eval_labels = [int(s.label) for s in eval_samples_raw]
        evaluator = CEBinaryAccuracyEvaluator(
            sentence_pairs=eval_texts,
            labels=eval_labels,
            name="tax-rag-eval",
        )

    # 7. 파인튜닝
    print(f"\n파인튜닝 시작 (epochs={epochs}, batch_size={batch_size}, lr={lr})")
    output_dir.mkdir(parents=True, exist_ok=True)

    model.fit(
        train_dataloader=train_dataloader,
        evaluator=evaluator,
        epochs=epochs,
        warmup_steps=warmup_steps,
        optimizer_params={"lr": lr},
        output_path=str(output_dir),
        evaluation_steps=max(50, len(train_dataloader)),
        save_best_model=True,
        show_progress_bar=True,
    )

    print(f"\n✅ 파인튜닝 완료 — 저장 경로: {output_dir}")
    print("\n다음 단계:")
    print(f"  .env 에 아래 줄을 추가하거나 변경하세요:")
    print(f"  BGE_RERANKER_MODEL={output_dir}")
    print("\n  적용 후 파이프라인 재시작이 필요합니다 (reranker 싱글톤 재초기화).")


# ── 파인튜닝 성능 평가 ────────────────────────────────────────────────────────

def evaluate_model(model_path: Path, pairs_path: Path) -> None:
    """저장된 모델을 로드해 전체 pairs에 대해 정확도를 측정한다."""
    from sentence_transformers import CrossEncoder, InputExample
    from sentence_transformers.cross_encoder.evaluation import CEBinaryAccuracyEvaluator

    complete, _ = load_pairs(pairs_path)
    if not complete:
        print("평가할 완전 triplet 없음.")
        return

    samples = build_input_examples(complete, [])
    model = CrossEncoder(str(model_path), max_length=256)

    eval_texts = [(s.texts[0], s.texts[1]) for s in samples]
    eval_labels = [int(s.label) for s in samples]

    evaluator = CEBinaryAccuracyEvaluator(
        sentence_pairs=eval_texts,
        labels=eval_labels,
        name="tax-rag-full",
    )
    score = evaluator(model, output_path=str(model_path))
    print(f"\n전체 데이터 정확도: {score:.4f}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="BGE Reranker 파인튜닝")
    parser.add_argument("--pairs", type=Path, default=DEFAULT_PAIRS_PATH,
                        help=f"학습 데이터 JSONL (기본: {DEFAULT_PAIRS_PATH})")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR,
                        help=f"모델 저장 경로 (기본: {DEFAULT_OUTPUT_DIR})")
    parser.add_argument("--base-model", default="BAAI/bge-reranker-v2-m3",
                        help="베이스 모델 (기본: BAAI/bge-reranker-v2-m3)")
    parser.add_argument("--epochs", type=int, default=3,
                        help="학습 에폭 수 (기본: 3)")
    parser.add_argument("--batch-size", type=int, default=16,
                        help="배치 크기 (기본: 16, GPU 메모리 부족 시 8로 줄일 것)")
    parser.add_argument("--lr", type=float, default=2e-5,
                        help="학습률 (기본: 2e-5)")
    parser.add_argument("--warmup-ratio", type=float, default=0.1,
                        help="웜업 스텝 비율 (기본: 0.1)")
    parser.add_argument("--eval-only", action="store_true",
                        help="파인튜닝 없이 --output 모델 평가만")
    parser.add_argument("--extract-first", action="store_true",
                        help="파인튜닝 전 extract_reranker_pairs.py 자동 실행")
    args = parser.parse_args()

    if args.extract_first:
        import subprocess
        print("=== pair 추출 선행 실행 ===")
        subprocess.run(
            [sys.executable, "scripts/extract_reranker_pairs.py", "--out", str(args.pairs)],
            check=True,
        )
        print()

    if args.eval_only:
        print("=== 저장 모델 평가 모드 ===")
        evaluate_model(args.output, args.pairs)
        return

    run_finetune(
        pairs_path=args.pairs,
        output_dir=args.output,
        base_model=args.base_model,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        warmup_ratio=args.warmup_ratio,
    )


if __name__ == "__main__":
    main()
