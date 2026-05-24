"""
업스트림 llm_fn 계약 구현 — RetrievedChunk + missing_hints → TaxAnswer.

프롬프트는 src/agents/prompts.py 에 버전 관리 (RAG_SYSTEM_PROMPT 재사용).
"""
from __future__ import annotations

import json
from typing import AsyncGenerator, List, Optional, Union

from anthropic import AsyncAnthropic

from src.agents.prompts import RAG_SYSTEM_PROMPT
from src.config import ANTHROPIC_API_KEY, CLAUDE_FAST_MODEL, CLAUDE_MODEL
from src.domain.retriever import RetrievedChunk
from src.domain.tax_answer import Citation, TaxAnswer

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


def _choose_default_model(enriched_query: str, missing_hints: List[str]) -> str:
    """Infer routing inputs from the enriched query without leaking retrieval into domain."""
    try:
        from src.domain.query_enrichment import detect_flags_from_text

        danger_flag_count = len(detect_flags_from_text(enriched_query))
    except Exception:
        danger_flag_count = 0
    return choose_model(danger_flag_count, len(missing_hints))


_MAX_CHUNK_CHARS = 800  # 조문 원문 최대 전달 길이 (토큰 절약 — 핵심 내용은 앞부분에 집중)


def _extract_json(text: str) -> str:
    """LLM 응답에서 JSON 블록 추출.

    JSON-first 프롬프트 기준:
    1. <reasoning> 이전 텍스트에서 첫 번째 { ... } 블록 추출
    2. <reasoning> 없으면 전체 텍스트에서 첫 번째 완결 JSON 블록 추출
    3. ```json 코드 펜스 제거
    """
    # JSON-first: <reasoning> 이전에 JSON이 있어야 함
    if "<reasoning>" in text:
        candidate = text.split("<reasoning>", 1)[0].strip()
    elif "</reasoning>" in text:
        # reasoning이 끝난 후 JSON이 있는 구 방식 대응
        candidate = text.split("</reasoning>", 1)[1].strip()
    else:
        candidate = text

    # ```json 또는 ``` 코드 펜스 제거
    if "```json" in candidate:
        candidate = candidate.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in candidate:
        parts = candidate.split("```")
        for part in parts:
            stripped = part.strip()
            if stripped.startswith("{"):
                candidate = stripped
                break

    # 첫 { 이전 텍스트 제거
    first_brace = candidate.find("{")
    if first_brace > 0:
        candidate = candidate[first_brace:]

    # JSON이 } 이후에 reasoning 잔여가 붙어있으면 잘라냄
    # 매칭되는 닫는 중괄호까지만 추출
    if candidate.startswith("{"):
        depth = 0
        end_idx = -1
        in_str = False
        escape = False
        for i, ch in enumerate(candidate):
            if escape:
                escape = False
                continue
            if ch == "\\" and in_str:
                escape = True
                continue
            if ch == '"' and not escape:
                in_str = not in_str
            if not in_str:
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end_idx = i
                        break
        if end_idx != -1:
            candidate = candidate[:end_idx + 1]

    return candidate.strip()


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
        source_label = getattr(m, "source_label", "") or m.law_name
        context_parts.append(
            f"[{i}]{marker} {m.law_name} 제{m.article_number}조"
            f"  ▶ 출처: {source_label}\n"
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

반드시 아래 JSON 형식으로 먼저 답변하고, 그 다음에 <reasoning> 태그로 판단 과정을 서술하십시오.
JSON을 가장 먼저 출력하는 것이 필수입니다.

{{
  "answer": "상세 판단 (법령 근거 포함)",
  "verdict": "비과세" | "고가주택" | "감면" | "중과" | "일반과세" | "단기세율" | "사실관계부족",
  "confidence": 0.0 ~ 1.0,
  "citations": [
    {{"chunk_id": "...", "article": "소득세법 시행령 제154조 제1항", "excerpt": "관련 조문 발췌", "law_version": "시행일"}}
  ],
  "missing_facts": ["추가 확인 필요 항목"],
  "warnings": ["주의사항"]
}}

<reasoning>
판단 과정을 단계별로 서술 (JSON 출력 후 여기에 작성)
</reasoning>

[verdict 선택 기준]
- "비과세": 1세대1주택 완전 비과세 (소득세법 §89, 양도가액 12억 이하)
- "고가주택": 1세대1주택이나 양도가액 12억 초과 (초과분만 과세)
- "감면": 조세특례제한법상 감면 (장기임대§97의3, 신축주택§99의3, 공익사업§77, 자경농지§69 등)
- "중과": 다주택자 조정대상지역 중과 (+20%/+30%, 소득세법 §104①7,8호)
- "일반과세": 기본세율 6~45% (중과·단기·비과세 어디도 해당하지 않는 경우)
- "단기세율": 보유기간 2년 미만 단기양도 (1년 미만 70%, 1~2년 60%), 미등기 전매
- "사실관계부족": 판단에 필수적인 사실관계가 없어 결론을 낼 수 없는 경우"""


async def llm_fn(
    enriched_query: str,
    chunks: List[RetrievedChunk],
    missing_hints: List[str],
    fact_json: Optional[dict] = None,
    model_override: Optional[str] = None,
) -> TaxAnswer:
    """
    업스트림 시그니처 — 검색된 청크와 누락 힌트로 TaxAnswer 생성.
    ANTHROPIC_API_KEY 미설정 시 사실관계부족 으로 안전 반환.
    """
    if not ANTHROPIC_API_KEY:
        return TaxAnswer(
            answer="[ANTHROPIC_API_KEY 미설정]",
            verdict="사실관계부족",
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
    model = model_override or _choose_default_model(enriched_query, missing_hints)

    message = await client.messages.create(
        model=model,
        max_tokens=4096,
        system=_SYSTEM_BLOCKS,
        messages=[{"role": "user", "content": user_prompt}],
        extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"},
    )

    raw_full = message.content[0].text.strip()

    raw_json = _extract_json(raw_full)

    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError:
        return TaxAnswer(
            answer=raw_full,
            verdict="사실관계부족",
            confidence=0.3,
            chunk_ids=[c.metadata.chunk_id for c in chunks],
            warnings=["JSON 파싱 실패 — 원문 반환"],
        )

    # chunk_id → source_label 역조회 테이블
    _label_map = {
        c.metadata.chunk_id: getattr(c.metadata, "source_label", "") or c.metadata.law_name
        for c in chunks
    }

    citations = [
        Citation(
            chunk_id=c.get("chunk_id", ""),
            article=c.get("article", ""),
            excerpt=c.get("excerpt", ""),
            law_version=c.get("law_version", ""),
            source_label=_label_map.get(c.get("chunk_id", ""), ""),
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
        yield TaxAnswer(answer="[API KEY MISSING]", verdict="사실관계부족")
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
    model = model_override or _choose_default_model(enriched_query, missing_hints)

    full_text = ""
    in_reasoning = False

    async with client.messages.stream(
        model=model,
        max_tokens=4096,
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
    raw_json = _extract_json(full_text)

    try:
        data = json.loads(raw_json)
        _label_map = {
            c.metadata.chunk_id: getattr(c.metadata, "source_label", "") or c.metadata.law_name
            for c in chunks
        }
        citations = [
            Citation(
                chunk_id=c.get("chunk_id", ""),
                article=c.get("article", ""),
                excerpt=c.get("excerpt", ""),
                law_version=c.get("law_version", ""),
                source_label=_label_map.get(c.get("chunk_id", ""), ""),
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
            verdict="사실관계부족",
            confidence=0.3,
            chunk_ids=[c.metadata.chunk_id for c in chunks],
            warnings=["JSON 파싱 실패"],
        )
