from __future__ import annotations

import asyncio
from datetime import date

from src.domain.chunk_metadata import (
    AmendmentType,
    AppendixType,
    ApplicabilityRuleType,
    ApplicabilitySpec,
    LawChunkMetadata,
    LawId,
    LawLevel,
)
from src.domain.retriever import RetrievedChunk
from src.domain.tax_answer import Citation, TaxAnswer
from src.retrieval.multi_agent_reasoner import (
    run_multi_agent_reasoning,
    run_multi_agent_reasoning_stream,
    synthesize_answers,
)


def _chunk(chunk_id: str = "law-1") -> RetrievedChunk:
    return RetrievedChunk(
        metadata=LawChunkMetadata(
            chunk_id=chunk_id,
            law_id=LawId.INCOME_TAX_ACT,
            law_name="소득세법",
            law_level=LawLevel.ACT,
            article_number="89",
            paragraph=None,
            item=None,
            lsi_seq="",
            promulgation_date=date(2024, 1, 1),
            effective_from=date(2024, 1, 1),
            effective_to=None,
            amendment_type=AmendmentType.PARTIAL,
            article_lineage_root="89",
            appendix_type=AppendixType.MAIN_BODY,
            applicability=ApplicabilitySpec(rule_type=ApplicabilityRuleType.NONE),
        ),
        content="제89조 비과세 양도소득",
        score=0.9,
    )


def test_synthesis_keeps_only_agent_a_retrieved_citations() -> None:
    agent_a = TaxAnswer(
        answer="검색 조문 기준 비과세",
        verdict="비과세",
        confidence=0.88,
        citations=[
            Citation(chunk_id="law-1", article="소득세법 제89조", excerpt="", law_version="20240101"),
            Citation(chunk_id="phantom", article="소득세법 제999조", excerpt="", law_version="20240101"),
        ],
    )
    agent_b = TaxAnswer(
        answer="비검색 검토상 일반과세 가능성",
        verdict="일반과세",
        confidence=0.7,
        citations=[
            Citation(chunk_id="b-made-up", article="소득세법 제104조", excerpt="", law_version="20240101"),
        ],
        missing_facts=["실거주 입증자료"],
        warnings=["Agent B warning"],
    )

    result = synthesize_answers(agent_a, agent_b, {"law-1"})

    assert result.answer.verdict == "비과세"
    assert [c.chunk_id for c in result.answer.citations] == ["law-1"]
    assert "실거주 입증자료" in result.answer.missing_facts
    assert result.agent_traces["disagreement"] is True
    assert any("비검색 독립 검토와 불일치" in warning for warning in result.answer.warnings)


def test_multi_agent_reasoning_falls_back_when_langgraph_unavailable_or_agent_b_missing_key() -> None:
    async def agent_a_fn(*args, **kwargs):
        return TaxAnswer(
            answer="Agent A result",
            verdict="비과세",
            confidence=0.9,
            citations=[Citation(chunk_id="law-1", article="소득세법 제89조", excerpt="", law_version="20240101")],
        )

    result = asyncio.run(
        run_multi_agent_reasoning(
            "1세대1주택 비과세 여부",
            [_chunk("law-1")],
            [],
            fact_json={"transfer_date": "20240601"},
            agent_a_fn=agent_a_fn,
        )
    )

    assert result.answer.verdict == "비과세"
    assert result.answer.citations[0].chunk_id == "law-1"
    assert result.agent_traces["agent_a"]["verdict"] == "비과세"
    assert result.agent_traces["agent_b"]["verdict"] == "사실관계부족"


def test_multi_agent_stream_emits_agent_a_reasoning_deltas() -> None:
    async def agent_a_stream_fn(*args, **kwargs):
        yield "A reasoning 1 "
        yield "A reasoning 2"
        yield TaxAnswer(
            answer="Agent A result",
            verdict="비과세",
            confidence=0.9,
            citations=[Citation(chunk_id="law-1", article="소득세법 제89조", excerpt="", law_version="20240101")],
        )

    async def run() -> list[dict]:
        events = []
        async for item in run_multi_agent_reasoning_stream(
            "1세대1주택 비과세 여부",
            [_chunk("law-1")],
            [],
            fact_json={"transfer_date": "20240601"},
            agent_a_stream_fn=agent_a_stream_fn,
        ):
            if isinstance(item, dict):
                events.append(item)
        return events

    events = asyncio.run(run())

    assert any(
        event.get("event") == "agent_reasoning_delta"
        and event.get("data", {}).get("agent") == "A"
        and event.get("data", {}).get("text") == "A reasoning 1 "
        for event in events
    )
    assert any(
        event.get("event") == "agent_reasoning_delta"
        and event.get("data", {}).get("agent") == "A"
        and event.get("data", {}).get("text") == "A reasoning 2"
        for event in events
    )


def test_multi_agent_stream_continues_after_one_agent_done() -> None:
    async def agent_a_stream_fn(*args, **kwargs):
        yield "A fast reasoning"
        yield TaxAnswer(
            answer="Agent A result",
            verdict="비과세",
            confidence=0.9,
            citations=[Citation(chunk_id="law-1", article="소득세법 제89조", excerpt="", law_version="20240101")],
        )

    async def run() -> list[dict]:
        original_agent_b_stream = __import__(
            "src.retrieval.multi_agent_reasoner",
            fromlist=["_run_agent_b_stream"],
        )._run_agent_b_stream

        async def slow_agent_b_stream(*args, **kwargs):
            emit_delta = args[-1]
            await asyncio.sleep(0.01)
            await emit_delta("B", "B still reasoning")
            return TaxAnswer(answer="Agent B result", verdict="일반과세", confidence=0.6)

        module = __import__("src.retrieval.multi_agent_reasoner", fromlist=["_run_agent_b_stream"])
        module._run_agent_b_stream = slow_agent_b_stream
        try:
            events = []
            async for item in run_multi_agent_reasoning_stream(
                "1세대1주택 비과세 여부",
                [_chunk("law-1")],
                [],
                fact_json={"transfer_date": "20240601"},
                agent_a_stream_fn=agent_a_stream_fn,
            ):
                if isinstance(item, dict):
                    events.append(item)
            return events
        finally:
            module._run_agent_b_stream = original_agent_b_stream

    events = asyncio.run(run())
    a_done_index = next(
        idx
        for idx, event in enumerate(events)
        if event.get("event") == "agent_reasoning_done"
        and event.get("data", {}).get("agent") == "A"
    )
    b_delta_index = next(
        idx
        for idx, event in enumerate(events)
        if event.get("event") == "agent_reasoning_delta"
        and event.get("data", {}).get("agent") == "B"
        and event.get("data", {}).get("text") == "B still reasoning"
    )

    assert b_delta_index > a_done_index
