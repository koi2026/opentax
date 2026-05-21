"""
PineconeTaxLawRetriever — TaxLawRetriever ABC 의 Pinecone 구현.

Pinecone 메타데이터 ↔ LawChunkMetadata 매핑을 담당한다.
현재 미수집 필드(linked_buchik_ids, entity_scopes 등)는 합리적 기본값 사용.
"""
from __future__ import annotations

import os
from datetime import date
from typing import List, Optional

from dotenv import load_dotenv

from src.domain.chunk_metadata import (
    AmendmentType,
    AppendixType,
    ApplicabilityRuleType,
    ApplicabilitySpec,
    LawChunkMetadata,
    LawId,
    LawLevel,
)
from src.domain.query_input import RAGQueryInput
from src.domain.retriever import RetrievedChunk, TaxLawRetriever
from src.infra.embedder import bm25_sparse_vector, embed_query
from src.infra.pinecone_client import get_pinecone_index, query_pinecone
from src.infra.reranker import rerank

load_dotenv()

_PREFILTER_LIMIT = int(os.getenv("RETRIEVER_PREFILTER_K", "8"))


def _cheap_prefilter(matches: list[dict], query_text: str, limit: int = _PREFILTER_LIMIT) -> list[dict]:
    """Reranker 투입 전 결정론 신호로 후보를 limit개로 축소 (CPU 추론 비용 절감).

    Pinecone vector score + 조문번호 exact-match + entity_scopes + linked_buchik_ids 가산점.
    """
    article_boost = 0.15 if "제" in query_text or "§" in query_text else 0.0

    def _score(m: dict) -> float:
        base = float(m.get("score", 0.0))
        meta = m.get("metadata", {})
        bonus = 0.0
        art_num = meta.get("article_number", "")
        if art_num and art_num in query_text:
            bonus += article_boost
        if meta.get("entity_scopes"):
            bonus += 0.05
        if meta.get("linked_buchik_ids"):
            bonus += 0.03
        return base + bonus

    return sorted(matches, key=_score, reverse=True)[:limit]

PINECONE_NAMESPACE = os.getenv("PINECONE_NAMESPACE", "tax-law")
TOP_K = int(os.getenv("RETRIEVER_TOP_K", "20"))
RERANK_TOP_N = int(os.getenv("RETRIEVER_RERANK_TOP_N", "5"))

# None = dense-only; float string = hybrid (0.0 pure sparse, 1.0 pure dense, 0.75 typical)
_HYBRID_ALPHA_RAW = os.getenv("PINECONE_HYBRID_ALPHA")

# 법령명 → LawId 매핑
_LAW_NAME_TO_ID = {
    "소득세법": LawId.INCOME_TAX_ACT,
    "소득세법 시행령": LawId.INCOME_TAX_DECREE,
    "소득세법 시행규칙": LawId.INCOME_TAX_RULE,
    "조세특례제한법": LawId.SPECIAL_TAX_ACT,
    "조세특례제한법 시행령": LawId.SPECIAL_TAX_DECREE,
    "조세특례제한법 시행규칙": LawId.SPECIAL_TAX_RULE,
    "지방세법": LawId.LOCAL_TAX_ACT,
    "지방세법 시행령": LawId.LOCAL_TAX_DECREE,
    "지방세법 시행규칙": LawId.LOCAL_TAX_RULE,
    "국세기본법": LawId.FRAMEWORK_TAX_ACT,
    "국세기본법 시행령": LawId.FRAMEWORK_TAX_DECREE,
    "국세기본법 시행규칙": LawId.FRAMEWORK_TAX_RULE,
    "상속세 및 증여세법": LawId.INHERITANCE_TAX_ACT,
    "상속세 및 증여세법 시행령": LawId.INHERITANCE_TAX_DECREE,
}

_LAW_CATEGORY_TO_LEVEL = {
    "법률": LawLevel.ACT,
    "대통령령": LawLevel.ENFORCEMENT_DECREE,
    "부령": LawLevel.ENFORCEMENT_RULE,
    "시행규칙": LawLevel.ENFORCEMENT_RULE,
}


def _select_anchor_date(query: RAGQueryInput) -> date:
    """Select the most appropriate date anchor for Pinecone version filtering.

    Special cases use a different date than the default transfer_date:
    - 이월과세: 증여일 (law version when the gift occurred)
    - 상속주택: 상속개시일 (law version when death occurred)
    - 조합원입주권: 관리처분계획인가일 (law version when reconstruction was approved)
    - Default: 양도일
    """
    sc = query.fact_vector.special_cases

    # 이월과세: 증여일 기준 법령 버전
    rt = sc.rollover_taxation if sc else None
    if rt and rt.is_gift_from_spouse_or_lineal and rt.gift_date:
        return rt.gift_date

    # 상속주택: 상속개시일 기준
    inh = sc.inheritance if sc else None
    if inh and inh.death_date:
        return inh.death_date

    # 조합원입주권: 관리처분인가일 기준
    rc = sc.reconstruction if sc else None
    if rc and rc.management_disposal_date:
        return rc.management_disposal_date

    # 기본: 양도일
    return query.date_bundle.transfer_date


def _int_to_date(val: int) -> date:
    """YYYYMMDD 정수 → date. 형식 오류면 2000-01-01 안전 fallback."""
    s = str(int(val))
    if len(s) != 8:
        return date(2000, 1, 1)
    try:
        return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
    except ValueError:
        return date(2000, 1, 1)


def _pinecone_meta_to_chunk_metadata(match_id: str, meta: dict) -> LawChunkMetadata:
    """Pinecone match.metadata → LawChunkMetadata 로 변환."""
    eff_int = int(float(meta.get("effective_date", 0) or 0))
    exp_int = int(float(meta.get("expiration_date", 99991231) or 99991231))
    law_name = meta.get("law_name", "")
    article_type = meta.get("article_type", "")
    appendix = AppendixType.BUCHIK if article_type == "부칙" else AppendixType.MAIN_BODY

    # linked_buchik_ids: Pinecone는 list 메타데이터를 그대로 반환
    raw_buchik = meta.get("linked_buchik_ids", [])
    buchik_ids: list[str] = list(raw_buchik) if isinstance(raw_buchik, list) else []

    # applicability_anchor → ApplicabilitySpec.anchors 매핑
    # 수집 시 _extract_buchik_anchor()로 추출한 키("transfer_date" 등)를 그대로 보존
    anchor_key = meta.get("applicability_anchor", "effective_date") or "effective_date"
    applicability = ApplicabilitySpec(
        rule_type=ApplicabilityRuleType.NONE,
        anchors=[anchor_key],
    )

    return LawChunkMetadata(
        chunk_id=match_id,
        law_id=_LAW_NAME_TO_ID.get(law_name, LawId.INCOME_TAX_ACT),
        law_name=law_name,
        law_level=_LAW_CATEGORY_TO_LEVEL.get(meta.get("law_category", ""), LawLevel.ACT),
        article_number=meta.get("article_number", ""),
        paragraph=None,
        item=None,
        lsi_seq=str(meta.get("version_mst", "")),
        promulgation_date=_int_to_date(eff_int) if eff_int else date(2000, 1, 1),
        effective_from=_int_to_date(eff_int) if eff_int else date(2000, 1, 1),
        effective_to=None if exp_int == 99991231 else _int_to_date(exp_int),
        amendment_type=AmendmentType.PARTIAL,
        article_lineage_root=meta.get("article_number", ""),
        appendix_type=appendix,
        applicability=applicability,
        tax_types=["transfer"],
        linked_buchik_ids=buchik_ids,
    )


class PineconeTaxLawRetriever(TaxLawRetriever):
    """Pinecone + BGE Reranker 기반 TaxLawRetriever 구현."""

    def __init__(
        self,
        top_k: int = TOP_K,
        rerank_top_n: int = RERANK_TOP_N,
        namespace: str = PINECONE_NAMESPACE,
    ):
        self.top_k = top_k
        self.rerank_top_n = rerank_top_n
        self.namespace = namespace

    def retrieve(self, query: RAGQueryInput) -> List[RetrievedChunk]:
        query_text = query.fact_vector.to_text()
        vector = embed_query(query_text)

        # query.top_k 우선, 없으면 인스턴스 기본값
        top_k = getattr(query, "top_k", None) or self.top_k

        # Hybrid search: BM25 sparse vector for article-number exact-match precision
        sparse_vec: Optional[dict] = None
        hybrid_alpha: Optional[float] = None
        if _HYBRID_ALPHA_RAW is not None:
            try:
                hybrid_alpha = float(_HYBRID_ALPHA_RAW)
                sparse_vec = bm25_sparse_vector(query_text)
            except ValueError:
                pass  # Malformed env var — fall back to dense-only

        # Stage 1 — Symbolic Filter: 앵커 날짜 기준 날짜 범위 (Pinecone 숫자 필터)
        # 이월과세→증여일, 상속→상속개시일, 입주권→관리처분인가일, 기본→양도일
        anchor_date = _select_anchor_date(query)
        as_of_int = int(anchor_date.strftime("%Y%m%d"))
        pinecone_filter = {
            "$and": [
                {"effective_date": {"$lte": as_of_int}},
                {"expiration_date": {"$gte": as_of_int}},
            ]
        }

        matches = query_pinecone(
            vector=vector,
            top_k=top_k,
            namespace=self.namespace,
            filter_dict=pinecone_filter,
            sparse_vector=sparse_vec,
            alpha=hybrid_alpha,
        )

        # 날짜 필터 결과 없으면 필터 없이 재검색 (법령 버전 이력 미수집 상태 대응)
        if not matches:
            matches = query_pinecone(
                vector=vector,
                top_k=top_k,
                namespace=self.namespace,
                sparse_vector=sparse_vec,
                alpha=hybrid_alpha,
            )

        if not matches:
            return []

        # Stage 1 보강 — entity_scope 후필터 (Pinecone entity_scopes 메타데이터 기반)
        # EntityScope.value = "주택"/"분양권" 등 — embed.py의 _tag_chunk()와 동일한 값 사용
        scope_val = query.entity_scope.value
        if scope_val:
            filtered = [
                m for m in matches
                if not m.get("metadata", {}).get("entity_scopes")  # 태그 없으면 통과
                or scope_val in m["metadata"]["entity_scopes"]
            ]
            matches = filtered if filtered else matches  # 필터 결과 비면 전체 유지

        # Stage 1.5 — Cheap Pre-filter: 결정론 신호로 후보 축소 후 BGE Reranker 투입
        prefiltered = _cheap_prefilter(matches, query_text)

        # Stage 2 — Vector Rerank
        ranked = rerank(query_text, prefiltered, self.rerank_top_n)

        results: List[RetrievedChunk] = []
        for score, match in ranked:
            meta = match["metadata"]
            chunk_meta = _pinecone_meta_to_chunk_metadata(match["id"], meta)
            results.append(
                RetrievedChunk(
                    metadata=chunk_meta,
                    content=meta.get("full_text", ""),
                    score=float(score),
                )
            )
        return results

    def _get_chunk_by_id(self, chunk_id: str) -> Optional[LawChunkMetadata]:
        index = get_pinecone_index()
        res = index.fetch(ids=[chunk_id], namespace=self.namespace)
        vectors = res.get("vectors", {}) if isinstance(res, dict) else getattr(res, "vectors", {})
        if chunk_id not in vectors:
            return None
        vec = vectors[chunk_id]
        meta = vec.get("metadata", {}) if isinstance(vec, dict) else getattr(vec, "metadata", {})
        return _pinecone_meta_to_chunk_metadata(chunk_id, meta or {})

    def _get_content(self, chunk_id: str) -> str:
        index = get_pinecone_index()
        res = index.fetch(ids=[chunk_id], namespace=self.namespace)
        vectors = res.get("vectors", {}) if isinstance(res, dict) else getattr(res, "vectors", {})
        if chunk_id not in vectors:
            return ""
        vec = vectors[chunk_id]
        meta = vec.get("metadata", {}) if isinstance(vec, dict) else getattr(vec, "metadata", {})
        return (meta or {}).get("full_text", "")

    def _get_anchor_date(self, query: RAGQueryInput, anchor_key: str) -> Optional[date]:
        """부칙 앵커 키 → 쿼리의 해당 날짜.

        DateBundle.get_anchor()로 커버되지 않는 gift_date/death_date는
        FactVector.special_cases에서 직접 조회한다.
        """
        d = query.date_bundle.get_anchor(anchor_key)
        if d is not None:
            return d

        sc = getattr(query.fact_vector, "special_cases", None)
        if sc is None:
            return None

        if anchor_key == "gift_date":
            rt = getattr(sc, "rollover_taxation", None)
            return getattr(rt, "gift_date", None) if rt else None

        if anchor_key == "death_date":
            inh = getattr(sc, "inheritance", None)
            return getattr(inh, "death_date", None) if inh else None

        return None

    def _is_buchik_applicable(self, chunk: RetrievedChunk, query: RAGQueryInput) -> bool:
        """부칙 청크가 쿼리 날짜 기준으로 적용 가능한지 판단.

        앵커 날짜 < 부칙 시행일 → 이 개정의 부칙은 아직 적용 전 → False(제외).
        앵커 날짜를 알 수 없으면 안전하게 True(포함).
        """
        anchors = chunk.metadata.applicability.anchors
        if not anchors:
            return True

        anchor_key = anchors[0]
        if anchor_key == "effective_date":
            # 시행일 기준 부칙 — Pinecone 날짜 필터가 이미 처리, 항상 통과
            return True

        anchor_date = self._get_anchor_date(query, anchor_key)
        if anchor_date is None:
            # 날짜 정보 없음 → 필터 불가 → 안전하게 포함
            return True

        effective_from = chunk.metadata.effective_from
        # 앵커 날짜가 이 부칙의 시행일 이후여야 적용 대상
        return anchor_date >= effective_from

    def retrieve_with_buchik(self, query: RAGQueryInput) -> List[RetrievedChunk]:
        """본칙 검색 후 linked_buchik_ids로 부칙 보강, applicability_anchor 하드필터 적용.

        부칙 적용례 예:
          "이 법 시행 후 양도분부터 적용" → anchor=transfer_date
          "취득분부터 적용" → anchor=acquisition_date
        앵커 날짜 < 부칙 시행일이면 해당 부칙은 이 사건에 미적용 → 제외.
        """
        results = self.retrieve(query)
        if not query.include_buchik:
            return results

        seen_ids = {r.metadata.chunk_id for r in results}
        extra: List[RetrievedChunk] = []
        for chunk in results:
            for buchik_id in chunk.metadata.linked_buchik_ids:
                if buchik_id in seen_ids:
                    continue
                buchik_meta = self._get_chunk_by_id(buchik_id)
                if buchik_meta is None:
                    continue
                buchik_chunk = RetrievedChunk(
                    metadata=buchik_meta,
                    content=self._get_content(buchik_id),
                    score=chunk.score,
                    included_as_linked_buchik=True,
                )
                # 앵커 날짜 기준 부칙 적용 가능 여부 검사
                if not self._is_buchik_applicable(buchik_chunk, query):
                    continue
                extra.append(buchik_chunk)
                seen_ids.add(buchik_id)

        return results + extra
