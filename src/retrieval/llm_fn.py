"""
업스트림 llm_fn 계약 구현 — RetrievedChunk + missing_hints → TaxAnswer.

anthropic SDK 는 sync 이므로 asyncio executor 로 래핑한다.
프롬프트는 src/agents/prompts.py 에 버전 관리 (RAG_SYSTEM_PROMPT 재사용).
"""
from __future__ import annotations

import asyncio
import json
import os
from typing import AsyncGenerator, List, Optional, Union

import anthropic
from anthropic import AsyncAnthropic
from dotenv import load_dotenv

from src.agents.prompts import RAG_SYSTEM_PROMPT
from src.domain.retriever import RetrievedChunk
from src.domain.tax_answer import Citation, TaxAnswer

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
CLAUDE_FAST_MODEL = os.getenv("CLAUDE_FAST_MODEL", "claude-haiku-4-5-20251001")

# 프롬프트 캐싱 — system prompt를 ephemeral 캐시로 고정해 TTFT 단축
# few_shot_block은 요청마다 달라지므로 캐시 블록에 포함하지 않음
_SYSTEM_BLOCKS = [
    {
        "type": "text",
        "text": RAG_SYSTEM_PROMPT,
        "cache_control": {"type": "ephemeral"},
    }
]


def choose_model(danger_flag_count: int, missing_count: int) -> str:
    """danger_flags >= 2 이거나 missing_facts 있으면 Sonnet, 그 외 Haiku.

    Haiku는 Sonnet 대비 3~5배 빠르고 단순 비과세 판단에 충분한 정확도를 보임.
    """
    if danger_flag_count >= 2 or missing_count > 0:
        return CLAUDE_MODEL
    return CLAUDE_FAST_MODEL


_MAX_CHUNK_CHARS = 800  # 조문 원문 최대 전달 길이 (토큰 절약 — 핵심 내용은 앞부분에 집중)


def _build_user_prompt(
    enriched_query: str,
    chunks: List[RetrievedChunk],
    missing_hints: List[str],
    few_shot_block: str = "",
) -> str:
    """검색 결과 + 누락 힌트 → Claude user prompt."""
    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        m = chunk.metadata
        marker = " [부칙]" if chunk.included_as_linked_buchik else ""
        context_parts.append(
            f"[{i}]{marker} {m.law_name} 제{m.article_number}조\n"
            f"(chunk_id: {m.chunk_id}, score: {chunk.score:.4f})\n"
            f"{chunk.content[:_MAX_CHUNK_CHARS]}"
        )
    context = "\n\n".join(context_parts)

    hints_text = ""
    if missing_hints:
        hints_text = "\n\n[추가 확인 필요 항목 — 이 정보가 없어 판단에 불확실성이 있습니다]\n"
        hints_text += "\n".join(f"- {h}" for h in missing_hints)

    few_shot_section = f"\n{few_shot_block}\n" if few_shot_block else ""

    return f"""다음 법령 조문을 근거로 판단하십시오.

[검색된 법령 조문]
{context}
{hints_text}{few_shot_section}
[질문]
{enriched_query}

먼저 <reasoning> 태그 내에 판단 과정을 단계별로 서술하십시오. 
그 후, 반드시 아래 JSON 형식으로 답변하십시오:
{{
  "answer": "상세 판단 (법령 근거 포함)",
  "verdict": "비과세" | "과세" | "조건부비과세" | "needs_verification",
  "confidence": 0.0 ~ 1.0,
  "citations": [
    {{"chunk_id": "...", "article": "소득세법 시행령 제154조 제1항", "excerpt": "관련 조문 발췌", "law_version": "시행일"}}
  ],
  "missing_facts": ["추가 확인 필요 항목"],
  "warnings": ["주의사항"]
}}"""


async def llm_fn(
    enriched_query: str,
    chunks: List[RetrievedChunk],
    missing_hints: List[str],
    fact_json: Optional[dict] = None,
    model_override: Optional[str] = None,
) -> TaxAnswer:
    """
    업스트림 시그니처 — 검색된 청크와 누락 힌트로 TaxAnswer 생성.
    ANTHROPIC_API_KEY 미설정 시 needs_verification 으로 안전 반환.
    """
    if not ANTHROPIC_API_KEY:
        return TaxAnswer(
            answer="[ANTHROPIC_API_KEY 미설정]",
            verdict="needs_verification",
            confidence=0.0,
            chunk_ids=[c.metadata.chunk_id for c in chunks],
            warnings=["LLM 미설정"],
        )

    # 골든셋 few-shot 주입 (5건 이상 쌓인 경우에만)
    few_shot_block = ""
    if fact_json:
        try:
            from src.eval.golden_injector import build_few_shot_block
            few_shot_block = build_few_shot_block(fact_json)
        except Exception:
            pass

    client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    user_prompt = _build_user_prompt(enriched_query, chunks, missing_hints, few_shot_block)
    model = model_override or CLAUDE_MODEL

    message = await client.messages.create(
        model=model,
        max_tokens=1200,
        system=_SYSTEM_BLOCKS,
        messages=[{"role": "user", "content": user_prompt}],
        extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"},
    )

    raw_full = message.content[0].text.strip()
    
    # <reasoning> 제거 및 JSON 추출
    raw_json = raw_full
    if "<reasoning>" in raw_full:
        parts = raw_full.split("</reasoning>")
        if len(parts) > 1:
            raw_json = parts[1].strip()

    if raw_json.startswith("```"):
        raw_json = raw_json.split("```")[1]
        if raw_json.startswith("json"):
            raw_json = raw_json[4:]

    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError:
        return TaxAnswer(
            answer=raw_full,
            verdict="needs_verification",
            confidence=0.3,
            chunk_ids=[c.metadata.chunk_id for c in chunks],
            warnings=["JSON 파싱 실패 — 원문 반환"],
        )

    citations = [
        Citation(
            chunk_id=c.get("chunk_id", ""),
            article=c.get("article", ""),
            excerpt=c.get("excerpt", ""),
            law_version=c.get("law_version", ""),
        )
        for c in data.get("citations", [])
    ]

    return TaxAnswer(
        answer=data.get("answer", ""),
        verdict=data.get("verdict", "needs_verification"),
        confidence=float(data.get("confidence", 0.0)),
        citations=citations,
        chunk_ids=[c.metadata.chunk_id for c in chunks],
        missing_facts=data.get("missing_facts", []),
        warnings=data.get("warnings", []),
    )


async def llm_fn_stream(
    enriched_query: str,
    chunks: List[RetrievedChunk],
    missing_hints: List[str],
    fact_json: Optional[dict] = None,
    model_override: Optional[str] = None,
) -> AsyncGenerator[Union[str, TaxAnswer], None]:
    """
    Claude 스트리밍 버전. 
    1. <reasoning> 내용을 텍스트 조각으로 먼저 yield.
    2. 최종 결과물로 TaxAnswer 객체를 yield.
    """
    if not ANTHROPIC_API_KEY:
        yield TaxAnswer(answer="[API KEY MISSING]", verdict="needs_verification")
        return

    few_shot_block = ""
    if fact_json:
        try:
            from src.eval.golden_injector import build_few_shot_block
            few_shot_block = build_few_shot_block(fact_json)
        except Exception:
            pass

    client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    user_prompt = _build_user_prompt(enriched_query, chunks, missing_hints, few_shot_block)
    model = model_override or CLAUDE_MODEL

    full_text = ""
    in_reasoning = False

    async with client.messages.stream(
        model=model,
        max_tokens=1500,
        system=_SYSTEM_BLOCKS,
        messages=[{"role": "user", "content": user_prompt}],
        extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"},
    ) as stream:
        async for event in stream:
            if event.type == "content_block_delta":
                text = event.delta.text
                full_text += text
                
                # <reasoning> 내부 텍스트만 실시간으로 yield (UI 표시용)
                if "<reasoning>" in full_text and not in_reasoning:
                    in_reasoning = True
                    continue
                
                if in_reasoning:
                    if "</reasoning>" in text:
                        # 태그가 포함된 조각이면 이전 부분까지만 보냄
                        reasoning_part = text.split("</reasoning>")[0]
                        yield reasoning_part
                        in_reasoning = False
                    else:
                        yield text

    # 최종 파싱
    raw_json = full_text
    if "<reasoning>" in full_text:
        raw_json = full_text.split("</reasoning>")[-1].strip()
    
    if "```json" in raw_json:
        raw_json = raw_json.split("```json")[1].split("```")[0].strip()
    elif "```" in raw_json:
        raw_json = raw_json.split("```")[1].strip()

    try:
        data = json.loads(raw_json)
        citations = [
            Citation(
                chunk_id=c.get("chunk_id", ""),
                article=c.get("article", ""),
                excerpt=c.get("excerpt", ""),
                law_version=c.get("law_version", ""),
            )
            for c in data.get("citations", [])
        ]
        yield TaxAnswer(
            answer=data.get("answer", ""),
            verdict=data.get("verdict", "needs_verification"),
            confidence=float(data.get("confidence", 0.0)),
            citations=citations,
            chunk_ids=[c.metadata.chunk_id for c in chunks],
            missing_facts=data.get("missing_facts", []),
            warnings=data.get("warnings", []),
        )
    except json.JSONDecodeError:
        yield TaxAnswer(
            answer=full_text,
            verdict="needs_verification",
            confidence=0.3,
            chunk_ids=[c.metadata.chunk_id for c in chunks],
            warnings=["JSON 파싱 실패"],
        )

