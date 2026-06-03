"""Natural-language question service for the tax RAG engine."""
from __future__ import annotations

import json
import os
import time as _time
from typing import Optional

import anthropic
from dotenv import load_dotenv
from pydantic import BaseModel

from src.agents.prompts import RAG_SYSTEM_PROMPT, RAG_USER_TEMPLATE
from src.retrieval.tax_law_search import retrieve_tax_law

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-4-7")


class TaxAnswer(BaseModel):
    answer: str
    citations: list[str]
    chunk_ids: list[str]
    confidence: float
    missing_facts: list[str]
    warnings: list[str]


def answer_with_citations(
    question: str,
    as_of_date: Optional[str] = None,
    facts: Optional[dict] = None,
    enable_trace: bool = True,
) -> TaxAnswer:
    """Search, rerank, ask the LLM, and return a citation-bound answer."""
    t0 = _time.time()
    chunks = retrieve_tax_law(question, as_of_date=as_of_date)

    if not chunks:
        return TaxAnswer(
            answer="관련 법령을 찾을 수 없습니다.",
            citations=[],
            chunk_ids=[],
            confidence=0.0,
            missing_facts=[],
            warnings=["검색 결과 없음"],
        )

    if not ANTHROPIC_API_KEY:
        return TaxAnswer(
            answer="[ANTHROPIC_API_KEY 미설정 — 검색 결과만 반환]\n\n"
            + "\n\n".join(
                f"[{c.law_name} 제{c.article_number}조] {c.full_text[:300]}" for c in chunks
            ),
            citations=[
                f"{c.law_name} 제{c.article_number}조 {c.article_title}".strip()
                for c in chunks
            ],
            chunk_ids=[c.id for c in chunks],
            confidence=0.0,
            missing_facts=[],
            warnings=["LLM 추론 미수행 — ANTHROPIC_API_KEY 필요"],
        )

    context_parts = []
    for index, chunk in enumerate(chunks, 1):
        context_parts.append(
            f"[{index}] {chunk.law_name} 제{chunk.article_number}조 {chunk.article_title}\n"
            f"(chunk_id: {chunk.id}, rerank_score: {chunk.score:.4f})\n"
            f"{chunk.full_text}"
        )

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=2048,
        system=RAG_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": RAG_USER_TEMPLATE.format(
                    context="\n\n".join(context_parts),
                    question=question,
                ),
            }
        ],
    )

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {
            "answer": raw,
            "citations": [f"{c.law_name} 제{c.article_number}조" for c in chunks],
            "chunk_ids": [c.id for c in chunks],
            "confidence": 0.5,
            "missing_facts": [],
            "warnings": ["JSON 파싱 실패 — 원문 반환"],
        }

    tax_answer = TaxAnswer(
        answer=data.get("answer", ""),
        citations=data.get("citations", []),
        chunk_ids=data.get("chunk_ids", []),
        confidence=float(data.get("confidence", 0.0)),
        missing_facts=data.get("missing_facts", []),
        warnings=data.get("warnings", []),
    )

    if enable_trace:
        try:
            from src.eval.feedback import generate_trace_id, log_trace

            latency_ms = int((_time.time() - t0) * 1000)
            log_trace(
                trace_id=generate_trace_id(),
                question=question,
                facts=facts or {},
                retrieved_chunk_ids=[c.id for c in chunks],
                rerank_scores=[c.score for c in chunks],
                cited_chunk_ids=tax_answer.chunk_ids,
                answer=tax_answer.answer,
                confidence=tax_answer.confidence,
                missing_facts=tax_answer.missing_facts,
                warnings=tax_answer.warnings,
                as_of_date=as_of_date,
                prompt_version="v1",
                model_version=CLAUDE_MODEL,
                latency_ms=latency_ms,
            )
        except Exception:
            pass

    return tax_answer


async def answer_with_pipeline(fact_json: dict) -> TaxAnswer:
    """Run the structured L1-L5 pipeline and return the natural-language answer shape."""
    from src.api.fact_input import FactInput, fact_input_to_rag_query
    from src.domain.pipeline import run_rag_pipeline
    from src.retrieval.llm_fn import llm_fn
    from src.retrieval.retriever_impl import PineconeTaxLawRetriever

    query = fact_input_to_rag_query(FactInput(**fact_json))
    result = await run_rag_pipeline(query, PineconeTaxLawRetriever(), llm_fn)

    answer = result.answer
    return TaxAnswer(
        answer=answer.answer,
        citations=[
            f"{citation.article}" if hasattr(citation, "article") else str(citation)
            for citation in answer.citations
        ],
        chunk_ids=answer.chunk_ids,
        confidence=answer.confidence,
        missing_facts=answer.missing_facts,
        warnings=answer.warnings,
    )
