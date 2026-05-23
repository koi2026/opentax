"""
유권해석 DB 임베딩 + Pinecone 업로드 파이프라인.
data/rulings/{ntis,tt,court}/*.json → Pinecone tax-ruling-{ntis,tt,court} 네임스페이스.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

load_dotenv()

import os

from pinecone import Pinecone

from src.ingestion.embed import _build_embed_client, _embed_texts, _get_or_create_index

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")

RULINGS_DIR = Path("data/rulings")
BATCH_SIZE = 100

# ── 출처 한국어 라벨 ───────────────────────────────────────────────────────────
# source_type + source_type 필드로 사용자에게 보여줄 출처 표시
SOURCE_LABELS: dict[str, str | dict] = {
    "ntis":      "국세청 예규",
    "tt":        "조세심판원 결정례",
    "court":     "대법원 판례",
    "nts": {     # source_type 필드로 세분화
        "qt":         "국세청 질의회신",
        "ic":         "국세청 세법해석례",
        "pd":         "국세청 판단사례",
        "hotissue":   "국세청 자주찾는쟁점별사례",
        "_default":   "국세청 예규",
    },
    "decisions": {   # dcm_type 필드로 세분화
        "tax_tribunal": "조세심판원 심판청구",
        "review":       "국세청 심사청구",
        "objection":    "국세청 이의신청",
        "assessment":   "과세적부심사",
        "_default":     "판례·결정례",
    },
    "pdf":       "세법집행기준",
}


def get_source_label(source: str, record: dict) -> str:
    """레코드의 source + 세부 타입 필드로 한국어 출처 라벨 반환."""
    entry = SOURCE_LABELS.get(source, source)
    if isinstance(entry, str):
        return entry
    # dict인 경우 세부 타입으로 분기
    sub_type = (
        record.get("source_type")     # nts 계열
        or record.get("dcm_type")     # decisions 계열
        or "_default"
    )
    return entry.get(sub_type, entry.get("_default", source))


SourceType = Literal["ntis", "tt", "court", "nts", "decisions", "pdf"]

_NAMESPACE_MAP: dict[str, str] = {
    "ntis": "tax-ruling-ntis",
    "tt": "tax-ruling-tt",
    "court": "tax-ruling-court",
    "nts": "tax-ruling-nts",        # 국세법령정보시스템 (질의회신·판단사례·세법해석례)
    "decisions": "tax-ruling-decisions",  # 판례·결정례 (심판청구·심사청구·이의신청·판례)
    "pdf": "tax-ruling-pdf",        # 세법집행기준 PDF 파싱본
}


def _load_ruling_files(source: str) -> list[dict]:
    """source 디렉터리 아래 *.json 파일을 모두 읽어 반환."""
    source_dir = RULINGS_DIR / source
    if not source_dir.exists():
        print(f"  디렉터리 없음 (건너뜀): {source_dir}")
        return []

    records: list[dict] = []
    for fpath in sorted(source_dir.glob("*.json")):
        try:
            data = json.loads(fpath.read_text(encoding="utf-8"))
            # 단일 객체 또는 리스트 모두 지원
            if isinstance(data, list):
                records.extend(data)
            else:
                records.append(data)
        except (json.JSONDecodeError, OSError) as exc:
            print(f"  파일 읽기 오류 {fpath.name}: {exc}")
    return records


def _build_chunk(record: dict, source: str) -> dict:
    """유권해석 레코드를 Pinecone 업로드용 청크로 변환."""
    question: str = record.get("question", "")
    answer: str = record.get("answer", "")
    full_text_raw = f"질문: {question}\n답변: {answer}"
    full_text = full_text_raw[:4000]

    ruling_id: str = record.get("id", "")
    chunk_id = f"{source}_{ruling_id}" if ruling_id else f"{source}_{hash(full_text_raw) & 0xFFFFFF}"

    issued_raw: str = record.get("issued_at", "")
    try:
        issued_at_int = int(issued_raw) if issued_raw else 0
    except ValueError:
        issued_at_int = 0

    related_articles: list[str] = record.get("related_articles", [])
    keywords: list[str] = record.get("keywords", [])

    source_label = get_source_label(source, record)

    return {
        "chunk_id": chunk_id,
        "full_text": full_text,
        "metadata": {
            "id": ruling_id,
            "source": source,
            "source_label": source_label,
            "title": record.get("title", ""),
            "issued_at": issued_at_int,
            "related_articles": related_articles,
            "keywords": keywords,
            "doc_number": record.get("doc_number", ""),
            "full_text": full_text,
        },
    }


def _upload_to_namespace(
    index,
    embed_client,
    embed_model: str,
    chunks: list[dict],
    namespace: str,
) -> int:
    """청크 배치를 임베딩 후 지정 네임스페이스에 upsert. 업로드 수 반환."""
    from tqdm import tqdm

    total_upserted = 0
    batches = [chunks[i : i + BATCH_SIZE] for i in range(0, len(chunks), BATCH_SIZE)]

    for batch in tqdm(batches, desc=f"업로드 → {namespace}"):
        texts = [c["full_text"] for c in batch]
        try:
            vectors = _embed_texts(embed_client, embed_model, texts)
        except Exception as exc:
            print(f"\n  임베딩 오류 (배치 건너뜀): {exc}")
            continue

        upsert_payload = [
            {
                "id": chunk["chunk_id"],
                "values": vec,
                "metadata": chunk["metadata"],
            }
            for chunk, vec in zip(batch, vectors)
        ]

        index.upsert(vectors=upsert_payload, namespace=namespace)
        total_upserted += len(upsert_payload)
        time.sleep(0.2)  # rate limit 방지

    return total_upserted


def embed_and_upload_rulings(source: str = "all") -> int:
    """
    data/rulings/{source}/*.json 읽기 → 청킹 → 임베딩 → Pinecone 업로드.

    Args:
        source: "ntis" | "tt" | "court" | "all"

    Returns:
        업로드된 벡터 수 합계.
    """
    if not PINECONE_API_KEY:
        raise RuntimeError("PINECONE_API_KEY가 필요합니다")

    sources: list[str] = list(_NAMESPACE_MAP.keys()) if source == "all" else [source]
    invalid = [s for s in sources if s not in _NAMESPACE_MAP]
    if invalid:
        raise ValueError(f"지원하지 않는 source: {invalid}. 가능한 값: ntis, tt, court, nts, decisions, pdf, all")

    embed_client, embed_model, dimension = _build_embed_client()
    print(f"임베딩 모델: {embed_model} (dim={dimension})")

    pc = Pinecone(api_key=PINECONE_API_KEY)
    index = _get_or_create_index(pc, dimension)

    total_upserted = 0

    for src in sources:
        namespace = _NAMESPACE_MAP[src]
        print(f"\n[{src}] 파일 로드 중...")
        records = _load_ruling_files(src)

        if not records:
            print(f"  레코드 없음 — 건너뜀")
            continue

        # deprecated(폐지) 예규 제외
        active = [r for r in records if not r.get("deprecated")]
        skipped = len(records) - len(active)
        if skipped:
            print(f"  deprecated 제외: {skipped}건")
        print(f"  {len(active)}건 로드 완료")
        chunks = [_build_chunk(rec, src) for rec in active]

        uploaded = _upload_to_namespace(index, embed_client, embed_model, chunks, namespace)
        total_upserted += uploaded
        print(f"  [{src}] {uploaded}개 벡터 → {namespace}")

    print(f"\n[완료] 총 {total_upserted}개 벡터 업로드")
    return total_upserted


if __name__ == "__main__":
    source_arg = sys.argv[1] if len(sys.argv) > 1 else "all"
    embed_and_upload_rulings(source_arg)
