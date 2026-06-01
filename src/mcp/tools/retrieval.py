"""Retrieval tools exposed by the MCP server."""
from __future__ import annotations

from typing import Any

from src.api.fact_input import FactInput, fact_input_to_rag_query
from src.application.serializers import chunk_to_payload
from src.config import RETRIEVER_RERANK_TOP_N, RETRIEVER_TOP_K
from src.retrieval.retriever_impl import PineconeTaxLawRetriever


def retrieve_tax_context_payload(
    fact_json: dict[str, Any],
    query_text: str = "",
    top_k: int = RETRIEVER_TOP_K,
    rerank_top_n: int = RETRIEVER_RERANK_TOP_N,
    include_buchik: bool = True,
) -> dict[str, Any]:
    """Run Pinecone + BGE retrieval and return API-consumable chunks."""
    fact_for_schema = {
        k: v
        for k, v in fact_json.items()
        if not k.startswith("simulation_") and k != "necessary_expenses"
    }
    if fact_for_schema.get("property_type") == "오피스텔":
        fact_for_schema["property_type"] = "주거용오피스텔"

    query = fact_input_to_rag_query(FactInput(**fact_for_schema))
    query.include_buchik = include_buchik
    retriever = PineconeTaxLawRetriever(top_k=top_k, rerank_top_n=rerank_top_n)
    chunks = retriever.retrieve_with_buchik(query, query_text=query_text or None)
    return {
        "status": "ok",
        "query_text": query_text or query.fact_vector.to_text(),
        "count": len(chunks),
        "chunks": [chunk_to_payload(chunk) for chunk in chunks],
    }

