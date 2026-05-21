"""
어드민 페이지 — 케이스 전체 목록 + 골든셋 관리 + 통계 + 검색 디버그.
판단 로직 없음. 표시·실행·통계 전용.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import streamlit as st

from src.api.sample_cases import CATEGORY_LABELS, SAMPLE_CASES

st.set_page_config(page_title="어드민 — 양도소득세 판단", page_icon="🛠️", layout="wide")

# ── 세션 상태 ──────────────────────────────────────────────────────────────────

for key, default in [
    ("admin_result", None),
    ("admin_running_idx", None),
    ("admin_golden_result", None),
    ("admin_golden_running_idx", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ── 헬퍼 ───────────────────────────────────────────────────────────────────────

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
}

_VERDICT_COLOR = {
    "비과세": "green", "감면": "blue", "중과": "red",
    "일반과세": "orange", "단기세율": "red",
    "고가주택": "orange", "사실관계부족": "gray",
}


def _fmt_value(v) -> str:
    if isinstance(v, bool):
        return "예" if v else "아니오"
    if isinstance(v, int):
        return f"{v:,}"
    if isinstance(v, float):
        return f"{v:,.3f}".rstrip("0").rstrip(".")
    if isinstance(v, str) and len(v) == 8 and v.isdigit():
        return f"{v[:4]}-{v[4:6]}-{v[6:]}"
    if isinstance(v, dict):
        return ", ".join(f"{k}: {_fmt_value(vv)}" for k, vv in v.items())
    return str(v)


def _fact_summary(fact: dict) -> str:
    parts = []
    if "transfer_date" in fact:
        parts.append(f"양도 {_fmt_value(fact['transfer_date'])}")
    if "property_type" in fact:
        parts.append(fact["property_type"])
    if "household_house_count" in fact:
        parts.append(f"{fact['household_house_count']}주택")
    if "transfer_price" in fact:
        price = fact["transfer_price"]
        parts.append(f"{price // 100_000_000}억")
    return " · ".join(parts)


def _run_case(fact_json: dict, enable_debate: bool) -> dict:
    from src.api.chat_api import chat_turn
    return asyncio.run(chat_turn(fact_json=fact_json, enable_debate=enable_debate))


def _render_result(result: dict, expected_verdict: str | None = None) -> None:
    verdict = result["verdict"]
    color = _VERDICT_COLOR.get(verdict, "gray")

    c1, c2, c3 = st.columns([2, 2, 4])
    with c1:
        st.markdown(f"**판단: :{color}[{verdict}]**")
    with c2:
        st.metric("신뢰도", f"{result['confidence']:.0%}")
    with c3:
        if expected_verdict:
            match = verdict == expected_verdict
            badge = "✅ 정답" if match else f"❌ 오답 (예상: {expected_verdict})"
            st.markdown(f"**{badge}**")

    st.markdown(result["answer"])

    col_left, col_right = st.columns(2)
    with col_left:
        if result.get("citations"):
            with st.expander("근거 법령"):
                for c in result["citations"]:
                    st.markdown(f"- {c}")
        if result.get("missing_facts"):
            with st.expander("추가 확인 필요"):
                for m in result["missing_facts"]:
                    st.warning(m, icon="⚠️")
    with col_right:
        if result.get("chunk_ids"):
            with st.expander("검색 조문 ID"):
                st.write(result["chunk_ids"])
        if result.get("debate_record"):
            dr = result["debate_record"]
            label = {
                "blue_won": "🔵 Blue 방어 성공",
                "red_won": "🔴 Red 지적 수용",
                "no_contest": "✅ Red 이의 없음",
                "draw": "⚖️ 무승부",
            }.get(dr.get("outcome", ""), "논쟁 실행됨")
            import os as _os
            _model = _os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
            _ts = dr.get("timestamp", "")
            _ts_fmt = f"{_ts[:4]}-{_ts[5:7]}-{_ts[8:10]} {_ts[11:16]}" if len(_ts) >= 16 else _ts
            with st.expander(f"Red Team: {label}  |  {_ts_fmt}  |  {_model}"):
                meta_c1, meta_c2 = st.columns(2)
                meta_c1.caption(f"검증일시: `{_ts_fmt}`")
                meta_c2.caption(f"검증모델: `{_model}`")
                st.json(dr)


# ── 사이드바 ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("🛠️ 어드민")
    st.caption("케이스 관리 · 골든셋 · 통계 · 검색 디버그")
    st.divider()
    enable_debate = st.toggle("🔴 Red Team 검증", value=True)

    st.divider()
    import os
    _debate_model = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
    st.caption(f"검증 모델: `{_debate_model}`")


# ── 탭 레이아웃 ───────────────────────────────────────────────────────────────

st.markdown("## 🛠️ 어드민 — 양도소득세 판단")

tab_cases, tab_golden, tab_stats, tab_debug = st.tabs([
    "📋 케이스 목록",
    "🏅 골든셋",
    "📊 통계",
    "🔍 검색 디버그",
])


# ──────────────────────────────────────────────────────────────────────────────
# 탭 1: 케이스 목록
# ──────────────────────────────────────────────────────────────────────────────

with tab_cases:
    st.subheader(f"전체 케이스 — {len(SAMPLE_CASES)}개")

    # 카테고리 필터
    all_cats = sorted({c["category"] for c in SAMPLE_CASES})
    selected_cats = st.multiselect(
        "카테고리 필터",
        options=all_cats,
        default=all_cats,
        format_func=lambda c: CATEGORY_LABELS.get(c, c),
    )

    filtered = [c for c in SAMPLE_CASES if c["category"] in selected_cats]
    st.caption(f"{len(filtered)}개 표시 중")

    for idx, case in enumerate(filtered):
        orig_idx = SAMPLE_CASES.index(case)
        cat_label = CATEGORY_LABELS.get(case["category"], case["category"])
        summary = _fact_summary(case["fact_json"])

        col_cat, col_label, col_summary, col_btn = st.columns([1.2, 2.5, 3, 1])
        col_cat.markdown(cat_label)
        col_label.markdown(f"**{case['label']}**")
        col_summary.caption(summary)

        if col_btn.button("▶ 실행", key=f"run_case_{orig_idx}"):
            with st.spinner(f"분석 중: {case['label']}"):
                result = _run_case(case["fact_json"], enable_debate)
            st.session_state.admin_result = result
            st.session_state.admin_running_idx = orig_idx

        # 결과 표시 (해당 케이스만)
        if (
            st.session_state.admin_running_idx == orig_idx
            and st.session_state.admin_result is not None
        ):
            with st.expander("결과 보기", expanded=True):
                _render_result(st.session_state.admin_result)

        st.divider()


# ──────────────────────────────────────────────────────────────────────────────
# 탭 2: 골든셋
# ──────────────────────────────────────────────────────────────────────────────

with tab_golden:
    from pathlib import Path

    GOLDEN_FILE = Path("data/golden/qa_pairs.json")

    st.subheader("골든셋 — qa_pairs.json")

    if not GOLDEN_FILE.exists():
        st.warning("data/golden/qa_pairs.json 파일이 없습니다.")
    else:
        try:
            golden_pairs = json.loads(GOLDEN_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            st.error("qa_pairs.json 파싱 오류")
            golden_pairs = []

        if not golden_pairs:
            st.info("골든셋이 비어 있습니다.")
        else:
            # 요약 메트릭
            total = len(golden_pairs)
            chunk_filled = sum(1 for g in golden_pairs if g.get("gold_chunk_ids"))
            m1, m2, m3 = st.columns(3)
            m1.metric("총 케이스", total)
            m2.metric("chunk_ids 채워짐", chunk_filled)
            m3.metric("chunk_ids 비어있음", total - chunk_filled, delta=-(total - chunk_filled) if total - chunk_filled > 0 else None, delta_color="inverse")

            st.divider()

            for g_idx, golden in enumerate(golden_pairs):
                chunk_status = "✅ 채워짐" if golden.get("gold_chunk_ids") else "⚠️ 비어있음"
                exp_v = golden.get("expected_verdict", "—")
                color = _VERDICT_COLOR.get(exp_v, "gray")

                col_id, col_desc, col_verdict, col_chunk, col_btn = st.columns([1, 3, 1.2, 1.2, 1])
                col_id.caption(golden.get("id", f"#{g_idx}"))
                col_desc.markdown(golden.get("description", ""))
                col_verdict.markdown(f":{color}[{exp_v}]")
                col_chunk.caption(chunk_status)

                if col_btn.button("▶ 실행", key=f"run_golden_{g_idx}"):
                    # 골든셋은 question 기반 (fact_json 없음)
                    question = golden.get("question", "")
                    if question:
                        with st.spinner(f"분석 중: {golden.get('description', '')}"):
                            from src.api.chat_api import chat_turn
                            result = asyncio.run(chat_turn(question=question, enable_debate=enable_debate))
                        st.session_state.admin_golden_result = result
                        st.session_state.admin_golden_running_idx = g_idx

                if (
                    st.session_state.admin_golden_running_idx == g_idx
                    and st.session_state.admin_golden_result is not None
                ):
                    with st.expander("결과 보기", expanded=True):
                        _render_result(
                            st.session_state.admin_golden_result,
                            expected_verdict=golden.get("expected_verdict"),
                        )

                if golden.get("notes"):
                    st.caption(f"📎 {golden['notes']}")

                st.divider()


# ──────────────────────────────────────────────────────────────────────────────
# 탭 3: 통계
# ──────────────────────────────────────────────────────────────────────────────

with tab_stats:
    st.subheader("논쟁 & 골든셋 통계")

    col_refresh, _ = st.columns([1, 4])
    if col_refresh.button("🔄 새로고침"):
        st.rerun()

    try:
        from src.eval.debate import debate_summary
        from src.eval.golden_injector import golden_summary
        ds = debate_summary()
        gs = golden_summary()

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("총 논쟁", ds.get("total", 0))
        m2.metric("🔵 Blue 승", ds.get("blue_won", 0))
        m3.metric("🔴 Red 승", ds.get("red_won", 0))
        m4.metric("골든셋 크기", gs.get("total", 0))

        st.divider()
        st.subheader("카테고리별 SAMPLE_CASES 분포")
        from collections import Counter
        cat_counts = Counter(c["category"] for c in SAMPLE_CASES)
        rows = [
            {"카테고리": CATEGORY_LABELS.get(cat, cat), "케이스 수": cnt}
            for cat, cnt in sorted(cat_counts.items(), key=lambda x: -x[1])
        ]
        st.dataframe(rows, use_container_width=True, hide_index=True)

        st.divider()
        st.subheader("상세 통계")
        st.json({**ds, "golden": gs})

    except Exception as e:
        st.warning(f"통계 로드 실패: {e}")
        st.subheader("카테고리별 SAMPLE_CASES 분포")
        from collections import Counter
        cat_counts = Counter(c["category"] for c in SAMPLE_CASES)
        rows = [
            {"카테고리": CATEGORY_LABELS.get(cat, cat), "케이스 수": cnt}
            for cat, cnt in sorted(cat_counts.items(), key=lambda x: -x[1])
        ]
        st.dataframe(rows, use_container_width=True, hide_index=True)


# ──────────────────────────────────────────────────────────────────────────────
# 탭 4: 검색 디버그
# ──────────────────────────────────────────────────────────────────────────────

with tab_debug:
    st.subheader("법령 검색 디버그")

    debug_query = st.text_input("검색 쿼리 (한국어 자유 입력)")
    col_btn, col_k, col_rn = st.columns([1, 1, 1])
    with col_btn:
        run_debug = st.button("🔍 검색", type="primary")
    with col_k:
        top_k = st.slider("top_k (후보 수)", 5, 50, 20)
    with col_rn:
        rerank_top_n = st.slider("rerank_top_n (LLM 전달 수)", 1, 10, 5)

    if run_debug and debug_query:
        try:
            from src.rag import retrieve_tax_law
            with st.spinner("검색 중..."):
                chunks = retrieve_tax_law(debug_query, top_k=top_k, rerank_top_n=rerank_top_n)
            st.success(f"{len(chunks)}개 조문 검색됨")
            for i, c in enumerate(chunks, 1):
                with st.expander(f"[{i}] {c.law_name} 제{c.article_number}조  score={c.score:.3f}"):
                    st.text(c.full_text)
                    col_a, col_b = st.columns(2)
                    col_a.caption(f"chunk_id: `{c.id}`")
                    col_b.caption(
                        f"effective: {c.effective_date} ~ {c.expiration_date}"
                        if hasattr(c, "effective_date") else ""
                    )
        except Exception as e:
            st.error(f"검색 실패: {e}")
    elif run_debug:
        st.warning("쿼리를 입력하세요.")
