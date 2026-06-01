"""Backward-compatible imports for the new API/application split."""
from __future__ import annotations

from src.api.main import app
from src.api.schemas import ChatRequest, ChatResponse
from src.application.chat_service import run_chat as chat_turn
from src.application.chat_service import stream_chat as chat_turn_stream

__all__ = ["app", "ChatRequest", "ChatResponse", "chat_turn", "chat_turn_stream"]

