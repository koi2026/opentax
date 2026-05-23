"""
임베딩 클라이언트 — Upstage Solar (기본) / OpenAI (fallback).
싱글톤 클라이언트로 모듈 수명 동안 재사용.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Optional, Tuple

from openai import OpenAI

from src.config import (
    OPENAI_API_KEY,
    OPENAI_EMBEDDING_MODEL,
    UPSTAGE_API_KEY,
    UPSTAGE_QUERY_EMBEDDING_MODEL,
)

_embed_client: Optional[OpenAI] = None
_embed_model: Optional[str] = None


def _get_embed_client() -> Tuple[OpenAI, str]:
    """임베딩 클라이언트와 모델명 반환 — Upstage 우선, 없으면 OpenAI."""
    global _embed_client, _embed_model
    if _embed_client is None:
        if UPSTAGE_API_KEY:
            _embed_client = OpenAI(
                api_key=UPSTAGE_API_KEY,
                base_url="https://api.upstage.ai/v1",
            )
            _embed_model = UPSTAGE_QUERY_EMBEDDING_MODEL
        elif OPENAI_API_KEY:
            _embed_client = OpenAI(api_key=OPENAI_API_KEY)
            _embed_model = OPENAI_EMBEDDING_MODEL
        else:
            raise RuntimeError("UPSTAGE_API_KEY 또는 OPENAI_API_KEY가 필요합니다")
    return _embed_client, _embed_model


def embed_query(query: str) -> list[float]:
    """쿼리 텍스트를 임베딩 벡터로 변환 (2000자 제한)."""
    client, model = _get_embed_client()
    resp = client.embeddings.create(model=model, input=[query[:2000]])
    return resp.data[0].embedding


def bm25_sparse_vector(
    text: str,
    vocab: Optional[dict[str, int]] = None,
    k1: float = 1.5,
    b: float = 0.75,
    avg_doc_len: float = 200.0,
) -> dict:
    """BM25 sparse vector for Pinecone hybrid search.

    Tokenizes Korean text plus article-number patterns (e.g. 제89조, §97)
    and returns Pinecone-compatible sparse_values.

    vocab: {token: index} mapping. If None, uses abs(hash(token)) % 65536.
    Returns {"indices": [...], "values": [...]}.
    """
    tokens = re.findall(r"제\d+조의?\d*|§\d+|[가-힣]+|[a-zA-Z0-9]+", text)
    if not tokens:
        return {"indices": [], "values": []}

    tf = Counter(tokens)
    doc_len = len(tokens)

    indices: list[int] = []
    values: list[float] = []
    for token, freq in tf.items():
        idx = vocab.get(token, abs(hash(token)) % 65536) if vocab else abs(hash(token)) % 65536
        tf_score = (freq * (k1 + 1)) / (freq + k1 * (1 - b + b * doc_len / avg_doc_len))
        indices.append(idx)
        values.append(float(tf_score))

    return {"indices": indices, "values": values}
