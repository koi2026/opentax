"""FastAPI entrypoint for the tax-rag API server."""
from __future__ import annotations

from fastapi import FastAPI

from src.api.routes.chat import router as chat_router

app = FastAPI(
    title="양도소득세 RAG API",
    description="UI/외부 클라이언트용 HTTP 오케스트레이터. 검색은 MCP 서버를 통해 수행합니다.",
    version="1.0.0",
)

app.include_router(chat_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

