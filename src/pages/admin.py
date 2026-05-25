"""
어드민 페이지 — 대시보드 / 법령 / 지역데이터 / 시나리오.
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


def _fmt_freshness(path: Path) -> tuple[str, str, str]:
    """파일 경로 → (상태 레이블, status_key, 상대 시간 문자열).

    status_key: "ok" / "warn" / "error"
    디렉터리가 전달되면 가장 최신 *.json 파일 기준으로 판단.
    path=None 또는 "not_implemented" 문자열이면 (구현전) 반환.
    """
    if path is None:
        return "❌ (구현전)", "error", "—"
    p = Path(path) if not isinstance(path, Path) else path
    if not p.exists():
        return "❌ 데이터 없음", "error", "—"
    # 디렉터리면 최신 json 파일 기준
    if p.is_dir():
        files = list(p.glob("*.json"))
        if not files:
            return "❌ 데이터 없음", "error", "—"
        p = max(files, key=lambda f: f.stat().st_mtime)
    hours_ago = (datetime.now().timestamp() - p.stat().st_mtime) / 3600
    if hours_ago < 36:
        rel = f"{int(hours_ago)}시간 전" if hours_ago >= 1 else "방금"
        return "✅ 현행 검증 완료", "ok", rel
    if hours_ago < 72:
        rel = f"{int(hours_ago)}시간 전"
        return "⚠️ 갱신 확인 필요", "warn", rel
    rel = f"{int(hours_ago / 24)}일 전"
    return "❌ 오래된 데이터", "error", rel


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


def _run_case(fact_json: dict) -> dict:
    from src.api.chat_api import chat_turn
    return asyncio.run(chat_turn(fact_json=fact_json, enable_debate=True))


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


def _load_ruling_summary() -> dict[str, tuple[int, str]]:
    """유권해석 소스별 (파일 수, 마지막수정일) 반환."""
    sources = {
        "nts":        ("data/rulings/nts",        "국세청 질의회신"),
        "decisions":  ("data/rulings/decisions",  "심판청구 결정례"),
        "pdf":        ("data/rulings/pdf",         "해석례 PDF"),
        "moef":       ("data/rulings/moef",        "기재부 법령해석"),
        "nts_interp": ("data/rulings/nts_interp",  "국세청 법령해석"),
    }
    result: dict[str, tuple[int, str]] = {}
    for key, (rel_path, _) in sources.items():
        d = _ROOT / rel_path
        if not d.exists():
            result[key] = (0, "—")
            continue
        files = list(d.glob("*.json"))
        if not files:
            result[key] = (0, "—")
            continue
        latest = max(files, key=lambda f: f.stat().st_mtime)
        result[key] = (len(files), _fmt_mtime(latest))
    return result


# ── 헬퍼: 모니터링 데이터 로드 ─────────────────────────────────────────────────

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


# ── 헬퍼: 골든셋 평가 로드 ────────────────────────────────────────────────────

def _load_golden_eval_latest() -> dict:
    p = _ROOT / "data" / "eval_results" / "golden_eval_latest.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _status_badge(case: dict) -> str:
    if case.get("invalidated"):
        return "⚠️ 재검토"
    ev = case.get("last_eval") or {}
    if not ev:
        return "🔘 미평가"
    if ev.get("error"):
        return "🚫 오류"
    if ev.get("blocked"):
        return "🟡 차단"
    match = ev.get("match")
    if match is True:
        return "✅ PASS"
    if match is False:
        return "❌ FAIL"
    return "— 비교불가"


# ── 사이드바 ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("🛠️ 어드민")
    st.divider()
    _debate_model = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
    st.caption(f"모델: `{_debate_model}`")

# ── 탭 ────────────────────────────────────────────────────────────────────────

st.markdown("## 🛠️ 어드민")

tab_laws, tab_scenarios = st.tabs([
    "⚖️ 법령관리",
    "📋 시나리오",
])


# ══════════════════════════════════════════════════════════════════════════════
# 탭 1: 총괄 대시보드
# ══════════════════════════════════════════════════════════════════════════════

def _sys_card(col, icon: str, title: str, value: str, detail: str, status: str) -> None:
    bg, fg = {"ok": ("#E8F5E9", "#1B5E20"), "warn": ("#FFF3E0", "#BF360C"), "error": ("#FFEBEE", "#B71C1C")}.get(
        status, ("#F5F5F5", "#333")
    )
    col.markdown(
        f'<div style="background:{bg};border-left:5px solid {fg};padding:16px 14px;border-radius:6px;min-height:100px">'
        f'<div style="color:{fg};font-weight:700;font-size:0.85em">{icon} {title}</div>'
        f'<div style="color:{fg};font-size:1.8em;font-weight:800;margin:6px 0">{value}</div>'
        f'<div style="color:#555;font-size:0.78em">{detail}</div></div>',
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════════════════════════════════════
# 탭 1: 법령관리 (대시보드 / 법령 / 지역 / 개정감지·조문검색)
# ══════════════════════════════════════════════════════════════════════════════

with tab_laws:
    import pandas as pd

    sub_dash, sub_law, sub_area, sub_monitor = st.tabs([
        "📊 대시보드", "📜 법령", "🗺️ 지역", "🔔 개정감지 · 🔍 조문검색",
    ])

    # ── 공통 데이터 로드 ──────────────────────────────────────────────────────
    law_rows = _load_law_inventory()
    area_active, area_total, area_mtime = _load_area_summary()
    golden_cnt, golden_mtime = _load_golden_summary()
    debate_cnt, debate_mtime = _load_debate_summary()
    ruling_summary = _load_ruling_summary()
    img_alerts = _load_image_alerts()
    amd_anomalies = _load_amendment_test_results()
    stale_cases = _load_stale_golden()
    red_wins, red_target = _load_red_win_progress()

    _gp_file = _ROOT / "data" / "golden" / "qa_pairs.json"
    golden_pairs: list[dict] = []
    if _gp_file.exists():
        try:
            golden_pairs = json.loads(_gp_file.read_text(encoding="utf-8"))
        except Exception:
            golden_pairs = []

    try:
        from src.ingestion.area_designation_pipeline import get_pending_proposals as _gpp
        pending_proposals = _gpp()
    except Exception:
        pending_proposals = []

    passed_cnt = sum(1 for g in golden_pairs if (g.get("last_eval") or {}).get("match") is True)
    failed_cnt = sum(1 for g in golden_pairs if (g.get("last_eval") or {}).get("match") is False)
    needs_review_cnt = sum(1 for g in golden_pairs if g.get("invalidated"))
    _red_pct = int(red_wins / red_target * 100) if red_target else 0
    _high_stale = [s for s in stale_cases if s.get("sensitivity") == "high"]

    # ══════════════════════════════════════════════════════════════════════════
    # 서브탭 1: 대시보드
    # ══════════════════════════════════════════════════════════════════════════
    with sub_dash:
        _law_lbl,  _law_sk,  _law_rel  = _fmt_freshness(_ROOT / "data" / "processed" / "all_chunks.json")
        _nts_lbl,  _nts_sk,  _nts_rel  = _fmt_freshness(_ROOT / "data" / "rulings" / "nts")
        _dec_lbl,  _dec_sk,  _dec_rel  = _fmt_freshness(_ROOT / "data" / "rulings" / "decisions")
        _pdf_lbl,  _pdf_sk,  _pdf_rel  = _fmt_freshness(_ROOT / "data" / "rulings" / "pdf")
        _moef_lbl, _moef_sk, _moef_rel = _fmt_freshness(_ROOT / "data" / "rulings" / "moef")
        _ni_lbl,   _ni_sk,   _ni_rel   = _fmt_freshness(_ROOT / "data" / "rulings" / "nts_interp")

        _ruling_statuses = [_nts_sk, _dec_sk, _pdf_sk, _moef_sk, _ni_sk]
        _ruling_overall = "error" if "error" in _ruling_statuses else ("warn" if "warn" in _ruling_statuses else "ok")
        _area_status = "ok" if (area_total > 0 and not pending_proposals) else ("warn" if area_total > 0 else "error")
        _ft_status = "ok" if (red_wins >= red_target and red_target > 0) else ("warn" if red_wins > 0 else "error")

        _alerts: list[tuple[str, str]] = []
        if img_alerts:
            _alerts.append(("error", f"🔴 별표·이미지 테이블 불일치 {len(img_alerts)}건 → 🔔 개정감지 탭 확인"))
        if amd_anomalies:
            _alerts.append(("error", f"🔴 개정 경계 케이스 이상 {len(amd_anomalies)}건 → 🔔 개정감지 탭 확인"))
        if _high_stale:
            _alerts.append(("error", f"🔴 HIGH stale {len(_high_stale)}건 → 전문가 즉시 검토"))
        if needs_review_cnt:
            _alerts.append(("warning", f"⚠️ 골든셋 재검토 {needs_review_cnt}건 (법령 개정 영향) → 📋 시나리오 탭"))
        if failed_cnt:
            _alerts.append(("warning", f"⚠️ 시나리오 평가 실패 {failed_cnt}건 → 📋 시나리오 탭"))
        if pending_proposals:
            _alerts.append(("warning", f"⚠️ 지역 승인 대기 {len(pending_proposals)}건 → 🗺️ 지역 탭"))

        if _alerts:
            for _lvl, _msg in _alerts:
                if _lvl == "error":
                    st.error(_msg)
                else:
                    st.warning(_msg)
        else:
            st.success("✅ 감지된 이상 없음 — 수집 상태는 아래 카드를 확인하세요.")

        st.markdown("<br>", unsafe_allow_html=True)

        _c1, _c2, _c3, _c4 = st.columns(4)
        _sys_card(_c1, "⚖️", "법령 조문", f"{len(law_rows)}개 법령", f"{_law_lbl} · {_law_rel}", _law_sk)
        _ruling_lbl_map = {"ok": "✅ 현행 검증 완료", "warn": "⚠️ 갱신 확인 필요", "error": "❌ 데이터 없음/오래됨"}
        _sys_card(_c2, "📋", "유권해석 6종", "국세청·심판원·PDF·기재부·법령해석", _ruling_lbl_map.get(_ruling_overall, ""), _ruling_overall)
        _sys_card(_c3, "🗺️", "지역데이터", f"{area_active}건 현행", f"대기 {len(pending_proposals)}건 · {_fmt_mtime(_ROOT / 'data' / 'area_designations' / 'manual_table.json')}", _area_status)
        _sys_card(_c4, "🤖", "AI 학습", f"{red_wins}/{red_target}건", f"Red Win {_red_pct}% · {'완료' if red_wins >= red_target else '미완'}", _ft_status)

        st.divider()
        st.markdown("##### 📡 파이프라인 수집 현황")

        _pipe_defs = [
            ("법령 조문",       "소득세법·시행령·조특법 등 9종",                   _ROOT / "data" / "processed" / "all_chunks.json"),
            ("국세청 질의회신", "hotissue·qt·ic·pd 4유형 (API 필터 없음)",          _ROOT / "data" / "rulings" / "nts"),
            ("심판청구 결정례", "조세심판원 (서버 사이드 필터: 양도)",               _ROOT / "data" / "rulings" / "decisions"),
            ("해석례 PDF",      "국세청 PDF 공개자료 (수동 등록)",                   _ROOT / "data" / "rulings" / "pdf"),
            ("기재부 법령해석", "전체 2,305건 수집 후 양도 클라이언트 필터",         _ROOT / "data" / "rulings" / "moef"),
            ("국세청 법령해석", "서버 필터: 양도·증여·상속·상생임대·임대주택",       _ROOT / "data" / "rulings" / "nts_interp"),
            ("판례",            "대법원·고등법원 (구현전)",                          None),
        ]
        _pipe_rows = []
        for _plabel, _pdetail, _ppath in _pipe_defs:
            _slabel, _skey, _rel = _fmt_freshness(_ppath)
            _cnt = "—"
            if _ppath is not None:
                _pp = Path(_ppath)
                if _pp.exists():
                    if _pp.is_dir():
                        _cnt = f"{len(list(_pp.glob('*.json')))}건"
                    else:
                        try:
                            _cnt = f"{len(json.loads(_pp.read_text(encoding='utf-8')))}건"
                        except Exception:
                            _cnt = "—"
            _pipe_rows.append({"유형": _plabel, "설명": _pdetail, "상태": _slabel, "업데이트": _rel, "수집량": _cnt})

        _debate_lbl2 = f"✅ {debate_cnt}건" if debate_cnt > 0 else "⚠️ 없음"
        _pipe_rows.append({"유형": "케이스 생성", "설명": "논쟁 → 골든셋 승격", "상태": _debate_lbl2, "업데이트": debate_mtime, "수집량": f"{debate_cnt}건"})
        _ft_lbl2 = "✅ 완료" if (red_wins >= red_target and red_target > 0) else (f"⚠️ 진행중 {red_wins}/{red_target}" if red_wins > 0 else "🔘 대기 중")
        _pipe_rows.append({"유형": "AI 학습 (파인튜닝)", "설명": f"Red Win 목표 {red_target}건", "상태": _ft_lbl2, "업데이트": "—", "수집량": f"{_red_pct}%"})

        st.dataframe(
            pd.DataFrame(_pipe_rows),
            use_container_width=True,
            hide_index=True,
            column_config={
                "유형": st.column_config.TextColumn("유형", width="medium"),
                "설명": st.column_config.TextColumn("설명", width="large"),
                "상태": st.column_config.TextColumn("상태", width="medium"),
                "업데이트": st.column_config.TextColumn("업데이트", width="small"),
                "수집량": st.column_config.TextColumn("수집량", width="small"),
            },
        )

        change_log_preview = _load_change_log(3)
        if change_log_preview:
            st.markdown("**최근 개정 감지**")
            for _rec in change_log_preview:
                st.caption(f"{_rec.get('detected_at', '')[:16]}  {_rec.get('law_name', _rec.get('event', ''))}")

    # ══════════════════════════════════════════════════════════════════════════
    # 서브탭 2: 법령 (전체 스프레드시트, 필터 없음)
    # ══════════════════════════════════════════════════════════════════════════
    with sub_law:
        st.caption("법령 API에서 수집한 전체 재료. API 수집 시 적용된 필터는 각 섹션 배너에 표기.")

        st.markdown("#### ⚖️ 법령 조문")
        _law_rows_d = _load_law_inventory()
        if not _law_rows_d:
            st.info("법령 데이터 없음 — `python -m src.ingestion.collect`")
        else:
            st.dataframe(
                pd.DataFrame(_law_rows_d),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "법령명":     st.column_config.TextColumn("법령명", width="large"),
                    "분류":       st.column_config.TextColumn("분류", width="small"),
                    "MST":        st.column_config.TextColumn("MST", width="small"),
                    "총 청크":    st.column_config.NumberColumn("총 청크", format="%d"),
                    "본칙":       st.column_config.NumberColumn("본칙", format="%d"),
                    "부칙":       st.column_config.NumberColumn("부칙", format="%d"),
                    "최신 시행일": st.column_config.TextColumn("최신 시행일", width="medium"),
                    "마지막 수집": st.column_config.TextColumn("마지막 수집", width="medium"),
                },
            )

        st.markdown("#### 📋 국세청 질의회신")
        st.info("ℹ️ **API 필터 없음** — 전체 수집. 임베딩 시 양도소득세 관련 청크만 Pinecone 색인.")
        _nts_dir = _ROOT / "data" / "rulings" / "nts"
        _nts_files = sorted(_nts_dir.glob("*.json"), reverse=True) if _nts_dir.exists() else []
        if not _nts_files:
            st.caption("데이터 없음 — `python -m src.ingestion.collect_rulings_nts --resume`")
        else:
            _nts_rows = []
            for _f in _nts_files[:300]:
                try:
                    _d = json.loads(_f.read_text(encoding="utf-8"))
                    _items = _d if isinstance(_d, list) else [_d]
                    for _item in _items[:3]:
                        _nts_rows.append({"문서번호": _item.get("doc_id") or _item.get("ruling_id", ""), "제목": (_item.get("title") or "")[:70], "유형": _item.get("type", ""), "일자": _item.get("date", "")})
                except Exception:
                    pass
            st.caption(f"파일 {len(_nts_files)}건 | {len(_nts_rows)}건 미리보기")
            if _nts_rows:
                st.dataframe(pd.DataFrame(_nts_rows), use_container_width=True, hide_index=True)

        st.markdown("#### ⚖️ 심판청구 결정례")
        st.warning("⚠️ **서버 사이드 필터 적용됨** — 수집 키워드: `양도`  \n→ 증여·상속·임대 결정례 현재 미수집. 추가 키워드 필요 시 재수집.")
        _dec_dir = _ROOT / "data" / "rulings" / "decisions"
        _dec_files = sorted(_dec_dir.glob("*.json"), reverse=True) if _dec_dir.exists() else []
        if not _dec_files:
            st.caption("데이터 없음 — `python -m src.ingestion.collect_rulings_decisions --resume`")
        else:
            _dec_rows = []
            for _f in _dec_files[:300]:
                try:
                    _d = json.loads(_f.read_text(encoding="utf-8"))
                    _items = _d if isinstance(_d, list) else [_d]
                    for _item in _items[:3]:
                        _dec_rows.append({"사건번호": _item.get("case_id") or _item.get("ruling_id", ""), "제목": (_item.get("title") or "")[:70], "결정유형": _item.get("decision_type", ""), "결정일": _item.get("date", "")})
                except Exception:
                    pass
            st.caption(f"파일 {len(_dec_files)}건 | {len(_dec_rows)}건 미리보기")
            if _dec_rows:
                st.dataframe(pd.DataFrame(_dec_rows), use_container_width=True, hide_index=True)

        st.markdown("#### 📄 해석례 PDF")
        st.info("ℹ️ **수동 등록** — 국세청 PDF 공개자료 직접 수집.")
        _pdf_dir = _ROOT / "data" / "rulings" / "pdf"
        _pdf_files = sorted(_pdf_dir.glob("*.json"), reverse=True) if _pdf_dir.exists() else []
        if not _pdf_files:
            st.caption("데이터 없음 — `python -m src.ingestion.embed_rulings pdf`")
        else:
            _pdf_rows = []
            for _f in _pdf_files[:100]:
                try:
                    _d = json.loads(_f.read_text(encoding="utf-8"))
                    _items = _d if isinstance(_d, list) else [_d]
                    for _item in _items[:2]:
                        _pdf_rows.append({"파일명": _f.stem, "제목": (_item.get("title") or "")[:60], "페이지": _item.get("page", "")})
                except Exception:
                    pass
            st.caption(f"파일 {len(_pdf_files)}건 | {len(_pdf_rows)}건 미리보기")
            if _pdf_rows:
                st.dataframe(pd.DataFrame(_pdf_rows), use_container_width=True, hide_index=True)

        st.markdown("#### 🏛️ 기재부 법령해석")
        st.warning("⚠️ **클라이언트 필터 적용됨** — 전체 2,305건 수집 후 안건명 기준 `양도` 키워드 클라이언트 필터  \n→ 전체 수집이므로 새 키워드 추가 시 재필터만 하면 됨.")
        _moef_dir = _ROOT / "data" / "rulings" / "moef"
        _moef_files = sorted(_moef_dir.glob("*.json"), reverse=True) if _moef_dir.exists() else []
        if not _moef_files:
            st.caption("데이터 없음 — `python -m src.ingestion.collect_rulings_moef --resume`")
        else:
            _moef_rows = []
            for _f in _moef_files[:200]:
                try:
                    _d = json.loads(_f.read_text(encoding="utf-8"))
                    if isinstance(_d, dict):
                        _moef_rows.append({"문서번호": _d.get("doc_number") or _d.get("id", ""), "제목": (_d.get("title") or "")[:70], "해석기관": _d.get("agency", ""), "해석일자": _d.get("issued_at", "")})
                except Exception:
                    pass
            st.caption(f"파일 {len(_moef_files)}건 | {len(_moef_rows)}건 미리보기")
            if _moef_rows:
                st.dataframe(pd.DataFrame(_moef_rows), use_container_width=True, hide_index=True)

        st.markdown("#### 📘 국세청 법령해석")
        st.warning(
            "⚠️ **서버 사이드 키워드 필터 적용됨** — 현재 수집 키워드:  \n"
            "`양도` 24,408건 / `증여` 8,819건 / `상속` 7,743건 / `상생임대` 72건 / `임대주택` 1,534건  \n"
            "→ 새 키워드 추가 시 `--keywords <키워드>` 옵션으로 재수집 필요."
        )
        _ni_dir = _ROOT / "data" / "rulings" / "nts_interp"
        _ni_files = sorted(_ni_dir.glob("*.json"), reverse=True) if _ni_dir.exists() else []
        if not _ni_files:
            st.caption("데이터 없음 — `python -m src.ingestion.collect_rulings_nts_interp --resume`")
        else:
            _ni_cat_counts: dict[str, int] = {}
            _ni_rows = []
            for _f in _ni_files:
                try:
                    _d = json.loads(_f.read_text(encoding="utf-8"))
                    if isinstance(_d, dict):
                        _cat = _d.get("tax_category", "")
                        _ni_cat_counts[_cat] = _ni_cat_counts.get(_cat, 0) + 1
                except Exception:
                    pass
            for _f in _ni_files[:200]:
                try:
                    _d = json.loads(_f.read_text(encoding="utf-8"))
                    if isinstance(_d, dict):
                        _ni_rows.append({"문서번호": _d.get("doc_number") or _d.get("id", ""), "제목": (_d.get("title") or "")[:70], "세목": _d.get("tax_category", ""), "해석기관": _d.get("agency", ""), "해석일자": _d.get("issued_at", "")})
                except Exception:
                    pass
            _cat_str = " / ".join(f"{k} {v}건" for k, v in sorted(_ni_cat_counts.items()))
            st.caption(f"전체 {len(_ni_files)}건 (세목: {_cat_str or '—'}) | {len(_ni_rows)}건 미리보기")
            if _ni_rows:
                st.dataframe(pd.DataFrame(_ni_rows), use_container_width=True, hide_index=True)

        st.markdown("#### ⚖️ 판례")
        st.error("🚧 **(구현전)** — 대법원 종합법률정보 수집 미구현. 추후 `data/rulings/precedents/` 경로로 추가 예정.")

    # ══════════════════════════════════════════════════════════════════════════
    # 서브탭 3: 지역
    # ══════════════════════════════════════════════════════════════════════════
    with sub_area:
        REG_FILE = _ROOT / "data" / "area_designations" / "manual_table.json"
        _TYPE_COLOR_CSS = {"조정대상지역": "#FF8C00", "투기과열지구": "#DC3232", "투기지역": "#9B59B6", "토지거래허가구역": "#1E90FF"}

        def _badge(area_type: str) -> str:
            color = _TYPE_COLOR_CSS.get(area_type, "#888")
            return f'<span style="background:{color};color:#fff;padding:2px 8px;border-radius:10px;font-size:12px;font-weight:600;">{area_type}</span>'

        c_s1, c_s2, c_s3 = st.columns(3)
        c_s1.info("**출처** 수동 관리 (manual_table.json)")
        c_s2.info(f"**마지막 수정** {_fmt_mtime(REG_FILE)}")
        c_s3.info("**자동 감지** `area_designation_pipeline.py`")
        st.divider()

        try:
            from src.ingestion.area_designation_pipeline import get_pending_proposals, apply_proposal, run_pipeline
            _pipeline_ok = True
        except Exception:
            _pipeline_ok = False

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

        with col_left:
            st.markdown("### 📋 현행 지정 현황")
            sub_active, sub_released = st.tabs([f"현행 지정 ({len(active_reg)})", f"해제 이력 ({len(released_reg)})"])
            with sub_active:
                if active_reg:
                    from collections import defaultdict as _dd
                    _region_map: dict = _dd(list)
                    for r in active_reg:
                        _region_map[r.get("region", "")].append(r)
                    rows_a = []
                    _type_emoji = {"조정대상지역": "🟠", "투기과열지구": "🔴", "투기지역": "🟣", "토지거래허가구역": "🔵"}
                    for region in sorted(_region_map):
                        regs = _region_map[region]
                        types_str = "  ".join(
                            f"{_type_emoji.get(r.get('area_type', ''), '●')} {r.get('area_type', '')}"
                            for r in sorted(regs, key=lambda x: x.get("area_type", ""))
                        )
                        earliest = min(r.get("designated_at", "") for r in regs)
                        rows_a.append({"지역": region, "지정 유형": types_str, "최초 지정일": earliest})
                    st.dataframe(pd.DataFrame(rows_a), use_container_width=True, hide_index=True)
                else:
                    st.info("현행 지정된 지역이 없습니다.")
            with sub_released:
                if released_reg:
                    rows_r = [
                        {"지역": r.get("region", ""), "구역 유형": r.get("area_type", ""),
                         "지정일": r.get("designated_at", ""), "해제일": r.get("released_at", ""),
                         "고시 번호": r.get("announcement_no", "")}
                        for r in sorted(released_reg, key=lambda x: x.get("released_at", ""), reverse=True)
                    ]
                    st.dataframe(pd.DataFrame(rows_r), use_container_width=True, hide_index=True)
                else:
                    st.info("해제 이력이 없습니다.")

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
                    with st.expander(f"{priority} {detected_at} — {len(candidates)}건 (신뢰도 {conf_avg:.0%})", expanded=pidx == 0):
                        for c in candidates:
                            action = "🔓 해제" if c.get("released_at") else "🔒 신규"
                            region = c.get("region") or "(지역 미추출)"
                            st.markdown(
                                f"**{action}** `{c.get('area_type', '')}` — {region}  \n"
                                f"고시: {c.get('announcement_no', '—')} | {c.get('source_name', '')} | {c.get('confidence', 0):.0%}"
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
                                proposal_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                                st.rerun()
                            except Exception as e:
                                st.error(f"실패: {e}")

            st.divider()
            st.caption("⚠️ 이 데이터는 수동 관리 파일입니다. 실제 고시와 반드시 대조하세요.")
            st.caption("출처: 국토교통부(molit.go.kr) / 기획재정부(moef.go.kr) / 서울특별시(seoul.go.kr)")

    # ══════════════════════════════════════════════════════════════════════════
    # 서브탭 4: 개정감지 · 조문검색
    # ══════════════════════════════════════════════════════════════════════════
    with sub_monitor:
        _img_alerts_m = _load_image_alerts()
        _amd_anomalies_m = _load_amendment_test_results()

        st.markdown("### 📋 별표·이미지 테이블 반영 현황")
        st.caption("법령 API 이미지로 제공되는 장기보유특별공제율 표1/표2 등의 레지스트리 반영 상태")

        try:
            from src.domain.tax_constants import _REGISTRY
            _table_rows_m = []
            for _tkey in ["LONG_TERM_DEDUCTION_RATE_TABLE1", "LONG_TERM_DEDUCTION_RATE_TABLE2"]:
                _versions = _REGISTRY.get(_tkey, [])
                if _versions:
                    _v = max(_versions, key=lambda x: x.effective_from)
                    _val = _v.value
                    _table_rows_m.append({
                        "상수 키": _tkey,
                        "설명": "장기보유특별공제율 표1 (일반)" if "TABLE1" in _tkey else "장기보유특별공제율 표2 (1세대1주택)",
                        "시행일": _v.effective_from.strftime("%Y-%m-%d"),
                        "행 수": len(_val) if isinstance(_val, dict) else "—",
                        "검토 필요": "⚠️ 예" if _v.manual_review_required else "✅ 정상",
                        "법령조문": _v.source_law,
                    })
            if _img_alerts_m:
                st.error(f"🔴 별표 불일치 {len(_img_alerts_m)}건 — tax_constants.py 확인 후 ConstantVersion 추가 필요")
                for _alert in _img_alerts_m[:5]:
                    with st.expander(f"⚠️ {_alert.get('law_name')} {_alert.get('table_id')} 불일치"):
                        _diff = _alert.get("diff", {})
                        if _diff:
                            st.dataframe(pd.DataFrame([
                                {"년수": k, "상태": v.get("status"), "레지스트리": v.get("current"), "추출값": v.get("extracted")}
                                for k, v in sorted(_diff.items(), key=lambda x: int(x[0]))
                            ]), use_container_width=True, hide_index=True)
                        st.caption(f"파일: {_alert.get('_file', '—')}")
            elif _table_rows_m:
                st.success("✅ 별표 검증 이상 없음")
            else:
                st.info("별표 테이블 상수 없음 (TaxConstantsRegistry 확인)")
            if _table_rows_m:
                st.dataframe(pd.DataFrame(_table_rows_m), use_container_width=True, hide_index=True)
        except Exception as _e:
            st.warning(f"레지스트리 로드 실패: {_e}")

        if _amd_anomalies_m:
            st.error(f"🚨 개정 경계 케이스 verdict 불일치 {len(_amd_anomalies_m)}건")
            with st.expander("불일치 상세"):
                st.dataframe(pd.DataFrame([
                    {"케이스 ID": a.get("case_id"), "설명": a.get("description", "")[:40],
                     "법령": ", ".join(a.get("_changed_laws", [])), "판단 결과": a.get("verdict"), "예상 결과": a.get("expected_verdict")}
                    for a in _amd_anomalies_m[:20]
                ]), use_container_width=True, hide_index=True)

        st.divider()
        st.markdown("### 🔔 법령 개정 감지 이력")
        _change_log_m = _load_change_log(15)
        if _change_log_m:
            _log_rows_m = []
            for _rec in _change_log_m:
                _event = _rec.get("event", "law_change")
                _detected = _rec.get("detected_at", "")[:16]
                if _event == "golden_stale_candidates":
                    _laws = ", ".join(_rec.get("triggered_by_laws", []))
                    _desc = f"Stale 후보 {len(_rec.get('stale_cases', []))}건"
                elif _event == "amendment_test_results":
                    _laws, _desc = "", f"경계케이스 {_rec.get('total_cases', 0)}건, 이상 {_rec.get('anomaly_count', 0)}건"
                elif _event == "image_table_verification":
                    _laws, _desc = "", f"별표 검증 ✅{_rec.get('verified_count', 0)} / 🔴{_rec.get('alert_count', 0)}"
                else:
                    _laws = _rec.get("law_name", "")
                    _desc = f"신규 MST {len(_rec.get('new_msts', []))}건"
                _log_rows_m.append({"감지 시각": _detected, "법령": _laws, "내용": _desc})
            st.dataframe(pd.DataFrame(_log_rows_m), use_container_width=True, hide_index=True)
        else:
            st.info("개정 감지 이력 없음 — `python -m scripts.detect_law_changes` 실행 후 표시됩니다.")

        st.divider()
        st.markdown("### 🔍 조문 검색")
        st.caption("키워드로 검색해서 법령이 올바르게 수집·색인됐는지 확인합니다.")
        srch_query = st.text_input("검색 쿼리 (한국어 자유 입력)", key="law_search_query")
        sc1, sc2, sc3 = st.columns([1, 1, 1])
        with sc1:
            srch_run = st.button("🔍 검색", type="primary", key="law_search_btn")
        with sc2:
            srch_top_k = st.slider("후보 수 (top_k)", 5, 50, 20, key="law_search_top_k")
        with sc3:
            srch_rerank_n = st.slider("최종 조문 수 (rerank_top_n)", 1, 10, 5, key="law_search_rerank_n")
        if srch_run and srch_query:
            try:
                from src.rag import retrieve_tax_law
                with st.spinner("검색 중..."):
                    chunks = retrieve_tax_law(srch_query, top_k=srch_top_k, rerank_top_n=srch_rerank_n)
                st.success(f"{len(chunks)}개 조문 검색됨")
                for i, c in enumerate(chunks, 1):
                    with st.expander(f"[{i}] {c.law_name} 제{c.article_number}조  score={c.score:.3f}"):
                        st.text(c.full_text)
                        col_a, col_b = st.columns(2)
                        col_a.caption(f"chunk_id: `{c.id}`")
                        col_b.caption(f"시행: {c.effective_date} ~ {c.expiration_date}" if hasattr(c, "effective_date") else "")
            except Exception as e:
                st.error(f"검색 실패: {e}")
        elif srch_run:
            st.warning("쿼리를 입력하세요.")

# ══════════════════════════════════════════════════════════════════════════════

with tab_scenarios:
    import pandas as pd

    _GOLDEN_FILE = _ROOT / "data" / "golden" / "qa_pairs.json"
    st.subheader("📋 시나리오 평가 현황")

    if not _GOLDEN_FILE.exists():
        st.warning("data/golden/qa_pairs.json 파일이 없습니다.")
    else:
        try:
            sc_pairs = json.loads(_GOLDEN_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            st.error("qa_pairs.json 파싱 오류")
            sc_pairs = []

        latest_report_sc = _load_golden_eval_latest()
        last_run_sc = latest_report_sc.get("run_at", "")
        last_run_sc_fmt = last_run_sc[:16].replace("T", " ") if last_run_sc else "미실행"

        # ── 요약 메트릭 ──────────────────────────────────────────────────────
        sc_total = len(sc_pairs)
        sc_passed = sum(1 for g in sc_pairs if (g.get("last_eval") or {}).get("match") is True)
        sc_failed = sum(1 for g in sc_pairs if (g.get("last_eval") or {}).get("match") is False)
        sc_needs_review = sum(1 for g in sc_pairs if g.get("invalidated"))
        sc_not_run = sum(1 for g in sc_pairs if not g.get("last_eval"))
        sc_has_expected = sum(1 for g in sc_pairs if g.get("expected_verdict") or g.get("verdict"))
        sc_acc_str = f"{sc_passed}/{sc_has_expected} ({sc_passed/sc_has_expected*100:.0f}%)" if sc_has_expected else "—"

        m1, m2, m3, m4, m5, m6 = st.columns(6)
        m1.metric("총 케이스", sc_total)
        m2.metric("✅ PASS", sc_passed)
        m3.metric("❌ FAIL", sc_failed)
        m4.metric("⚠️ 재검토", sc_needs_review)
        m5.metric("정확도", sc_acc_str)
        m6.metric("마지막 평가", last_run_sc_fmt)

        st.divider()

        # ── 필터 라디오 ──────────────────────────────────────────────────────
        filter_choice = st.radio(
            "보기",
            ["전체", "미검증", "검증됨", "재검토필요"],
            horizontal=True,
            key="sc_filter",
        )

        if filter_choice == "미검증":
            filtered_pairs = [g for g in sc_pairs if not g.get("last_eval")]
        elif filter_choice == "검증됨":
            filtered_pairs = [g for g in sc_pairs if g.get("last_eval") and not g.get("invalidated")]
        elif filter_choice == "재검토필요":
            filtered_pairs = [
                g for g in sc_pairs
                if g.get("invalidated") or (g.get("last_eval") or {}).get("match") is False
            ]
        else:
            filtered_pairs = sc_pairs

        # ── 상태 테이블 ──────────────────────────────────────────────────────
        if not sc_pairs:
            st.info("골든셋이 비어 있습니다.")
        else:
            sc_rows = []
            for g in filtered_pairs:
                ev = g.get("last_eval") or {}
                exp_v = g.get("expected_verdict") or g.get("verdict") or "—"
                actual_v = ev.get("verdict", "—")
                conf = ev.get("confidence")
                run_at = ev.get("run_at", "")
                run_at_fmt = f"{run_at[:4]}-{run_at[4:6]}-{run_at[6:8]}" if len(run_at) >= 8 else "—"
                sc_rows.append({
                    "ID": (g.get("id") or g.get("case_id", ""))[:10],
                    "설명": g.get("description", "")[:45],
                    "출처": g.get("source", "manual"),
                    "예상판결": exp_v,
                    "실제판결": actual_v,
                    "신뢰도": f"{conf:.2f}" if conf is not None else "—",
                    "상태": _status_badge(g),
                    "평가일": run_at_fmt,
                })

            st.caption(f"{len(filtered_pairs)}건 표시 중")
            sc_df = pd.DataFrame(sc_rows)
            st.dataframe(sc_df, use_container_width=True, hide_index=True)

            # ── 실패·재검토 케이스 상세 ──────────────────────────────────────
            problem_cases_sc = [
                g for g in filtered_pairs
                if g.get("invalidated") or (g.get("last_eval") or {}).get("match") is False
            ]
            if problem_cases_sc:
                with st.expander(f"⚠️ 조치 필요 케이스 ({len(problem_cases_sc)}건)", expanded=True):
                    for g in problem_cases_sc:
                        ev = g.get("last_eval") or {}
                        badge = _status_badge(g)
                        exp_v = g.get("expected_verdict") or g.get("verdict") or "—"
                        gid = (g.get("id") or g.get("case_id", ""))[:10]
                        st.markdown(
                            f"**{badge}** `{gid}` — {g.get('description', '')}  \n"
                            f"예상: **{exp_v}** → 실제: **{ev.get('verdict', '—')}** "
                            f"(신뢰도 {ev.get('confidence', 0):.2f})"
                        )
                        if g.get("invalidated"):
                            deps = g.get("law_deps", [])
                            st.caption(f"법령 개정 영향: {', '.join(deps) or '알 수 없음'}")
                        if ev.get("error"):
                            st.caption(f"오류: {ev['error']}")
                        st.divider()

            if sc_not_run > 0:
                st.info(f"미평가 케이스 {sc_not_run}건 — `python -m scripts.run_golden_eval` 으로 평가를 실행하세요.")
