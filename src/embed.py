"""
임베딩 생성 및 Pinecone 업로드
data/processed/all_chunks.json → Pinecone Serverless
"""
import os
import json
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from pinecone import Pinecone, ServerlessSpec

load_dotenv()

UPSTAGE_API_KEY = os.getenv("UPSTAGE_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
UPSTAGE_EMBEDDING_MODEL = os.getenv("UPSTAGE_EMBEDDING_MODEL", "solar-embedding-1-large-passage")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "tax-rag")
PINECONE_NAMESPACE = os.getenv("PINECONE_NAMESPACE", "tax-law")
PINECONE_CLOUD = os.getenv("PINECONE_CLOUD", "aws")
PINECONE_REGION = os.getenv("PINECONE_REGION", "us-east-1")

PROCESSED_DIR = Path("data/processed")
BATCH_SIZE = 50  # Upstage API 안정성 고려
MAX_EMBED_CHARS = 2000  # solar-embedding-1-large 최대 4000토큰 → 한국어 약 2000자 이내


def _require(key: str, value: str | None) -> str:
    if not value:
        raise RuntimeError(f"환경변수 누락: {key}")
    return value


def get_embedding_client() -> tuple[OpenAI, str]:
    """Upstage Solar 우선, OpenAI fallback"""
    if UPSTAGE_API_KEY:
        print("임베딩: Upstage Solar")
        return (
            OpenAI(api_key=UPSTAGE_API_KEY, base_url="https://api.upstage.ai/v1"),
            UPSTAGE_EMBEDDING_MODEL,
        )
    if OPENAI_API_KEY:
        print("임베딩: OpenAI text-embedding-3-large (fallback)")
        return OpenAI(api_key=OPENAI_API_KEY), "text-embedding-3-large"
    raise RuntimeError("UPSTAGE_API_KEY 또는 OPENAI_API_KEY 중 하나는 필수입니다")


def embed_texts(client: OpenAI, model: str, texts: list[str]) -> list[list[float]]:
    truncated = [t[:MAX_EMBED_CHARS] for t in texts]
    resp = client.embeddings.create(model=model, input=truncated)
    return [d.embedding for d in resp.data]


def get_or_create_index(pc: Pinecone, dimension: int) -> None:
    existing_names = [idx.name for idx in pc.list_indexes()]
    if PINECONE_INDEX_NAME not in existing_names:
        print(f"Pinecone 인덱스 생성 중: {PINECONE_INDEX_NAME} (dim={dimension})")
        pc.create_index(
            name=PINECONE_INDEX_NAME,
            dimension=dimension,
            metric="cosine",
            spec=ServerlessSpec(cloud=PINECONE_CLOUD, region=PINECONE_REGION),
        )
        while True:
            status = pc.describe_index(PINECONE_INDEX_NAME).status
            if status.get("ready"):
                break
            print("  인덱스 준비 대기 중...")
            time.sleep(2)
        print("인덱스 준비 완료")
    else:
        print(f"기존 인덱스 사용: {PINECONE_INDEX_NAME}")


def embed_and_upsert() -> None:
    pinecone_api_key = _require("PINECONE_API_KEY", PINECONE_API_KEY)

    chunks = json.loads((PROCESSED_DIR / "all_chunks.json").read_text(encoding="utf-8"))
    print(f"청크 로드: {len(chunks)}개")

    client, model = get_embedding_client()

    # 차원 확인 (샘플 1개)
    sample_emb = embed_texts(client, model, ["테스트"])[0]
    dimension = len(sample_emb)
    print(f"임베딩 차원: {dimension}")

    pc = Pinecone(api_key=pinecone_api_key)
    get_or_create_index(pc, dimension)
    index = pc.Index(PINECONE_INDEX_NAME)

    upserted = 0
    total_batches = (len(chunks) + BATCH_SIZE - 1) // BATCH_SIZE
    for batch_idx, i in enumerate(range(0, len(chunks), BATCH_SIZE), start=1):
        print(f"Pinecone 업로드 {batch_idx}/{total_batches} 배치 시작", flush=True)
        batch = chunks[i : i + BATCH_SIZE]
        texts = [c["full_text"] for c in batch]
        embeddings = embed_texts(client, model, texts)

        vectors = [
            {
                "id": c["id"],
                "values": emb,
                "metadata": {
                    "law_name": c["law_name"],
                    "law_category": c["law_category"],
                    "article_number": c["article_number"],
                    "article_title": c["article_title"],
                    "effective_date": c["effective_date"],
                    # full_text는 검색 결과 표시용으로 저장 (2000자 제한)
                    "full_text": c["full_text"][:2000],
                    "source": "law.go.kr",
                },
            }
            for c, emb in zip(batch, embeddings)
        ]

        index.upsert(vectors=vectors, namespace=PINECONE_NAMESPACE)
        upserted += len(vectors)
        print(f"Pinecone 업로드 {batch_idx}/{total_batches} 배치 완료: {len(vectors)}개", flush=True)

    print(f"[완료] {upserted}개 벡터 업로드 → {PINECONE_INDEX_NAME}/{PINECONE_NAMESPACE}")
    stats = index.describe_index_stats()
    print(f"인덱스 통계: {stats}")


if __name__ == "__main__":
    embed_and_upsert()
