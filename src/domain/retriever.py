"""
2단계 법령 검색 전략 인터페이스.

Stage 1: SymbolicFilter — chunk applicability/날짜/scope 기반 후보 좁힘.
Stage 2: VectorRanker — 임베딩 유사도 + reranker로 최종 선택.
이 모듈은 TaxLawRetriever ABC 만 정의하고, 구현체는 src/core/retriever_impl.py.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Protocol

from .chunk_metadata import LawChunkMetadata
from .query_input import DateBundle, RAGQueryInput


@dataclass
class RetrievedChunk:
    """검색 결과 1건 — 메타데이터 + 본문 + 점수."""
    metadata: LawChunkMetadata
    content: str
    score: float
    included_as_linked_buchik: bool = False


class SymbolicFilter(Protocol):
    """Stage 1 — 후보 좁히기."""
    def filter(
        self,
        query: RAGQueryInput,
        all_chunks: List[LawChunkMetadata],
    ) -> List[LawChunkMetadata]: ...


class VectorRanker(Protocol):
    """Stage 2 — 벡터 검색 + reranker."""
    def rank(
        self,
        query: RAGQueryInput,
        candidates: List[LawChunkMetadata],
    ) -> List[RetrievedChunk]: ...


class TaxLawRetriever(ABC):
    """업스트림 계약 — 양도소득세 법령 검색기."""

    @abstractmethod
    def retrieve(self, query: RAGQueryInput, query_text: Optional[str] = None) -> List[RetrievedChunk]:
        """기본 검색 — 본칙 청크 우선 반환. query_text 제공 시 fact_vector.to_text() 대신 사용."""

    def retrieve_with_buchik(self, query: RAGQueryInput, query_text: Optional[str] = None) -> List[RetrievedChunk]:
        """
        본칙 검색 후 query.include_buchik=True 면 연결된 부칙 청크를 보강해서 반환.
        부칙(경과조치/적용례)은 적용 법령 결정에 필수.
        """
        results = self.retrieve(query, query_text=query_text)
        if not query.include_buchik:
            return results

        seen_ids = {r.metadata.chunk_id for r in results}
        extra: List[RetrievedChunk] = []
        for chunk in results:
            for buchik_id in chunk.metadata.linked_buchik_ids:
                if buchik_id in seen_ids:
                    continue
                buchik_chunk = self._get_chunk_by_id(buchik_id)
                if buchik_chunk is None:
                    continue
                extra.append(
                    RetrievedChunk(
                        metadata=buchik_chunk,
                        content=self._get_content(buchik_id),
                        score=chunk.score,
                        included_as_linked_buchik=True,
                    )
                )
                seen_ids.add(buchik_id)
        return results + extra

    @abstractmethod
    def _get_chunk_by_id(self, chunk_id: str) -> Optional[LawChunkMetadata]:
        """단건 메타데이터 조회 (부칙 보강용)."""

    @abstractmethod
    def _get_content(self, chunk_id: str) -> str:
        """단건 본문 조회 (부칙 보강용)."""
