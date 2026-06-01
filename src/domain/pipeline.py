"""
RAG 파이프라인 진입점 — L1~L5 통합

사용법:
    result = await run_rag_pipeline(
        query=RAGQueryInput.from_fact_ledger(...),
        retriever=retriever,
        llm_fn=call_llm,
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Awaitable, Callable, Dict, List, Literal, Optional, Set, Union

from .confirmation import check_confirmation
from .fact_checker import FactCheckResult, check_facts
from .output_validator import validate_output
from .query_enrichment import DANGER_KEYWORD_MAP, build_rag_query
from .query_input import RAGQueryInput
from .retriever import RetrievedChunk, TaxLawRetriever
from .tax_answer import TaxAnswer, TaxVerdict


@dataclass
class PipelineResult:
    answer: TaxAnswer
    fact_check: FactCheckResult
    enriched_query: str
    retrieved_chunks: List[RetrievedChunk] = field(default_factory=list)
    blocked_at_l2: bool = False
    blocked_at_confirmation: bool = False
    debate_record: Optional[dict] = None   # 논쟁이 실행된 경우 결과 요약
    query_mode: str = "report"
    consulting_scenarios: Optional[List[dict]] = None


def _fmt_date(value: Any) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _stream_event(event: str, data: dict) -> dict[str, Any]:
    return {"event": event, "data": data}


def _fact_summary_data(query: RAGQueryInput) -> dict[str, Any]:
    fv = query.fact_vector
    db = query.date_bundle
    return {
        "transfer_date": _fmt_date(db.transfer_date),
        "acquisition_date": _fmt_date(db.acquisition_date),
        "property_type": fv.property_type.value,
        "acquisition_reason": fv.acquisition_reason.value,
        "holding_years": round(float(fv.holding_period_years or 0.0), 2),
        "residence_years": round(float(fv.residence_period_years or 0.0), 2),
        "household_house_count": fv.household_house_count,
        "transfer_price": fv.transfer_price,
        "adjustment_area_at_acquisition": fv.adjustment_area_at_acquisition,
        "adjustment_area_at_transfer": fv.adjustment_area_at_transfer,
    }


def _fact_check_data(fact_check: FactCheckResult) -> dict[str, Any]:
    return {
        "can_proceed": fact_check.can_proceed,
        "missing_facts": fact_check.missing_fact_texts(),
        "critical_missing_count": len(fact_check.critical_missing),
        "danger_flags": fact_check.danger_flags,
    }


def _query_enrichment_data(enriched_query: str, danger_flags: List[str]) -> dict[str, Any]:
    return {
        "danger_flags": danger_flags,
        "keywords": [
            {"flag": flag, "keyword": DANGER_KEYWORD_MAP[flag]}
            for flag in danger_flags
            if flag in DANGER_KEYWORD_MAP
        ],
        "enriched_query_preview": enriched_query[:600],
    }


def _retrieved_chunks_data(chunks: List[RetrievedChunk]) -> List[dict[str, Any]]:
    items: List[dict[str, Any]] = []
    for chunk in chunks:
        meta = chunk.metadata
        article = f"{meta.law_name} 제{meta.article_number}조"
        if getattr(meta, "article_title", ""):
            article += f" ({meta.article_title})"
        items.append({
            "article": article,
            "source_label": getattr(meta, "source_label", "") or meta.law_name,
            "chunk_id": meta.chunk_id,
            "score": round(float(chunk.score), 4),
            "included_as_linked_buchik": chunk.included_as_linked_buchik,
        })
    return items


def _validation_data(
    raw_answer: TaxAnswer,
    validated: TaxAnswer,
    retrieved_ids: Set[str],
) -> dict[str, Any]:
    cited_ids = {c.chunk_id for c in raw_answer.citations if c.chunk_id}
    phantom_ids = sorted(cited_ids - retrieved_ids)
    return {
        "citation_count": len(cited_ids),
        "retrieved_count": len(retrieved_ids),
        "phantom_count": len(phantom_ids),
        "phantom_ids": phantom_ids,
        "confidence_before": raw_answer.confidence,
        "confidence_after": validated.confidence,
        "warnings_added": max(0, len(validated.warnings) - len(raw_answer.warnings)),
    }


def _build_consulting_scenarios(
    query: RAGQueryInput,
    answer: TaxAnswer,
    fact_json: Optional[dict] = None,
) -> List[dict]:
    """
    컨설팅 모드: 양도/증여/부담부증여 시나리오 비교.
    SimulationEngine을 통해 실제 세액을 계산하여 반환한다.
    """
    from src.services.simulation_engine import run_simulation

    fv = query.fact_vector
    fact = fact_json or {}

    market_value = fv.transfer_price or 0
    acquisition_price = fv.acquisition_price or 0

    if market_value == 0 or acquisition_price == 0:
        return [{"error": "시가 또는 취득가액 미입력 — 시뮬레이션 불가"}]

    sim = run_simulation(
        market_value=market_value,
        acquisition_price=acquisition_price,
        holding_years=fv.holding_period_years,
        residence_years=fv.residence_period_years,
        household_house_count=fv.household_house_count,
        verdict=answer.verdict,
        encumbrance=int(fact.get("simulation_encumbrance", 0) or 0),
        gift_recipient=str(fact.get("simulation_gift_recipient", "직계존비속")),
        recipient_is_adult=bool(fact.get("simulation_recipient_is_adult", True)),
        necessary_expenses=int(fact.get("necessary_expenses", 0) or 0),
        heavy_tax_suspended=bool(fact.get("heavy_tax_suspended", False)),
        is_non_resident=fv.overseas_residence_yn,
    )

    return sim.to_dict()["scenarios"] + [
        {
            "optimal_type": sim.optimal_type,
            "optimal_saving": sim.optimal_saving,
            "recommendation_reason": sim.recommendation_reason,
            "expert_review_needed": sim.expert_review_needed,
            "warnings": sim.warnings,
        }
    ]


def _confirmation_blocked_result(unconfirmed_questions: List[str]) -> PipelineResult:
    answer = TaxAnswer(
        answer="다음 항목을 먼저 확인해 주세요:\n" + "\n".join(
            f"- {q}" for q in unconfirmed_questions
        ),
        verdict=TaxVerdict.NEEDS_VERIFICATION,
        confidence=0.0,
        citations=[],
        chunk_ids=[],
        missing_facts=unconfirmed_questions,
        warnings=["확인서 미완료 — 판단을 진행할 수 없습니다."],
        expert_review_signals=[],
    )
    return PipelineResult(
        answer=answer,
        fact_check=FactCheckResult(can_proceed=True),
        enriched_query="",
        blocked_at_l2=False,
        blocked_at_confirmation=True,
    )


def _l2_blocked_result(fact_check: FactCheckResult) -> PipelineResult:
    answer = TaxAnswer(
        answer="판단에 필요한 사실관계가 불충분합니다. 아래 항목을 추가로 확인해 주세요.",
        verdict=TaxVerdict.NEEDS_VERIFICATION,
        confidence=0.0,
        missing_facts=fact_check.missing_fact_texts(),
        warnings=[f"크리티컬 정보 {len(fact_check.critical_missing)}건 누락으로 추론 중단"],
    )
    return PipelineResult(
        answer=answer,
        fact_check=fact_check,
        enriched_query="",
        blocked_at_l2=True,
    )


async def run_rag_pipeline(
    query: RAGQueryInput,
    retriever: TaxLawRetriever,
    llm_fn: Callable[[str, List[RetrievedChunk], List[str]], Awaitable[TaxAnswer]],
    fact_json: Optional[dict] = None,
    enable_debate: bool = False,
    debate_auto_promote: bool = True,
    confirmed: Optional[Dict[str, bool]] = None,
    query_mode: Literal["report", "consulting"] = "report",
) -> PipelineResult:
    """
    L1: schema validation — RAGQueryInput 생성 시 이미 처리됨
    L2: fact completeness check
    L3: query enrichment
    L4: RAG + LLM
    L5: output validation
    """

    # ── L1.5: Confirmation Gate ──────────────────────────────────────────
    confirmation = check_confirmation(confirmed)
    if not confirmation.can_proceed:
        return _confirmation_blocked_result(confirmation.unconfirmed_questions)

    # ── L2: Fact Completeness ────────────────────────────────────────────
    fact_check = check_facts(query)

    if not fact_check.can_proceed:
        return _l2_blocked_result(fact_check)

    # ── L3: Query Enrichment ─────────────────────────────────────────────
    enriched_query = build_rag_query(query, fact_check.danger_flags)

    # ── L4: RAG + LLM ────────────────────────────────────────────────────
    chunks = retriever.retrieve_with_buchik(query, query_text=enriched_query)
    retrieved_ids: Set[str] = {c.metadata.chunk_id for c in chunks}

    # missing_facts를 LLM 프롬프트에 전달 → "이 정보가 없어서 불확실합니다" 안내
    llm_missing_hints = fact_check.missing_fact_texts()

    raw_answer = await llm_fn(enriched_query, chunks, llm_missing_hints)

    # chunk_ids 동기화 — LLM이 누락시켰을 수 있으므로 검색 결과로 보완
    if not raw_answer.chunk_ids:
        raw_answer = raw_answer.with_update(chunk_ids=list(retrieved_ids))

    # missing_facts 병합
    combined_missing = list(set(raw_answer.missing_facts + llm_missing_hints))
    raw_answer = raw_answer.with_update(missing_facts=combined_missing)

    # ── L5: Output Validation ────────────────────────────────────────────
    validated = validate_output(raw_answer, retrieved_ids, danger_flags=fact_check.danger_flags, query=query)

    result = PipelineResult(
        answer=validated,
        fact_check=fact_check,
        enriched_query=enriched_query,
        retrieved_chunks=chunks,
        query_mode=query_mode,
    )

    # ── Consulting Mode: 시나리오 비교 노드 ──────────────────────────────
    if query_mode == "consulting":
        result.consulting_scenarios = _build_consulting_scenarios(query, validated, fact_json)

    # ── 선택적 Red-Blue 논쟁 ─────────────────────────────────────────────
    if enable_debate and fact_json:
        try:
            from src.eval.debate import run_red_blue_debate, should_debate
            if should_debate(result):
                debate = await run_red_blue_debate(
                    fact_json=fact_json,
                    pipeline_result=result,
                    auto_promote=debate_auto_promote,
                )
                result.debate_record = {
                    "debate_id": debate.debate_id,
                    "outcome": debate.outcome,
                    "challenge_type": debate.red_challenge.get("challenge_type"),
                    "challenge_text": debate.red_challenge.get("challenge_text", ""),
                    "defense_text": debate.blue_defense.get("defense_text", ""),
                    "new_citations": debate.blue_defense.get("new_citations", []),
                    "revised_verdict": debate.blue_defense.get("revised_verdict"),
                    "promoted_to_golden": debate.promoted_to_golden,
                }
                if debate.outcome == "red_won":
                    revised = debate.blue_defense.get("revised_verdict", validated.verdict)
                    result.answer = validated.with_update(verdict=revised)
        except Exception as e:
            # 논쟁 실패가 주 파이프라인을 막으면 안 됨
            result.debate_record = {"error": str(e)}

    return result


async def run_rag_pipeline_stream(
    query: RAGQueryInput,
    retriever: TaxLawRetriever,
    llm_fn_stream_fn: Callable,
    fact_json: Optional[dict] = None,
    enable_debate: bool = False,
    debate_auto_promote: bool = True,
    confirmed: Optional[Dict[str, bool]] = None,
    query_mode: Literal["report", "consulting"] = "report",
) -> AsyncGenerator[Union[str, dict[str, Any], PipelineResult], None]:
    """파이프라인 스트리밍 버전.

    Yields:
        str: "PROGRESS:메시지" (단계 진행 상태) 또는 Claude reasoning 텍스트 조각
        dict: {"event": "...", "data": ...} 구조화 중간 이벤트
        PipelineResult: 최종 결과 (마지막에 한 번만 yield)
    """
    yield _stream_event("fact_summary", _fact_summary_data(query))

    # ── L1.5 Confirmation ──────────────────────────────────────────────────
    confirmation = check_confirmation(confirmed)
    if not confirmation.can_proceed:
        yield _confirmation_blocked_result(confirmation.unconfirmed_questions)
        return

    # ── L2 Fact Check ──────────────────────────────────────────────────────
    fact_check = check_facts(query)
    yield _stream_event("fact_check", _fact_check_data(fact_check))
    if not fact_check.can_proceed:
        yield _l2_blocked_result(fact_check)
        return

    # ── L3 Query Enrichment ─────────────────────────────────────────────────
    enriched_query = build_rag_query(query, fact_check.danger_flags)
    llm_missing_hints = fact_check.missing_fact_texts()
    yield _stream_event(
        "query_enrichment",
        _query_enrichment_data(enriched_query, fact_check.danger_flags),
    )

    # ── L4a Retrieval ───────────────────────────────────────────────────────
    yield "PROGRESS:관련 법령 조문 검색 중..."
    chunks = retriever.retrieve_with_buchik(query, query_text=enriched_query)
    retrieved_ids: Set[str] = {c.metadata.chunk_id for c in chunks}
    yield _stream_event("retrieved_chunks", {"chunks": _retrieved_chunks_data(chunks)})

    yield f"PROGRESS:AI 법령 해석 중 ({len(chunks)}개 조문)..."

    # ── L4b LLM Streaming ───────────────────────────────────────────────────
    raw_answer: Optional[TaxAnswer] = None
    async for item in llm_fn_stream_fn(enriched_query, chunks, llm_missing_hints, fact_json):
        if isinstance(item, str):
            yield item  # reasoning 텍스트 조각
        elif hasattr(item, "verdict"):
            raw_answer = item  # TaxAnswer

    if raw_answer is None:
        raw_answer = TaxAnswer(
            answer="AI 추론 중 오류가 발생했습니다.",
            verdict=TaxVerdict.NEEDS_VERIFICATION,
            confidence=0.0,
            chunk_ids=list(retrieved_ids),
            warnings=["스트리밍 오류"],
        )

    # chunk_ids / missing_facts 동기화
    if not raw_answer.chunk_ids:
        raw_answer = raw_answer.with_update(chunk_ids=list(retrieved_ids))
    combined_missing = list(set(raw_answer.missing_facts + llm_missing_hints))
    raw_answer = raw_answer.with_update(missing_facts=combined_missing)

    # ── L5 Output Validation ────────────────────────────────────────────────
    validated = validate_output(raw_answer, retrieved_ids, danger_flags=fact_check.danger_flags, query=query)
    yield _stream_event("validation", _validation_data(raw_answer, validated, retrieved_ids))

    result = PipelineResult(
        answer=validated,
        fact_check=fact_check,
        enriched_query=enriched_query,
        retrieved_chunks=chunks,
        query_mode=query_mode,
    )

    # ── Consulting Scenarios ─────────────────────────────────────────────────
    if query_mode == "consulting":
        result.consulting_scenarios = _build_consulting_scenarios(query, validated, fact_json)

    # ── Red-Blue 논쟁 ────────────────────────────────────────────────────────
    if enable_debate and fact_json:
        try:
            from src.eval.debate import run_red_blue_debate, should_debate
            if should_debate(result):
                yield "PROGRESS:Red Team 검증 중..."
                debate = await run_red_blue_debate(
                    fact_json=fact_json,
                    pipeline_result=result,
                    auto_promote=debate_auto_promote,
                )
                result.debate_record = {
                    "debate_id": debate.debate_id,
                    "outcome": debate.outcome,
                    "challenge_type": debate.red_challenge.get("challenge_type"),
                    "challenge_text": debate.red_challenge.get("challenge_text", ""),
                    "defense_text": debate.blue_defense.get("defense_text", ""),
                    "new_citations": debate.blue_defense.get("new_citations", []),
                    "revised_verdict": debate.blue_defense.get("revised_verdict"),
                    "promoted_to_golden": debate.promoted_to_golden,
                }
                if debate.outcome == "red_won":
                    revised = debate.blue_defense.get("revised_verdict", validated.verdict)
                    result.answer = validated.with_update(verdict=revised)
        except Exception as e:
            result.debate_record = {"error": str(e)}

    yield result
