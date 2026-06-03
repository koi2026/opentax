"""TaxLawRetriever implementation backed by the MCP retrieval server."""
from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any, List, Optional

from src.application.serializers import payload_to_chunk
from src.config import MCP_SERVER_URL, RETRIEVER_RERANK_TOP_N, RETRIEVER_TOP_K
from src.domain.chunk_metadata import LawChunkMetadata
from src.domain.query_input import RAGQueryInput
from src.domain.retriever import RetrievedChunk, TaxLawRetriever


def _mcp_sse_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    return base if base.endswith("/sse") else f"{base}/sse"


async def _call_mcp_tool_async(
    server_url: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Call a FastMCP SSE tool and normalize the returned payload."""
    from mcp import ClientSession
    from mcp.client.sse import sse_client

    async with sse_client(_mcp_sse_url(server_url)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)

    content = getattr(result, "content", None) or []
    if getattr(result, "isError", False):
        message = ""
        if content:
            first = content[0]
            message = first.get("text", "") if isinstance(first, dict) else getattr(first, "text", "")
        raise RuntimeError(f"MCP tool {tool_name} failed: {message or result}")

    structured = getattr(result, "structuredContent", None) or getattr(result, "structured_content", None)
    if isinstance(structured, dict):
        return structured

    if content:
        first = content[0]
        if isinstance(first, dict):
            if isinstance(first.get("json"), dict):
                return first["json"]
            text = first.get("text")
        else:
            text = getattr(first, "text", None)
        if text:
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"MCP tool {tool_name} returned non-JSON text: {text}") from exc
            if isinstance(parsed, dict):
                return parsed

    raise RuntimeError(f"MCP tool {tool_name} returned an unsupported payload")


def _run_async_from_sync(coro):
    """Run an async MCP call from the synchronous retriever contract."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(lambda: asyncio.run(coro)).result()


class McpTaxLawRetriever(TaxLawRetriever):
    """Retrieve legal context by calling the MCP retrieval tool."""

    def __init__(
        self,
        fact_json: dict[str, Any],
        server_url: str = MCP_SERVER_URL,
        top_k: int = RETRIEVER_TOP_K,
        rerank_top_n: int = RETRIEVER_RERANK_TOP_N,
    ):
        self.fact_json = fact_json
        self.server_url = server_url
        self.top_k = top_k
        self.rerank_top_n = rerank_top_n
        self._cache: dict[str, RetrievedChunk] = {}

    def _retrieve_payloads(self, query_text: str, include_buchik: bool) -> list[dict[str, Any]]:
        payload = _run_async_from_sync(
            _call_mcp_tool_async(
                self.server_url,
                "retrieve_tax_context",
                {
                    "fact_json": self.fact_json,
                    "query_text": query_text,
                    "top_k": self.top_k,
                    "rerank_top_n": self.rerank_top_n,
                    "include_buchik": include_buchik,
                },
            )
        )
        if payload.get("status") != "ok":
            raise RuntimeError(f"MCP retrieval failed: {payload}")
        chunks = payload.get("chunks") or []
        if not isinstance(chunks, list):
            raise RuntimeError("MCP retrieval returned invalid chunks payload")
        return chunks

    def retrieve(self, query: RAGQueryInput, query_text: Optional[str] = None) -> List[RetrievedChunk]:
        text = query_text or query.fact_vector.to_text()
        chunks = [payload_to_chunk(item) for item in self._retrieve_payloads(text, include_buchik=False)]
        self._cache.update({chunk.metadata.chunk_id: chunk for chunk in chunks})
        return chunks

    def retrieve_with_buchik(self, query: RAGQueryInput, query_text: Optional[str] = None) -> List[RetrievedChunk]:
        text = query_text or query.fact_vector.to_text()
        chunks = [payload_to_chunk(item) for item in self._retrieve_payloads(text, include_buchik=query.include_buchik)]
        self._cache.update({chunk.metadata.chunk_id: chunk for chunk in chunks})
        return chunks

    def _get_chunk_by_id(self, chunk_id: str) -> Optional[LawChunkMetadata]:
        chunk = self._cache.get(chunk_id)
        return chunk.metadata if chunk else None

    def _get_content(self, chunk_id: str) -> str:
        chunk = self._cache.get(chunk_id)
        return chunk.content if chunk else ""
