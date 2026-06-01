"""Chat HTTP routes."""
from __future__ import annotations

import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from src.api.schemas import ChatRequest, ChatResponse
from src.application.chat_service import run_chat, stream_chat

router = APIRouter(prefix="/api/v1", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest) -> ChatResponse:
    result = await run_chat(
        fact_json=req.fact_json,
        question=req.question,
        session_id=req.session_id,
        enable_debate=req.enable_debate,
        query_mode=req.query_mode,
    )
    return ChatResponse(**result)


@router.post("/chat/stream")
async def chat_stream_endpoint(req: ChatRequest) -> StreamingResponse:
    async def _iter():
        async for item in stream_chat(
            fact_json=req.fact_json,
            question=req.question,
            session_id=req.session_id,
            enable_debate=req.enable_debate,
            query_mode=req.query_mode,
        ):
            if isinstance(item, str):
                if item.startswith("PROGRESS:"):
                    payload = {"type": "progress", "data": item[9:]}
                else:
                    payload = {"type": "token", "data": item}
            elif isinstance(item, dict) and "event" in item:
                payload = {"type": "event", "event": item["event"], "data": item.get("data", {})}
            else:
                payload = {"type": "result", "data": item}
            yield json.dumps(payload, ensure_ascii=False) + "\n"

    return StreamingResponse(_iter(), media_type="application/x-ndjson")

