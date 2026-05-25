"""Centralized runtime configuration.

Environment variables are loaded once here so application modules can avoid
scattering ``load_dotenv()`` and ``os.getenv()`` calls across the codebase.
"""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return int(raw)


def _optional_float_env(name: str) -> float | None:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return None
    try:
        return float(raw)
    except ValueError:
        return None


# law.go.kr DRF API
LAW_API_OC = os.getenv("LAW_API_OC", "jctax")
LAW_API_BASE_URL = os.getenv("LAW_API_BASE_URL", "https://www.law.go.kr/DRF")

# LLM
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
CLAUDE_FAST_MODEL = os.getenv("CLAUDE_FAST_MODEL", "claude-haiku-4-5-20251001")

# Embeddings
UPSTAGE_API_KEY = os.getenv("UPSTAGE_API_KEY")
UPSTAGE_EMBEDDING_MODEL = os.getenv("UPSTAGE_EMBEDDING_MODEL", "solar-embedding-1-large-passage")
UPSTAGE_QUERY_EMBEDDING_MODEL = os.getenv("UPSTAGE_QUERY_EMBEDDING_MODEL", "solar-embedding-1-large-query")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large")

# Pinecone
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "tax-rag")
PINECONE_NAMESPACE = os.getenv("PINECONE_NAMESPACE", "tax-law")
PINECONE_CLOUD = os.getenv("PINECONE_CLOUD", "aws")
PINECONE_REGION = os.getenv("PINECONE_REGION", "us-east-1")
PINECONE_HYBRID_ALPHA = _optional_float_env("PINECONE_HYBRID_ALPHA")

# Retrieval / reranking
RETRIEVER_TOP_K = _int_env("RETRIEVER_TOP_K", 20)
RETRIEVER_RERANK_TOP_N = _int_env("RETRIEVER_RERANK_TOP_N", 7)
RETRIEVER_PREFILTER_K = _int_env("RETRIEVER_PREFILTER_K", 8)
BGE_RERANKER_MODEL = os.getenv("BGE_RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")

# Service ports
MCP_HOST = os.getenv("MCP_HOST", "0.0.0.0")
MCP_PORT = _int_env("MCP_PORT", 8001)
FASTAPI_PORT = _int_env("FASTAPI_PORT", 8000)
STREAMLIT_PORT = _int_env("STREAMLIT_PORT", 8501)
