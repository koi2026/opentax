"""Human-facing tax-law search helpers.

This module owns the legacy natural-language law search path that is still used
by MCP helper tools, eval utilities, and CrewAI tools. Structured JSON cases
continue to use the MCP-backed pipeline retriever.
"""
from __future__ import annotations

import os
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel

from src.infra import embedder as _embedder
from src.infra import pinecone_client as _pinecone_client
from src.infra import reranker as _reranker_mod

load_dotenv()

PINECONE_NAMESPACE = os.getenv("PINECONE_NAMESPACE", "tax-law")


class LawChunk(BaseModel):
    id: str
    law_name: str
    article_number: str
    article_title: str
    effective_date: str
    expiration_date: str = ""
    full_text: str
    score: float


def _embed_query(query: str) -> list[float]:
    return _embedder.embed_query(query)


def _get_pinecone_index():
    return _pinecone_client.get_pinecone_index()


def _get_reranker():
    return _reranker_mod.get_reranker()


def _date_str(value) -> str:
    """Convert Pinecone date metadata to a compact YYYYMMDD string."""
    if value is None or value == "":
        return ""
    parsed = int(float(value))
    return "" if parsed in (0, 99991231) else str(parsed)


def retrieve_tax_law(
    query: str,
    top_k: int = 20,
    rerank_top_n: int = 5,
    as_of_date: Optional[str] = None,
) -> list[LawChunk]:
    """
    Search tax-law chunks with vector retrieval and BGE reranking.

    Args:
        query: Natural-language query or article hint.
        top_k: Pinecone candidate count.
        rerank_top_n: Number of reranked chunks to return.
        as_of_date: Optional YYYYMMDD date filter.
    """
    query_vec = _embed_query(query)

    pinecone_filter = None
    if as_of_date:
        as_of_int = int(as_of_date)
        pinecone_filter = {
            "$and": [
                {"effective_date": {"$lte": as_of_int}},
                {"expiration_date": {"$gte": as_of_int}},
            ]
        }

    index = _get_pinecone_index()
    query_kwargs = {
        "vector": query_vec,
        "top_k": top_k,
        "namespace": PINECONE_NAMESPACE,
        "include_metadata": True,
    }
    if pinecone_filter:
        query_kwargs["filter"] = pinecone_filter

    result = index.query(**query_kwargs)
    matches = result.get("matches", [])

    if not matches and pinecone_filter:
        fallback_kwargs = {k: v for k, v in query_kwargs.items() if k != "filter"}
        result = index.query(**fallback_kwargs)
        matches = result.get("matches", [])

    if not matches:
        return []

    reranker = _get_reranker()
    pairs = [(query, match["metadata"].get("full_text", "")) for match in matches]
    rerank_scores = reranker.predict(pairs)

    ranked = sorted(
        zip(rerank_scores, matches),
        key=lambda item: item[0],
        reverse=True,
    )[:rerank_top_n]

    chunks: list[LawChunk] = []
    for score, match in ranked:
        meta = match["metadata"]
        chunks.append(
            LawChunk(
                id=match["id"],
                law_name=meta.get("law_name", ""),
                article_number=meta.get("article_number", ""),
                article_title=meta.get("article_title", ""),
                effective_date=_date_str(meta.get("effective_date")),
                expiration_date=_date_str(meta.get("expiration_date")),
                full_text=meta.get("full_text", ""),
                score=float(score),
            )
        )
    return chunks
