"""Retrieval quality scoring for legal RAG.

The score here is not a probability that the final tax answer is correct. It is
a retrieval-side signal: did the search return the legal anchors that this kind
of case usually needs, and are the reranker scores usable?
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import exp
from typing import Iterable, List, Sequence

from .query_input import AcquisitionReason, PropertyType, RAGQueryInput
from .retriever import RetrievedChunk


@dataclass(frozen=True)
class ArticleRef:
    law_name: str
    article_number: str

    @property
    def label(self) -> str:
        return f"{self.law_name} 제{self.article_number}조"


@dataclass(frozen=True)
class RequiredArticle(ArticleRef):
    reason: str = ""


@dataclass
class RetrievalQuality:
    confidence: float
    coverage_score: float
    relevance_score: float
    filter_score: float
    result_count: int
    required_articles: List[str] = field(default_factory=list)
    missing_required_articles: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def normalize_article_number(value: str) -> str:
    return (
        str(value or "")
        .strip()
        .replace("제", "")
        .replace("조", "")
        .replace(" ", "")
    )


def article_key(law_name: str, article_number: str) -> tuple[str, str]:
    return law_name.replace(" ", ""), normalize_article_number(article_number)


def article_refs_from_chunks(chunks: Sequence[RetrievedChunk]) -> List[ArticleRef]:
    return [
        ArticleRef(chunk.metadata.law_name, chunk.metadata.article_number)
        for chunk in chunks
    ]


def _has_article(article_refs: Sequence[ArticleRef], req: RequiredArticle) -> bool:
    req_key = article_key(req.law_name, req.article_number)
    return any(article_key(ref.law_name, ref.article_number) == req_key for ref in article_refs)


def _dedupe_required(items: Iterable[RequiredArticle]) -> List[RequiredArticle]:
    seen: set[tuple[str, str]] = set()
    result: List[RequiredArticle] = []
    for item in items:
        key = article_key(item.law_name, item.article_number)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def required_articles_for_query(
    query: RAGQueryInput,
    danger_flags: Sequence[str],
) -> List[RequiredArticle]:
    """Return rule-based article coverage expectations for a query."""

    fv = query.fact_vector
    flags = set(danger_flags)
    required: List[RequiredArticle] = []

    house_like = {
        PropertyType.APARTMENT,
        PropertyType.HOUSE,
        PropertyType.VILLA,
        PropertyType.DAGAGU,
        PropertyType.GYEOMYONG,
        PropertyType.OFFICETEL_RESIDENTIAL,
        PropertyType.RURAL_HOUSE,
    }

    if fv.property_type in house_like:
        required.extend([
            RequiredArticle("소득세법", "89", "1세대1주택 비과세 기본 조문"),
            RequiredArticle("소득세법 시행령", "154", "1세대1주택 보유·거주 요건"),
        ])

    if fv.is_high_value_house or "고가주택" in flags or "고가주택_미확인" in flags:
        required.extend([
            RequiredArticle("소득세법", "89", "고가주택 비과세 범위"),
            RequiredArticle("소득세법 시행령", "156의2", "고가주택 초과분 계산"),
        ])

    if fv.holding_period_years < 2.0 or fv.property_type == PropertyType.SUBSCRIPTION_RIGHT:
        required.append(RequiredArticle("소득세법", "104", "단기양도 및 세율 판단"))

    if fv.household_house_count >= 2 and fv.adjustment_area_at_transfer:
        required.append(RequiredArticle("소득세법", "104", "다주택자 중과세율 판단"))

    if "일시적2주택" in flags or fv.special_cases.is_temporary_two_house:
        required.append(RequiredArticle("소득세법 시행령", "155", "일시적 2주택 및 주택 수 특례"))

    if "상속주택" in flags or fv.acquisition_reason == AcquisitionReason.INHERITANCE:
        required.append(RequiredArticle("소득세법 시행령", "155", "상속주택 특례"))

    if any(flag.startswith("이월과세") for flag in flags) or fv.acquisition_reason in {
        AcquisitionReason.GIFT,
        AcquisitionReason.BURDEN_GIFT,
    }:
        required.append(RequiredArticle("소득세법", "97의2", "배우자·직계존비속 증여 이월과세"))

    if fv.property_type == PropertyType.ASSOCIATION_RIGHT or "조합원입주권" in flags:
        required.append(RequiredArticle("소득세법 시행령", "156의2", "조합원입주권 및 재건축 특례"))

    if fv.is_related_party_transaction or "특수관계자거래" in flags:
        required.append(RequiredArticle("소득세법", "101", "특수관계자 부당행위계산부인"))

    return _dedupe_required(required)


def _relevance_score(scores: Sequence[float], result_count: int) -> float:
    if not scores:
        return 0.0

    ranked = sorted((float(s) for s in scores), reverse=True)
    top_norm = 1.0 / (1.0 + exp(-ranked[0]))
    count_bonus = min(result_count, 5) / 5.0
    margin_bonus = 0.5
    if len(ranked) >= 2:
        margin_bonus = min(max((ranked[0] - ranked[1] + 1.0) / 2.0, 0.0), 1.0)

    return round((0.70 * top_norm) + (0.20 * count_bonus) + (0.10 * margin_bonus), 4)


def assess_retrieval_quality_from_refs(
    query: RAGQueryInput,
    article_refs: Sequence[ArticleRef],
    scores: Sequence[float],
    danger_flags: Sequence[str],
    result_count: int,
    has_date_filter_signal: bool = True,
    has_scope_signal: bool = True,
    has_buchik: bool = False,
) -> RetrievalQuality:
    required = required_articles_for_query(query, danger_flags)
    missing = [req for req in required if not _has_article(article_refs, req)]

    coverage_score = 1.0
    if required:
        coverage_score = (len(required) - len(missing)) / len(required)

    relevance_score = _relevance_score(scores, result_count)

    filter_score = 0.70
    if has_date_filter_signal:
        filter_score += 0.15
    if has_scope_signal:
        filter_score += 0.10
    if has_buchik:
        filter_score += 0.05
    filter_score = min(filter_score, 1.0)

    confidence = (0.50 * coverage_score) + (0.35 * relevance_score) + (0.15 * filter_score)

    warnings: List[str] = []
    if result_count == 0:
        warnings.append("검색 결과 없음 - 법령 근거를 확보하지 못했습니다.")
    if missing:
        labels = ", ".join(req.label for req in missing)
        warnings.append(f"검색 커버리지 부족 가능성 - 필수 조문 후보 누락: {labels}")
    if required and coverage_score < 0.5:
        warnings.append("검색된 조문이 질문 유형의 핵심 법령을 충분히 포함하지 못했습니다.")

    return RetrievalQuality(
        confidence=round(max(0.0, min(confidence, 1.0)), 4),
        coverage_score=round(coverage_score, 4),
        relevance_score=relevance_score,
        filter_score=round(filter_score, 4),
        result_count=result_count,
        required_articles=[req.label for req in required],
        missing_required_articles=[req.label for req in missing],
        warnings=warnings,
    )


def assess_retrieval_quality(
    query: RAGQueryInput,
    chunks: Sequence[RetrievedChunk],
    danger_flags: Sequence[str],
) -> RetrievalQuality:
    return assess_retrieval_quality_from_refs(
        query=query,
        article_refs=article_refs_from_chunks(chunks),
        scores=[chunk.score for chunk in chunks],
        danger_flags=danger_flags,
        result_count=len(chunks),
        has_date_filter_signal=bool(chunks),
        has_scope_signal=bool(chunks),
        has_buchik=any(chunk.included_as_linked_buchik for chunk in chunks),
    )
