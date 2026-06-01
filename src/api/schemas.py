"""HTTP API request and response schemas."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    question: Optional[str] = None
    fact_json: Optional[dict[str, Any]] = None
    enable_debate: bool = False
    query_mode: str = "report"


class ChatResponse(BaseModel):
    session_id: str
    verdict: str
    answer: str
    confidence: float
    citations: list[str]
    chunk_ids: list[str]
    missing_facts: list[str]
    warnings: list[str]
    blocked: bool
    mode: str
    consulting_scenarios: Optional[list[dict[str, Any]]] = None
    debate_record: Optional[dict[str, Any]] = None
    agent_traces: Optional[dict[str, Any]] = None
