"""
행정 레이어 지도 페이지 — 조정대상지역 / 투기과열지구 / 투기지역 / 토지거래허가구역 현황.
data/area_designations/manual_table.json 기반.
판단 로직 없음. 표시·필터 전용.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pandas as pd
import pydeck as pdk
import streamlit as st

st.set_page_config(page_title="행정 레이어 조회", layout="wide")

# ── 좌표 테이블 ────────────────────────────────────────────────────────────────

_REGION_COORDS: dict[str, tuple[float, float]] = {
    "서울특별시": (37.5665, 126.9780),
    "서울특별시 강남구": (37.5172, 127.0473),
    "서울특별시 서초구": (37.4837, 127.0324),
    "서울특별시 송파구": (37.5145, 127.1059),
    "서울특별시 용산구": (37.5384, 126.9654),
    "서울특별시 마포구": (37.5638, 126.9084),
    "서울특별시 성동구": (37.5634, 127.0370),
    "서울특별시 노원구": (37.6542, 127.0568),
    "서울특별시 강동구": (37.5301, 127.1238),
    "경기도 성남시 분당구": (37.3825, 127.1192),
    "경기도 과천시": (37.4292, 126.9876),
    "경기도 하남시": (37.5390, 127.2149),
    "인천광역시 연수구": (37.4102, 126.6780),
    "세종특별자치시": (36.4800, 127.2890),
}

# 지역 유형별 색상 (RGBA)
_TYPE_COLOR: dict[str, list[int]] = {
    "조정대상지역": [255, 165, 0, 180],      # 주황
    "투기과열지구": [220, 50, 50, 180],       # 빨강
    "투기지역": [160, 32, 240, 180],          # 보라
    "토지거래허가구역": [30, 144, 255, 180],  # 파랑
}

_DATA_PATH = Path(__file__).parent.parent.parent / "data" / "area_designations" / "manual_table.json"

ALL_AREA_TYPES = ["조정대상지역", "투기과열지구", "투기지역", "토지거래허가구역"]


# ── 데이터 로드 ────────────────────────────────────────────────────────────────

@st.cache_data
def _load_data() -> list[dict]:
    if not _DATA_PATH.exists():
        return []
    return json.loads(_DATA_PATH.read_text(encoding="utf-8"))


def _is_active(row: dict, ref_date: date) -> bool:
    """ref_date 기준으로 해당 레코드가 유효한지 판단."""
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
        released = date.fromisoformat(released_raw)
        return ref_date <= released
    except ValueError:
        return True


def _apply_filters(
    rows: list[dict],
    ref_date: date,
    selected_types: list[str],
    active_only: bool,
) -> list[dict]:
    result = []
    for row in rows:
        if row.get("area_type") not in selected_types:
            continue
        is_active = _is_active(row, ref_date)
        if active_only and not is_active:
            continue
        result.append({**row, "_active": is_active})
    return result


def _build_map_df(rows: list[dict]) -> pd.DataFrame:
    records = []
    for row in rows:
        region = row.get("region", "")
        coords = _REGION_COORDS.get(region)
        if coords is None:
            continue
        is_active = row.get("_active", False)
        base_color = _TYPE_COLOR.get(row.get("area_type", ""), [128, 128, 128, 150])
        color = base_color if is_active else [180, 180, 180, 120]
        records.append(
            {
                "region": region,
                "area_type": row.get("area_type", ""),
                "designated_at": row.get("designated_at", ""),
                "released_at": row.get("released_at") or "현재 지정 중",
                "announcement_no": row.get("announcement_no", ""),
                "source_url": row.get("source_url", ""),
                "lat": coords[0],
                "lon": coords[1],
                "active": is_active,
                "color": color,
                "radius": 2500 if is_active else 1500,
            }
        )
    return pd.DataFrame(records)


# ── 사이드바 ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("필터")

    ref_date = st.date_input("기준일", value=date.today())

    st.subheader("지역 유형")
    selected_types: list[str] = []
    for atype in ALL_AREA_TYPES:
        if st.checkbox(atype, value=True, key=f"chk_{atype}"):
            selected_types.append(atype)

    active_only = st.checkbox("현재 지정 중만 표시", value=False)

    st.markdown("---")
    st.caption("색상 범례")
    for atype, color in _TYPE_COLOR.items():
        hex_color = "#{:02X}{:02X}{:02X}".format(color[0], color[1], color[2])
        st.markdown(
            f'<span style="display:inline-block;width:12px;height:12px;'
            f'background:{hex_color};border-radius:50%;margin-right:6px;"></span>{atype}',
            unsafe_allow_html=True,
        )
    st.markdown(
        '<span style="display:inline-block;width:12px;height:12px;'
        'background:#B4B4B4;border-radius:50%;margin-right:6px;"></span>해제된 구역',
        unsafe_allow_html=True,
    )

# ── 메인 ───────────────────────────────────────────────────────────────────────

st.title("행정 레이어 조회")
st.caption(f"기준일: {ref_date}  |  출처: data/area_designations/manual_table.json")

raw_data = _load_data()

if not raw_data:
    st.warning("데이터 파일을 찾을 수 없습니다: data/area_designations/manual_table.json")
    st.stop()

filtered = _apply_filters(raw_data, ref_date, selected_types, active_only)
map_df = _build_map_df(filtered)

# ── 요약 메트릭 ───────────────────────────────────────────────────────────────

st.subheader("현재 지정 건수 요약")
active_counts = {atype: 0 for atype in ALL_AREA_TYPES}
for row in filtered:
    if row.get("_active"):
        atype = row.get("area_type", "")
        if atype in active_counts:
            active_counts[atype] += 1

cols = st.columns(len(ALL_AREA_TYPES))
for col, atype in zip(cols, ALL_AREA_TYPES):
    col.metric(atype, f"{active_counts[atype]}건")

st.markdown("---")

# ── 지도 ──────────────────────────────────────────────────────────────────────

st.subheader("지도")

if map_df.empty:
    st.info("선택된 조건에 해당하는 지역이 없습니다.")
else:
    scatter_layer = pdk.Layer(
        "ScatterplotLayer",
        data=map_df,
        get_position="[lon, lat]",
        get_fill_color="color",
        get_radius="radius",
        pickable=True,
        opacity=0.8,
        stroked=True,
        get_line_color=[80, 80, 80],
        line_width_min_pixels=1,
    )

    view_state = pdk.ViewState(
        latitude=37.5,
        longitude=127.0,
        zoom=9,
        pitch=0,
    )

    tooltip = {
        "html": (
            "<b>{region}</b><br/>"
            "유형: {area_type}<br/>"
            "지정일: {designated_at}<br/>"
            "해제일: {released_at}<br/>"
            "고시: {announcement_no}"
        ),
        "style": {
            "backgroundColor": "white",
            "color": "black",
            "fontSize": "13px",
            "padding": "8px",
            "border": "1px solid #ccc",
        },
    }

    deck = pdk.Deck(
        layers=[scatter_layer],
        initial_view_state=view_state,
        tooltip=tooltip,
        map_style="mapbox://styles/mapbox/light-v10",
    )
    st.pydeck_chart(deck)

st.markdown("---")

# ── 결과 테이블 ───────────────────────────────────────────────────────────────

st.subheader(f"필터된 결과 ({len(filtered)}건)")

if filtered:
    display_rows = []
    for row in filtered:
        display_rows.append(
            {
                "지역": row.get("region", ""),
                "구역 유형": row.get("area_type", ""),
                "지정일": row.get("designated_at", ""),
                "해제일": row.get("released_at") or "현재 지정 중",
                "현재 지정": "O" if row.get("_active") else "X",
                "고시 번호": row.get("announcement_no", ""),
                "출처": row.get("source_url", ""),
            }
        )
    display_df = pd.DataFrame(display_rows)
    st.dataframe(display_df, use_container_width=True, hide_index=True)
else:
    st.info("선택된 조건에 해당하는 데이터가 없습니다.")
