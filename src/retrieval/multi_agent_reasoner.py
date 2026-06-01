"""LangGraph-backed multi-agent reasoning for L4b.

Agent A is the grounded RAG agent. Agent B is an ungrounded independent
reviewer. The synthesis step keeps citations anchored to Agent A's retrieved
chunks and uses Agent B only for disagreement, warnings, and missing facts.
"""
from __future__ import annotations

import asyncio
import json
import operator
import os
from dataclasses import dataclass
from typing import Annotated, Any, AsyncGenerator, Awaitable, Callable, List, Optional, TypedDict, Union

from src.domain.retriever import RetrievedChunk
from src.domain.tax_answer import Citation, TaxAnswer


AgentAFn = Callable[[str, List[RetrievedChunk], List[str], Optional[dict]], Awaitable[TaxAnswer]]
AgentAStreamFn = Callable[
    [str, List[RetrievedChunk], List[str], Optional[dict]],
    AsyncGenerator[Union[str, TaxAnswer], None],
]


def _anthropic_api_key() -> Optional[str]:
    return os.getenv("ANTHROPIC_API_KEY")


def _claude_model() -> str:
    return os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")


@dataclass
class MultiAgentReasoningResult:
    """Final synthesized answer plus UI/API trace metadata."""

    answer: TaxAnswer
    agent_traces: dict[str, Any]


class MultiAgentState(TypedDict, total=False):
    enriched_query: str
    fact_json: Optional[dict]
    chunks: List[RetrievedChunk]
    missing_hints: List[str]
    agent_a_answer: TaxAnswer
    agent_b_answer: TaxAnswer
    synthesized_answer: TaxAnswer
    agent_traces: dict[str, Any]
    stream_events: Annotated[list[dict[str, Any]], operator.add]


def _short_summary(answer: TaxAnswer) -> str:
    text = (answer.answer or "").strip().replace("\n", " ")
    return text[:280] + ("..." if len(text) > 280 else "")


def _trace_for_answer(answer: Optional[TaxAnswer], *, error: Optional[str] = None) -> dict[str, Any]:
    if answer is None:
        return {
            "verdict": "사실관계부족",
            "confidence": 0.0,
            "short_summary": "",
            "warnings": [error] if error else [],
        }
    warnings = list(answer.warnings)
    if error:
        warnings.append(error)
    return {
        "verdict": str(answer.verdict),
        "confidence": float(answer.confidence or 0.0),
        "short_summary": _short_summary(answer),
        "warnings": warnings,
    }


_VERDICT_ALIAS = {
    "needs_verification": "사실관계부족",
    "exempt": "비과세",
    "reduced": "감면",
    "heavy_tax": "중과",
    "general": "일반과세",
    "short_term": "단기세율",
    "partially_exempt": "고가주택",
    "uncertain": "사실관계부족",
}


def _normalize_verdict(verdict: str) -> str:
    v = verdict.strip()
    if v in _VERDICT_ALIAS:
        return _VERDICT_ALIAS[v]
    for canonical in ("비과세", "고가주택", "감면", "중과", "일반과세", "단기세율", "사실관계부족"):
        if canonical in v or v in canonical:
            return canonical
    return "사실관계부족"


def _extract_json(text: str) -> str:
    candidate = text.split("<reasoning>", 1)[0].strip() if "<reasoning>" in text else text
    if "```json" in candidate:
        candidate = candidate.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in candidate:
        for part in candidate.split("```"):
            stripped = part.strip()
            if stripped.startswith("{"):
                candidate = stripped
                break
    first = candidate.find("{")
    if first > 0:
        candidate = candidate[first:]
    if not candidate.startswith("{"):
        return candidate.strip()

    depth = 0
    in_str = False
    escape = False
    for idx, ch in enumerate(candidate):
        if escape:
            escape = False
            continue
        if ch == "\\" and in_str:
            escape = True
            continue
        if ch == '"' and not escape:
            in_str = not in_str
        if in_str:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return candidate[:idx + 1].strip()
    return candidate.strip()


def _parse_tax_answer(data: dict[str, Any], *, source_label_map: Optional[dict[str, str]] = None) -> TaxAnswer:
    label_map = source_label_map or {}
    citations = [
        Citation(
            chunk_id=str(c.get("chunk_id", "")),
            article=str(c.get("article", "")),
            excerpt=str(c.get("excerpt", "")),
            law_version=str(c.get("law_version", "")),
            source_label=label_map.get(str(c.get("chunk_id", "")), ""),
        )
        for c in data.get("citations", [])
        if isinstance(c, dict)
    ]
    return TaxAnswer(
        answer=str(data.get("answer", "")),
        verdict=_normalize_verdict(str(data.get("verdict", "사실관계부족"))),
        confidence=float(data.get("confidence", 0.0) or 0.0),
        citations=citations,
        missing_facts=list(data.get("missing_facts") or []),
        warnings=list(data.get("warnings") or []),
    )


def _build_agent_b_prompt(enriched_query: str, fact_json: Optional[dict], missing_hints: List[str]) -> str:
    fact_text = json.dumps(fact_json or {}, ensure_ascii=False, indent=2)
    hints_text = "\n".join(f"- {item}" for item in missing_hints) if missing_hints else "- 없음"
    return f"""당신은 한국 양도소득세 독립 검토 Agent B입니다.
RAG 검색 결과나 chunk_id 없이, 아래 사실관계와 사용자 질문만 보고 독립적으로 판단하십시오.
Claude 내부 세법 지식 사용은 허용되지만, 검색된 법령 근거가 아니므로 citations는 반드시 빈 배열로 두십시오.
확실하지 않은 부분은 missing_facts와 warnings에 명시하십시오.

[fact_json]
{fact_text}

[기존 누락 힌트]
{hints_text}

[질문]
{enriched_query}

반드시 아래 JSON 형식으로 먼저 답변하고, 그 다음에 <reasoning> 태그로 판단 과정을 실시간 서술하십시오.
JSON을 가장 먼저 출력하는 것이 필수입니다.

{{
  "answer": "독립 검토 요약. 검색 근거가 없는 가설임을 전제로 작성",
  "verdict": "비과세" | "고가주택" | "감면" | "중과" | "일반과세" | "단기세율" | "사실관계부족",
  "confidence": 0.0 ~ 1.0,
  "citations": [],
  "missing_facts": [],
  "warnings": []
}}

<reasoning>
아래 heading을 그대로 사용해 판단 과정을 작성하십시오.
사용자에게 보이는 추론 문단에서는 JSON 필드명인 verdict, confidence를 쓰지 말고
반드시 "판정", "신뢰도"라고 표현하십시오.

### 1. 사실관계 확인
입력 사실관계 중 결론에 영향을 주는 항목을 정리합니다.

### 2. 쟁점 식별
비과세·감면·중과·단기세율·고가주택 여부의 핵심 쟁점을 정리합니다.

### 3. 근거 검토
검색 조문 없이 내부 지식과 사실관계만으로 적용 가능성과 반대 가능성을 검토합니다.

### 4. 잠정 결론
최종 판정과 신뢰도를 선택한 이유를 정리합니다.
</reasoning>"""


async def _run_agent_a(
    enriched_query: str,
    chunks: List[RetrievedChunk],
    missing_hints: List[str],
    fact_json: Optional[dict],
    agent_a_fn: AgentAFn,
) -> TaxAnswer:
    return await agent_a_fn(enriched_query, chunks, missing_hints, fact_json)


async def _run_agent_b(
    enriched_query: str,
    fact_json: Optional[dict],
    missing_hints: List[str],
) -> TaxAnswer:
    api_key = _anthropic_api_key()
    if not api_key:
        return TaxAnswer(
            answer="[ANTHROPIC_API_KEY 미설정] Agent B 독립 검토를 건너뜁니다.",
            verdict="사실관계부족",
            confidence=0.0,
            citations=[],
            missing_facts=[],
            warnings=["Agent B LLM 미설정 — 비검색 독립 검토 없음"],
        )

    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=api_key)
    message = await client.messages.create(
        model=_claude_model(),
        max_tokens=4096,
        system=(
            "당신은 한국 양도소득세 독립 검토자입니다. "
            "RAG 검색 근거 없이 판단하므로 citations는 항상 빈 배열입니다."
        ),
        messages=[{"role": "user", "content": _build_agent_b_prompt(enriched_query, fact_json, missing_hints)}],
    )
    raw = message.content[0].text.strip()
    try:
        answer = _parse_tax_answer(json.loads(_extract_json(raw)))
    except Exception:
        answer = TaxAnswer(
            answer=raw,
            verdict="사실관계부족",
            confidence=0.2,
            citations=[],
            warnings=["Agent B JSON 파싱 실패 — 원문 요약만 사용"],
        )

    return answer.with_update(
        citations=[],
        chunk_ids=[],
        warnings=list(answer.warnings) + ["비검색 독립 검토 — 최종 법령 근거로 직접 사용하지 않음"],
    )


async def _run_agent_a_stream(
    enriched_query: str,
    chunks: List[RetrievedChunk],
    missing_hints: List[str],
    fact_json: Optional[dict],
    agent_a_stream_fn: AgentAStreamFn,
    emit_delta: Callable[[str, str], Awaitable[None]],
) -> TaxAnswer:
    final_answer: Optional[TaxAnswer] = None
    async for item in agent_a_stream_fn(enriched_query, chunks, missing_hints, fact_json):
        if isinstance(item, str):
            await emit_delta("A", item)
        elif hasattr(item, "verdict"):
            final_answer = item
    if final_answer is None:
        raise RuntimeError("Agent A 스트리밍 결과가 비어 있습니다.")
    return final_answer


async def _run_agent_b_stream(
    enriched_query: str,
    fact_json: Optional[dict],
    missing_hints: List[str],
    emit_delta: Callable[[str, str], Awaitable[None]],
) -> TaxAnswer:
    api_key = _anthropic_api_key()
    if not api_key:
        return await _run_agent_b(enriched_query, fact_json, missing_hints)

    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=api_key)
    full_text = ""
    emitted_reasoning_chars = 0
    stop_reason = ""

    async with client.messages.stream(
        model=_claude_model(),
        max_tokens=4096,
        system=(
            "당신은 한국 양도소득세 독립 검토자입니다. "
            "RAG 검색 근거 없이 판단하므로 citations는 항상 빈 배열입니다."
        ),
        messages=[{"role": "user", "content": _build_agent_b_prompt(enriched_query, fact_json, missing_hints)}],
    ) as stream:
        async for event in stream:
            if event.type == "message_delta":
                stop_reason = getattr(getattr(event, "delta", None), "stop_reason", "") or stop_reason
                continue
            if event.type != "content_block_delta":
                continue
            text = getattr(event.delta, "text", "")
            if not text:
                continue
            full_text += text

            if "<reasoning>" not in full_text:
                continue
            reasoning = full_text.split("<reasoning>", 1)[1]
            if "</reasoning>" in reasoning:
                reasoning = reasoning.split("</reasoning>", 1)[0]
            new_text = reasoning[emitted_reasoning_chars:]
            if new_text:
                emitted_reasoning_chars += len(new_text)
                await emit_delta("B", new_text)

    try:
        answer = _parse_tax_answer(json.loads(_extract_json(full_text)))
    except Exception:
        answer = TaxAnswer(
            answer=full_text,
            verdict="사실관계부족",
            confidence=0.2,
            citations=[],
            warnings=["Agent B JSON 파싱 실패 — 원문 요약만 사용"],
        )

    incomplete_reasoning = "### 4. 잠정 결론" not in full_text
    return answer.with_update(
        citations=[],
        chunk_ids=[],
        warnings=list(answer.warnings)
        + (["Agent B 출력이 토큰 한도에서 종료되었습니다."] if stop_reason == "max_tokens" else [])
        + (["Agent B 추론이 공통 heading 포맷을 끝까지 채우기 전에 종료되었습니다."] if incomplete_reasoning else [])
        + ["비검색 독립 검토 — 최종 법령 근거로 직접 사용하지 않음"],
    )


def synthesize_answers(
    agent_a_answer: TaxAnswer,
    agent_b_answer: Optional[TaxAnswer],
    retrieved_chunk_ids: set[str],
) -> MultiAgentReasoningResult:
    """Synthesize A/B answers while preserving RAG-first citation policy."""
    safe_citations = [
        citation
        for citation in agent_a_answer.citations
        if citation.chunk_id and citation.chunk_id in retrieved_chunk_ids
    ]
    warnings = list(agent_a_answer.warnings)
    missing_facts = list(agent_a_answer.missing_facts)
    disagreement = False

    if agent_b_answer is not None:
        for item in agent_b_answer.missing_facts:
            if item not in missing_facts:
                missing_facts.append(item)
        for item in agent_b_answer.warnings:
            if item not in warnings:
                warnings.append(item)
        disagreement = str(agent_b_answer.verdict) != str(agent_a_answer.verdict)
        if disagreement:
            warnings.append(
                f"비검색 독립 검토와 불일치 — Agent A(RAG)={agent_a_answer.verdict}, "
                f"Agent B(비검색)={agent_b_answer.verdict}. 최종 판단은 검색 법령 근거를 우선합니다."
            )

    answer = agent_a_answer.with_update(
        citations=safe_citations,
        missing_facts=missing_facts,
        warnings=warnings,
        chunk_ids=list(retrieved_chunk_ids),
    )
    traces = {
        "agent_a": _trace_for_answer(agent_a_answer),
        "agent_b": _trace_for_answer(agent_b_answer),
        "disagreement": disagreement,
        "policy": "RAG 우선 — Agent B는 누락 쟁점과 경고 보강에만 사용",
    }
    return MultiAgentReasoningResult(answer=answer, agent_traces=traces)


async def _run_parallel_fallback(
    enriched_query: str,
    chunks: List[RetrievedChunk],
    missing_hints: List[str],
    fact_json: Optional[dict],
    agent_a_fn: AgentAFn,
) -> MultiAgentReasoningResult:
    agent_a_task = asyncio.create_task(_run_agent_a(enriched_query, chunks, missing_hints, fact_json, agent_a_fn))
    agent_b_task = asyncio.create_task(_run_agent_b(enriched_query, fact_json, missing_hints))

    agent_b_answer: Optional[TaxAnswer] = None
    try:
        agent_a_answer, agent_b_answer = await asyncio.gather(agent_a_task, agent_b_task)
    except Exception:
        if not agent_a_task.done():
            agent_a_task.cancel()
        if not agent_b_task.done():
            agent_b_task.cancel()
        raise

    return synthesize_answers(agent_a_answer, agent_b_answer, {c.metadata.chunk_id for c in chunks})


async def run_multi_agent_reasoning(
    enriched_query: str,
    chunks: List[RetrievedChunk],
    missing_hints: List[str],
    fact_json: Optional[dict] = None,
    agent_a_fn: Optional[AgentAFn] = None,
) -> MultiAgentReasoningResult:
    """Run Agent A and Agent B through LangGraph, with a parallel fallback."""
    if agent_a_fn is None and agent_a_stream_fn is None:
        from src.retrieval.llm_fn import llm_fn

        agent_a_fn = llm_fn

    try:
        from langgraph.graph import END, START, StateGraph
    except Exception:
        return await _run_parallel_fallback(enriched_query, chunks, missing_hints, fact_json, agent_a_fn)

    async def agent_a_node(state: MultiAgentState) -> dict[str, Any]:
        answer = await _run_agent_a(
            state["enriched_query"],
            state["chunks"],
            state["missing_hints"],
            state.get("fact_json"),
            agent_a_fn,
        )
        return {
            "agent_a_answer": answer,
            "stream_events": [{"event": "agent_reasoning_done", "data": {"agent": "A", **_trace_for_answer(answer)}}],
        }

    async def agent_b_node(state: MultiAgentState) -> dict[str, Any]:
        try:
            answer = await _run_agent_b(state["enriched_query"], state.get("fact_json"), state["missing_hints"])
            error = None
        except Exception as exc:
            answer = TaxAnswer(
                answer="Agent B 독립 검토 실패",
                verdict="사실관계부족",
                confidence=0.0,
                warnings=[f"Agent B 실패: {exc}"],
            )
            error = str(exc)
        return {
            "agent_b_answer": answer,
            "stream_events": [{"event": "agent_reasoning_done", "data": {"agent": "B", **_trace_for_answer(answer, error=error)}}],
        }

    async def synthesize_node(state: MultiAgentState) -> dict[str, Any]:
        result = synthesize_answers(
            state["agent_a_answer"],
            state.get("agent_b_answer"),
            {c.metadata.chunk_id for c in state["chunks"]},
        )
        return {
            "synthesized_answer": result.answer,
            "agent_traces": result.agent_traces,
            "stream_events": [{
                "event": "synthesis_done",
                "data": {
                    "verdict": str(result.answer.verdict),
                    "confidence": result.answer.confidence,
                    "disagreement": result.agent_traces.get("disagreement", False),
                },
            }],
        }

    try:
        graph_builder = StateGraph(MultiAgentState)
        graph_builder.add_node("agent_a", agent_a_node)
        graph_builder.add_node("agent_b", agent_b_node)
        graph_builder.add_node("synthesize", synthesize_node)
        graph_builder.add_edge(START, "agent_a")
        graph_builder.add_edge(START, "agent_b")
        graph_builder.add_edge(["agent_a", "agent_b"], "synthesize")
        graph_builder.add_edge("synthesize", END)
        graph = graph_builder.compile()
    except Exception:
        return await _run_parallel_fallback(enriched_query, chunks, missing_hints, fact_json, agent_a_fn)

    state = await graph.ainvoke({
        "enriched_query": enriched_query,
        "fact_json": fact_json,
        "chunks": chunks,
        "missing_hints": missing_hints,
        "stream_events": [],
    })
    return MultiAgentReasoningResult(
        answer=state["synthesized_answer"],
        agent_traces=state.get("agent_traces", {}),
    )


async def run_multi_agent_reasoning_stream(
    enriched_query: str,
    chunks: List[RetrievedChunk],
    missing_hints: List[str],
    fact_json: Optional[dict] = None,
    agent_a_fn: Optional[AgentAFn] = None,
    agent_a_stream_fn: Optional[AgentAStreamFn] = None,
) -> AsyncGenerator[Union[dict[str, Any], MultiAgentReasoningResult], None]:
    """Stream Agent A/B reasoning deltas while both agents run concurrently."""
    if agent_a_fn is None and agent_a_stream_fn is None:
        from src.retrieval.llm_fn import llm_fn

        agent_a_fn = llm_fn

    yield {
        "event": "agent_reasoning_start",
        "data": {
            "agents": [
                {"agent": "A", "label": "검색 법령 기반"},
                {"agent": "B", "label": "비검색 독립 검토"},
            ]
        },
    }

    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def emit_delta(agent: str, text: str) -> None:
        await queue.put({"event": "agent_reasoning_delta", "data": {"agent": agent, "text": text}})

    async def run_agent_a() -> None:
        try:
            if agent_a_stream_fn is not None:
                answer = await _run_agent_a_stream(
                    enriched_query,
                    chunks,
                    missing_hints,
                    fact_json,
                    agent_a_stream_fn,
                    emit_delta,
                )
            else:
                answer = await _run_agent_a(enriched_query, chunks, missing_hints, fact_json, agent_a_fn)
            await queue.put({"event": "_agent_done", "agent": "A", "answer": answer})
        except Exception as exc:
            await queue.put({"event": "_agent_done", "agent": "A", "error": exc})

    async def run_agent_b() -> None:
        try:
            answer = await _run_agent_b_stream(enriched_query, fact_json, missing_hints, emit_delta)
            await queue.put({"event": "_agent_done", "agent": "B", "answer": answer})
        except Exception as exc:
            answer = TaxAnswer(
                answer="Agent B 독립 검토 실패",
                verdict="사실관계부족",
                confidence=0.0,
                warnings=[f"Agent B 실패: {exc}"],
            )
            await queue.put({"event": "_agent_done", "agent": "B", "answer": answer, "error": exc})

    agent_a_task = asyncio.create_task(run_agent_a())
    agent_b_task = asyncio.create_task(run_agent_b())
    agent_a_answer: Optional[TaxAnswer] = None
    agent_b_answer: Optional[TaxAnswer] = None
    done_agents: set[str] = set()

    while len(done_agents) < 2:
        try:
            item = await asyncio.wait_for(queue.get(), timeout=1.0)
        except asyncio.TimeoutError:
            for agent in ("A", "B"):
                if agent not in done_agents:
                    yield {"event": "agent_reasoning_heartbeat", "data": {"agent": agent}}
            continue

        if item.get("event") != "_agent_done":
            yield item
            continue

        agent = item.get("agent")
        done_agents.add(str(agent))

        if agent == "A" and item.get("error") is not None:
            if not agent_b_task.done():
                agent_b_task.cancel()
            raise item["error"]

        answer = item.get("answer")
        if agent == "A":
            agent_a_answer = answer
        elif agent == "B":
            agent_b_answer = answer

        yield {
            "event": "agent_reasoning_done",
            "data": {
                "agent": agent,
                **_trace_for_answer(answer, error=str(item["error"]) if item.get("error") else None),
            },
        }

    await asyncio.gather(agent_a_task, agent_b_task, return_exceptions=True)

    if agent_a_answer is None:
        raise RuntimeError("Agent A 결과가 비어 있습니다.")

    result = synthesize_answers(agent_a_answer, agent_b_answer, {c.metadata.chunk_id for c in chunks})
    yield {
        "event": "synthesis_done",
        "data": {
            "verdict": str(result.answer.verdict),
            "confidence": result.answer.confidence,
            "disagreement": result.agent_traces.get("disagreement", False),
        },
    }
    yield result
