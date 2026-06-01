from __future__ import annotations

from pathlib import Path
import asyncio

from src.api.fact_input import FactInput, fact_input_to_rag_query
from src.application.serializers import chunk_to_payload, payload_to_chunk
from src.domain.pipeline import run_rag_pipeline
from src.domain.retriever import RetrievedChunk, TaxLawRetriever
from src.domain.tax_answer import TaxAnswer, TaxVerdict
from src.retrieval.retriever_impl import _pinecone_meta_to_chunk_metadata


ROOT = Path(__file__).resolve().parents[1]


def test_api_package_does_not_import_pinecone_retriever_directly() -> None:
    offenders = []
    for path in (ROOT / "src" / "api").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "PineconeTaxLawRetriever" in text:
            offenders.append(path.relative_to(ROOT).as_posix())
    assert offenders == []


def test_mcp_payload_roundtrip_preserves_required_chunk_fields() -> None:
    sample = {
        "id": "sample_chunk",
        "score": 0.7,
        "metadata": {
            "law_name": "소득세법",
            "law_category": "법률",
            "article_number": "89",
            "effective_date": 20240101,
            "expiration_date": 99991231,
            "full_text": "제89조 비과세 양도소득",
            "source_label": "법령 (소득세법)",
        },
    }
    chunk = RetrievedChunk(
        metadata=_pinecone_meta_to_chunk_metadata(sample["id"], sample["metadata"]),
        content=sample["metadata"]["full_text"],
        score=sample["score"],
    )

    payload = chunk_to_payload(chunk)
    restored = payload_to_chunk(payload)

    assert payload["chunk_id"] == "sample_chunk"
    assert payload["source_label"]
    assert round(payload["score"], 3) == 0.7
    assert restored.metadata.chunk_id == "sample_chunk"
    assert restored.metadata.law_name == "소득세법"
    assert restored.content == "제89조 비과세 양도소득"


class RaisingRetriever(TaxLawRetriever):
    def retrieve(self, query, query_text=None):
        raise AssertionError("retriever should not be called for L2-blocked cases")

    def _get_chunk_by_id(self, chunk_id):
        return None

    def _get_content(self, chunk_id):
        return ""


async def _unused_llm(*args, **kwargs):
    return TaxAnswer(answer="", verdict=TaxVerdict.NEEDS_VERIFICATION, confidence=0.0)


def test_l2_blocked_case_does_not_call_mcp_retriever() -> None:
    fact = FactInput(
        transfer_date="20240601",
        acquisition_date="20200301",
        property_type="아파트",
        acquisition_reason="매매",
        household_house_count=1,
        transfer_price=None,
    )
    result = asyncio.run(
        run_rag_pipeline(
            fact_input_to_rag_query(fact),
            RaisingRetriever(),
            _unused_llm,
            fact_json=fact.model_dump(),
        )
    )
    assert result.blocked_at_l2 is True
