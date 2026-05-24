"""
어드민 페이지 — 총괄 대시보드 / 법령 데이터 / 지역 데이터 / 케이스 / 골든셋 / 통계 / 디버그.
판단 로직 없음. 표시·실행·통계 전용.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import streamlit as st

from src.api.sample_cases import CATEGORY_LABELS, SAMPLE_CASES

st.set_page_config(page_title="어드민", page_icon="🛠️", layout="wide")

# ── 세션 상태 ──────────────────────────────────────────────────────────────────

for key, default in [
    ("admin_result", None),
    ("admin_running_idx", None),
    ("admin_golden_result", None),
    ("admin_golden_running_idx", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ── 헬퍼: 공통 ────────────────────────────────────────────────────────────────

_ROOT = Path(__file__).parent.parent.parent

_VERDICT_COLOR = {
    "비과세": "green", "감면": "blue", "중과": "red",
    "일반과세": "orange", "단기세율": "red",
    "고가주택": "orange", "사실관계부족": "gray",
}

_LAW_CATEGORY_LABEL = {
    "법률": "법률", "시행령": "시행령", "시행규칙": "시행규칙",
    "규정": "규정", "": "—",
}


def _fmt_mtime(path: Path) -> str:
    if not path.exists():
        return "—"
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")


def _fmt_date8(v) -> str:
    s = str(int(v)) if v else ""
    if len(s) == 8:
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    return s or "—"


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
            _model = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
            _ts = dr.get("timestamp", "")
            _ts_fmt = f"{_ts[:4]}-{_ts[5:7]}-{_ts[8:10]} {_ts[11:16]}" if len(_ts) >= 16 else _ts
            with st.expander(f"Red Team: {label}  |  {_ts_fmt}  |  {_model}"):
                st.json(dr)


# ── 헬퍼: 데이터 로드 ─────────────────────────────────────────────────────────

def _load_law_inventory() -> list[dict]:
    """all_chunks.json → 법령별 요약 목록."""
    p = _ROOT / "data" / "processed" / "all_chunks.json"
    if not p.exists():
        return []
    try:
        chunks = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(chunks, list):
        return []

    agg: dict[str, dict] = defaultdict(lambda: {
        "count": 0, "max_eff": 0, "mst": "", "category": "",
        "article_cnt": 0, "buchik_cnt": 0,
    })
    for c in chunks:
        if not isinstance(c, dict):
            continue
        law = c.get("law_name", "?")
        agg[law]["count"] += 1
        agg[law]["mst"] = c.get("version_mst", "")
        agg[law]["category"] = c.get("law_category", "")
        art_type = c.get("article_type", "")
        if art_type == "부칙":
            agg[law]["buchik_cnt"] += 1
        else:
            agg[law]["article_cnt"] += 1
        try:
            eff = int(c.get("effective_date", 0) or 0)
            if eff > agg[law]["max_eff"]:
                agg[law]["max_eff"] = eff
        except Exception:
            pass

    mtime_str = _fmt_mtime(p)
    rows = []
    for law, info in sorted(agg.items(), key=lambda x: -x[1]["count"]):
        rows.append({
            "법령명": law,
            "분류": info["category"] or "—",
            "MST": info["mst"],
            "총 청크": info["count"],
            "본칙": info["article_cnt"],
            "부칙": info["buchik_cnt"],
            "최신 시행일": _fmt_date8(info["max_eff"]),
            "마지막 수집": mtime_str,
            "출처": "law.go.kr DRF",
        })
    return rows


def _load_area_summary() -> tuple[int, int, str]:
    """(현행 수, 전체 수, 마지막수정일)"""
    p = _ROOT / "data" / "area_designations" / "manual_table.json"
    if not p.exists():
        return 0, 0, "—"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return 0, 0, "—"
    active = sum(1 for r in data if not r.get("released_at"))
    return active, len(data), _fmt_mtime(p)


def _load_golden_summary() -> tuple[int, str]:
    p = _ROOT / "data" / "golden" / "qa_pairs.json"
    if not p.exists():
        return 0, "—"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return len(data), _fmt_mtime(p)
    except Exception:
        return 0, "—"


def _load_debate_summary() -> tuple[int, str]:
    d = _ROOT / "data" / "debates"
    if not d.exists():
        return 0, "—"
    files = list(d.glob("*.json"))
    if not files:
        return 0, "—"
    latest = max(files, key=lambda f: f.stat().st_mtime)
    return len(files), _fmt_mtime(latest)


# ── 사이드바 ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("🛠️ 어드민")
    st.divider()
    enable_debate = st.toggle("🔴 Red Team 검증", value=True)
    st.divider()
    _debate_model = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
    st.caption(f"모델: `{_debate_model}`")
    pinecone_idx = os.getenv("PINECONE_INDEX_NAME", "tax-rag")
    pinecone_ns = os.getenv("PINECONE_NAMESPACE", "tax-law")
    st.caption(f"Pinecone: `{pinecone_idx}` / `{pinecone_ns}`")

# ── 탭 ────────────────────────────────────────────────────────────────────────

st.markdown("## 🛠️ 어드민")

(
    tab_dashboard,
    tab_laws,
    tab_areas,
    tab_cases,
    tab_golden,
    tab_stats,
    tab_monitor,
    tab_debug,
) = st.tabs([
    "📊 대시보드",
    "⚖️ 법령 데이터",
    "🗺️ 지역 데이터",
    "📋 케이스 목록",
    "🏅 골든셋",
    "📈 통계",
    "🔔 법령 모니터링",
    "🔍 디버그",
])


# ══════════════════════════════════════════════════════════════════════════════
# 탭 1: 총괄 대시보드
# ══════════════════════════════════════════════════════════════════════════════

with tab_dashboard:
    law_rows = _load_law_inventory()
    area_active, area_total, area_mtime = _load_area_summary()
    golden_cnt, golden_mtime = _load_golden_summary()
    debate_cnt, debate_mtime = _load_debate_summary()

    total_chunks = sum(r["총 청크"] for r in law_rows)
    all_chunks_mtime = _fmt_mtime(_ROOT / "data" / "processed" / "all_chunks.json")

    # ── 핵심 메트릭 ──────────────────────────────────────────────────────────
    st.subheader("현재 반영 중인 데이터")
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("법령 수", f"{len(law_rows)}개")
    m2.metric("총 청크 (Pinecone)", f"{total_chunks:,}")
    m3.metric("현행 규제지역", f"{area_active}건")
    m4.metric("골든셋", f"{golden_cnt}건")
    m5.metric("누적 논쟁", f"{debate_cnt}건")

    st.divider()

    # ── 데이터 인벤토리 ───────────────────────────────────────────────────────
    st.subheader("데이터 인벤토리 — 출처 · 수량 · 최종 수집")

    inventory = [
        {
            "데이터": "법령 조문",
            "출처": "law.go.kr DRF API",
            "수집 방식": "수동 실행 (`python -m src.ingestion.collect`)",
            "마지막 수집": all_chunks_mtime,
            "현황": f"{len(law_rows)}개 법령 / {total_chunks:,}청크",
            "상태": "✅ 수집됨" if law_rows else "❌ 없음",
        },
        {
            "데이터": "Pinecone 벡터 인덱스",
            "출처": f"Pinecone `{pinecone_idx}` / `{pinecone_ns}`",
            "수집 방식": "수동 실행 (`python -m src.ingestion.embed`)",
            "마지막 수집": all_chunks_mtime,
            "현황": f"{total_chunks:,}청크 (embed 기준)",
            "상태": "✅ 수집됨" if law_rows else "❌ 없음",
        },
        {
            "데이터": "규제지역 현황",
            "출처": "수동 관리 (manual_table.json)",
            "수집 방식": "어드민 직접 편집 또는 제안서 승인",
            "마지막 수집": area_mtime,
            "현황": f"현행 {area_active}건 / 전체 {area_total}건",
            "상태": "✅ 관리 중" if area_total > 0 else "❌ 없음",
        },
        {
            "데이터": "골든셋 QA",
            "출처": "Red-Blue 논쟁 자동 생성",
            "수집 방식": "debate.py → golden_injector.py 자동 누적",
            "마지막 수집": golden_mtime,
            "현황": f"{golden_cnt}건",
            "상태": "✅ 운영 중" if golden_cnt > 0 else "⚠️ 비어있음",
        },
        {
            "데이터": "Red-Blue 논쟁 기록",
            "출처": "내부 논쟁 엔진",
            "수집 방식": "신뢰도 < 0.8 또는 danger_flags ≥ 2 시 자동 실행",
            "마지막 수집": debate_mtime,
            "현황": f"{debate_cnt}건",
            "상태": "✅ 운영 중" if debate_cnt > 0 else "⚠️ 없음",
        },
    ]

    import pandas as pd
    inv_df = pd.DataFrame(inventory)
    st.dataframe(
        inv_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "데이터": st.column_config.TextColumn("데이터", width="medium"),
            "출처": st.column_config.TextColumn("출처", width="large"),
            "수집 방식": st.column_config.TextColumn("수집 방식", width="large"),
            "마지막 수집": st.column_config.TextColumn("마지막 수집", width="medium"),
            "현황": st.column_config.TextColumn("현황", width="medium"),
            "상태": st.column_config.TextColumn("상태", width="small"),
        },
    )

    st.divider()

    # ── 법령 요약 (간략) ──────────────────────────────────────────────────────
    st.subheader("법령별 청크 수")
    if law_rows:
        col_chart, col_table = st.columns([1, 1])
        with col_chart:
            chart_data = pd.DataFrame({
                "법령명": [r["법령명"] for r in law_rows],
                "청크": [r["총 청크"] for r in law_rows],
            }).set_index("법령명")
            st.bar_chart(chart_data)
        with col_table:
            quick_df = pd.DataFrame([
                {"법령명": r["법령명"], "분류": r["분류"], "청크": r["총 청크"], "최신시행": r["최신 시행일"]}
                for r in law_rows
            ])
            st.dataframe(quick_df, use_container_width=True, hide_index=True)
    else:
        st.info("data/processed/all_chunks.json 파일이 없습니다. `python -m src.ingestion.collect` 후 `embed`를 실행하세요.")


# ══════════════════════════════════════════════════════════════════════════════
# 탭 2: 법령 데이터
# ══════════════════════════════════════════════════════════════════════════════

with tab_laws:
    all_chunks_path = _ROOT / "data" / "processed" / "all_chunks.json"

    # ── 출처 배너 ──────────────────────────────────────────────────────────────
    c_src1, c_src2, c_src3 = st.columns(3)
    c_src1.info("**출처** law.go.kr DRF API")
    c_src2.info(f"**마지막 수집** {_fmt_mtime(all_chunks_path)}")
    c_src3.info(f"**수집 명령** `python -m src.ingestion.collect`")

    st.divider()

    law_rows = _load_law_inventory()
    if not law_rows:
        st.warning("law 데이터가 없습니다. ingestion을 먼저 실행하세요.")
    else:
        total = sum(r["총 청크"] for r in law_rows)
        m1, m2, m3 = st.columns(3)
        m1.metric("수집된 법령", f"{len(law_rows)}개")
        m2.metric("총 조문 청크", f"{total:,}")
        m3.metric("부칙 포함", f"{sum(r['부칙'] for r in law_rows):,}")

        st.subheader("법령별 상세")

        # 분류 필터
        cats = sorted({r["분류"] for r in law_rows})
        sel_cats = st.multiselect("분류 필터", cats, default=cats, key="law_cat_filter")
        filtered_laws = [r for r in law_rows if r["분류"] in sel_cats]

        import pandas as pd
        df = pd.DataFrame(filtered_laws)
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "법령명": st.column_config.TextColumn("법령명", width="large"),
                "분류": st.column_config.TextColumn("분류", width="small"),
                "MST": st.column_config.TextColumn("MST", width="small"),
                "총 청크": st.column_config.NumberColumn("총 청크", format="%d"),
                "본칙": st.column_config.NumberColumn("본칙", format="%d"),
                "부칙": st.column_config.NumberColumn("부칙", format="%d"),
                "최신 시행일": st.column_config.TextColumn("최신 시행일", width="medium"),
                "마지막 수집": st.column_config.TextColumn("마지막 수집", width="medium"),
                "출처": st.column_config.TextColumn("출처", width="medium"),
            },
        )

        st.divider()
        st.subheader("데이터 갱신")
        st.code("python -m src.ingestion.collect   # law.go.kr 재수집\npython -m src.ingestion.embed     # Pinecone 재인덱싱")
        st.caption("⚠️ reindex 시 기존 벡터가 덮어쓰여집니다. 운영 중 실행은 주의하세요.")


# ══════════════════════════════════════════════════════════════════════════════
# 탭 3: 지역 데이터
# ══════════════════════════════════════════════════════════════════════════════

with tab_areas:
    REG_FILE = _ROOT / "data" / "area_designations" / "manual_table.json"

    _ALL_AREA_TYPES = ["조정대상지역", "투기과열지구", "투기지역", "토지거래허가구역"]
    _TYPE_COLOR_CSS = {
        "조정대상지역":    "#FF8C00",
        "투기과열지구":    "#DC3232",
        "투기지역":        "#9B59B6",
        "토지거래허가구역": "#1E90FF",
    }

    def _badge(area_type: str) -> str:
        color = _TYPE_COLOR_CSS.get(area_type, "#888")
        return (
            f'<span style="background:{color};color:#fff;padding:2px 8px;'
            f'border-radius:10px;font-size:12px;font-weight:600;">{area_type}</span>'
        )

    # ── 출처 배너 ──────────────────────────────────────────────────────────────
    c_s1, c_s2, c_s3 = st.columns(3)
    c_s1.info("**출처** 수동 관리 (manual_table.json)")
    c_s2.info(f"**마지막 수정** {_fmt_mtime(REG_FILE)}")
    c_s3.info("**자동 감지** `area_designation_pipeline.py`")

    st.divider()

    # ── 파이프라인 모듈 로드 ────────────────────────────────────────────────────
    try:
        from src.ingestion.area_designation_pipeline import (
            get_pending_proposals, apply_proposal, run_pipeline,
        )
        _pipeline_ok = True
    except Exception as _e:
        _pipeline_ok = False

    # ── 현행 메트릭 ──────────────────────────────────────────────────────────
    if REG_FILE.exists():
        try:
            current_reg = json.loads(REG_FILE.read_text(encoding="utf-8"))
        except Exception:
            current_reg = []

        active_reg = [r for r in current_reg if not r.get("released_at")]
        released_reg = [r for r in current_reg if r.get("released_at")]

        type_counts = Counter(r.get("area_type", "") for r in active_reg)
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("현행 지정 전체", f"{len(active_reg)}건")
        m2.metric("🟠 조정대상지역", f"{type_counts.get('조정대상지역', 0)}건")
        m3.metric("🔴 투기과열지구", f"{type_counts.get('투기과열지구', 0)}건")
        m4.metric("🟣 투기지역", f"{type_counts.get('투기지역', 0)}건")
        m5.metric("🔵 토지거래허가구역", f"{type_counts.get('토지거래허가구역', 0)}건")

        st.divider()
    else:
        current_reg, active_reg, released_reg = [], [], []
        st.error("manual_table.json 파일이 없습니다.")

    col_left, col_right = st.columns([1, 1])

    # ── 현행 / 이력 탭 ────────────────────────────────────────────────────────
    with col_left:
        st.markdown("### 📋 현행 지정 현황")
        sub_active, sub_released = st.tabs([
            f"현행 지정 ({len(active_reg)})",
            f"해제 이력 ({len(released_reg)})",
        ])

        import pandas as pd

        with sub_active:
            if active_reg:
                rows_a = []
                for r in sorted(active_reg, key=lambda x: (x.get("region", ""), x.get("area_type", ""))):
                    rows_a.append({
                        "지역": r.get("region", ""),
                        "구역 유형": r.get("area_type", ""),
                        "지정일": r.get("designated_at", ""),
                        "고시 번호": r.get("announcement_no", ""),
                        "출처": r.get("source_url", ""),
                    })
                st.dataframe(
                    pd.DataFrame(rows_a),
                    use_container_width=True,
                    hide_index=True,
                    column_config={"출처": st.column_config.LinkColumn("출처")},
                )
            else:
                st.info("현행 지정된 지역이 없습니다.")

        with sub_released:
            if released_reg:
                rows_r = []
                for r in sorted(released_reg, key=lambda x: x.get("released_at", ""), reverse=True):
                    rows_r.append({
                        "지역": r.get("region", ""),
                        "구역 유형": r.get("area_type", ""),
                        "지정일": r.get("designated_at", ""),
                        "해제일": r.get("released_at", ""),
                        "고시 번호": r.get("announcement_no", ""),
                    })
                st.dataframe(pd.DataFrame(rows_r), use_container_width=True, hide_index=True)
            else:
                st.info("해제 이력이 없습니다.")

    # ── 제안서 / 자동 감지 ────────────────────────────────────────────────────
    with col_right:
        st.markdown("### 📥 자동 감지 & 승인")

        col_run, col_pending = st.columns([1, 1])
        if col_run.button("🔍 지금 감지 실행", type="primary", disabled=not _pipeline_ok):
            with st.spinner("소스 스캔 중..."):
                summary = run_pipeline(dry_run=False)
            alert = summary.get("alert_level")
            if alert == "critical":
                st.error("🚨 변경 감지! 제안서를 확인하세요.")
            elif alert == "warning":
                st.warning("⚠️ 경보 신호 감지 — 공식 공고 확인 필요")
            elif summary.get("health_warning"):
                st.error(f"❌ {summary['health_warning']}")
            else:
                st.success("변경 없음")
            st.rerun()

        pending_list = get_pending_proposals() if _pipeline_ok else []
        col_pending.metric("대기 제안서", len(pending_list))

        if not _pipeline_ok:
            st.info("파이프라인 모듈 없음 — 수동 관리만 가능합니다.")
        elif not pending_list:
            st.info("승인 대기 제안서가 없습니다.")
        else:
            for pidx, proposal_path in enumerate(pending_list):
                try:
                    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
                except Exception:
                    continue

                detected_at = proposal.get("detected_at", "")[:19]
                candidates = proposal.get("candidates", [])
                conf_avg = sum(c.get("confidence", 0) for c in candidates) / max(len(candidates), 1)
                sources = {c.get("source_name", "") for c in candidates}
                priority = "🔴 P0" if sources & {"gwanbo", "molit_board", "moef_board"} else "🟡 P1"

                with st.expander(
                    f"{priority} {detected_at} — {len(candidates)}건 (신뢰도 {conf_avg:.0%})",
                    expanded=pidx == 0,
                ):
                    for c in candidates:
                        action = "🔓 해제" if c.get("released_at") else "🔒 신규"
                        region = c.get("region") or "(지역 미추출)"
                        st.markdown(
                            f"**{action}** `{c.get('area_type','')}` — {region}  \n"
                            f"고시: {c.get('announcement_no','—')} | {c.get('source_name','')} | {c.get('confidence',0):.0%}"
                        )
                        if c.get("source_url"):
                            st.caption(c["source_url"])

                    ca, cb = st.columns(2)
                    if ca.button("✅ 승인", key=f"approve_{pidx}"):
                        try:
                            n = apply_proposal(proposal_path)
                            st.success(f"{n}건 반영")
                            st.rerun()
                        except Exception as e:
                            st.error(f"실패: {e}")
                    if cb.button("🗑️ 거절", key=f"reject_{pidx}"):
                        try:
                            data = json.loads(proposal_path.read_text(encoding="utf-8"))
                            data["status"] = "rejected"
                            data["rejected_at"] = datetime.now().isoformat()
                            proposal_path.write_text(
                                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
                            )
                            st.rerun()
                        except Exception as e:
                            st.error(f"실패: {e}")

        st.divider()
        st.caption("⚠️ 이 데이터는 수동 관리 파일입니다. 실제 고시와 반드시 대조하세요.")
        st.caption("출처: 국토교통부(molit.go.kr) / 기획재정부(moef.go.kr) / 서울특별시(seoul.go.kr)")


# ══════════════════════════════════════════════════════════════════════════════
# 탭 4: 케이스 목록
# ══════════════════════════════════════════════════════════════════════════════

with tab_cases:
    st.subheader(f"전체 케이스 — {len(SAMPLE_CASES)}개")

    all_cats = sorted({c["category"] for c in SAMPLE_CASES})
    selected_cats = st.multiselect(
        "카테고리 필터",
        options=all_cats,
        default=all_cats,
        format_func=lambda c: CATEGORY_LABELS.get(c, c),
    )
    filtered_cases = [c for c in SAMPLE_CASES if c["category"] in selected_cats]
    st.caption(f"{len(filtered_cases)}개 표시 중")

    for idx, case in enumerate(filtered_cases):
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

        if (
            st.session_state.admin_running_idx == orig_idx
            and st.session_state.admin_result is not None
        ):
            with st.expander("결과 보기", expanded=True):
                _render_result(st.session_state.admin_result)

        st.divider()


# ══════════════════════════════════════════════════════════════════════════════
# 탭 5: 골든셋
# ══════════════════════════════════════════════════════════════════════════════

with tab_golden:
    GOLDEN_FILE = _ROOT / "data" / "golden" / "qa_pairs.json"
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
            total = len(golden_pairs)
            chunk_filled = sum(1 for g in golden_pairs if g.get("gold_chunk_ids"))
            m1, m2, m3 = st.columns(3)
            m1.metric("총 케이스", total)
            m2.metric("chunk_ids 채워짐", chunk_filled)
            m3.metric("chunk_ids 비어있음", total - chunk_filled)

            st.divider()

            for g_idx, golden in enumerate(golden_pairs):
                chunk_status = "✅" if golden.get("gold_chunk_ids") else "⚠️"
                exp_v = golden.get("expected_verdict", "—")
                color = _VERDICT_COLOR.get(exp_v, "gray")

                col_id, col_desc, col_verdict, col_chunk, col_btn = st.columns([1, 3, 1.2, 0.6, 1])
                col_id.caption(golden.get("id", f"#{g_idx}"))
                col_desc.markdown(golden.get("description", ""))
                col_verdict.markdown(f":{color}[{exp_v}]")
                col_chunk.write(chunk_status)

                if col_btn.button("▶ 실행", key=f"run_golden_{g_idx}"):
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


# ══════════════════════════════════════════════════════════════════════════════
# 탭 6: 통계
# ══════════════════════════════════════════════════════════════════════════════

with tab_stats:
    st.subheader("논쟁 & 골든셋 통계")
    if st.button("🔄 새로고침"):
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
        st.json({**ds, "golden": gs})

    except Exception as e:
        st.warning(f"통계 로드 실패: {e}")

    st.divider()
    st.subheader("카테고리별 케이스 분포")
    from collections import Counter
    cat_counts = Counter(c["category"] for c in SAMPLE_CASES)
    rows = [
        {"카테고리": CATEGORY_LABELS.get(cat, cat), "케이스 수": cnt}
        for cat, cnt in sorted(cat_counts.items(), key=lambda x: -x[1])
    ]
    import pandas as pd
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# 탭 7: 법령 모니터링
# ══════════════════════════════════════════════════════════════════════════════

with tab_monitor:
    st.subheader("🔔 법령 개정 모니터링")
    if st.button("🔄 새로고침", key="monitor_refresh"):
        st.rerun()

    # ── 헬퍼: 모니터링 데이터 로드 ────────────────────────────────────────────

    def _load_change_log(limit: int = 30) -> list[dict]:
        p = _ROOT / "data" / "law_change_log.jsonl"
        if not p.exists():
            return []
        lines = p.read_text(encoding="utf-8").strip().splitlines()
        records = []
        for line in reversed(lines[-100:]):
            try:
                records.append(json.loads(line))
            except Exception:
                pass
        return records[:limit]

    def _load_image_alerts() -> list[dict]:
        d = _ROOT / "data" / "image_table_alerts"
        if not d.exists():
            return []
        alerts: list[dict] = []
        for f in sorted(d.glob("table_alerts_*.json"), reverse=True)[:5]:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                for a in data.get("alerts", []):
                    a["_file"] = f.name
                    alerts.append(a)
            except Exception:
                pass
        return alerts

    def _load_amendment_test_results() -> list[dict]:
        d = _ROOT / "data" / "amendment_test_results"
        if not d.exists():
            return []
        anomalies: list[dict] = []
        for f in sorted(d.glob("amendment_test_*.json"), reverse=True)[:5]:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                for a in data.get("anomalies", []):
                    a["_file"] = f.name
                    a["_changed_laws"] = data.get("changed_laws", [])
                    anomalies.append(a)
            except Exception:
                pass
        return anomalies

    def _load_stale_golden() -> list[dict]:
        p = _ROOT / "data" / "law_change_log.jsonl"
        if not p.exists():
            return []
        stale: list[dict] = []
        for line in p.read_text(encoding="utf-8").strip().splitlines():
            try:
                rec = json.loads(line)
                if rec.get("event") == "golden_stale_candidates":
                    stale.extend(rec.get("stale_cases", []))
            except Exception:
                pass
        seen = set()
        unique = []
        for s in reversed(stale):
            cid = s.get("case_id", "")
            if cid not in seen:
                seen.add(cid)
                unique.append(s)
        return unique

    def _load_red_win_progress() -> tuple[int, int]:
        d = _ROOT / "data" / "red_wins"
        if not d.exists():
            return 0, 50
        return len(list(d.glob("*.json"))), 50

    # ── 요약 메트릭 ──────────────────────────────────────────────────────────

    img_alerts = _load_image_alerts()
    amd_anomalies = _load_amendment_test_results()
    stale_cases = _load_stale_golden()
    red_wins, red_target = _load_red_win_progress()

    high_stale = [s for s in stale_cases if s.get("sensitivity") == "high"]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "별표 불일치",
        f"{len(img_alerts)}건",
        delta="수동 확인 필요" if img_alerts else None,
        delta_color="inverse",
    )
    c2.metric(
        "개정 케이스 이상",
        f"{len(amd_anomalies)}건",
        delta="즉시 확인" if amd_anomalies else None,
        delta_color="inverse",
    )
    c3.metric(
        "골든케이스 Stale",
        f"{len(stale_cases)}건",
        delta=f"🔴 HIGH {len(high_stale)}건" if high_stale else None,
        delta_color="inverse",
    )
    c4.metric(
        "Red Win 누적",
        f"{red_wins}/{red_target}건",
        delta=f"목표 {red_target - red_wins}건 남음" if red_wins < red_target else "✅ 목표 달성",
        delta_color="normal" if red_wins >= red_target else "inverse",
    )

    st.divider()

    # ── 1. 별표 이미지 테이블 검증 현황 ────────────────────────────────────

    st.markdown("#### 📋 별표·이미지 테이블 반영 현황")
    st.caption("법령 API에서 이미지로 제공되는 별표(장기보유특별공제율 표1/표2 등)의 레지스트리 반영 상태")

    try:
        from src.domain.tax_constants import TaxConstantsRegistry, _REGISTRY
        table_rows = []
        today_d = datetime.now().date()

        for key in ["LONG_TERM_DEDUCTION_RATE_TABLE1", "LONG_TERM_DEDUCTION_RATE_TABLE2"]:
            versions = _REGISTRY.get(key, [])
            if versions:
                v = max(versions, key=lambda x: x.effective_from)
                val = v.value
                row_count = len(val) if isinstance(val, dict) else "—"
                table_rows.append({
                    "상수 키": key,
                    "설명": "장기보유특별공제율 표1 (일반)" if "TABLE1" in key else "장기보유특별공제율 표2 (1세대1주택)",
                    "시행일": v.effective_from.strftime("%Y-%m-%d"),
                    "행 수": row_count,
                    "수동검토필요": "⚠️ 예" if v.manual_review_required else "✅ 정상",
                    "법령조문": v.source_law,
                })

        # 별표 알림 통합 표시
        if img_alerts:
            st.error(f"🔴 별표 불일치 {len(img_alerts)}건 — tax_constants.py 수동 확인 후 ConstantVersion 추가 필요")
            for alert in img_alerts[:5]:
                with st.expander(f"⚠️ {alert.get('law_name')} {alert.get('table_id')} 불일치"):
                    diff = alert.get("diff", {})
                    if diff:
                        import pandas as pd
                        diff_rows = [
                            {"년수": k, "상태": v.get("status"), "레지스트리": v.get("current"), "추출값": v.get("extracted")}
                            for k, v in sorted(diff.items(), key=lambda x: int(x[0]))
                        ]
                        st.dataframe(pd.DataFrame(diff_rows), use_container_width=True, hide_index=True)
                    st.caption(f"파일: {alert.get('_file', '—')}")
        elif table_rows:
            st.success("✅ 별표 검증 이상 없음 — 레지스트리 반영 확인됨")

        if table_rows:
            import pandas as pd
            st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)

    except Exception as e:
        st.warning(f"레지스트리 로드 실패: {e}")

    st.divider()

    # ── 2. 개정 임계값 경계 케이스 검증 결과 ────────────────────────────────

    st.markdown("#### 🧪 개정 임계값 경계 케이스 검증")
    st.caption("법령 개정 감지 시 자동 생성한 경계 케이스 verdict 불일치 내역")

    if amd_anomalies:
        st.error(f"🚨 verdict 불일치 {len(amd_anomalies)}건 — 파이프라인 또는 골든케이스 수정 필요")
        import pandas as pd
        df_amd = pd.DataFrame([
            {
                "케이스 ID": a.get("case_id"),
                "설명": a.get("description", "")[:40],
                "법령": ", ".join(a.get("_changed_laws", [])),
                "판단 결과": a.get("verdict"),
                "예상 결과": a.get("expected_verdict"),
                "파일": a.get("_file", "—"),
            }
            for a in amd_anomalies[:20]
        ])
        st.dataframe(df_amd, use_container_width=True, hide_index=True)
    else:
        latest_amd = sorted(
            (_ROOT / "data" / "amendment_test_results").glob("*.json"),
            reverse=True,
        )[:1] if (_ROOT / "data" / "amendment_test_results").exists() else []
        if latest_amd:
            mtime = _fmt_mtime(latest_amd[0])
            st.success(f"✅ 경계 케이스 verdict 모두 정상 (마지막 검증: {mtime})")
        else:
            st.info("검증 이력 없음 — 법령 개정 감지 시 자동 실행됩니다.")

    st.divider()

    # ── 3. 골든케이스 Stale 현황 ─────────────────────────────────────────────

    st.markdown("#### 🏅 골든케이스 Stale 현황")
    st.caption("법령 개정에 의해 expected_verdict가 바뀔 수 있는 케이스 목록")

    if stale_cases:
        import pandas as pd
        df_stale = pd.DataFrame([
            {
                "케이스 ID": s.get("case_id"),
                "민감도": {"high": "🔴 HIGH", "medium": "🟡 MEDIUM", "low": "🟢 LOW"}.get(s.get("sensitivity", ""), s.get("sensitivity", "")),
                "촉발 법령": s.get("triggered_by", "—"),
                "영향": s.get("notes", "")[:50],
            }
            for s in sorted(stale_cases, key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x.get("sensitivity", ""), 9))
        ])
        st.dataframe(df_stale, use_container_width=True, hide_index=True)
        if high_stale:
            st.error(f"🚨 HIGH sensitivity {len(high_stale)}건 — 즉시 expected_verdict 재검토 필요")
    else:
        st.success("✅ 개정으로 인한 stale 케이스 없음")

    st.divider()

    # ── 4. 최근 법령 개정 감지 이력 ─────────────────────────────────────────

    st.markdown("#### 📜 최근 법령 개정 감지 이력")
    change_log = _load_change_log(20)

    if change_log:
        import pandas as pd
        log_rows = []
        for rec in change_log:
            event = rec.get("event", "law_change")
            detected = rec.get("detected_at", "")[:16]
            if event == "golden_stale_candidates":
                laws = ", ".join(rec.get("triggered_by_laws", []))
                desc = f"Stale 후보 {len(rec.get('stale_cases', []))}건"
            elif event == "amendment_test_results":
                desc = f"경계 케이스 {rec.get('total_cases', 0)}건, 이상 {rec.get('anomaly_count', 0)}건"
                laws = ""
            elif event == "image_table_verification":
                desc = f"별표 검증: ✅{rec.get('verified_count', 0)} / 🔴{rec.get('alert_count', 0)}"
                laws = ""
            else:
                laws = rec.get("law_name", "")
                msts = rec.get("new_msts", [])
                desc = f"신규 MST {len(msts)}건: {', '.join(msts[:3])}"
            log_rows.append({"감지 시각": detected, "이벤트": event, "법령": laws, "내용": desc})

        st.dataframe(pd.DataFrame(log_rows), use_container_width=True, hide_index=True)
    else:
        st.info("법령 개정 감지 이력 없음\n`python -m scripts.detect_law_changes` 실행 후 결과가 표시됩니다.")


# ══════════════════════════════════════════════════════════════════════════════
# 탭 8: 디버그
# ══════════════════════════════════════════════════════════════════════════════

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
