"""Streamlit render helpers."""
from __future__ import annotations

import html

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

VERDICT_HEX_COLOR = {
    "비과세": "#188038",
    "감면": "#1a73e8",
    "중과": "#c5221f",
    "일반과세": "#b06000",
    "단기세율": "#c5221f",
    "고가주택": "#b06000",
    "사실관계부족": "#5f6368",
    "전문가검토": "#5f6368",
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
    if "_agent_panels" not in st.session_state:
        st.session_state["_agent_panels"] = {
            "A": {"label": "검색 법령 기반", "text": "", "done": False, "summary": None, "heartbeat": 0},
            "B": {"label": "비검색 독립 검토", "text": "", "done": False, "summary": None, "heartbeat": 0},
            "synthesis": None,
        }

    def _render_agent_panels() -> None:
        panel_state = st.session_state["_agent_panels"]
        with placeholders["agents"].container():
            st.markdown("#### 5. 병렬 에이전트 추론")
            col_a, col_b = st.columns(2)
            for col, key in [(col_a, "A"), (col_b, "B")]:
                agent = panel_state[key]
                pulse = "." * int(agent.get("heartbeat", 0) % 4)
                status = "완료" if agent["done"] else f"추론 중{pulse}"
                with col:
                    st.markdown(f"**Agent {key} · {agent['label']}**")
                    st.caption(status)
                    if agent["text"]:
                        st.markdown(agent["text"])
                    if agent["summary"]:
                        summary = agent["summary"]
                        st.caption(
                            f"판단: **{summary.get('verdict', '')}** · "
                            f"신뢰도: **{float(summary.get('confidence', 0.0) or 0.0):.0%}**"
                        )
                        warnings = summary.get("warnings") or []
                        if warnings:
                            st.caption(" / ".join(str(w) for w in warnings[:2]))
            synthesis = panel_state.get("synthesis")
            if synthesis:
                disagreement = " · 불일치 감지" if synthesis.get("disagreement") else ""
                st.success(
                    f"종합 완료: {synthesis.get('verdict', '')} "
                    f"({float(synthesis.get('confidence', 0.0) or 0.0):.0%}){disagreement}"
                )

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
    elif event == "agent_reasoning_start":
        st.session_state["_agent_panels"] = {
            "A": {"label": "검색 법령 기반", "text": "", "done": False, "summary": None, "heartbeat": 0},
            "B": {"label": "비검색 독립 검토", "text": "", "done": False, "summary": None, "heartbeat": 0},
            "synthesis": None,
        }
        for agent in data.get("agents") or []:
            key = agent.get("agent")
            if key in st.session_state["_agent_panels"]:
                st.session_state["_agent_panels"][key]["label"] = agent.get("label", "")
        _render_agent_panels()
    elif event == "agent_reasoning_delta":
        key = data.get("agent")
        if key in st.session_state["_agent_panels"]:
            existing = st.session_state["_agent_panels"][key]["text"]
            text = data.get("text", "")
            st.session_state["_agent_panels"][key]["text"] = (existing + text).strip()
        _render_agent_panels()
    elif event == "agent_reasoning_heartbeat":
        key = data.get("agent")
        if key in st.session_state["_agent_panels"] and not st.session_state["_agent_panels"][key]["done"]:
            st.session_state["_agent_panels"][key]["heartbeat"] += 1
        _render_agent_panels()
    elif event == "agent_reasoning_done":
        key = data.get("agent")
        if key in st.session_state["_agent_panels"]:
            st.session_state["_agent_panels"][key]["done"] = True
            st.session_state["_agent_panels"][key]["summary"] = data
        _render_agent_panels()
    elif event == "synthesis_done":
        st.session_state["_agent_panels"]["synthesis"] = data
        _render_agent_panels()
    elif event == "validation":
        with placeholders["validation"].container():
            st.markdown("#### 6. 인용 검증")
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
    verdict_text = html.escape(str(verdict))
    rate_text = html.escape(VERDICT_RATE.get(verdict, ""))
    color = VERDICT_HEX_COLOR.get(verdict, "#5f6368")
    st.markdown("---")
    st.markdown("#### 최종 판단")
    st.markdown(
        f"""
<style>
.tax-result-summary {{
    display: grid;
    grid-template-columns: minmax(110px, 0.75fr) minmax(150px, 1fr) minmax(90px, 0.7fr);
    gap: 8px clamp(24px, 5vw, 72px);
    align-items: start;
    max-width: 820px;
    margin: 0.35rem 0 1.25rem;
}}
.tax-result-item {{
    display: flex;
    flex-direction: column;
    gap: 0.45rem;
    min-width: 0;
}}
.tax-result-label {{
    color: #111f4d;
    font-size: 1rem;
    font-weight: 800;
    line-height: 1.25;
}}
.tax-result-value {{
    color: #111f4d;
    font-size: 1.08rem;
    font-weight: 800;
    line-height: 1.2;
    overflow-wrap: anywhere;
}}
.tax-result-verdict {{
    color: {color};
    font-size: 2.35rem;
    font-weight: 900;
    line-height: 1;
}}
@media (max-width: 640px) {{
    .tax-result-summary {{
        grid-template-columns: 1fr;
        gap: 1rem;
        max-width: none;
    }}
}}
</style>
<div class="tax-result-summary">
  <div class="tax-result-item">
    <div class="tax-result-label">판단</div>
    <div class="tax-result-verdict">{verdict_text}</div>
  </div>
  <div class="tax-result-item">
    <div class="tax-result-label">적용 세율</div>
    <div class="tax-result-value">{rate_text}</div>
  </div>
  <div class="tax-result-item">
    <div class="tax-result-label">신뢰도</div>
    <div class="tax-result-value">{confidence:.0%}</div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

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
