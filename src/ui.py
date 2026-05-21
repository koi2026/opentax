"""
Streamlit 채팅 UI
입력 수집 + 결과 표시만 담당. 법령 판단 로직 없음.
"""
import asyncio
import json
import random
import sys
import os

# streamlit run src/ui.py 실행 시 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st

from src.api.sample_cases import SAMPLE_CASES

# ── 사실관계 한국어 표시 ───────────────────────────────────────────────────────

_FIELD_LABELS = {
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


def _fmt_value(v) -> str:
    if isinstance(v, bool):
        return "예" if v else "아니오"
    if isinstance(v, int):
        return f"{v:,}"
    if isinstance(v, float):
        formatted = f"{v:,.3f}".rstrip("0").rstrip(".")
        return formatted
    if isinstance(v, str) and len(v) == 8 and v.isdigit():
        return f"{v[:4]}-{v[4:6]}-{v[6:]}"
    if isinstance(v, dict):
        return ", ".join(f"{k}: {_fmt_value(vv)}" for k, vv in v.items())
    return str(v)


def _render_fact_korean(fact: dict) -> None:
    for k, v in fact.items():
        label = _FIELD_LABELS.get(k, k)
        col1, col2 = st.columns([4, 5])
        col1.caption(label)
        col2.caption(f"**{_fmt_value(v)}**")

st.set_page_config(page_title="양도소득세 판단", page_icon="⚖️", layout="wide")

# ── 세션 상태 초기화 (사이드바보다 반드시 먼저) ──────────────────────────────

if "fact_json_str" not in st.session_state:
    st.session_state.fact_json_str = ""
if "current_case_label" not in st.session_state:
    st.session_state.current_case_label = ""
if "messages" not in st.session_state:
    st.session_state.messages = []
if "run_analysis" not in st.session_state:
    st.session_state.run_analysis = False

# ── 사이드바 ──────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("양도소득세 판단")
    st.caption("법령 조문 기반 — 법률 자문이 아닌 정보 제공 목적입니다.")

    st.divider()
    st.subheader("케이스 생성기")

    # ── 케이스 선택 ──────────────────────────────────────────────────────────
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("🎲 랜덤 케이스", use_container_width=True):
            pool = [c for c in SAMPLE_CASES if c["category"] != "사실관계부족"]
            case = random.choice(pool)
            st.session_state.fact_json_str = json.dumps(
                case["fact_json"], ensure_ascii=False, indent=2
            )
            st.session_state.current_case_label = case["label"]
            st.rerun()
    with col_btn2:
        if st.button("🗑️ 초기화", use_container_width=True):
            st.session_state.fact_json_str = ""
            st.session_state.current_case_label = ""
            st.rerun()

    if st.session_state.current_case_label:
        _lbl = st.session_state.current_case_label
        _short = _lbl.split("—")[0].strip() if "—" in _lbl else _lbl
        st.info(f"**요약**\n{_short}", icon="📋")

    fact_json_str = st.session_state.fact_json_str

    st.divider()

    # ── 분석 모드 ────────────────────────────────────────────────────────────
    st.subheader("분석 모드")
    query_mode = st.radio(
        "모드 선택",
        ["report", "consulting"],
        format_func=lambda x: "신고용 판단" if x == "report" else "절세 컨설팅",
        help="컨설팅 모드: 양도/증여/부담부증여 세금 비교 시뮬레이션 포함",
    )

    sim_params: dict = {}
    if query_mode == "consulting":
        st.caption("시뮬레이션 추가 정보")
        encumbrance = st.number_input(
            "채무총액 (담보대출+임대보증금, 원)",
            min_value=0,
            value=0,
            step=10_000_000,
            format="%d",
            help="부담부증여 시나리오 계산에 사용됩니다.",
        )
        gift_recipient = st.selectbox(
            "증여 대상자",
            ["직계존비속", "배우자", "기타"],
            help="증여세 공제액이 달라집니다.",
        )
        recipient_is_adult = st.checkbox("성년 자녀 (직계존비속)", value=True)
        if encumbrance > 0:
            sim_params["simulation_encumbrance"] = encumbrance
        sim_params["simulation_gift_recipient"] = gift_recipient
        sim_params["simulation_recipient_is_adult"] = recipient_is_adult

    st.divider()

    if st.button("⚡ 분석 시작", type="primary", use_container_width=True):
        st.session_state.run_analysis = True
        st.rerun()

    if st.button("💬 대화 초기화", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

    st.divider()
    enable_debate = True



# ── 채팅 메시지 표시 ──────────────────────────────────────────────────────────

st.markdown("## 양도소득세 판단 채팅")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "user" and msg.get("fact_json"):
            if msg.get("case_label"):
                st.markdown("**요약**")
                st.markdown(f"**세부내용:** {msg['case_label']}")
            _render_fact_korean(msg["fact_json"])
        else:
            st.markdown(msg["content"])
        if "extra" in msg:
            extra = msg["extra"]
            _verdict = extra.get("verdict", "")
            _conf = extra.get("confidence", 0.0)
            _citations = extra.get("citations", [])
            _missing = extra.get("missing_facts", [])
            _warnings = extra.get("warnings", [])
            _chunks = extra.get("chunk_ids", [])

            c1, c2 = st.columns(2)
            with c1:
                verdict_color = {
                    "비과세": "green", "감면": "blue", "중과": "red",
                    "일반과세": "orange", "단기세율": "red",
                    "고가주택": "orange", "사실관계부족": "gray",
                }.get(_verdict, "gray")
                st.markdown(f"**판단: :{verdict_color}[{_verdict}]**")
            with c2:
                st.metric("신뢰도", f"{_conf:.0%}")

            if _citations:
                with st.expander("근거 법령"):
                    for c in _citations:
                        st.markdown(f"- {c}")
            if _missing:
                with st.expander("추가 확인 필요"):
                    for m in _missing:
                        st.warning(m, icon="⚠️")
            if _warnings:
                with st.expander("유의사항"):
                    for w in _warnings:
                        st.info(w)
            if _chunks:
                with st.expander("검색된 조문 ID"):
                    st.write(_chunks)
            if extra.get("consulting_scenarios"):
                _render_consulting_scenarios(extra["consulting_scenarios"])


# ── 분석 실행 함수 ────────────────────────────────────────────────────────────

def _render_pipeline_result(result: dict) -> None:
    """파이프라인 결과를 채팅 말풍선 안에 렌더링."""
    verdict = result["verdict"]
    answer_text = result["answer"]
    st.markdown(answer_text)

    verdict_color = {
        "비과세": "green", "감면": "blue", "중과": "red",
        "일반과세": "orange", "단기세율": "red",
        "고가주택": "orange", "사실관계부족": "gray",
    }.get(verdict, "gray")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"**판단: :{verdict_color}[{verdict}]**")
    with c2:
        st.metric("신뢰도", f"{result['confidence']:.0%}")

    if result.get("citations"):
        with st.expander("근거 법령"):
            for c in result["citations"]:
                st.markdown(f"- {c}")
    if result.get("missing_facts"):
        with st.expander("추가 확인 필요"):
            for m in result["missing_facts"]:
                st.warning(m, icon="⚠️")
    if result.get("warnings"):
        with st.expander("유의사항"):
            for w in result["warnings"]:
                st.info(w)
    if result.get("chunk_ids"):
        with st.expander("검색된 조문 ID"):
            st.write(result["chunk_ids"])
    if result.get("debate_record"):
        dr = result["debate_record"]
        outcome_label = {
            "blue_won": "🔵 Blue 방어 성공",
            "red_won": "🔴 Red 지적 수용 — 판단 수정됨",
            "no_contest": "✅ Red 이의 없음",
            "draw": "⚖️ 논쟁 무승부",
        }.get(dr.get("outcome", ""), "논쟁 실행됨")
        with st.expander(f"Red Team 검증 결과: {outcome_label}"):
            st.write(dr)
    if result.get("consulting_scenarios"):
        _render_consulting_scenarios(result["consulting_scenarios"])


def _render_consulting_scenarios(scenarios: list) -> None:
    """컨설팅 시나리오 비교표 렌더링."""
    # 마지막 항목이 요약(optimal_type 포함)인 경우 분리
    summary: dict = {}
    items: list = []
    for s in scenarios:
        if "optimal_type" in s:
            summary = s
        else:
            items.append(s)

    if not items:
        return

    st.divider()
    st.subheader("절세 시나리오 비교")

    if summary:
        opt = summary.get("optimal_type", "")
        saving = summary.get("optimal_saving", 0)
        st.success(
            f"최적 방안: **{opt}** — 양도 대비 **{saving:,}원** 절세\n\n"
            f"{summary.get('recommendation_reason', '')}",
        )
        if summary.get("warnings"):
            for w in summary["warnings"]:
                st.warning(w)

    cols = st.columns(len(items))
    _COLOR = {"양도": "#FF6B6B", "증여": "#4ECDC4", "부담부증여": "#45B7D1"}
    for col, s in zip(cols, items):
        with col:
            scenario_type = s.get("scenario_type", "")
            color = _COLOR.get(scenario_type, "#888")
            total = s.get("total_tax", 0)
            rate = s.get("effective_rate", 0.0)
            is_calc = s.get("is_calculable", True)

            st.markdown(
                f"<div style='border-left:4px solid {color}; padding-left:8px;'>"
                f"<strong>{scenario_type}</strong><br/>"
                f"<span style='font-size:0.85em;'>{s.get('description','')}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )
            if is_calc:
                st.metric("총 세금", f"{total:,}원", delta=f"실효세율 {rate:.1%}", delta_color="off")
                d = s.get("detail") or {}
                detail_lines = []
                if s.get("transfer_income_tax"):
                    detail_lines.append(f"양도소득세: {s['transfer_income_tax']:,}원")
                if s.get("gift_tax"):
                    detail_lines.append(f"증여세: {s['gift_tax']:,}원")
                if s.get("local_income_tax"):
                    detail_lines.append(f"지방소득세: {s['local_income_tax']:,}원")
                if s.get("acquisition_tax_estimate"):
                    detail_lines.append(f"취득세(추산): {s['acquisition_tax_estimate']:,}원")
                if detail_lines:
                    with st.expander("세부 내역"):
                        for line in detail_lines:
                            st.caption(line)
                        if d.get("rate_type"):
                            st.caption(f"세율유형: {d['rate_type']}")
                        if d.get("ltd_rate"):
                            st.caption(f"장특공율: {d['ltd_rate']:.0%}")
            else:
                st.info("계산 불가 — 전문가 확인 필요")

            if s.get("notes"):
                with st.expander("유의사항"):
                    for n in s["notes"]:
                        st.caption(f"* {n}")

    if summary.get("expert_review_needed"):
        st.info(
            "이 시뮬레이션은 참고용입니다. 실제 절세 전략은 세무사와 함께 구체적인 사실관계를 기반으로 수립하세요.",
        )


async def _run_analysis_async(user_text: str, parsed_fact: dict | None) -> None:
    """분석 실행 (비동기 스트리밍 버전)."""
    case_label = st.session_state.current_case_label if parsed_fact else None
    msg_entry: dict = {"role": "user", "content": user_text}
    if parsed_fact:
        msg_entry["fact_json"] = parsed_fact
        msg_entry["case_label"] = case_label
    st.session_state.messages.append(msg_entry)
    
    with st.chat_message("user"):
        if parsed_fact:
            if case_label:
                st.markdown("**요약**")
                st.markdown(f"**세부내용:** {case_label}")
            _render_fact_korean(parsed_fact)
        else:
            st.markdown(user_text)

    with st.chat_message("assistant"):
        status_placeholder = st.status("🚀 분석 엔진 가동 중...", expanded=True)
        reasoning_placeholder = st.empty()
        reasoning_text = ""
        
        from src.api.chat_api import chat_turn_stream
        
        # 컨설팅 파라미터를 fact_json에 병합
        fact_with_sim = {**(parsed_fact or {}), **sim_params} if parsed_fact else parsed_fact
        
        result = None
        async for item in chat_turn_stream(
            fact_json=fact_with_sim,
            question=user_text if not parsed_fact else None,
            enable_debate=enable_debate,
            query_mode=query_mode,
        ):
            if isinstance(item, str):
                if item.startswith("PROGRESS:"):
                    status_placeholder.update(label=item[9:])
                else:
                    # Claude의 추론 과정 스트리밍
                    if not reasoning_text:
                        status_placeholder.update(label="🧠 AI 법령 해석 중...", expanded=False)
                    reasoning_text += item
                    reasoning_placeholder.markdown(f"**AI 사고 과정:**\n\n{reasoning_text}▌")
            else:
                result = item
        
        if result:
            reasoning_placeholder.empty() # 사고 과정은 지우고 최종 결과로 대체 (또는 expander에 보존)
            if reasoning_text:
                with st.expander("AI 사고 과정 (상세)"):
                    st.markdown(reasoning_text)
            
            status_placeholder.update(label="✅ 분석 완료", state="complete", expanded=False)
            _render_pipeline_result(result)
            
            extra = {k: result[k] for k in ("verdict", "confidence", "citations", "missing_facts", "warnings", "chunk_ids")}
            extra["consulting_scenarios"] = result.get("consulting_scenarios")
            st.session_state.messages.append({
                "role": "assistant",
                "content": result["answer"],
                "extra": extra,
            })


def _run_analysis(user_text: str, parsed_fact: dict | None) -> None:
    """분석 실행 래퍼 (asyncio.run 사용)."""
    asyncio.run(_run_analysis_async(user_text, parsed_fact))



# ── 사이드바 분석 버튼 트리거 ────────────────────────────────────────────────

if st.session_state.run_analysis:
    st.session_state.run_analysis = False
    parsed_fact = None
    if fact_json_str.strip():
        try:
            parsed_fact = json.loads(fact_json_str)
        except json.JSONDecodeError:
            parsed_fact = None
    if parsed_fact:
        label = st.session_state.current_case_label or "사실관계 분석"
        _run_analysis(label, parsed_fact)
    else:
        st.warning("먼저 케이스를 생성해주세요.")


# ── 채팅 입력 ─────────────────────────────────────────────────────────────────

user_input = st.chat_input("추가 질문을 입력하거나, 케이스 선택 후 '⚡ 분석 시작'을 클릭하세요.")

if user_input:
    parsed_fact = None
    if fact_json_str.strip():
        try:
            parsed_fact = json.loads(fact_json_str)
        except json.JSONDecodeError:
            parsed_fact = None
    _run_analysis(user_input, parsed_fact)
