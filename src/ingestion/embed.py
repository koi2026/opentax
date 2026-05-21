"""
임베딩 + Pinecone 업로드 스크립트
data/processed/all_chunks.json → Pinecone Serverless
"""
import os
import json
import time
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI
from pinecone import Pinecone, ServerlessSpec
from tqdm import tqdm

load_dotenv()

UPSTAGE_API_KEY = os.getenv("UPSTAGE_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "tax-rag")
PINECONE_NAMESPACE = os.getenv("PINECONE_NAMESPACE", "tax-law")
PINECONE_CLOUD = os.getenv("PINECONE_CLOUD", "aws")
PINECONE_REGION = os.getenv("PINECONE_REGION", "us-east-1")
UPSTAGE_EMBEDDING_MODEL = os.getenv("UPSTAGE_EMBEDDING_MODEL", "solar-embedding-1-large-passage")

PROCESSED_DIR = Path("data/processed")
BATCH_SIZE = 100  # Pinecone upsert 배치 크기

# ── Stage 1 필터 태깅 규칙 ─────────────────────────────────────────────────────
# 조문→태그 매핑은 src/infra/article_tag_map.json에서 로드.
# 신규 조문 추가 시 JSON만 수정하면 되며 코드 변경 불필요.

_TAG_MAP_PATH = Path(__file__).parent.parent / "infra" / "article_tag_map.json"
_TAG_MAP: dict = {}


def _load_tag_map() -> dict:
    global _TAG_MAP
    if not _TAG_MAP:
        try:
            _TAG_MAP = json.loads(_TAG_MAP_PATH.read_text(encoding="utf-8"))
        except FileNotFoundError:
            _TAG_MAP = {}
    return _TAG_MAP


def _tag_chunk(law_name: str, article_number: str, full_text: str) -> dict:
    """
    조문 정보 기반 규칙 태깅 (article_tag_map.json 주도).
    entity_scopes: ["주택", "분양권", "조합원입주권", "토지", ...]
    topic_tags: ["1세대1주택비과세", "장기보유특별공제", ...]
    tax_types: ["transfer"] (현재 수집 대상 전체)
    """
    tag_map = _load_tag_map()

    # 법령명 공백 제거로 JSON 키 정규화 ("소득세법 시행령" → "소득세법시행령")
    law_key = law_name.replace(" ", "")
    law_entry: dict = tag_map.get(law_key) or tag_map.get(law_name) or {}

    entity_scopes: list[str] = list(law_entry.get("default_entity_scopes", []))
    topic_tags: list[str] = list(law_entry.get("default_topic_tags", []))

    articles: dict = law_entry.get("articles", {})
    art_num = article_number.strip().lstrip("제").split("조")[0]
    art_entry: dict = articles.get(art_num, {})

    topic_tags += art_entry.get("topic_tags", [])
    entity_scopes += art_entry.get("entity_scopes", [])

    # 부칙 태그
    if "부칙" in full_text[:50] or "부  칙" in full_text[:50]:
        topic_tags.append("부칙경과조치")

    return {
        "entity_scopes": list(dict.fromkeys(entity_scopes)),  # 순서 유지 중복 제거
        "topic_tags": list(dict.fromkeys(topic_tags)),
        "tax_types": ["transfer"],
    }


def _build_embed_client() -> tuple[OpenAI, str, int]:
    """(client, model_name, dimension) 반환"""
    if UPSTAGE_API_KEY:
        client = OpenAI(
            api_key=UPSTAGE_API_KEY,
            base_url="https://api.upstage.ai/v1",
        )
        return client, UPSTAGE_EMBEDDING_MODEL, 4096
    if OPENAI_API_KEY:
        client = OpenAI(api_key=OPENAI_API_KEY)
        return client, "text-embedding-3-large", 3072
    raise RuntimeError("UPSTAGE_API_KEY 또는 OPENAI_API_KEY 중 하나가 필요합니다")


def _embed_texts(client: OpenAI, model: str, texts: list[str]) -> list[list[float]]:
    """텍스트 배치를 임베딩 벡터로 변환"""
    truncated = [t[:3000] for t in texts]
    resp = client.embeddings.create(model=model, input=truncated)
    return [item.embedding for item in resp.data]


def _get_or_create_index(pc: Pinecone, dimension: int):
    """Pinecone 인덱스 조회 또는 생성"""
    existing = [idx.name for idx in pc.list_indexes()]
    if PINECONE_INDEX_NAME not in existing:
        print(f"인덱스 생성 중: {PINECONE_INDEX_NAME} (dim={dimension})")
        pc.create_index(
            name=PINECONE_INDEX_NAME,
            dimension=dimension,
            metric="cosine",
            spec=ServerlessSpec(cloud=PINECONE_CLOUD, region=PINECONE_REGION),
        )
        # 인덱스 준비 대기
        while not pc.describe_index(PINECONE_INDEX_NAME).status["ready"]:
            print("  인덱스 준비 중...")
            time.sleep(3)
        print("  인덱스 준비 완료")
    else:
        print(f"기존 인덱스 사용: {PINECONE_INDEX_NAME}")
    return pc.Index(PINECONE_INDEX_NAME)


def embed_and_upload(chunks_path: Optional[Path] = None) -> int:
    """
    JSON 청크 파일을 읽어 임베딩 후 Pinecone에 업로드.
    반환값: upsert된 벡터 수
    """
    if chunks_path is None:
        chunks_path = PROCESSED_DIR / "all_chunks.json"

    if not chunks_path.exists():
        raise FileNotFoundError(
            f"{chunks_path} 없음 — 먼저 `python src/collect.py` 실행"
        )

    if not PINECONE_API_KEY:
        raise RuntimeError("PINECONE_API_KEY가 필요합니다")

    # 청크 로드
    chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
    print(f"총 {len(chunks)}개 청크 로드 완료")

    # 임베딩 클라이언트
    embed_client, embed_model, dimension = _build_embed_client()
    print(f"임베딩 모델: {embed_model} (dim={dimension})")

    # Pinecone 인덱스
    pc = Pinecone(api_key=PINECONE_API_KEY)
    index = _get_or_create_index(pc, dimension)

    # 배치 업로드
    total_upserted = 0
    batches = [chunks[i : i + BATCH_SIZE] for i in range(0, len(chunks), BATCH_SIZE)]

    for batch in tqdm(batches, desc="Pinecone 업로드"):
        texts = [c.get("full_text", "") for c in batch]
        try:
            vectors = _embed_texts(embed_client, embed_model, texts)
        except Exception as e:
            print(f"\n임베딩 오류 (배치 건너뜀): {e}")
            continue

        upsert_payload = []
        for chunk, vec in zip(batch, vectors):
            law_name = chunk.get("law_name", "")
            article_number = chunk.get("article_number", "")
            full_text = chunk.get("full_text", "")
            tags = _tag_chunk(law_name, article_number, full_text)
            metadata = {
                "law_name": law_name,
                "article_number": article_number,
                "article_title": chunk.get("article_title", ""),
                "article_type": chunk.get("article_type", ""),  # "본문" | "부칙"
                # Pinecone $lte/$gte는 숫자 타입 전용 — YYYYMMDD 정수로 저장
                "effective_date": int(chunk["effective_date"]) if chunk.get("effective_date") else 0,
                "expiration_date": int(chunk["expiration_date"]) if chunk.get("expiration_date") else 99991231,
                "version_mst": chunk.get("version_mst", chunk.get("law_mst", "")),
                "law_category": chunk.get("law_category", ""),
                "source": "law.go.kr",
                "source_label": f"법령 ({law_name})",
                # 본칙↔부칙 연결 — retrieve_with_buchik()가 이 목록으로 부칙 청크를 자동 보강
                "linked_buchik_ids": chunk.get("linked_buchik_ids", []),
                # 부칙 적용례 앵커 — "transfer_date"|"acquisition_date"|"contract_date"|"gift_date"|"death_date"|"effective_date"
                "applicability_anchor": chunk.get("applicability_anchor", "effective_date"),
                # Stage 1 symbolic filter용 태그 (업스트림 entity_scope/tax_type 매칭)
                "entity_scopes": tags["entity_scopes"],
                "topic_tags": tags["topic_tags"],
                "tax_types": tags["tax_types"],
                # Pinecone 벡터당 메타데이터 한도 40KB — 4000자까지 저장 (reranker + LLM 모두 이 필드 사용)
                "full_text": full_text[:4000],
            }
            upsert_payload.append(
                {"id": chunk["id"], "values": vec, "metadata": metadata}
            )

        index.upsert(vectors=upsert_payload, namespace=PINECONE_NAMESPACE)
        total_upserted += len(upsert_payload)
        time.sleep(0.2)  # rate limit 방지

    print(f"\n[완료] {total_upserted}개 벡터 업로드 → {PINECONE_INDEX_NAME}/{PINECONE_NAMESPACE}")
    return total_upserted


def embed_and_upload_chunks(chunks: list[dict]) -> int:
    """
    청크 리스트를 직접 받아 임베딩 후 Pinecone에 업로드.
    detect_law_changes.py 등에서 신규 버전만 부분 업로드할 때 사용.
    반환값: upsert된 벡터 수
    """
    if not chunks:
        return 0
    if not PINECONE_API_KEY:
        raise RuntimeError("PINECONE_API_KEY가 필요합니다")

    embed_client, embed_model, dimension = _build_embed_client()
    pc = Pinecone(api_key=PINECONE_API_KEY)
    index = _get_or_create_index(pc, dimension)

    total_upserted = 0
    batches = [chunks[i : i + BATCH_SIZE] for i in range(0, len(chunks), BATCH_SIZE)]

    for batch in tqdm(batches, desc="신규 버전 업로드"):
        texts = [c.get("full_text", "") for c in batch]
        try:
            vectors = _embed_texts(embed_client, embed_model, texts)
        except Exception as e:
            print(f"\n임베딩 오류 (배치 건너뜀): {e}")
            continue

        upsert_payload = []
        for chunk, vec in zip(batch, vectors):
            law_name = chunk.get("law_name", "")
            article_number = chunk.get("article_number", "")
            full_text = chunk.get("full_text", "")
            tags = _tag_chunk(law_name, article_number, full_text)
            metadata = {
                "law_name": law_name,
                "article_number": article_number,
                "article_title": chunk.get("article_title", ""),
                "article_type": chunk.get("article_type", ""),
                "effective_date": int(chunk["effective_date"]) if chunk.get("effective_date") else 0,
                "expiration_date": int(chunk["expiration_date"]) if chunk.get("expiration_date") else 99991231,
                "version_mst": chunk.get("version_mst", chunk.get("law_mst", "")),
                "law_category": chunk.get("law_category", ""),
                "source": "law.go.kr",
                "source_label": f"법령 ({law_name})",
                "linked_buchik_ids": chunk.get("linked_buchik_ids", []),
                "entity_scopes": tags["entity_scopes"],
                "topic_tags": tags["topic_tags"],
                "tax_types": tags["tax_types"],
                "full_text": full_text[:4000],
            }
            upsert_payload.append(
                {"id": chunk["id"], "values": vec, "metadata": metadata}
            )

        index.upsert(vectors=upsert_payload, namespace=PINECONE_NAMESPACE)
        total_upserted += len(upsert_payload)
        time.sleep(0.2)

    print(f"\n[완료] {total_upserted}개 신규 벡터 업로드 → {PINECONE_INDEX_NAME}/{PINECONE_NAMESPACE}")
    return total_upserted


if __name__ == "__main__":
    embed_and_upload()
