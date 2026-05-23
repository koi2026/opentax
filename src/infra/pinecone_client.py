"""
Pinecone Serverless 클라이언트 — 인덱스 싱글톤 + 검색 헬퍼.
"""
from __future__ import annotations

from typing import Optional

from pinecone import Pinecone

from src.config import PINECONE_API_KEY, PINECONE_INDEX_NAME, PINECONE_NAMESPACE

_pinecone_index = None


def get_pinecone_index():
    """Pinecone 인덱스 싱글톤."""
    global _pinecone_index
    if _pinecone_index is None:
        if not PINECONE_API_KEY:
            raise RuntimeError("PINECONE_API_KEY가 필요합니다")
        pc = Pinecone(api_key=PINECONE_API_KEY)
        _pinecone_index = pc.Index(PINECONE_INDEX_NAME)
    return _pinecone_index


def query_pinecone(
    vector: list[float],
    top_k: int = 20,
    namespace: str = PINECONE_NAMESPACE,
    filter_dict: Optional[dict] = None,
    sparse_vector: Optional[dict] = None,
    alpha: Optional[float] = None,
) -> list[dict]:
    """벡터 검색 — matches 리스트 반환 (없으면 빈 리스트).

    sparse_vector: {"indices": [...], "values": [...]} for BM25 hybrid search.
    alpha: 0.0 = pure sparse, 1.0 = pure dense, 0.75 = typical hybrid. None = dense only.
    """
    index = get_pinecone_index()
    kwargs: dict = dict(
        vector=vector,
        top_k=top_k,
        namespace=namespace,
        include_metadata=True,
    )
    if filter_dict:
        kwargs["filter"] = filter_dict

    if sparse_vector is not None and alpha is not None:
        kwargs["vector"] = [v * alpha for v in vector]
        kwargs["sparse_vector"] = {
            "indices": sparse_vector["indices"],
            "values": [v * (1 - alpha) for v in sparse_vector["values"]],
        }

    result = index.query(**kwargs)
    return result.get("matches", []) or []
