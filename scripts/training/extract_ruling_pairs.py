"""
nts_interp / moef answer 본문에서 BGE reranker 훈련 쌍 자동 추출.

각 유권해석 레코드:
  question → query
  answer 내 법령 조문 참조(제N조) → Pinecone tax-law 검색 → positive chunk
  검색됐지만 조문 미매칭 chunk → negative chunk

출력: data/reranker_pairs.jsonl (기존 파일에 append, chunk_id 기준 중복 제거)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

RULINGS_DIR = Path("data/rulings")
OUTPUT_PATH = Path("data/reranker_pairs.jsonl")
ARTICLE_RE = re.compile(r"제\s*(\d+)조")
BATCH_EMBED = 20
TOP_K_SEARCH = 15


def _load_existing_queries(path: Path) -> set[str]:
    if not path.exists():
        return set()
    existing = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            existing.add(rec.get("query", "")[:120])
        except json.JSONDecodeError:
            pass
    return existing


def _extract_article_numbers(answer: str) -> set[str]:
    return set(ARTICLE_RE.findall(answer))


def _build_pairs_from_rulings(
    source: str,
    index,
    embed_fn,
    existing_queries: set[str],
    limit: int,
) -> list[dict]:
    source_dir = RULINGS_DIR / source
    if not source_dir.exists():
        print(f"  [{source}] 디렉터리 없음 — 건너뜀")
        return []

    records = []
    for fpath in sorted(source_dir.glob("*.json")):
        try:
            d = json.loads(fpath.read_text(encoding="utf-8"))
            q = (d.get("question") or "").strip()
            a = (d.get("answer") or "").strip()
            if q and a and len(a) > 30:
                records.append((q, a))
        except (json.JSONDecodeError, OSError):
            continue

    print(f"  [{source}] 로드: {len(records)}건 (answer 있는 것)")

    new_pairs: list[dict] = []
    skipped = 0
    processed = 0

    for query, answer in records:
        if limit and processed >= limit:
            break

        query_key = query[:120]
        if query_key in existing_queries:
            skipped += 1
            continue

        article_nums = _extract_article_numbers(answer)
        if not article_nums:
            continue

        try:
            q_vec = embed_fn(query)
            response = index.query(
                vector=q_vec,
                top_k=TOP_K_SEARCH,
                namespace="tax-law",
                include_metadata=True,
            )
            matches = response.get("matches", [])
        except Exception as exc:
            print(f"\n  임베딩/검색 오류: {exc}")
            time.sleep(2)
            continue

        positive = None
        negatives = []
        for m in matches:
            art_no = str(m.get("metadata", {}).get("article_number", ""))
            if art_no in article_nums and positive is None:
                positive = m["metadata"].get("full_text") or m["metadata"].get("text", "")
            elif art_no not in article_nums:
                neg_text = m["metadata"].get("full_text") or m["metadata"].get("text", "")
                if neg_text:
                    negatives.append(neg_text)

        if not positive:
            continue

        pair: dict = {
            "query": query,
            "positive": positive[:1200],
            "source": source,
        }
        if negatives:
            pair["negative"] = negatives[0][:1200]

        new_pairs.append(pair)
        existing_queries.add(query_key)
        processed += 1

        if processed % 100 == 0:
            print(f"    {processed}건 처리 ({len(new_pairs)}쌍 추출)...")
        time.sleep(0.05)

    print(f"  [{source}] 완료: {processed}건 처리, {len(new_pairs)}쌍 추출 (skipped={skipped})")
    return new_pairs


def main(sources: list[str], limit: int) -> None:
    from src.infra.pinecone_client import get_pinecone_index
    from src.infra.embedder import embed_query

    index = get_pinecone_index()
    existing = _load_existing_queries(OUTPUT_PATH)
    print(f"기존 pairs: {len(existing)}건")

    all_new: list[dict] = []
    for src in sources:
        pairs = _build_pairs_from_rulings(src, index, embed_query, existing, limit)
        all_new.extend(pairs)

    if not all_new:
        print("추출된 신규 쌍 없음.")
        return

    with OUTPUT_PATH.open("a", encoding="utf-8") as f:
        for pair in all_new:
            f.write(json.dumps(pair, ensure_ascii=False) + "\n")

    complete = sum(1 for p in all_new if p.get("negative"))
    print(f"\n[완료] 신규 {len(all_new)}쌍 추가 (complete={complete}, pos_only={len(all_new)-complete})")
    print(f"저장: {OUTPUT_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("sources", nargs="*", default=["nts_interp", "moef"],
                        help="추출할 소스 (기본: nts_interp moef)")
    parser.add_argument("--limit", type=int, default=0,
                        help="소스당 최대 처리 건수 (0=전체)")
    args = parser.parse_args()
    main(args.sources, args.limit)
