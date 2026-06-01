"""HTTP client used by the Streamlit UI."""
from __future__ import annotations

import json
from typing import Any, Iterator

import requests

from src.config import API_BASE_URL


def stream_chat(
    fact_json: dict[str, Any] | None,
    question: str | None,
    enable_debate: bool = False,
    query_mode: str = "report",
) -> Iterator[dict[str, Any]]:
    url = f"{API_BASE_URL.rstrip('/')}/api/v1/chat/stream"
    payload = {
        "fact_json": fact_json,
        "question": question,
        "enable_debate": enable_debate,
        "query_mode": query_mode,
    }
    with requests.post(url, json=payload, stream=True, timeout=300) as response:
        response.raise_for_status()
        for line in response.iter_lines(decode_unicode=True):
            if not line:
                continue
            yield json.loads(line)

