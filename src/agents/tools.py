"""
CrewAI Agent 도구 정의
"""
from crewai.tools import BaseTool
from pydantic import Field

from src.retrieval.tax_law_search import retrieve_tax_law


class RAGSearchTool(BaseTool):
    name: str = "search_tax_law"
    description: str = (
        "한국 양도소득세 관련 법령 조문을 벡터 검색 + BGE reranking으로 검색합니다. "
        "query: 검색할 법령 키워드나 질문, top_k: 검색 후보 수(기본 20), "
        "rerank_top_n: reranking 후 반환 수(기본 5)"
    )
    top_k: int = Field(default=20)
    rerank_top_n: int = Field(default=5)

    def _run(self, query: str) -> str:
        chunks = retrieve_tax_law(query, top_k=self.top_k, rerank_top_n=self.rerank_top_n)
        if not chunks:
            return "관련 법령 조문을 찾을 수 없습니다."

        lines = []
        for i, chunk in enumerate(chunks, 1):
            lines.append(
                f"[{i}] {chunk.law_name} 제{chunk.article_number}조 {chunk.article_title}\n"
                f"    chunk_id: {chunk.id} | rerank_score: {chunk.score:.4f}\n"
                f"    {chunk.full_text[:300]}"
            )
        return "\n\n".join(lines)
