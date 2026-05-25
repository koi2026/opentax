"""
BGE Reranker fine-tuning 스크립트.

입력:
- data/reranker_pairs.jsonl (extract_reranker_pairs.py 출력)

중요:
- CrossEncoder.fit()는 positive-only 샘플에서 자동으로 in-batch negative를 만들지 않는다.
- 따라서 기본 학습은 complete triplet(positive+negative)만 사용한다.
"""
from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

MIN_COMPLETE_PAIRS = 20
EVAL_RATIO = 0.15
DEFAULT_PAIRS_PATH = Path("data/reranker_pairs.jsonl")
DEFAULT_OUTPUT_DIR = Path("data/models/bge-reranker-tax-rag")


def load_pairs(path: Path) -> tuple[list[dict], list[dict]]:
    """JSONL을 로드해 complete pair와 positive-only pair로 분리한다."""
    if not path.exists():
        print(f"[오류] {path} 없음. 먼저 extract_reranker_pairs.py를 실행하세요.")
        sys.exit(1)

    complete: list[dict] = []
    pos_only: list[dict] = []

    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            if record.get("positive") and record.get("negative"):
                complete.append(record)
            elif record.get("positive"):
                pos_only.append(record)

    return complete, pos_only


def build_input_examples(complete: list[dict]) -> list:
    """
    CrossEncoder.fit()용 InputExample 목록 생성.

    각 triplet은 아래 2개 샘플로 변환된다.
    - (query, positive, 1.0)
    - (query, negative, 0.0)
    """
    from sentence_transformers import InputExample

    samples = []
    for record in complete:
        samples.append(InputExample(texts=[record["query"], record["positive"]], label=1.0))
        samples.append(InputExample(texts=[record["query"], record["negative"]], label=0.0))
    return samples


def split_train_eval(
    complete: list[dict],
    eval_ratio: float = EVAL_RATIO,
    seed: int = 42,
) -> tuple[list[dict], list[dict]]:
    """
    같은 debate(source)가 train/eval에 동시에 들어가지 않도록 분할한다.

    pair-level 분할을 하면 동일 query가 train/eval 양쪽에 섞여 평가가 부풀려진다.
    """
    if len(complete) <= 1:
        return complete, []

    grouped: dict[str, list[dict]] = {}
    for record in complete:
        grouped.setdefault(record["source"], []).append(record)

    sources = list(grouped)
    if len(sources) <= 1:
        return complete, []

    rng = random.Random(seed)
    rng.shuffle(sources)

    n_eval_sources = max(1, int(len(sources) * eval_ratio))
    n_eval_sources = min(n_eval_sources, len(sources) - 1)
    eval_sources = set(sources[:n_eval_sources])

    train = [record for record in complete if record["source"] not in eval_sources]
    eval_set = [record for record in complete if record["source"] in eval_sources]
    return train, eval_set


def run_finetune(
    pairs_path: Path,
    output_dir: Path,
    base_model: str,
    epochs: int,
    batch_size: int,
    lr: float,
    warmup_ratio: float,
    max_length: int,
) -> None:
    """CrossEncoder fine-tuning 메인."""
    from sentence_transformers import CrossEncoder
    from sentence_transformers.cross_encoder.evaluation import CrossEncoderClassificationEvaluator
    from torch.utils.data import DataLoader

    print("=== BGE Reranker 파인튜닝 ===")
    print(f"  base model : {base_model}")
    print(f"  pairs file : {pairs_path}")
    print(f"  output dir : {output_dir}")
    print(f"  max length : {max_length}")

    complete, pos_only = load_pairs(pairs_path)
    print("\n데이터")
    print(f"  complete triplet : {len(complete)}건")
    print(f"  positive-only    : {len(pos_only)}건")

    if len(complete) < MIN_COMPLETE_PAIRS:
        print(f"\n[경고] complete triplet {len(complete)}건 < 최소 권장 {MIN_COMPLETE_PAIRS}건")
        if len(complete) == 0:
            print("  complete triplet이 0건이라 학습을 중단합니다.")
            sys.exit(1)
        print("  데이터 부족 상태로 계속 진행합니다.")

    train_complete, eval_complete = split_train_eval(complete)
    train_samples = build_input_examples(train_complete)
    eval_samples = build_input_examples(eval_complete)

    print(f"  학습 triplet     : {len(train_complete)}건")
    print(f"  평가 triplet     : {len(eval_complete)}건")
    print(f"  학습 debate 수   : {len({rec['source'] for rec in train_complete})}개")
    print(f"  평가 debate 수   : {len({rec['source'] for rec in eval_complete})}개")
    print(f"  학습 샘플 수     : {len(train_samples)}개")
    if pos_only:
        print(f"  참고: positive-only {len(pos_only)}건은 기본 학습에서 제외")

    print(f"\n모델 로드 중: {base_model}")
    model = CrossEncoder(base_model, num_labels=1, max_length=max_length)

    train_dataloader = DataLoader(
        train_samples,
        shuffle=True,
        batch_size=batch_size,
    )
    warmup_steps = int(len(train_dataloader) * epochs * warmup_ratio)

    evaluator = None
    if eval_samples:
        eval_texts = [(sample.texts[0], sample.texts[1]) for sample in eval_samples]
        eval_labels = [int(sample.label) for sample in eval_samples]
        evaluator = CrossEncoderClassificationEvaluator(
            sentence_pairs=eval_texts,
            labels=eval_labels,
            name="tax-rag-eval",
        )

    print(f"\n파인튜닝 시작 (epochs={epochs}, batch_size={batch_size}, lr={lr})")
    output_dir.mkdir(parents=True, exist_ok=True)

    model.fit(
        train_dataloader=train_dataloader,
        evaluator=evaluator,
        epochs=epochs,
        warmup_steps=warmup_steps,
        optimizer_params={"lr": lr},
        output_path=str(output_dir),
        evaluation_steps=max(1, len(train_dataloader)),
        save_best_model=True,
        show_progress_bar=True,
    )

    print(f"\n파인튜닝 완료: {output_dir}")
    print(f"BGE_RERANKER_MODEL={output_dir}")


def evaluate_model(model_path: Path, pairs_path: Path, max_length: int) -> None:
    """저장된 모델을 전체 complete pair에 대해 평가한다."""
    from sentence_transformers import CrossEncoder
    from sentence_transformers.cross_encoder.evaluation import CrossEncoderClassificationEvaluator

    complete, _ = load_pairs(pairs_path)
    if not complete:
        print("평가할 complete triplet이 없습니다.")
        return

    samples = build_input_examples(complete)
    model = CrossEncoder(str(model_path), max_length=max_length)

    eval_texts = [(sample.texts[0], sample.texts[1]) for sample in samples]
    eval_labels = [int(sample.label) for sample in samples]
    evaluator = CrossEncoderClassificationEvaluator(
        sentence_pairs=eval_texts,
        labels=eval_labels,
        name="tax-rag-full",
    )
    score = evaluator(model, output_path=str(model_path))
    print(f"\n전체 데이터 정확도: {score:.4f}")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="BGE Reranker 파인튜닝")
    parser.add_argument("--pairs", type=Path, default=DEFAULT_PAIRS_PATH,
                        help=f"학습 데이터 JSONL (기본: {DEFAULT_PAIRS_PATH})")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR,
                        help=f"모델 저장 경로 (기본: {DEFAULT_OUTPUT_DIR})")
    parser.add_argument("--base-model", default="BAAI/bge-reranker-v2-m3",
                        help="베이스 모델 (기본: BAAI/bge-reranker-v2-m3)")
    parser.add_argument("--epochs", type=int, default=4,
                        help="학습 epoch 수 (기본: 4 — 소규모 도메인 적응 권장)")
    parser.add_argument("--batch-size", type=int, default=4,
                        help="배치 크기 (기본: 4 — 소규모 데이터셋 권장, GPU VRAM 부족 시 2)")
    parser.add_argument("--lr", type=float, default=1e-5,
                        help="학습률 (기본: 1e-5 — 소규모 데이터셋 보수적 설정)")
    parser.add_argument("--max-length", type=int, default=512,
                        help="query+chunk 최대 토큰 길이 (기본: 512 — 한국 법령 조문 길이 기준)")
    parser.add_argument("--warmup-ratio", type=float, default=0.05,
                        help="워밍업 스텝 비율 (기본: 0.05 — 소규모 데이터셋 권장)")
    parser.add_argument("--eval-only", action="store_true",
                        help="파인튜닝 없이 --output 모델만 평가")
    parser.add_argument("--extract-first", action="store_true",
                        help="학습 전 extract_reranker_pairs.py를 먼저 실행")
    args = parser.parse_args()

    if args.extract_first:
        print("=== pair 추출 선행 실행 ===")
        subprocess.run(
            [sys.executable, "scripts/extract_reranker_pairs.py", "--out", str(args.pairs)],
            check=True,
        )
        print()

    if args.eval_only:
        print("=== 저장 모델 평가 모드 ===")
        evaluate_model(args.output, args.pairs, args.max_length)
        return

    run_finetune(
        pairs_path=args.pairs,
        output_dir=args.output,
        base_model=args.base_model,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        warmup_ratio=args.warmup_ratio,
        max_length=args.max_length,
    )


if __name__ == "__main__":
    main()
