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


def _fmt_optional(v) -> str:
    return "미입력" if v is None else _fmt_value(v)


def _short_chunk_id(chunk_id: str) -> str:
    return chunk_id if len(chunk_id) <= 28 else f"{chunk_id[:25]}..."


def _render_realtime_event(event: dict, placeholders: dict) -> None:
    name = event.get("event")
    data = event.get("data") or {}

    if name == "fact_summary":
        with placeholders["fact"].container():
            st.markdown("#### 1. 입력 이해")
            cols = st.columns(3)
            cols[0].caption(f"양도일: **{_fmt_optional(data.get('transfer_date'))}**")
            cols[1].caption(f"취득일: **{_fmt_optional(data.get('acquisition_date'))}**")
            cols[2].caption(f"보유기간: **{_fmt_optional(data.get('holding_years'))}년**")
            cols = st.columns(3)
            cols[0].caption(f"부동산: **{_fmt_optional(data.get('property_type'))}**")
            cols[1].caption(f"주택 수: **{_fmt_optional(data.get('household_house_count'))}주택**")
            cols[2].caption(f"양도가액: **{_fmt_optional(data.get('transfer_price'))}원**")
            st.caption(
                "조정지역: "
                f"취득시 **{_fmt_optional(data.get('adjustment_area_at_acquisition'))}**, "
                f"양도시 **{_fmt_optional(data.get('adjustment_area_at_transfer'))}**"
            )

    elif name == "fact_check":
        missing = data.get("missing_facts") or []
        flags = data.get("danger_flags") or []
        with placeholders["fact_check"].container():
            st.markdown("#### 2. 사실관계 점검")
            if data.get("can_proceed"):
                st.success("필수 사실관계 확인 완료")
            else:
                st.warning("필수 사실관계가 부족해 판단을 중단합니다.")
            if flags:
                st.caption("탐지된 쟁점: " + ", ".join(f"`{flag}`" for flag in flags))
            else:
                st.caption("탐지된 고위험 쟁점 없음")
            for item in missing:
                st.warning(item, icon="⚠️")

    elif name == "query_enrichment":
        keywords = data.get("keywords") or []
        with placeholders["query"].container():
            st.markdown("#### 3. 검색 쟁점")
            if keywords:
                st.table([
                    {"쟁점": item.get("flag", ""), "검색 보강": item.get("keyword", "")}
                    for item in keywords
                ])
            else:
                st.caption("추가 검색 보강 없이 기본 사실관계로 검색합니다.")

    elif name == "retrieved_chunks":
        chunks = data.get("chunks") or []
        with placeholders["chunks"].container():
            st.markdown("#### 4. 검색된 근거 후보")
            if chunks:
                st.table([
                    {
                        "조문": c.get("article", ""),
                        "출처": c.get("source_label", ""),
                        "chunk_id": _short_chunk_id(c.get("chunk_id", "")),
                        "score": c.get("score", 0.0),
                    }
                    for c in chunks
                ])
            else:
                st.warning("검색된 근거 후보가 없습니다.")

    elif name == "validation":
        with placeholders["validation"].container():
            st.markdown("#### 5. 인용 검증")
            if data.get("phantom_count", 0):
                st.warning(
                    f"검색 결과에 없는 인용 {data.get('phantom_count')}건을 감지했습니다. "
                    f"신뢰도 {data.get('confidence_before'):.2f} → {data.get('confidence_after'):.2f}"
                )
            else:
                st.success(
                    f"검색된 {data.get('retrieved_count')}개 후보 기준으로 "
                    f"인용 {data.get('citation_count')}건 검증 완료"
                )

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

    if st.button("⚡ 분석 시작", type="primary", use_container_width=True):
        st.session_state.run_analysis = True
        st.rerun()

    if st.button("💬 대화 초기화", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

    st.divider()



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
            _render_pipeline_result(msg["extra"])


# ── 분석 실행 함수 ────────────────────────────────────────────────────────────

_VERDICT_COLOR = {
    "비과세": "green", "감면": "blue", "중과": "red",
    "일반과세": "orange", "단기세율": "red",
    "고가주택": "orange", "사실관계부족": "gray", "전문가검토": "gray",
}

_VERDICT_RATE = {
    "비과세":       "세금 없음",
    "감면":         "감면 세율 적용",
    "중과":         "기본세율 + 20~30%p 중과",
    "일반과세":     "기본세율 6~45%",
    "단기세율":     "단기세율 60~70%",
    "고가주택":     "12억 초과분 기본세율",
    "사실관계부족": "추가 확인 필요",
    "전문가검토":   "전문가 검토 필요",
}

_CONFIDENCE_LABEL = {
    (0.0, 0.5): ("⚠️ 검토 권장", "orange"),
    (0.5, 0.75): ("◑ 보통", "gray"),
    (0.75, 1.01): ("● 높음", "green"),
}


def _confidence_label(score: float) -> tuple[str, str]:
    for (lo, hi), (label, color) in _CONFIDENCE_LABEL.items():
        if lo <= score < hi:
            return label, color
    return "—", "gray"


def _render_debate_section(dr: dict) -> None:
    """2단계: Red Team 검증 결과 구조화 렌더링."""
    outcome = dr.get("outcome", "")
    if not outcome or dr.get("error"):
        return

    outcome_cfg = {
        "blue_won":   ("🔵", "Blue 방어 성공",      "Blue의 원판단이 유지됐습니다."),
        "red_won":    ("🔴", "Red 지적 수용",        "판단이 수정됐습니다."),
        "no_contest": ("✅", "Red 이의 없음",        "Red Team이 이의를 제기하지 않았습니다."),
        "draw":       ("⚖️", "판단 보류 — 전문가 검토 권장", ""),
    }
    icon, title, subtitle = outcome_cfg.get(outcome, ("❓", outcome, ""))

    st.markdown(f"#### {icon} 2단계: Red Team 검증 — {title}")
    if subtitle:
        st.caption(subtitle)

    challenge_type = dr.get("challenge_type", "")
    challenge_text = dr.get("challenge_text", "")
    defense_text = dr.get("defense_text", "")
    new_citations = dr.get("new_citations") or []

    if outcome == "no_contest":
        st.success("1차 판단이 법령 근거 검토를 통과했습니다.")
        return

    col_r, col_b = st.columns(2)
    with col_r:
        st.markdown("**🔴 Red Team 반박**")
        if challenge_type:
            st.caption(f"반박 유형: `{challenge_type}`")
        st.markdown(challenge_text or "_(반박 내용 없음)_")

    with col_b:
        st.markdown("**🔵 Blue Team 방어**")
        st.markdown(defense_text or "_(방어 내용 없음)_")
        if new_citations:
            st.caption("추가 인용 법령:")
            for c in new_citations:
                st.markdown(f"  - {c}")

    if outcome == "red_won" and dr.get("revised_verdict"):
        st.info(f"판단 수정: **{dr['revised_verdict']}** 으로 변경됐습니다.")


def _render_pipeline_result(result: dict) -> None:
    """최종 판단 결과 렌더링."""
    verdict = result["verdict"]
    answer_text = result["answer"]
    confidence = result.get("confidence", 0.0)
    conf_label, conf_color = _confidence_label(confidence)

    # ── 2단계: Red Team ───────────────────────────────────────────────────────
    if result.get("debate_record") and not result["debate_record"].get("error"):
        st.markdown("")
        _render_debate_section(result["debate_record"])

    # ── 최종 판단 ─────────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### ⚖️ 최종 판단")

    verdict_color = _VERDICT_COLOR.get(verdict, "gray")
    rate_text = _VERDICT_RATE.get(verdict, "")

    col_v, col_r, col_c = st.columns([2, 3, 2])
    with col_v:
        st.markdown(f"**판단**")
        st.markdown(f"## :{verdict_color}[{verdict}]")
    with col_r:
        st.markdown(f"**적용 세율**")
        st.markdown(f"**{rate_text}**")
    with col_c:
        st.markdown(f"**신뢰도**")
        st.markdown(f":{conf_color}[{conf_label}]")

    with st.expander("판단 근거 설명", expanded=True):
        st.markdown(answer_text)
        if result.get("missing_facts"):
            st.divider()
            for m in result["missing_facts"]:
                st.warning(m, icon="⚠️")

    if result.get("citations"):
        with st.expander("📋 근거 법령", expanded=True):
            for c in result["citations"]:
                st.markdown(f"- {c}")

    warnings = [w for w in (result.get("warnings") or []) if not w.startswith("[Red Team")]
    if warnings:
        with st.expander("⚠️ 유의사항"):
            for w in warnings:
                st.info(w)

    if result.get("as_of_date"):
        d = str(result["as_of_date"])
        if len(d) == 8:
            d = f"{d[:4]}-{d[4:6]}-{d[6:]}"
        st.caption(f"적용 법령 기준일: {d}  |  본 결과는 정보 제공 목적이며 세무 자문이 아닙니다.")



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
        realtime_placeholders = {
            "fact": st.empty(),
            "fact_check": st.empty(),
            "query": st.empty(),
            "chunks": st.empty(),
            "validation": st.empty(),
            "reasoning": st.empty(),
        }
        
        from src.api.chat_api import chat_turn_stream

        result = None
        showed_reasoning_status = False
        async for item in chat_turn_stream(
            fact_json=parsed_fact,
            question=user_text if not parsed_fact else None,
            enable_debate=False,
            query_mode="report",
        ):
            if isinstance(item, str):
                if item.startswith("PROGRESS:"):
                    status_placeholder.update(label=item[9:])
                else:
                    if not showed_reasoning_status:
                        showed_reasoning_status = True
                        status_placeholder.update(label="AI 판단 생성 중...", expanded=False)
                    reasoning_text += item
                    with realtime_placeholders["reasoning"].container():
                        st.markdown("#### 6. AI 추론 과정")
                        st.markdown(reasoning_text + "▌")
            elif isinstance(item, dict) and "event" in item:
                _render_realtime_event(item, realtime_placeholders)
            else:
                result = item
        
        if result:
            reasoning_placeholder.empty()
            if reasoning_text:
                with realtime_placeholders["reasoning"].container():
                    st.markdown("#### 6. AI 추론 과정")
                    st.markdown(reasoning_text)
            
            status_placeholder.update(label="✅ 분석 완료", state="complete", expanded=False)
            _render_pipeline_result(result)
            
            extra = {k: result[k] for k in ("verdict", "confidence", "citations", "missing_facts", "warnings", "chunk_ids")}
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
