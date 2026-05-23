"""
BGE Cross-Encoder Reranker — 최종 조문 선택 직전 호출.
"""
from __future__ import annotations

from typing import Optional

from sentence_transformers import CrossEncoder

from src.config import BGE_RERANKER_MODEL

_reranker: Optional[CrossEncoder] = None

_MAX_TEXT_CHARS = 400  # 400자 이후는 tokenizer 부하 대비 rerank 신호 증가 미미
_MAX_LENGTH = 256      # CrossEncoder 내부 max_length — 기본값 512보다 작아 CPU 추론 2배 빠름


def get_reranker() -> CrossEncoder:
    """BGE reranker 싱글톤."""
    global _reranker
    if _reranker is None:
        print(f"BGE Reranker 로드 중: {BGE_RERANKER_MODEL}")
        _reranker = CrossEncoder(BGE_RERANKER_MODEL, max_length=_MAX_LENGTH)
        print("Reranker 준비 완료")
    return _reranker


def rerank(
    query: str,
    candidates: list[dict],
    top_n: int = 5,
) -> list[tuple[float, dict]]:
    """
    BGE Cross-Encoder로 (query, candidate.full_text) 점수 계산 후 상위 N개 반환.
    candidates: Pinecone matches (id, metadata) — metadata.full_text 사용.
    """
    if not candidates:
        return []
    reranker = get_reranker()
    pairs = [(query, c["metadata"].get("full_text", "")[:_MAX_TEXT_CHARS]) for c in candidates]
    scores = reranker.predict(pairs, show_progress_bar=False, batch_size=len(pairs))
    ranked = sorted(
        zip(scores, candidates),
        key=lambda x: x[0],
        reverse=True,
    )[:top_n]
    return list(ranked)
