"""
Extract BGE reranker training pairs from debate records.

Source of truth:
- data/debates/*.json
  - blue_answer.chunk_ids: chunk ids retrieved by the original answer
  - new_chunks_found: chunk ids found during debate that improved coverage

Training mapping:
- red_won:
  - negative = blue_answer.chunk_ids
  - positive = new_chunks_found
- no_contest / blue_won:
  - positive-only = blue_answer.chunk_ids
"""
from __future__ import annotations

import argparse
import json
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

DEBATES_DIR = Path("data/debates")
PROCESSED_DIR = Path("data/processed")
DEFAULT_OUTPUT = Path("data/reranker_pairs.jsonl")

NEGATIVE_OUTCOMES = {"red_won"}
POSITIVE_ONLY_OUTCOMES = {"no_contest", "blue_won"}

MAX_NEGATIVE_IDS_PER_DEBATE = 5
MAX_POSITIVE_IDS_PER_DEBATE = 5


def _fact_json_to_query(fact_json: dict[str, Any]) -> str:
    parts: list[str] = []

    question = fact_json.get("question")
    if question:
        parts.append(str(question))

    basic_fields = [
        ("양도일", fact_json.get("transfer_date")),
        ("취득일", fact_json.get("acquisition_date")),
        ("부동산유형", fact_json.get("property_type")),
        ("취득원인", fact_json.get("acquisition_reason")),
        ("세대주택수", fact_json.get("household_house_count")),
        ("양도가액", fact_json.get("transfer_price")),
        ("취득가액", fact_json.get("acquisition_price")),
        ("보유연수", fact_json.get("holding_years")),
        ("거주연수", fact_json.get("residence_years")),
    ]
    for label, value in basic_fields:
        if value not in (None, "", []):
            parts.append(f"{label}: {value}")

    bool_fields = [
        ("취득시조정대상지역", fact_json.get("is_adjustment_area_at_acquisition")),
        ("양도시조정대상지역", fact_json.get("is_adjustment_area_at_transfer")),
        ("일시적2주택", fact_json.get("is_temporary_two_house")),
        ("상생임대", fact_json.get("sangsaeng_rental")),
        ("특수관계인거래", fact_json.get("is_related_party_transaction")),
        ("상속주택", fact_json.get("inheritance")),
        ("배우자직계존비속증여", fact_json.get("is_gift_from_spouse_or_lineal")),
    ]
    for label, value in bool_fields:
        if value is not None:
            parts.append(f"{label}: {'예' if value else '아니오'}")

    return " | ".join(parts) if parts else "양도소득세 판단"


@lru_cache(maxsize=1)
def _load_chunk_map() -> dict[str, str]:
    chunk_map: dict[str, str] = {}

    candidate_files = sorted(PROCESSED_DIR.glob("*.json"))

    for path in candidate_files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        if not isinstance(data, list):
            continue

        for chunk in data:
            if not isinstance(chunk, dict):
                continue
            chunk_id = chunk.get("id") or chunk.get("chunk_id")
            if not chunk_id or chunk_id in chunk_map:
                continue

            text = (
                chunk.get("full_text")
                or chunk.get("text")
                or chunk.get("content")
                or chunk.get("excerpt")
            )
            if isinstance(text, str) and text.strip():
                chunk_map[chunk_id] = text.strip()

    return chunk_map


def _old_format_fallback(chunk_id: str) -> str | None:
    """Old-format ID (285631_0154001) → new-format 텍스트 역조회.
    Old: {mst}_{article4digit}{clause3digit}  e.g. 285631_0154001
    New: {mst}_{code}_a{article}_{date}        e.g. 285631_itd_a154_20260423
    """
    parts = chunk_id.split("_")
    if len(parts) != 2 or not parts[1].isdigit() or len(parts[1]) < 4:
        return None
    mst, num = parts[0], parts[1]
    article = str(int(num[:4]))  # "0154" -> "154"
    prefix = f"{mst}_"
    suffix = f"_a{article}_"
    chunk_map = _load_chunk_map()
    # 메인 조문 우선 (clause 접미사 없는 것)
    for cid, text in chunk_map.items():
        tail = cid.split(suffix)[-1] if suffix in cid else ""
        if cid.startswith(prefix) and suffix in cid and "_c" not in tail:
            return text
    # 없으면 첫 번째 clause라도
    for cid, text in chunk_map.items():
        if cid.startswith(prefix) and suffix in cid:
            return text
    return None


def _chunk_text(chunk_id: str) -> str | None:
    chunk_map = _load_chunk_map()
    text = chunk_map.get(chunk_id)
    if text:
        return text
    return _old_format_fallback(chunk_id)


def _load_debate(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _dedupe_keep_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _extract_from_red_won(debate: dict[str, Any], debate_id: str) -> list[dict[str, Any]]:
    query = _fact_json_to_query(debate.get("fact_json", {}))

    positive_ids = _dedupe_keep_order(
        list(debate.get("new_chunks_found") or [])
    )[:MAX_POSITIVE_IDS_PER_DEBATE]
    positive_id_set = set(positive_ids)
    negative_ids = [
        chunk_id
        for chunk_id in _dedupe_keep_order(
            list((debate.get("blue_answer") or {}).get("chunk_ids") or [])
        )
        if chunk_id not in positive_id_set
    ][:MAX_NEGATIVE_IDS_PER_DEBATE]

    positive_rows = [(chunk_id, _chunk_text(chunk_id)) for chunk_id in positive_ids]
    negative_rows = [(chunk_id, _chunk_text(chunk_id)) for chunk_id in negative_ids]
    positive_rows = [(chunk_id, text) for chunk_id, text in positive_rows if text]
    negative_rows = [(chunk_id, text) for chunk_id, text in negative_rows if text]

    pairs: list[dict[str, Any]] = []
    for positive_chunk_id, positive_text in positive_rows:
        for negative_chunk_id, negative_text in negative_rows:
            pairs.append(
                {
                    "query": query,
                    "positive": positive_text,
                    "negative": negative_text,
                    "source": debate_id,
                    "pair_type": "red_won_triplet",
                    "positive_chunk_id": positive_chunk_id,
                    "negative_chunk_id": negative_chunk_id,
                }
            )

    return pairs


def _extract_positive_only(debate: dict[str, Any], debate_id: str) -> list[dict[str, Any]]:
    query = _fact_json_to_query(debate.get("fact_json", {}))
    positive_ids = _dedupe_keep_order(list(debate.get("new_chunks_found") or []))
    if not positive_ids:
        positive_ids = _dedupe_keep_order(
            list((debate.get("blue_answer") or {}).get("chunk_ids") or [])
        )
    positive_ids = positive_ids[:MAX_POSITIVE_IDS_PER_DEBATE]

    pairs: list[dict[str, Any]] = []
    for positive_chunk_id in positive_ids:
        positive_text = _chunk_text(positive_chunk_id)
        if not positive_text:
            continue
        pairs.append(
            {
                "query": query,
                "positive": positive_text,
                "negative": None,
                "source": debate_id,
                "pair_type": "positive_only",
                "positive_chunk_id": positive_chunk_id,
            }
        )

    return pairs


def extract_pairs() -> list[dict[str, Any]]:
    if not DEBATES_DIR.exists():
        print(f"[error] debate directory not found: {DEBATES_DIR}")
        sys.exit(1)

    pairs: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    debate_files = sorted(DEBATES_DIR.glob("*.json"))
    print(f"[debates] processing {len(debate_files)} files...")

    for path in debate_files:
        debate = _load_debate(path)
        if not debate:
            continue

        debate_id = str(debate.get("debate_id") or path.stem)
        outcome = str(debate.get("outcome") or "").strip()

        if outcome in NEGATIVE_OUTCOMES:
            debate_pairs = _extract_from_red_won(debate, debate_id)
        elif outcome in POSITIVE_ONLY_OUTCOMES:
            debate_pairs = _extract_positive_only(debate, debate_id)
        else:
            continue

        for pair in debate_pairs:
            key = (
                pair["query"],
                pair.get("positive") or "",
                pair.get("negative") or "",
            )
            if key in seen:
                continue
            seen.add(key)
            pairs.append(pair)

    return pairs


def _save_jsonl(pairs: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for pair in pairs:
            f.write(json.dumps(pair, ensure_ascii=False) + "\n")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description="Extract BGE reranker training pairs from debate files."
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output JSONL path (default: {DEFAULT_OUTPUT})",
    )
    args = parser.parse_args()

    print("=== Extract BGE reranker pairs from debates ===")
    print(f"[chunks] loaded {len(_load_chunk_map())} chunk texts")

    pairs = extract_pairs()
    complete = [pair for pair in pairs if pair.get("positive") and pair.get("negative")]
    positive_only = [pair for pair in pairs if pair.get("positive") and not pair.get("negative")]

    print(f"[summary] complete triplets: {len(complete)}")
    print(f"[summary] positive-only: {len(positive_only)}")
    print(f"[summary] total rows: {len(pairs)}")

    _save_jsonl(pairs, args.out)
    print(f"[saved] {args.out}")


if __name__ == "__main__":
    main()
