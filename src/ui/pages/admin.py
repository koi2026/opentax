"""
어드민 페이지 — 대시보드 / 법령 / 지역데이터 / 시나리오.
판단 로직 없음. 표시·실행·통계 전용.
"""
from __future__ import annotations

import html
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import streamlit as st


st.set_page_config(page_title="어드민", page_icon="🛠️", layout="wide")

# ── 세션 상태 ──────────────────────────────────────────────────────────────────

for key, default in [
    ("admin_result", None),
    ("admin_running_idx", None),
    ("admin_command_result", None),
    ("admin_command_running", False),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ── 헬퍼: 공통 ────────────────────────────────────────────────────────────────

_ROOT = Path(__file__).parent.parent.parent

def _fmt_mtime(path: Path) -> str:
    if not path.exists():
        return "—"
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")


def _fmt_date8(v) -> str:
    s = str(int(v)) if v else ""
    if len(s) == 8:
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    return s or "—"


def _command_text(args: list[str]) -> str:
    return " ".join(["python", "-m", *args])


def _path_status(path: Path | None) -> str:
    if path is None:
        return "상태 파일 없음"
    if isinstance(path, str):
        path = Path(path)
    if not path.is_absolute():
        path = _ROOT / path
    if path.is_dir():
        files = list(path.glob("*.json"))
        if not files:
            return f"데이터 없음 · {path.relative_to(_ROOT)}"
        latest = max(files, key=lambda f: f.stat().st_mtime)
        return f"{len(files):,}개 파일 · 최신 {_fmt_mtime(latest)}"
    if path.exists():
        return f"수정 {_fmt_mtime(path)} · {path.relative_to(_ROOT)}"
    return f"데이터 없음 · {path.relative_to(_ROOT)}"


def _render_command_overlay(
    placeholder,
    command: dict,
    log_lines: list[str],
    started_at: datetime,
    returncode: int | None = None,
) -> None:
    elapsed_s = time.monotonic() - st.session_state.get("admin_command_t0", time.monotonic())
    state = "실행 중" if returncode is None else ("완료" if returncode == 0 else f"실패 exit {returncode}")
    log_text = "\n".join(log_lines[-300:]) or "로그 대기 중..."
    escaped_log = html.escape(log_text)
    escaped_label = html.escape(command["label"])
    escaped_cmd = html.escape(_command_text(command["args"]))
    started = html.escape(started_at.strftime("%Y-%m-%d %H:%M:%S"))
    placeholder.markdown(
        f"""
<style>
@media (max-width: 720px) {{
  .admin-command-overlay {{
    padding-left: 24px !important;
    padding-right: 24px !important;
  }}
}}
</style>
<div style="
    position: fixed;
    inset: 0;
    z-index: 999999;
    background: rgba(0, 0, 0, 0.72);
    color: #f5f5f5;
    padding: 32px 48px;
    box-sizing: border-box;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
" class="admin-command-overlay">
<div style="max-width:1120px; margin:0 auto;">
  <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:24px; margin-bottom:18px;">
    <div>
      <div style="font-size:24px; font-weight:800; margin-bottom:8px;">{escaped_label}</div>
      <div style="color:#bdbdbd; font-size:13px;">{escaped_cmd}</div>
    </div>
    <div style="text-align:right; color:#e0e0e0; font-size:13px; line-height:1.7;">
      <div>상태: <strong>{state}</strong></div>
      <div>시작: {started}</div>
      <div>경과: {elapsed_s:.1f}s</div>
    </div>
  </div>
  <pre style="
      height: calc(100vh - 170px);
      overflow: auto;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      word-break: break-word;
      background: #050505;
      border: 1px solid #333;
      border-radius: 8px;
      padding: 18px;
      margin: 0;
      color: #d7ffd9;
      font: 13px/1.55 ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', monospace;
  ">{escaped_log}</pre>
</div>
</div>
""",
        unsafe_allow_html=True,
    )


def _run_admin_command(command: dict, overlay_placeholder) -> dict:
    import requests
    from src.config import API_BASE_URL

    started = datetime.now()
    t0 = time.monotonic()
    st.session_state.admin_command_t0 = t0
    result: dict = {
        "label": command["label"],
        "cmd": _command_text(command["args"]),
        "started_at": started.strftime("%Y-%m-%d %H:%M:%S"),
        "finished_at": "",
        "elapsed_s": 0.0,
        "returncode": None,
        "timed_out": False,
    }
    log_lines = [f"$ {_command_text(command['args'])}"]
    _render_command_overlay(overlay_placeholder, command, log_lines, started)
    try:
        base_url = API_BASE_URL.rstrip("/")
        response = requests.post(
            f"{base_url}/api/v1/admin/jobs",
            json={
                "command_key": command["key"],
                "confirm_paid": bool(command.get("_paid_confirmed")),
            },
            timeout=20,
        )
        response.raise_for_status()
        job = response.json()
        job_id = job["job_id"]
        while True:
            poll = requests.get(f"{base_url}/api/v1/admin/jobs/{job_id}", timeout=20)
            poll.raise_for_status()
            job = poll.json()
            log_lines = job.get("log_lines") or log_lines
            result["returncode"] = job.get("returncode")
            result["timed_out"] = bool(job.get("timed_out"))
            result["elapsed_s"] = float(job.get("elapsed_s") or (time.monotonic() - t0))
            if job.get("started_at"):
                result["started_at"] = str(job["started_at"])[:19].replace("T", " ")
            if job.get("finished_at"):
                result["finished_at"] = str(job["finished_at"])[:19].replace("T", " ")
            _render_command_overlay(overlay_placeholder, command, log_lines, started)
            if job.get("status") in ("succeeded", "failed"):
                break
            time.sleep(0.5)
        if result["returncode"] is None:
            result["returncode"] = 0 if job.get("status") == "succeeded" else -1
        _render_command_overlay(overlay_placeholder, command, log_lines, started, int(result["returncode"]))
        time.sleep(0.7)
    except requests.HTTPError as exc:
        result["returncode"] = -1
        detail = ""
        try:
            detail = f" · {exc.response.json().get('detail')}"
        except Exception:
            detail = f" · {exc.response.text[:160]}" if exc.response is not None else ""
        log_lines.append(f"API 실행 요청 실패: {exc}{detail}")
        log_lines.append(f"API_BASE_URL={API_BASE_URL} 및 API 서버 실행 상태를 확인하세요.")
        _render_command_overlay(overlay_placeholder, command, log_lines, started, result["returncode"])
        time.sleep(0.7)
    except Exception as exc:
        result["returncode"] = -1
        log_lines.append(f"API 연결/실행 오류: {exc}")
        log_lines.append("API_BASE_URL 설정과 API 서버 실행 상태를 확인하세요.")
        _render_command_overlay(overlay_placeholder, command, log_lines, started, result["returncode"])
        time.sleep(0.7)
    finally:
        result["finished_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        result["elapsed_s"] = time.monotonic() - t0
        overlay_placeholder.empty()
    return result


def _render_command_result(result: dict | None) -> None:
    if not result:
        return
    elapsed = f"{result.get('elapsed_s', 0):.1f}s"
    returncode = result.get("returncode")
    if returncode == 0:
        st.success(f"`{result.get('label')}` 완료 · {elapsed}")
    else:
        st.error(f"`{result.get('label')}` 실패 · exit {returncode} · {elapsed}")
    meta_cols = st.columns(3)
    meta_cols[0].caption(f"시작: {result.get('started_at', '—')}")
    meta_cols[1].caption(f"종료: {result.get('finished_at', '—')}")
    meta_cols[2].caption(f"명령: `{result.get('cmd', '')}`")


def _render_command_card(command: dict, paid_confirmed: bool, pc_stats: dict[str, int]) -> None:
    is_paid = bool(command.get("paid"))
    disabled = bool(st.session_state.admin_command_running) or (is_paid and not paid_confirmed)
    status = _path_status(command.get("path"))
    ns = command.get("namespace")
    if ns:
        status = f"{status} · Pinecone {pc_stats.get(ns, 0):,}개"
    phase_label = {
        "collect": "로컬 데이터 생성",
        "upload": "Pinecone 업로드/API 비용 가능",
        "automation": "수집+업로드 혼합",
    }.get(command.get("phase"), "명령")

    with st.container(border=True):
        c1, c2 = st.columns([3, 1])
        with c1:
            st.markdown(f"**{command['label']}**")
            st.caption(command.get("description", ""))
            st.code(_command_text(command["args"]), language="bash")
            st.caption(status)
        with c2:
            st.caption(phase_label)
            if command.get("long"):
                st.caption("장시간 작업")
            if st.button("실행", key=f"run_cmd_{command['key']}", disabled=disabled, use_container_width=True):
                st.session_state.admin_command_running = True
                _overlay = st.empty()
                try:
                    command["_paid_confirmed"] = paid_confirmed
                    st.session_state.admin_command_result = _run_admin_command(command, _overlay)
                finally:
                    _overlay.empty()
                    st.session_state.admin_command_running = False
                    st.rerun()


def _load_admin_command_groups() -> dict[str, list[tuple[str, list[dict]]]]:
    import requests
    from src.config import API_BASE_URL

    response = requests.get(f"{API_BASE_URL.rstrip('/')}/api/v1/admin/commands", timeout=20)
    response.raise_for_status()
    commands = response.json().get("commands", [])

    result: dict[str, list[tuple[str, list[dict]]]] = {"collect": [], "upload": [], "automation": []}
    by_phase_group: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for command in commands:
        phase = command.get("phase", "")
        if phase not in result:
            continue
        by_phase_group[(phase, command.get("group", "기타"))].append(command)

    for phase in ("collect", "upload", "automation"):
        for (group_phase, group_name), group_commands in by_phase_group.items():
            if group_phase == phase:
                result[phase].append((group_name, group_commands))
    return result

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


# ── 헬퍼: Pinecone 네임스페이스 통계 ──────────────────────────────────────────

@st.cache_data(ttl=300)
def _load_pinecone_stats() -> dict[str, int]:
    """Pinecone describe_index_stats() → 네임스페이스별 벡터 수 반환.

    API 키 없거나 실패 시 빈 dict 반환 (로컬 파일 fallback 사용).
    """
    try:
        from src.infra.pinecone_client import get_pinecone_index
        idx = get_pinecone_index()
        stats = idx.describe_index_stats()
        ns = stats.get("namespaces") or {}
        return {k: v.get("vector_count", 0) for k, v in ns.items()}
    except Exception:
        return {}


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


# ── 사이드바 ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("🛠️ 어드민")
    st.divider()
    _llm_model = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
    st.caption(f"모델: `{_llm_model}`")

# ── 탭 ────────────────────────────────────────────────────────────────────────

st.markdown("""
<div style="padding:20px 0 10px 0; border-bottom:2px solid #e0e0e0; margin-bottom:20px">
    <div style="font-size:1.6em; font-weight:800; color:#1a1a2e">🛠️ 시스템 어드민</div>
    <div style="color:#666; font-size:0.9em; margin-top:4px">RAW Agent — 법령 RAG 파이프라인 운영 현황</div>
</div>
""", unsafe_allow_html=True)

import pandas as pd

# ── 공통 데이터 로드 ──────────────────────────────────────────────────────────
law_rows = _load_law_inventory()
area_active, area_total, _ = _load_area_summary()
img_alerts = _load_image_alerts()
amd_anomalies = _load_amendment_test_results()

try:
    from src.ingestion.area_designation_pipeline import get_pending_proposals as _gpp
    pending_proposals = _gpp()
except Exception:
    pending_proposals = []

tab_dash, tab_law, tab_collect = st.tabs([
    "📊 대시보드",
    "📜 법령 데이터",
    "🧰 법령 수집",
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
# 탭 1: 대시보드
# ══════════════════════════════════════════════════════════════════════════════

with tab_dash:
        # Pinecone 네임스페이스별 벡터 수 로드 (API 키 없으면 빈 dict)
        _pc_stats = _load_pinecone_stats()

        _law_vec   = _pc_stats.get("tax-law", 0)
        _ruling_ns = ["tax-ruling-nts", "tax-ruling-decisions", "tax-ruling-moef", "tax-ruling-nts-interp"]
        _ruling_total = sum(_pc_stats.get(ns, 0) for ns in _ruling_ns)

        _law_sk      = "ok" if _law_vec > 0 else "error"
        _law_lbl     = "✅ Pinecone 인덱싱 완료" if _law_vec > 0 else "❌ 미인덱싱"
        _law_rel     = f"{_law_vec:,}개 벡터"
        _ruling_overall = "ok" if _ruling_total > 0 else "error"

        _area_status = "ok" if area_total > 0 else "warn"

        _alerts: list[tuple[str, str]] = []
        if img_alerts:
            _alerts.append(("warning", f"⚠️ 별표/이미지 테이블 확인 필요 {len(img_alerts)}건"))
        if amd_anomalies:
            _alerts.append(("warning", f"⚠️ 개정 영향 케이스 확인 필요 {len(amd_anomalies)}건"))

        for _lvl, _msg in _alerts:
            st.warning(_msg)
        if not _alerts:
            st.success("✅ 감지된 이상 없음")

        st.markdown("<br>", unsafe_allow_html=True)

        _c1, _c2, _c3 = st.columns(3)
        _sys_card(_c1, "⚖️", "법령 조문", f"{len(law_rows)}개 법령", f"{_law_lbl} · {_law_rel}", _law_sk)
        _ruling_lbl_map = {"ok": "✅ 수집 완료", "warn": "⚠️ 일부 누락", "error": "❌ 미수집"}
        _sys_card(_c2, "📋", "유권해석 5종", f"국세청·기재부·심판원 · 총 {_ruling_total:,}건", _ruling_lbl_map.get(_ruling_overall, ""), _ruling_overall)
        _sys_card(_c3, "🗺️", "지역데이터", f"{area_active}건 현행", f"대기 {len(pending_proposals)}건 · {_fmt_mtime(_ROOT / 'data' / 'area_designations' / 'manual_table.json')}", _area_status)

        st.divider()
        st.markdown("#### 📡 데이터 파이프라인 수집 현황")

        _pipe_rows = []

        # ── 법령 조문: 14개 법령 개별 행으로 펼치기 ──────────────────────────
        for _lr in law_rows:
            _lr_eff = str(_lr.get("최신 시행일", "") or "")
            _lr_eff_fmt = _lr_eff if _lr_eff else "—"
            _lr_chunks = _lr.get("총 청크", 0)
            _pipe_rows.append({
                "구분": "법령 조문",
                "법령명": _lr.get("법령명", ""),
                "분류": _lr.get("분류", ""),
                "상태": "✅ 수집 완료",
                "최신 시행일": _lr_eff_fmt,
                "청크 수": f"{_lr_chunks}건",
            })

        # ── 유권해석 (Pinecone 벡터 수 기반) ────────────────────────────────
        _ruling_pc_defs = [
            ("유권해석", "국세청 질의회신",  "hotissue·qt·ic·pd",               "tax-ruling-nts"),
            ("유권해석", "심판청구 결정례",  "조세심판원 (양도 필터)",            "tax-ruling-decisions"),
            ("유권해석", "기재부 법령해석",  "전체 2,305건 · 양도 필터",         "tax-ruling-moef"),
            ("유권해석", "국세청 법령해석",  "양도·증여·상속·상생임대·임대주택",  "tax-ruling-nts-interp"),
            ("유권해석", "판례",             "대법원·고등법원 (미구현)",           None),
        ]
        for _grp, _plabel, _pdetail, _ns in _ruling_pc_defs:
            if _ns is None:
                _slabel, _cnt = "❌ 미구현", "—"
            else:
                _vec = _pc_stats.get(_ns, 0)
                _slabel = "✅ 인덱싱 완료" if _vec > 0 else "❌ 미인덱싱"
                _cnt = f"{_vec:,}건" if _vec > 0 else "—"
            _pipe_rows.append({
                "구분": _grp,
                "법령명": _plabel,
                "분류": _pdetail,
                "상태": _slabel,
                "최신 시행일": "—",
                "청크 수": _cnt,
            })


        st.dataframe(
            pd.DataFrame(_pipe_rows),
            use_container_width=True,
            hide_index=True,
            height=(len(_pipe_rows) + 1) * 36 + 38,
            column_config={
                "구분":       st.column_config.TextColumn("구분", width="small"),
                "법령명":     st.column_config.TextColumn("법령명", width="medium"),
                "분류":       st.column_config.TextColumn("분류", width="medium"),
                "상태":       st.column_config.TextColumn("상태", width="small"),
                "최신 시행일": st.column_config.TextColumn("최신 시행일", width="small"),
                "청크 수":    st.column_config.TextColumn("청크 수", width="small"),
            },
        )

        change_log_preview = _load_change_log(3)
        if change_log_preview:
            st.markdown("**최근 개정 감지**")
            for _rec in change_log_preview:
                st.caption(f"{_rec.get('detected_at', '')[:16]}  {_rec.get('law_name', _rec.get('event', ''))}")

# ══════════════════════════════════════════════════════════════════════════════
# 탭 2: 법령 데이터 (전체 스프레드시트, 필터 없음)
# ══════════════════════════════════════════════════════════════════════════════

with tab_law:
    st.caption("law.go.kr DRF API에서 수집한 법령 조문 및 유권해석 원천 데이터입니다.")

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
    st.warning(
        "⚠️ **서버 사이드 필터 적용됨** — 현재 수집 키워드: `양도`  \n"
        "→ **미수집 누락 영역**: 신탁/수탁 구조 이전, 재건축조합원 입주권, 이월과세, 증여·상속 결정례  \n"
        "→ 추가 키워드(`신탁`, `재건축`, `입주권`, `이월`) 필요 시 `--keyword <키워드>` 옵션으로 재수집."
    )
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
        "→ **미수집 누락 영역**: 신탁 구조(`신탁`), 재건축(`재건축`), 가산세/제척기간(`가산세`, `부과제척기간`)  \n"
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
    st.error(
        "🚧 **(구현전)** — 대법원 종합법률정보 수집 미구현.  \n"
        "→ 수집 대상: 대법원 판례(`law.go.kr` 또는 대법원 종합법률정보 API), 감사원 결정  \n"
        "→ 추후 `data/rulings/precedents/` 경로로 추가 예정."
    )


# ══════════════════════════════════════════════════════════════════════════════
# 탭 3: 법령 수집 명령 실행
# ══════════════════════════════════════════════════════════════════════════════

with tab_collect:
    st.caption("수집과 Pinecone 업로드 명령은 API 서버에서 비동기 작업으로 실행됩니다.")

    _collect_pc_stats = _load_pinecone_stats()
    _confirm_paid_ops = st.checkbox(
        "임베딩/Pinecone 업로드 비용 가능 작업 실행을 허용합니다.",
        key="admin_confirm_paid_ops",
        help="순수 수집 명령은 체크 없이 실행할 수 있습니다. 업로드와 통합 자동화 작업은 임베딩/Pinecone API 비용 또는 장시간 실행이 발생할 수 있습니다.",
    )

    if st.session_state.admin_command_running:
        st.info("명령 실행 중입니다. 완료될 때까지 페이지를 닫지 마세요.")

    _render_command_result(st.session_state.admin_command_result)

    st.divider()

    try:
        _command_groups = _load_admin_command_groups()
    except Exception as exc:
        st.error(f"API 서버에서 실행 명령 목록을 불러오지 못했습니다: {exc}")
        st.caption("API_BASE_URL 설정과 API 서버 실행 상태를 확인하세요.")
        _command_groups = {"collect": [], "upload": [], "automation": []}

    _sections = [
        ("1. 데이터 수집", "로컬 파일과 JSON 원천 데이터를 생성합니다. Pinecone 업로드는 하지 않습니다.", _command_groups["collect"], True),
        ("2. 임베딩/Pinecone 업로드", "이미 수집된 로컬 데이터를 임베딩하고 Pinecone 네임스페이스에 업로드합니다.", _command_groups["upload"], True),
        ("3. 통합 자동화", "수집 후 신규 데이터가 있으면 업로드까지 이어서 수행하는 혼합 명령입니다.", _command_groups["automation"], False),
    ]

    for _section_title, _section_caption, _groups, _expanded in _sections:
        st.markdown(f"#### {_section_title}")
        st.caption(_section_caption)
        if not _groups:
            st.info("표시할 명령이 없습니다.")
            st.divider()
            continue
        for _group_name, _commands in _groups:
            with st.expander(_group_name, expanded=_expanded):
                _cols = st.columns(2)
                for _idx, _command in enumerate(_commands):
                    with _cols[_idx % 2]:
                        _render_command_card(_command, _confirm_paid_ops, _collect_pc_stats)
        st.divider()
