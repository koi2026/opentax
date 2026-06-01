"""Serialization helpers shared by API and MCP adapters."""
from __future__ import annotations

from datetime import date
from typing import Any

from src.domain.chunk_metadata import (
    AmendmentType,
    AppendixType,
    ApplicabilityRuleType,
    ApplicabilitySpec,
    LawChunkMetadata,
    LawId,
    LawLevel,
    TopicTag,
)
from src.domain.retriever import RetrievedChunk


def _date_to_yyyymmdd(value: date | None) -> int | None:
    if value is None:
        return None
    return int(value.strftime("%Y%m%d"))


def _date_from_yyyymmdd(value: Any, default: date = date(2000, 1, 1)) -> date:
    if value in (None, ""):
        return default
    s = str(int(float(value)))
    if len(s) != 8:
        return default
    return date(int(s[:4]), int(s[4:6]), int(s[6:8]))


def chunk_to_payload(chunk: RetrievedChunk) -> dict[str, Any]:
    meta = chunk.metadata
    return {
        "chunk_id": meta.chunk_id,
        "law_name": meta.law_name,
        "law_id": meta.law_id.value,
        "law_level": meta.law_level.value,
        "article_number": meta.article_number,
        "article_title": "",
        "paragraph": meta.paragraph,
        "item": meta.item,
        "source_label": meta.source_label or meta.law_name,
        "law_version": str(_date_to_yyyymmdd(meta.effective_from) or ""),
        "excerpt": chunk.content[:500],
        "full_text": chunk.content,
        "score": chunk.score,
        "included_as_linked_buchik": chunk.included_as_linked_buchik,
        "metadata": {
            "lsi_seq": meta.lsi_seq,
            "promulgation_date": _date_to_yyyymmdd(meta.promulgation_date),
            "effective_date": _date_to_yyyymmdd(meta.effective_from),
            "expiration_date": _date_to_yyyymmdd(meta.effective_to) or 99991231,
            "amendment_type": meta.amendment_type.value,
            "article_lineage_root": meta.article_lineage_root,
            "appendix_type": meta.appendix_type.value,
            "applicability_rule_type": meta.applicability.rule_type.value,
            "applicability_anchors": meta.applicability.anchors,
            "applicability_condition_text": meta.applicability.condition_text,
            "linked_buchik_ids": meta.linked_buchik_ids,
            "parent_main_chunk_id": meta.parent_main_chunk_id,
            "cross_refs": meta.cross_refs,
            "entity_scopes": meta.entity_scopes,
            "tax_types": meta.tax_types,
            "topic_tags": [tag.value if hasattr(tag, "value") else str(tag) for tag in meta.topic_tags],
            "source_url": meta.source_url,
            "source_hash": meta.source_hash,
        },
    }


def payload_to_chunk(payload: dict[str, Any]) -> RetrievedChunk:
    meta_payload = payload.get("metadata") or {}
    topic_tags = []
    for value in meta_payload.get("topic_tags") or []:
        try:
            topic_tags.append(TopicTag(value))
        except ValueError:
            continue

    law_id_value = payload.get("law_id") or LawId.INCOME_TAX_ACT.value
    law_level_value = payload.get("law_level") or LawLevel.ACT.value
    amendment_value = meta_payload.get("amendment_type") or AmendmentType.PARTIAL.value
    appendix_value = meta_payload.get("appendix_type") or AppendixType.MAIN_BODY.value
    rule_value = meta_payload.get("applicability_rule_type") or ApplicabilityRuleType.NONE.value

    metadata = LawChunkMetadata(
        chunk_id=str(payload.get("chunk_id", "")),
        law_id=LawId(law_id_value) if law_id_value in LawId._value2member_map_ else LawId.INCOME_TAX_ACT,
        law_name=str(payload.get("law_name", "")),
        law_level=LawLevel(law_level_value) if law_level_value in LawLevel._value2member_map_ else LawLevel.ACT,
        article_number=str(payload.get("article_number", "")),
        paragraph=payload.get("paragraph"),
        item=payload.get("item"),
        lsi_seq=str(meta_payload.get("lsi_seq", "")),
        promulgation_date=_date_from_yyyymmdd(meta_payload.get("promulgation_date")),
        effective_from=_date_from_yyyymmdd(meta_payload.get("effective_date")),
        effective_to=None
        if int(meta_payload.get("expiration_date", 99991231) or 99991231) == 99991231
        else _date_from_yyyymmdd(meta_payload.get("expiration_date")),
        amendment_type=AmendmentType(amendment_value)
        if amendment_value in AmendmentType._value2member_map_
        else AmendmentType.PARTIAL,
        article_lineage_root=str(meta_payload.get("article_lineage_root", payload.get("article_number", ""))),
        appendix_type=AppendixType(appendix_value)
        if appendix_value in AppendixType._value2member_map_
        else AppendixType.MAIN_BODY,
        applicability=ApplicabilitySpec(
            rule_type=ApplicabilityRuleType(rule_value)
            if rule_value in ApplicabilityRuleType._value2member_map_
            else ApplicabilityRuleType.NONE,
            anchors=list(meta_payload.get("applicability_anchors") or ["transfer_date"]),
            condition_text=meta_payload.get("applicability_condition_text"),
        ),
        linked_buchik_ids=list(meta_payload.get("linked_buchik_ids") or []),
        parent_main_chunk_id=meta_payload.get("parent_main_chunk_id"),
        cross_refs=list(meta_payload.get("cross_refs") or []),
        entity_scopes=list(meta_payload.get("entity_scopes") or []),
        tax_types=list(meta_payload.get("tax_types") or ["transfer"]),
        topic_tags=topic_tags,
        source_label=str(payload.get("source_label", "")),
        source_url=meta_payload.get("source_url"),
        source_hash=meta_payload.get("source_hash"),
    )
    return RetrievedChunk(
        metadata=metadata,
        content=str(payload.get("full_text") or payload.get("excerpt") or ""),
        score=float(payload.get("score", 0.0) or 0.0),
        included_as_linked_buchik=bool(payload.get("included_as_linked_buchik", False)),
    )


def citation_to_display(citation: Any) -> str:
    article = citation.article if hasattr(citation, "article") else str(citation)
    label = getattr(citation, "source_label", "") or ""
    version = getattr(citation, "law_version", "") or ""
    v_str = ""
    if version:
        v = str(version)
        if len(v) == 8 and v.isdigit():
            v = f"{v[:4]}-{v[4:6]}-{v[6:]}"
        v_str = f" [시행 {v}]"
    prefix = f"[{label}] " if label else ""
    return f"{prefix}{article}{v_str}"


def pipeline_result_to_response(result: Any, session_id: str, mode: str = "pipeline") -> dict[str, Any]:
    ans = result.answer
    return {
        "session_id": session_id,
        "verdict": str(ans.verdict),
        "answer": ans.answer,
        "confidence": ans.confidence,
        "citations": [citation_to_display(c) for c in ans.citations],
        "chunk_ids": ans.chunk_ids,
        "missing_facts": ans.missing_facts,
        "warnings": ans.warnings,
        "blocked": result.blocked_at_l2 or getattr(result, "blocked_at_confirmation", False),
        "mode": mode,
        "consulting_scenarios": result.consulting_scenarios,
        "debate_record": result.debate_record,
    }
