"""
PineconeTaxLawRetriever — TaxLawRetriever ABC 의 Pinecone 구현.

Pinecone 메타데이터 ↔ LawChunkMetadata 매핑을 담당한다.
현재 미수집 필드(linked_buchik_ids, entity_scopes 등)는 합리적 기본값 사용.
"""
from __future__ import annotations

from datetime import date
from typing import List, Optional

from src.config import (
    PINECONE_HYBRID_ALPHA,
    PINECONE_NAMESPACE,
    RETRIEVER_PREFILTER_K,
    RETRIEVER_RERANK_TOP_N,
    RETRIEVER_TOP_K,
    RULING_RETRIEVAL_NAMESPACES,
    RULING_TOP_K_RATIO,
)
from src.domain.chunk_metadata import (
    AmendmentType,
    AppendixType,
    ApplicabilityRuleType,
    ApplicabilitySpec,
    LawChunkMetadata,
    LawId,
    LawLevel,
)
from src.domain.fact_checker import check_facts
from src.domain.query_input import RAGQueryInput
from src.domain.retrieval_quality import ArticleRef, assess_retrieval_quality
from src.domain.retriever import RetrievedChunk, TaxLawRetriever
from src.infra.embedder import bm25_sparse_vector, embed_query
from src.infra.pinecone_client import get_pinecone_index, query_pinecone
from src.infra.reranker import rerank

_PREFILTER_LIMIT = RETRIEVER_PREFILTER_K


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

TOP_K = RETRIEVER_TOP_K
RERANK_TOP_N = RETRIEVER_RERANK_TOP_N

# None = dense-only; float string = hybrid (0.0 pure sparse, 1.0 pure dense, 0.75 typical)
_HYBRID_ALPHA = PINECONE_HYBRID_ALPHA

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


def _pinecone_meta_to_ruling_chunk_metadata(match_id: str, meta: dict) -> LawChunkMetadata:
    """유권해석 Pinecone match.metadata → LawChunkMetadata 변환.

    법령 청크와 달리 effective_date/expiration_date 없음.
    issued_at(YYYYMMDD int) → effective_from, effective_to=None.
    source_label 필드 보존 (citation 표시용).
    """
    issued_int = int(float(meta.get("issued_at", 0) or 0))
    issued_date = _int_to_date(issued_int) if issued_int else date(2000, 1, 1)
    source_label = meta.get("source_label", "") or meta.get("source", "")
    doc_number = str(meta.get("doc_number", "") or meta.get("id", match_id))

    return LawChunkMetadata(
        chunk_id=match_id,
        law_id=LawId.INCOME_TAX_ACT,
        law_name=source_label or "유권해석",
        law_level=LawLevel.ACT,
        article_number=doc_number,
        paragraph=None,
        item=None,
        lsi_seq="",
        promulgation_date=issued_date,
        effective_from=issued_date,
        effective_to=None,
        amendment_type=AmendmentType.PARTIAL,
        article_lineage_root=doc_number,
        appendix_type=AppendixType.MAIN_BODY,
        applicability=ApplicabilitySpec(
            rule_type=ApplicabilityRuleType.NONE,
            anchors=["issued_at"],
        ),
        tax_types=["transfer"],
        source_label=source_label,
    )


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


def _article_ref_from_label(label: str) -> ArticleRef:
    law_name, article = label.rsplit(" 제", 1)
    return ArticleRef(law_name=law_name, article_number=article.removesuffix("조"))


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

    def retrieve(self, query: RAGQueryInput, query_text: Optional[str] = None) -> List[RetrievedChunk]:
        query_text = query_text or query.fact_vector.to_text()
        vector = embed_query(query_text)

        # query.top_k 우선, 없으면 인스턴스 기본값
        top_k = getattr(query, "top_k", None) or self.top_k

        # Hybrid search: BM25 sparse vector for article-number exact-match precision
        sparse_vec: Optional[dict] = None
        hybrid_alpha: Optional[float] = None
        if _HYBRID_ALPHA is not None:
            hybrid_alpha = _HYBRID_ALPHA
            sparse_vec = bm25_sparse_vector(query_text)

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

        # Stage 1 보강 — entity_scope 후필터 (Pinecone entity_scopes 메타데이터 기반)
        # EntityScope.value = "주택"/"분양권" 등 — embed.py의 _tag_chunk()와 동일한 값 사용
        scope_val = query.entity_scope.value
        if scope_val and matches:
            filtered = [
                m for m in matches
                if not m.get("metadata", {}).get("entity_scopes")  # 태그 없으면 통과
                or scope_val in m["metadata"]["entity_scopes"]
            ]
            matches = filtered if filtered else matches  # 필터 결과 비면 전체 유지

        # ── 유권해석 병렬 검색 ────────────────────────────────────────────────────
        # RULING_RETRIEVAL_NAMESPACES 네임스페이스를 날짜 필터 없이 병렬 쿼리.
        # 예규/심판원 결정은 deprecated 필터가 embed 단계에서 처리됨 (re-date 불필요).
        ruling_matches: list[dict] = []
        ruling_top_k = max(1, int(top_k * RULING_TOP_K_RATIO))
        for ns in RULING_RETRIEVAL_NAMESPACES:
            ns_matches = query_pinecone(
                vector=vector,
                top_k=ruling_top_k,
                namespace=ns,
                sparse_vector=sparse_vec,
                alpha=hybrid_alpha,
            )
            for m in ns_matches:
                m["_ruling_namespace"] = ns  # 출처 네임스페이스 태깅
            ruling_matches.extend(ns_matches)

        # 법령 + 유권해석 통합 풀 — BGE가 단일 pass로 최종 순위 결정
        all_matches = matches + ruling_matches
        if not all_matches:
            return []

        # Stage 1.5 — Cheap Pre-filter: 통합 풀에서 결정론 신호로 후보 축소
        # 유권해석 후보가 추가됐으므로 prefilter limit을 비례 확대
        prefilter_limit = _PREFILTER_LIMIT + len(RULING_RETRIEVAL_NAMESPACES) * (ruling_top_k // 2)
        prefiltered = _cheap_prefilter(all_matches, query_text, limit=prefilter_limit)

        # Stage 2 — BGE Rerank (법령 + 유권해석 통합)
        ranked = rerank(query_text, prefiltered, self.rerank_top_n)

        results: List[RetrievedChunk] = []
        for score, match in ranked:
            meta = match["metadata"]
            is_ruling = "_ruling_namespace" in match
            if is_ruling:
                chunk_meta = _pinecone_meta_to_ruling_chunk_metadata(match["id"], meta)
            else:
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

    def _get_required_article_by_metadata(self, label: str) -> Optional[RetrievedChunk]:
        """Fetch one exact legal anchor by Pinecone metadata.

        Pinecone still requires a query vector, but relevance is constrained by
        exact law_name/article_number metadata filters.
        """
        ref = _article_ref_from_label(label)
        matches = query_pinecone(
            vector=embed_query(label),
            top_k=5,
            namespace=self.namespace,
            filter_dict={
                "$and": [
                    {"law_name": {"$eq": ref.law_name}},
                    {"article_number": {"$eq": ref.article_number}},
                ]
            },
        )
        if not matches:
            return None

        best = max(matches, key=lambda m: float(m.get("score", 0.0)))
        meta = best.get("metadata", {})
        return RetrievedChunk(
            metadata=_pinecone_meta_to_chunk_metadata(best["id"], meta),
            content=meta.get("full_text", ""),
            score=float(best.get("score", 0.0)),
        )

    def _dedupe_chunks(self, chunks: List[RetrievedChunk]) -> List[RetrievedChunk]:
        seen: set[str] = set()
        result: List[RetrievedChunk] = []
        for chunk in chunks:
            if chunk.metadata.chunk_id in seen:
                continue
            seen.add(chunk.metadata.chunk_id)
            result.append(chunk)
        return result

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

    def retrieve_with_buchik(self, query: RAGQueryInput, query_text: Optional[str] = None) -> List[RetrievedChunk]:
        """본칙 검색 후 linked_buchik_ids로 부칙 보강, applicability_anchor 하드필터 적용.

        부칙 적용례 예:
          "이 법 시행 후 양도분부터 적용" → anchor=transfer_date
          "취득분부터 적용" → anchor=acquisition_date
        앵커 날짜 < 부칙 시행일이면 해당 부칙은 이 사건에 미적용 → 제외.

        기본 embedding retrieval이 핵심 조항을 놓친 경우, query 유형별 필수
        anchor 조항을 Pinecone metadata exact filter로 보강하고 그 anchor의
        linked_buchik_ids도 동일한 applicability 기준으로 확장한다.
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

        repaired = results + extra

        fact_check = check_facts(query)
        quality = assess_retrieval_quality(query, repaired, fact_check.danger_flags)
        if not quality.missing_required_articles:
            return repaired

        for label in quality.missing_required_articles:
            anchor_chunk = self._get_required_article_by_metadata(label)
            if anchor_chunk is None or anchor_chunk.metadata.chunk_id in seen_ids:
                continue

            repaired.append(anchor_chunk)
            seen_ids.add(anchor_chunk.metadata.chunk_id)

            for buchik_id in anchor_chunk.metadata.linked_buchik_ids:
                if buchik_id in seen_ids:
                    continue
                buchik_meta = self._get_chunk_by_id(buchik_id)
                if buchik_meta is None:
                    continue
                buchik_chunk = RetrievedChunk(
                    metadata=buchik_meta,
                    content=self._get_content(buchik_id),
                    score=anchor_chunk.score,
                    included_as_linked_buchik=True,
                )
                if not self._is_buchik_applicable(buchik_chunk, query):
                    continue
                repaired.append(buchik_chunk)
                seen_ids.add(buchik_id)

        return self._dedupe_chunks(repaired)
