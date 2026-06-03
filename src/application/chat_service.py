"""Chat use cases used by the HTTP API."""
from __future__ import annotations

import asyncio
import uuid
from typing import Any, AsyncGenerator, Optional, Union

from src.api.fact_input import FactInput, fact_input_to_rag_query
from src.application.serializers import pipeline_result_to_response
from src.domain.pipeline import PipelineResult, run_rag_pipeline, run_rag_pipeline_stream
from src.retrieval.llm_fn import llm_fn, llm_fn_stream
from src.retrieval.mcp_retriever import McpTaxLawRetriever


def _normalize_fact_json(fact_json: dict[str, Any]) -> dict[str, Any]:
    fact_for_schema = {
        k: v
        for k, v in fact_json.items()
        if not k.startswith("simulation_") and k != "necessary_expenses"
    }
    if fact_for_schema.get("property_type") == "오피스텔":
        fact_for_schema["property_type"] = "주거용오피스텔"
    return fact_for_schema


def _input_error_response(session_id: str, exc: Exception) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "verdict": "사실관계부족",
        "answer": f"입력 형식 오류 — 필수 항목 누락: {exc}",
        "confidence": 0.0,
        "citations": [],
        "chunk_ids": [],
        "missing_facts": [f"입력 형식 오류: {exc}"],
        "warnings": [],
        "blocked": True,
        "mode": "pipeline",
        "consulting_scenarios": [],
        "debate_record": None,
    }


def _empty_input_response(session_id: str) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "verdict": "사실관계부족",
        "answer": "fact_json 또는 question 중 하나를 입력해 주세요.",
        "confidence": 0.0,
        "citations": [],
        "chunk_ids": [],
        "missing_facts": [],
        "warnings": ["입력 없음"],
        "blocked": True,
        "mode": "none",
        "consulting_scenarios": [],
        "debate_record": None,
    }


async def run_chat(
    fact_json: Optional[dict[str, Any]] = None,
    question: Optional[str] = None,
    session_id: Optional[str] = None,
    enable_debate: bool = False,
    query_mode: str = "report",
) -> dict[str, Any]:
    """Run one chat turn. Structured cases use MCP-backed retrieval."""
    sid = session_id or str(uuid.uuid4())[:8]

    if fact_json:
        try:
            query = fact_input_to_rag_query(FactInput(**_normalize_fact_json(fact_json)))
        except Exception as exc:
            return _input_error_response(sid, exc)

        retriever = McpTaxLawRetriever(fact_json=fact_json)
        result = await run_rag_pipeline(
            query,
            retriever,
            llm_fn,
            fact_json=fact_json,
            enable_debate=enable_debate,
            query_mode=query_mode,
        )
        return pipeline_result_to_response(result, session_id=sid, mode="pipeline")

    if question:
        from src.application.question_service import answer_with_citations

        loop = asyncio.get_event_loop()
        ans = await loop.run_in_executor(None, lambda: answer_with_citations(question))
        return {
            "session_id": sid,
            "verdict": "사실관계부족",
            "answer": ans.answer,
            "confidence": ans.confidence,
            "citations": ans.citations,
            "chunk_ids": ans.chunk_ids,
            "missing_facts": ans.missing_facts,
            "warnings": ans.warnings,
            "blocked": False,
            "mode": "legacy",
            "consulting_scenarios": [],
            "debate_record": None,
        }

    return _empty_input_response(sid)


async def stream_chat(
    fact_json: Optional[dict[str, Any]] = None,
    question: Optional[str] = None,
    session_id: Optional[str] = None,
    enable_debate: bool = False,
    query_mode: str = "report",
) -> AsyncGenerator[Union[str, dict[str, Any]], None]:
    """Stream one chat turn as pipeline events, token chunks, and final response."""
    sid = session_id or str(uuid.uuid4())[:8]

    if not fact_json:
        yield await run_chat(
            fact_json=fact_json,
            question=question,
            session_id=sid,
            enable_debate=enable_debate,
            query_mode=query_mode,
        )
        return

    try:
        query = fact_input_to_rag_query(FactInput(**_normalize_fact_json(fact_json)))
    except Exception as exc:
        yield _input_error_response(sid, exc)
        return

    retriever = McpTaxLawRetriever(fact_json=fact_json)
    async for item in run_rag_pipeline_stream(
        query,
        retriever,
        llm_fn_stream,
        fact_json=fact_json,
        enable_debate=enable_debate,
        query_mode=query_mode,
    ):
        if isinstance(item, PipelineResult):
            yield pipeline_result_to_response(item, session_id=sid, mode="pipeline")
        else:
            yield item
