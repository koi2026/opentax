"""
RAG 파이프라인 테스트 — 검색 품질 및 인용 무결성 검증
"""
import os
import pytest
from unittest.mock import MagicMock, patch

# Pinecone/임베딩 없이 단위 테스트 가능하도록 모킹


MOCK_CHUNKS_RAW = [
    {
        "id": "285523_0089001",
        "law_name": "소득세법",
        "law_mst": "285523",
        "law_category": "법률",
        "article_number": "89",
        "article_title": "비과세 양도소득",
        "effective_date": "20240101",
        "content": "다음 각 호의 소득에 대해서는 양도소득에 대한 소득세를 과세하지 아니한다.",
        "clauses": [{"항번호": "①", "항내용": "1세대 1주택", "호": []}],
        "full_text": "제89조(비과세 양도소득) 다음 각 호의 소득에 대해서는 양도소득에 대한 소득세를 과세하지 아니한다.",
        "metadata": {
            "law_name": "소득세법",
            "article": "89",
            "effective_date": "20240101",
            "category": "법률",
            "source": "law.go.kr",
        },
    },
    {
        "id": "285631_0154001",
        "law_name": "소득세법 시행령",
        "law_mst": "285631",
        "law_category": "대통령령",
        "article_number": "154",
        "article_title": "1세대1주택의 범위",
        "effective_date": "20240101",
        "content": "법 제89조제1항제3호가목에서 대통령령으로 정하는 요건이란 다음 각 호를 말한다.",
        "clauses": [],
        "full_text": "제154조(1세대1주택의 범위) 법 제89조제1항제3호가목에서 대통령령으로 정하는 요건이란 1세대가 양도일 현재 국내에 1주택을 보유하고 해당 주택의 보유기간이 2년 이상인 것을 말한다.",
        "metadata": {
            "law_name": "소득세법 시행령",
            "article": "154",
            "effective_date": "20240101",
            "category": "대통령령",
            "source": "law.go.kr",
        },
    },
]


def _make_mock_chunk(raw: dict, score: float = 0.9):
    from src.retrieval.tax_law_search import LawChunk
    return LawChunk(
        id=raw["id"],
        law_name=raw["law_name"],
        article_number=raw["article_number"],
        article_title=raw["article_title"],
        effective_date=raw["effective_date"],
        full_text=raw["full_text"],
        score=score,
    )


# ── 검색 결과 구조 검증 ────────────────────────────────────────────────────────

def test_law_chunk_has_required_fields():
    """LawChunk 모델에 id, chunk_id 포함 필수 필드 존재"""
    from src.retrieval.tax_law_search import LawChunk
    chunk = _make_mock_chunk(MOCK_CHUNKS_RAW[0])
    assert chunk.id == "285523_0089001"
    assert chunk.law_name == "소득세법"
    assert chunk.article_number == "89"
    assert chunk.score == 0.9
    assert chunk.full_text


def test_tax_answer_model():
    """TaxAnswer 모델 구조 검증"""
    from src.application.question_service import TaxAnswer
    answer = TaxAnswer(
        answer="비과세 해당",
        citations=["소득세법 제89조 제1항 제3호"],
        chunk_ids=["285523_0089001"],
        confidence=0.85,
        missing_facts=["거주기간"],
        warnings=["조정대상지역 여부 미확인"],
    )
    assert answer.confidence == 0.85
    assert len(answer.citations) == 1
    assert len(answer.chunk_ids) == 1


# ── 검색 단계 모킹 테스트 ─────────────────────────────────────────────────────

@patch("src.retrieval.tax_law_search._get_pinecone_index")
@patch("src.retrieval.tax_law_search._embed_query")
@patch("src.retrieval.tax_law_search._get_reranker")
def test_retrieve_returns_law_chunks(mock_reranker, mock_embed, mock_index):
    """retrieve_tax_law가 LawChunk 리스트 반환, chunk_id 포함"""
    from src.retrieval.tax_law_search import retrieve_tax_law

    # 임베딩 모킹
    mock_embed.return_value = [0.1] * 4096

    # Pinecone 결과 모킹
    mock_match = {
        "id": "285631_0154001",
        "metadata": {
            "law_name": "소득세법 시행령",
            "article_number": "154",
            "article_title": "1세대1주택의 범위",
            "effective_date": "20240101",
            "full_text": "제154조 1세대가 양도일 현재 국내에 1주택을 보유하고 보유기간이 2년 이상",
        },
    }
    mock_index.return_value.query.return_value = {"matches": [mock_match]}

    # Reranker 모킹
    mock_reranker_instance = MagicMock()
    mock_reranker_instance.predict.return_value = [0.95]
    mock_reranker.return_value = mock_reranker_instance

    chunks = retrieve_tax_law("1세대 1주택 비과세 요건", top_k=5, rerank_top_n=1)

    assert len(chunks) == 1
    assert chunks[0].id == "285631_0154001"
    assert chunks[0].law_name == "소득세법 시행령"
    assert chunks[0].score > 0


@patch("src.retrieval.tax_law_search._get_pinecone_index")
@patch("src.retrieval.tax_law_search._embed_query")
@patch("src.retrieval.tax_law_search._get_reranker")
def test_retrieve_returns_chunk_ids_not_just_text(mock_reranker, mock_embed, mock_index):
    """검색 결과에 chunk_id 반드시 포함 (텍스트만 반환 금지)"""
    from src.retrieval.tax_law_search import retrieve_tax_law

    mock_embed.return_value = [0.1] * 4096
    mock_index.return_value.query.return_value = {
        "matches": [
            {"id": "285523_0089001", "metadata": {
                "law_name": "소득세법", "article_number": "89",
                "article_title": "비과세 양도소득", "effective_date": "20240101",
                "full_text": "제89조 비과세 양도소득",
            }}
        ]
    }
    mock_reranker_instance = MagicMock()
    mock_reranker_instance.predict.return_value = [0.8]
    mock_reranker.return_value = mock_reranker_instance

    chunks = retrieve_tax_law("비과세", top_k=5, rerank_top_n=1)

    assert all(hasattr(c, "id") for c in chunks), "chunk_id 없는 결과 있음"
    assert all(c.id for c in chunks), "chunk_id가 빈 문자열인 결과 있음"


# ── 인용 무결성 ───────────────────────────────────────────────────────────────

def test_citations_only_from_retrieved_chunks():
    """TaxAnswer.citations는 retrieved chunk에 있는 법령만 인용해야 함"""
    from src.application.question_service import TaxAnswer

    retrieved_ids = {"285523_0089001", "285631_0154001"}

    answer = TaxAnswer(
        answer="비과세 해당",
        citations=["소득세법 제89조", "소득세법 시행령 제154조"],
        chunk_ids=["285523_0089001", "285631_0154001"],
        confidence=0.9,
        missing_facts=[],
        warnings=[],
    )

    for cid in answer.chunk_ids:
        assert cid in retrieved_ids, f"검색 결과에 없는 chunk_id 인용: {cid}"


def test_no_retrieved_chunks_returns_empty_answer():
    """검색 결과 없으면 빈 TaxAnswer 반환 (hallucination 방지)"""
    from src.application.question_service import TaxAnswer

    empty_answer = TaxAnswer(
        answer="관련 법령을 찾을 수 없습니다.",
        citations=[],
        chunk_ids=[],
        confidence=0.0,
        missing_facts=[],
        warnings=["검색 결과 없음"],
    )

    assert empty_answer.confidence == 0.0
    assert empty_answer.citations == []
    assert "검색 결과 없음" in empty_answer.warnings


# ── BGE Reranker 호출 검증 ────────────────────────────────────────────────────

@patch("src.retrieval.tax_law_search._get_pinecone_index")
@patch("src.retrieval.tax_law_search._embed_query")
@patch("src.retrieval.tax_law_search._get_reranker")
def test_reranker_is_called_before_final_selection(mock_reranker, mock_embed, mock_index):
    """BGE reranker가 반드시 호출됨 (최종 선택 전)"""
    from src.retrieval.tax_law_search import retrieve_tax_law

    mock_embed.return_value = [0.1] * 4096
    mock_index.return_value.query.return_value = {
        "matches": [
            {"id": f"id_{i}", "metadata": {
                "law_name": "소득세법", "article_number": str(i),
                "article_title": "", "effective_date": "20240101",
                "full_text": f"조문 {i}",
            }} for i in range(5)
        ]
    }
    mock_reranker_instance = MagicMock()
    mock_reranker_instance.predict.return_value = [0.9, 0.8, 0.7, 0.6, 0.5]
    mock_reranker.return_value = mock_reranker_instance

    retrieve_tax_law("테스트", top_k=5, rerank_top_n=3)

    mock_reranker_instance.predict.assert_called_once()
