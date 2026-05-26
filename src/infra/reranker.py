"""
BGE Cross-Encoder Reranker — 최종 조문 선택 직전 호출.
"""
from __future__ import annotations

from typing import Optional

from sentence_transformers import CrossEncoder

from src.config import BGE_RERANKER_MODEL

_reranker: Optional[CrossEncoder] = None

_MAX_TEXT_CHARS = 900  # 한국 법령 조문 단서조항·부칙이 400자 이후에 위치하는 경우 있음
_MAX_LENGTH = 512      # fine-tuning(finetune_reranker.py default=512)과 동일하게 유지


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
    scores = reranker.predict(pairs, show_progress_bar=False, batch_size=min(len(pairs), 16))
    ranked = sorted(
        zip(scores, candidates),
        key=lambda x: x[0],
        reverse=True,
    )[:top_n]
    return list(ranked)
