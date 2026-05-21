"""
행정 레이어 조회 — 조정대상지역 / 투기과열지구 / 투기지역 / 토지거래허가구역 현황 리스트.
data/area_designations/manual_table.json 기반. 판단 로직 없음.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import streamlit as st

st.set_page_config(page_title="행정 레이어 조회", layout="wide")

_DATA_PATH = Path(__file__).parent.parent.parent / "data" / "area_designations" / "manual_table.json"

ALL_AREA_TYPES = ["조정대상지역", "투기과열지구", "투기지역", "토지거래허가구역"]

_TYPE_BADGE: dict[str, str] = {
    "조정대상지역":   "🟠",
    "투기과열지구":   "🔴",
    "투기지역":       "🟣",
    "토지거래허가구역": "🔵",
}

_TYPE_COLOR_CSS: dict[str, str] = {
    "조정대상지역":   "#FF8C00",
    "투기과열지구":   "#DC3232",
    "투기지역":       "#9B59B6",
    "토지거래허가구역": "#1E90FF",
}


def _load_data() -> list[dict]:
    if not _DATA_PATH.exists():
        return []
    return json.loads(_DATA_PATH.read_text(encoding="utf-8"))


def _is_active(row: dict, ref_date: date) -> bool:
    try:
        designated = date.fromisoformat(row["designated_at"])
    except (TypeError, ValueError):
        return False
    if ref_date < designated:
        return False
    released_raw: Optional[str] = row.get("released_at")
    if released_raw is None:
        return True
    try:
        return ref_date <= date.fromisoformat(released_raw)
    except ValueError:
        return True


def _badge_html(area_type: str) -> str:
    color = _TYPE_COLOR_CSS.get(area_type, "#888")
    return (
        f'<span style="background:{color};color:#fff;padding:2px 8px;'
        f'border-radius:10px;font-size:12px;font-weight:600;">{area_type}</span>'
    )


def _status_html(active: bool, released_at: Optional[str]) -> str:
    if active:
        return '<span style="color:#16a34a;font-weight:700;">● 지정 중</span>'
    date_str = released_at or ""
    return f'<span style="color:#9ca3af;">○ 해제 ({date_str})</span>'


# ── 사이드바 ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("필터")
    ref_date = st.date_input("기준일", value=date.today())

    st.subheader("구역 유형")
    selected_types: list[str] = []
    for atype in ALL_AREA_TYPES:
        emoji = _TYPE_BADGE.get(atype, "")
        if st.checkbox(f"{emoji} {atype}", value=True, key=f"chk_{atype}"):
            selected_types.append(atype)

    active_only = st.checkbox("현재 지정 중만", value=False)

    search_text = st.text_input("지역 검색", placeholder="예: 강남, 서초, 용산")

    st.markdown("---")
    st.caption("⚠️ 이 데이터는 수동 관리 파일입니다. 실제 고시와 반드시 대조하세요.")
    st.caption("출처: 국토교통부(molit.go.kr) / 기획재정부(moef.go.kr) / 서울특별시(seoul.go.kr)")

# ── 데이터 준비 ────────────────────────────────────────────────────────────────

raw_data = _load_data()

if not raw_data:
    st.warning("데이터 파일 없음: data/area_designations/manual_table.json")
    st.stop()

filtered: list[dict] = []
for row in raw_data:
    if row.get("area_type") not in selected_types:
        continue
    active = _is_active(row, ref_date)
    if active_only and not active:
        continue
    if search_text and search_text not in row.get("region", ""):
        continue
    filtered.append({**row, "_active": active})

# ── 헤더 + 메트릭 ────────────────────────────────────────────────────────────

st.title("행정 레이어 조회")
st.caption(f"기준일: **{ref_date}**  |  전체 {len(raw_data)}건 중 필터 결과 {len(filtered)}건")

active_counts = {t: 0 for t in ALL_AREA_TYPES}
for row in raw_data:
    if _is_active(row, ref_date):
        t = row.get("area_type", "")
        if t in active_counts:
            active_counts[t] += 1

cols = st.columns(len(ALL_AREA_TYPES))
for col, atype in zip(cols, ALL_AREA_TYPES):
    emoji = _TYPE_BADGE.get(atype, "")
    col.metric(f"{emoji} {atype}", f"{active_counts[atype]}건 지정 중")

st.markdown("---")

if not filtered:
    st.info("선택된 조건에 해당하는 지역이 없습니다.")
    st.stop()

# ── 현재 지정 중 섹션 ─────────────────────────────────────────────────────────

active_rows = [r for r in filtered if r["_active"]]
if active_rows:
    st.subheader(f"현재 지정 중 ({len(active_rows)}건)")

    header_cols = st.columns([3, 2, 1, 2, 3])
    header_cols[0].markdown("**지역**")
    header_cols[1].markdown("**구역 유형**")
    header_cols[2].markdown("**지정일**")
    header_cols[3].markdown("**고시 번호**")
    header_cols[4].markdown("**출처**")
    st.markdown('<hr style="margin:4px 0 8px 0;border-color:#e5e7eb;">', unsafe_allow_html=True)

    for row in sorted(active_rows, key=lambda r: (r.get("region", ""), r.get("area_type", ""))):
        c = st.columns([3, 2, 1, 2, 3])
        c[0].markdown(f"**{row.get('region', '')}**")
        c[1].markdown(_badge_html(row.get("area_type", "")), unsafe_allow_html=True)
        c[2].write(row.get("designated_at", ""))
        c[3].write(row.get("announcement_no", ""))
        url = row.get("source_url", "")
        c[4].markdown(f"[고시 원문]({url})" if url else "—")

    st.markdown("---")

# ── 전체 이력 ─────────────────────────────────────────────────────────────────

st.subheader(f"전체 이력 ({len(filtered)}건)")

rows_display = []
for row in sorted(filtered, key=lambda r: (r.get("region", ""), r.get("area_type", ""), r.get("designated_at", ""))):
    active = row["_active"]
    rows_display.append({
        "지역": row.get("region", ""),
        "구역 유형": row.get("area_type", ""),
        "상태": "지정 중" if active else "해제",
        "지정일": row.get("designated_at", ""),
        "해제일": row.get("released_at") or "—",
        "고시 번호": row.get("announcement_no", ""),
        "출처": row.get("source_url", ""),
    })

if rows_display:
    import pandas as pd

    df = pd.DataFrame(rows_display)
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "지역": st.column_config.TextColumn("지역", width="medium"),
            "구역 유형": st.column_config.TextColumn("구역 유형", width="medium"),
            "상태": st.column_config.TextColumn("상태", width="small"),
            "지정일": st.column_config.TextColumn("지정일", width="small"),
            "해제일": st.column_config.TextColumn("해제일", width="small"),
            "고시 번호": st.column_config.TextColumn("고시 번호", width="large"),
            "출처": st.column_config.LinkColumn("출처", width="medium"),
        },
    )
