"""Streamlit render helpers."""
from __future__ import annotations

import streamlit as st


FIELD_LABELS = {
    "transfer_date": "양도일",
    "acquisition_date": "취득일",
    "property_type": "부동산 종류",
    "acquisition_reason": "취득 원인",
    "household_house_count": "보유 주택 수",
    "transfer_price": "양도가액",
    "acquisition_price": "취득가액",
    "residence_years": "거주기간(년)",
    "holding_years": "보유기간(년)",
    "is_adjustment_area_at_transfer": "양도시 조정대상지역",
    "is_adjustment_area_at_acquisition": "취득시 조정대상지역",
    "is_gift_from_spouse_or_lineal": "배우자/직계존비속 증여",
    "special_cases": "특례 사항",
}

VERDICT_COLOR = {
    "비과세": "green",
    "감면": "blue",
    "중과": "red",
    "일반과세": "orange",
    "단기세율": "red",
    "고가주택": "orange",
    "사실관계부족": "gray",
    "전문가검토": "gray",
}

VERDICT_RATE = {
    "비과세": "세금 없음",
    "감면": "감면 세율 적용",
    "중과": "기본세율 + 20~30%p 중과",
    "일반과세": "기본세율 6~45%",
    "단기세율": "단기세율 60~70%",
    "고가주택": "12억 초과분 기본세율",
    "사실관계부족": "추가 확인 필요",
    "전문가검토": "전문가 검토 필요",
}


def fmt_value(value) -> str:
    if isinstance(value, bool):
        return "예" if value else "아니오"
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        return f"{value:,.3f}".rstrip("0").rstrip(".")
    if isinstance(value, str) and len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"
    if isinstance(value, dict):
        return ", ".join(f"{k}: {fmt_value(v)}" for k, v in value.items())
    return str(value)


def render_fact_korean(fact: dict) -> None:
    for key, value in fact.items():
        col1, col2 = st.columns([4, 5])
        col1.caption(FIELD_LABELS.get(key, key))
        col2.caption(f"**{fmt_value(value)}**")


def render_realtime_event(event: str, data: dict, placeholders: dict) -> None:
    if event == "fact_summary":
        with placeholders["fact"].container():
            st.markdown("#### 1. 입력 이해")
            cols = st.columns(3)
            cols[0].caption(f"양도일: **{fmt_value(data.get('transfer_date'))}**")
            cols[1].caption(f"취득일: **{fmt_value(data.get('acquisition_date'))}**")
            cols[2].caption(f"보유기간: **{fmt_value(data.get('holding_years'))}년**")
            cols = st.columns(3)
            cols[0].caption(f"부동산: **{fmt_value(data.get('property_type'))}**")
            cols[1].caption(f"주택 수: **{fmt_value(data.get('household_house_count'))}주택**")
            cols[2].caption(f"양도가액: **{fmt_value(data.get('transfer_price'))}원**")
    elif event == "fact_check":
        with placeholders["fact_check"].container():
            st.markdown("#### 2. 사실관계 점검")
            if data.get("can_proceed"):
                st.success("필수 사실관계 확인 완료")
            else:
                st.warning("필수 사실관계가 부족해 판단을 중단합니다.")
            flags = data.get("danger_flags") or []
            st.caption("탐지된 쟁점: " + ", ".join(f"`{f}`" for f in flags) if flags else "탐지된 고위험 쟁점 없음")
            for item in data.get("missing_facts") or []:
                st.warning(item)
    elif event == "query_enrichment":
        with placeholders["query"].container():
            st.markdown("#### 3. 검색 쟁점")
            keywords = data.get("keywords") or []
            if keywords:
                st.table([{"쟁점": i.get("flag", ""), "검색 보강": i.get("keyword", "")} for i in keywords])
            else:
                st.caption("추가 검색 보강 없이 기본 사실관계로 검색합니다.")
    elif event == "retrieved_chunks":
        with placeholders["chunks"].container():
            st.markdown("#### 4. 검색된 근거 후보")
            chunks = data.get("chunks") or []
            if chunks:
                st.table([
                    {
                        "조문": c.get("article", ""),
                        "출처": c.get("source_label", ""),
                        "chunk_id": c.get("chunk_id", "")[:28],
                        "score": c.get("score", 0.0),
                    }
                    for c in chunks
                ])
            else:
                st.warning("검색된 근거 후보가 없습니다.")
    elif event == "validation":
        with placeholders["validation"].container():
            st.markdown("#### 5. 인용 검증")
            if data.get("phantom_count", 0):
                st.warning(
                    f"검색 결과에 없는 인용 {data.get('phantom_count')}건을 감지했습니다. "
                    f"신뢰도 {data.get('confidence_before'):.2f} -> {data.get('confidence_after'):.2f}"
                )
            else:
                st.success(f"검색된 {data.get('retrieved_count')}개 후보 기준으로 인용 검증 완료")


def render_pipeline_result(result: dict) -> None:
    verdict = result.get("verdict", "사실관계부족")
    confidence = float(result.get("confidence", 0.0) or 0.0)
    st.markdown("---")
    st.markdown("#### 최종 판단")
    col_v, col_r, col_c = st.columns([2, 3, 2])
    with col_v:
        st.markdown("**판단**")
        st.markdown(f"## :{VERDICT_COLOR.get(verdict, 'gray')}[{verdict}]")
    with col_r:
        st.markdown("**적용 세율**")
        st.markdown(f"**{VERDICT_RATE.get(verdict, '')}**")
    with col_c:
        st.markdown("**신뢰도**")
        st.markdown(f"**{confidence:.0%}**")

    with st.expander("판단 근거 설명", expanded=True):
        st.markdown(result.get("answer", ""))
        for item in result.get("missing_facts") or []:
            st.warning(item)

    if result.get("citations"):
        with st.expander("근거 법령", expanded=True):
            for citation in result["citations"]:
                st.markdown(f"- {citation}")

    warnings = [w for w in (result.get("warnings") or []) if not w.startswith("[Red Team")]
    if warnings:
        with st.expander("유의사항"):
            for warning in warnings:
                st.info(warning)
