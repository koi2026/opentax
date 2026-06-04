"""Streamlit UI. Input/display only; all analysis goes through the API server."""
from __future__ import annotations

import json
import html
import importlib
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import requests
import streamlit as st

import src.ui.chrome as ui_chrome
from src.api.sample_cases import SAMPLE_CASES
from src.ui.api_client import stream_chat
from src.ui.renderers import render_fact_korean, render_pipeline_result, render_realtime_event


ui_chrome = importlib.reload(ui_chrome)
st.set_page_config(page_title="opentax", page_icon="o", layout="wide")
ui_chrome.apply_chatgpt_style()

for key, default in [
    ("fact_json_str", ""),
    ("current_case_label", ""),
    ("messages", []),
    ("run_analysis", False),
]:
    if key not in st.session_state:
        st.session_state[key] = default

with st.sidebar:
    ui_chrome.render_sidebar_nav("chat")

    with st.container(key="case_generator_block"):
        st.markdown('<div class="opentax-sidebar-label">케이스 생성기</div>', unsafe_allow_html=True)

        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("랜덤 케이스", use_container_width=True):
                pool = [c for c in SAMPLE_CASES if c["category"] != "사실관계부족"]
                case = random.choice(pool)
                st.session_state.fact_json_str = json.dumps(case["fact_json"], ensure_ascii=False, indent=2)
                st.session_state.current_case_label = case["label"]
                st.rerun()
        with col_btn2:
            if st.button("초기화", use_container_width=True):
                st.session_state.fact_json_str = ""
                st.session_state.current_case_label = ""
                st.rerun()

        if st.session_state.current_case_label:
            label = st.session_state.current_case_label
            summary = label.split("—")[0].strip() if "—" in label else label
            st.markdown(
                f'<div class="opentax-case-summary"><span>요약</span> {html.escape(summary)}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown('<div class="opentax-case-summary-slot"></div>', unsafe_allow_html=True)

        fact_json_str = st.session_state.fact_json_str
        st.divider()

        if st.button("분석 시작", type="primary", use_container_width=True):
            st.session_state.run_analysis = True
            st.rerun()

        if st.button("대화 초기화", use_container_width=True):
            st.session_state.messages = []
            st.rerun()

is_empty_chat = not st.session_state.messages and not st.session_state.run_analysis

if is_empty_chat:
    st.markdown(
        """
<div class="opentax-empty-chat"></div>
<h1 class="opentax-empty-chat-title">법령과 사실관계를 기반으로 양도소득세를 판단합니다.</h1>
""",
        unsafe_allow_html=True,
    )
else:
    st.markdown("## 법령과 사실관계를 기반으로 양도소득세를 판단합니다.")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "user" and msg.get("fact_json"):
            if msg.get("case_label"):
                st.markdown("**요약**")
                st.markdown(f"**세부내용:** {msg['case_label']}")
            render_fact_korean(msg["fact_json"])
        else:
            st.markdown(msg["content"])
        if "extra" in msg:
            render_pipeline_result(msg["extra"])


def _run_analysis(user_text: str, parsed_fact: dict | None) -> None:
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
            render_fact_korean(parsed_fact)
        else:
            st.markdown(user_text)

    with st.chat_message("assistant"):
        status_placeholder = st.status("분석 엔진 가동 중...", expanded=True)
        realtime_placeholders = {
            "fact": st.empty(),
            "fact_check": st.empty(),
            "query": st.empty(),
            "chunks": st.empty(),
            "agents": st.empty(),
            "validation": st.empty(),
            "reasoning": st.empty(),
        }
        reasoning_text = ""
        result = None

        try:
            for item in stream_chat(
                fact_json=parsed_fact,
                question=user_text if not parsed_fact else None,
                enable_debate=False,
                query_mode="report",
            ):
                kind = item.get("type")
                if kind == "progress":
                    status_placeholder.update(label=item.get("data", "진행 중..."))
                elif kind == "token":
                    reasoning_text += item.get("data", "")
                    with realtime_placeholders["reasoning"].container():
                        st.markdown("#### 6. AI 추론 과정")
                        st.markdown(reasoning_text + "▌")
                elif kind == "event":
                    render_realtime_event(item.get("event", ""), item.get("data") or {}, realtime_placeholders)
                elif kind == "result":
                    result = item.get("data")
        except requests.RequestException as exc:
            status_placeholder.update(label="API 서버 호출 실패", state="error", expanded=True)
            st.error(f"API 서버에 연결할 수 없습니다: {exc}")
            return

        if result:
            if reasoning_text:
                with realtime_placeholders["reasoning"].container():
                    st.markdown("#### 6. AI 추론 과정")
                    st.markdown(reasoning_text)
            status_placeholder.update(label="분석 완료", state="complete", expanded=False)
            render_pipeline_result(result)
            st.session_state.messages.append({
                "role": "assistant",
                "content": result.get("answer", ""),
                "extra": result,
            })


if st.session_state.run_analysis:
    st.session_state.run_analysis = False
    parsed_fact = None
    if fact_json_str.strip():
        try:
            parsed_fact = json.loads(fact_json_str)
        except json.JSONDecodeError:
            parsed_fact = None
    if parsed_fact:
        _run_analysis(st.session_state.current_case_label or "사실관계 분석", parsed_fact)
    else:
        st.warning("먼저 케이스를 생성해주세요.")

user_input = st.chat_input("추가 질문을 입력하거나, 케이스 선택 후 '분석 시작'을 클릭하세요.")
if user_input:
    parsed_fact = None
    if fact_json_str.strip():
        try:
            parsed_fact = json.loads(fact_json_str)
        except json.JSONDecodeError:
            parsed_fact = None
    _run_analysis(user_input, parsed_fact)
