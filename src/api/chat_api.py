"""
채팅 모드 API — FastAPI 엔드포인트 + 직접 함수 호출 양쪽 지원.

Streamlit UI는 이 모듈의 chat_turn()을 직접 임포트해서 사용한다.
외부 클라이언트는 uvicorn으로 실행 후 POST /api/v1/chat 으로 호출한다.

실행:
    uvicorn src.api.chat_api:app --host 0.0.0.0 --port 8001 --reload
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any, Optional

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(
    title="양도소득세 RAG 채팅 API",
    description="JSON 사실관계 → L1-L5 파이프라인 → 세율 판단",
    version="1.0.0",
)


# ── 요청/응답 스키마 ─────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    """
    채팅 1턴 요청.

    fact_json이 있으면 파이프라인으로 라우팅.
    fact_json이 없으면 자연어 question만으로 레거시 RAG 호출.
    """
    session_id: Optional[str] = None    # 없으면 자동 생성
    question: Optional[str] = None      # 자연어 질문 (fact_json 없을 때 사용)
    fact_json: Optional[dict] = None    # 구조화 사실관계
    enable_debate: bool = False         # Red-Blue 논쟁 실행 여부

    class Config:
        json_schema_extra = {
            "example": {
                "fact_json": {
                    "transfer_date": "20240601",
                    "acquisition_date": "20200301",
                    "property_type": "아파트",
                    "acquisition_reason": "매매",
                    "household_house_count": 1,
                    "transfer_price": 1100000000,
                    "residence_years": 2.5,
                    "is_adjustment_area_at_transfer": True,
                }
            }
        }


class ChatResponse(BaseModel):
    session_id: str
    verdict: str                    # 비과세 | 감면 | 중과 | 일반과세 | 단기세율 | 고가주택 | 사실관계부족
    answer: str
    confidence: float
    citations: list[str]
    chunk_ids: list[str]
    missing_facts: list[str]
    warnings: list[str]
    blocked: bool                   # L2에서 차단됐으면 True (missing_facts로 재요청)
    mode: str                       # "pipeline" | "legacy"


# ── 핵심 로직 ─────────────────────────────────────────────────────────────────

from typing import Any, AsyncGenerator, Optional, Union


async def chat_turn_stream(
    fact_json: Optional[dict] = None,
    question: Optional[str] = None,
    session_id: Optional[str] = None,
    enable_debate: bool = False,
    query_mode: str = "report",
) -> AsyncGenerator[Union[str, dict[str, Any]], None]:
    """
    채팅 1턴 스트리밍 처리 함수.
    진행 상태(str), Claude 추론 과정(str), 최종 결과(dict)를 순차적으로 yield 한다.
    """
    sid = session_id or str(uuid.uuid4())[:8]

    if fact_json:
        from src.api.fact_input import FactInput, fact_input_to_rag_query
        from src.domain.pipeline import run_rag_pipeline_stream, PipelineResult
        from src.retrieval.retriever_impl import PineconeTaxLawRetriever
        from src.retrieval.llm_fn import llm_fn_stream

        fact_for_schema = {k: v for k, v in fact_json.items() if not k.startswith("simulation_") and k != "necessary_expenses"}
        query = fact_input_to_rag_query(FactInput(**fact_for_schema))
        retriever = PineconeTaxLawRetriever()

        async for item in run_rag_pipeline_stream(
            query, retriever, llm_fn_stream,
            fact_json=fact_json,
            enable_debate=enable_debate,
            query_mode=query_mode,
        ):
            if isinstance(item, str):
                yield item
            elif isinstance(item, PipelineResult):
                ans = item.answer
                citations_str = [
                    f"[{c.source_label}] {c.article}" if getattr(c, "source_label", "") else c.article
                    for c in ans.citations
                ]
                yield {
                    "session_id": sid,
                    "verdict": ans.verdict,
                    "answer": ans.answer,
                    "confidence": ans.confidence,
                    "citations": citations_str,
                    "chunk_ids": ans.chunk_ids,
                    "missing_facts": ans.missing_facts,
                    "warnings": ans.warnings,
                    "blocked": item.blocked_at_l2,
                    "mode": "pipeline",
                    "consulting_scenarios": item.consulting_scenarios,
                    "debate_record": item.debate_record,
                }
    else:
        # 자연어 질문은 아직 스트리밍 미지원 (레거시)
        res = await chat_turn(question=question, session_id=sid)
        yield res


async def chat_turn(
    fact_json: Optional[dict] = None,
    question: Optional[str] = None,
    session_id: Optional[str] = None,
    enable_debate: bool = False,
    query_mode: str = "report",
) -> dict[str, Any]:
    """
    채팅 1턴 처리 함수. Streamlit UI에서 직접 호출 가능.

    fact_json 있음 → L1-L5 파이프라인 (verdict 포함)
    fact_json 없음 → 레거시 answer_with_citations (자연어 질문)
    query_mode: "report" | "consulting" — consulting이면 consulting_scenarios 포함 반환
    """
    sid = session_id or str(uuid.uuid4())[:8]

    if fact_json:
        # ── L1-L5 파이프라인 경로 ──────────────────────────────────────────
        from src.api.fact_input import FactInput, fact_input_to_rag_query
        from src.domain.pipeline import run_rag_pipeline
        from src.retrieval.retriever_impl import PineconeTaxLawRetriever
        from src.retrieval.llm_fn import llm_fn

        # simulation_* 키는 FactInput 스키마 외부 → 파싱 전 분리
        fact_for_schema = {k: v for k, v in fact_json.items() if not k.startswith("simulation_") and k != "necessary_expenses"}
        try:
            query = fact_input_to_rag_query(FactInput(**fact_for_schema))
        except Exception as e:
            return {
                "session_id": sid,
                "verdict": "사실관계부족",
                "answer": f"입력 형식 오류 — 필수 항목 누락: {e}",
                "confidence": 0.0,
                "citations": [],
                "chunk_ids": [],
                "missing_facts": [f"입력 형식 오류: {e}"],
                "warnings": [],
                "blocked": True,
                "mode": "pipeline",
                "consulting_scenarios": [],
            }
        retriever = PineconeTaxLawRetriever()
        result = await run_rag_pipeline(
            query, retriever, llm_fn,
            fact_json=fact_json,
            enable_debate=enable_debate,
            query_mode=query_mode,
        )

        ans = result.answer
        citations_str = [
            c.article if hasattr(c, "article") else str(c)
            for c in ans.citations
        ]
        return {
            "session_id": sid,
            "verdict": ans.verdict,
            "answer": ans.answer,
            "confidence": ans.confidence,
            "citations": citations_str,
            "chunk_ids": ans.chunk_ids,
            "missing_facts": ans.missing_facts,
            "warnings": ans.warnings,
            "blocked": result.blocked_at_l2,
            "mode": "pipeline",
            "consulting_scenarios": result.consulting_scenarios,
        }

    elif question:
        # ── 레거시 경로 (자연어 질문) ──────────────────────────────────────
        from src.rag import answer_with_citations

        loop = asyncio.get_event_loop()
        ans = await loop.run_in_executor(
            None, lambda: answer_with_citations(question)
        )
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
        }

    else:
        return {
            "session_id": sid,
            "verdict": "사실관계부족",
            "answer": "fact_json 또는 question 중 하나를 입력해 주세요.",
            "confidence": 0.0,
            "citations": [],
            "chunk_ids": [],
            "missing_facts": [],
            "warnings": ["입력 없음"],
            "blocked": True,
            "mode": "none",
        }


# ── FastAPI 엔드포인트 ────────────────────────────────────────────────────────

@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest) -> ChatResponse:
    """
    채팅 1턴 처리.

    - fact_json 있음: L1-L5 파이프라인으로 비과세/감면/중과/일반과세/단기세율 판단
    - fact_json 없음: 자연어 질문으로 레거시 RAG 검색

    blocked=true 이면 missing_facts 항목을 채워 재요청하세요.
    """
    result = await chat_turn(
        fact_json=req.fact_json,
        question=req.question,
        session_id=req.session_id,
    )
    return ChatResponse(**result)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
