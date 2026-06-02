"""
어드민 페이지 — 대시보드 / 법령 / 지역데이터 / 시나리오.
판단 로직 없음. 표시·실행·통계 전용.
"""
from __future__ import annotations

import asyncio
import html
import json
import os
import queue
import subprocess
import sys
import threading
import time
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
    ("admin_command_result", None),
    ("admin_command_running", False),
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

_VERDICT_OPTIONS = ["비과세", "고가주택", "일반과세", "중과", "단기세율", "감면", "사실관계부족"]
_CONFIDENCE_OPTIONS = ["높음", "보통", "낮음 (재검토 필요)"]

_FACT_LABELS = {
    "property_type": "부동산 유형",
    "acquisition_date": "취득일",
    "transfer_date": "양도일",
    "acquisition_price": "취득가액",
    "transfer_price": "양도가액",
    "household_house_count": "세대 주택 수",
    "residence_years": "실거주 기간(년)",
    "is_adjustment_area_at_transfer": "양도 시 조정대상지역",
    "is_adjustment_area_at_acquisition": "취득 시 조정대상지역",
    "acquisition_reason": "취득 원인",
    "holding_years": "보유 기간(년)",
}

_LABELS_PATH = _ROOT / "data" / "golden" / "expert_labels.json"

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


def _fmt_money(v) -> str:
    if not v:
        return "—"
    try:
        v = int(v)
        if v >= 100_000_000:
            return f"{v / 100_000_000:,.1f}억원"
        if v >= 10_000:
            return f"{v / 10_000:,.0f}만원"
        return f"{v:,}원"
    except Exception:
        return str(v)


def _fmt_fact(key: str, val) -> str:
    if val is None:
        return "—"
    if key in ("acquisition_price", "transfer_price"):
        return _fmt_money(val)
    if key in ("acquisition_date", "transfer_date"):
        s = str(int(val)) if val else ""
        return f"{s[:4]}년 {s[4:6]}월 {s[6:]}일" if len(s) == 8 else s or "—"
    if key in ("residence_years", "holding_years"):
        return f"{float(val):.1f}년"
    if isinstance(val, bool):
        return "예" if val else "아니오"
    return str(val)


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
    import requests
    from src.config import API_BASE_URL

    response = requests.post(
        f"{API_BASE_URL.rstrip('/')}/api/v1/chat",
        json={"fact_json": fact_json, "enable_debate": False},
        timeout=300,
    )
    response.raise_for_status()
    return response.json()


def _command_text(args: list[str]) -> str:
    return " ".join(["python", "-m", *args])


def _path_status(path: Path | None) -> str:
    if path is None:
        return "상태 파일 없음"
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
    args = list(command["args"])
    cmd = [sys.executable, "-m", *args]
    timeout_s = int(command.get("timeout_s", 1800))
    started = datetime.now()
    t0 = time.monotonic()
    st.session_state.admin_command_t0 = t0
    result: dict = {
        "label": command["label"],
        "cmd": _command_text(args),
        "started_at": started.strftime("%Y-%m-%d %H:%M:%S"),
        "finished_at": "",
        "elapsed_s": 0.0,
        "returncode": None,
        "timed_out": False,
    }
    log_lines = [f"$ {_command_text(args)}"]
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    _render_command_overlay(overlay_placeholder, command, log_lines, started)
    try:
        process = subprocess.Popen(
            cmd,
            cwd=_ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
        )
        assert process.stdout is not None
        output_queue: queue.Queue[str | None] = queue.Queue()

        def _read_output() -> None:
            try:
                for output_line in process.stdout:
                    output_queue.put(output_line.rstrip("\n"))
            finally:
                output_queue.put(None)

        threading.Thread(target=_read_output, daemon=True).start()
        reader_done = False
        while True:
            if time.monotonic() - t0 > timeout_s:
                result["timed_out"] = True
                log_lines.append(f"명령이 {timeout_s}초 제한을 초과해 중단되었습니다.")
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                break

            updated = False
            while True:
                try:
                    line = output_queue.get_nowait()
                except queue.Empty:
                    break
                if line is None:
                    reader_done = True
                    continue
                log_lines.append(line)
                updated = True
            if updated:
                _render_command_overlay(overlay_placeholder, command, log_lines, started)

            if process.poll() is not None and reader_done:
                break
            _render_command_overlay(overlay_placeholder, command, log_lines, started)
            time.sleep(0.1)

        result["returncode"] = process.returncode if process.returncode is not None else -1
        if result["timed_out"]:
            result["returncode"] = -1
        _render_command_overlay(overlay_placeholder, command, log_lines, started, result["returncode"])
        time.sleep(0.7)
    except Exception as exc:
        result["returncode"] = -1
        log_lines.append(f"실행 오류: {exc}")
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
        "eval": "LLM/eval 비용 가능",
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
                    st.session_state.admin_command_result = _run_admin_command(command, _overlay)
                finally:
                    _overlay.empty()
                    st.session_state.admin_command_running = False
                    st.rerun()


_COLLECT_COMMAND_GROUPS: list[tuple[str, list[dict]]] = [
    ("법령 조문", [
        {
            "key": "law_collect",
            "label": "법령 조문 수집",
            "description": "law.go.kr DRF API에서 법령 XML을 수집하고 로컬 청크 파일을 갱신합니다.",
            "args": ["src.ingestion.collect"],
            "path": _ROOT / "data" / "processed" / "all_chunks.json",
            "phase": "collect",
        },
        {
            "key": "law_changes",
            "label": "법령 개정 감지",
            "description": "법령 버전 스냅샷과 최신 목록을 비교하고 개정 로그를 기록합니다. Pinecone 업로드는 하지 않습니다.",
            "args": ["scripts.detect_law_changes"],
            "path": _ROOT / "data" / "law_change_log.jsonl",
            "phase": "collect",
        },
    ]),
    ("유권해석 개별 수집", [
        {
            "key": "ruling_revision",
            "label": "폐지 예규 목록 수집",
            "description": "세법해석정비 목록을 수집해 폐지 예규 필터의 원천 데이터를 갱신합니다.",
            "args": ["src.ingestion.collect_rulings_revision", "--tax", "transfer"],
            "path": _ROOT / "data" / "rulings" / "deprecated_ids.json",
            "phase": "collect",
        },
        {
            "key": "ruling_nts",
            "label": "국세청 질의회신 수집",
            "description": "양도소득세 질의회신/쟁점별 사례를 resume 모드로 수집합니다.",
            "args": ["src.ingestion.collect_rulings_nts", "--tax", "양도소득세", "--resume"],
            "path": _ROOT / "data" / "rulings" / "nts",
            "phase": "collect",
        },
        {
            "key": "ruling_decisions",
            "label": "심판청구 결정례 수집",
            "description": "조세심판원 결정례를 양도 키워드로 수집합니다.",
            "args": ["src.ingestion.collect_rulings_decisions", "--type", "tax_tribunal", "--keyword", "양도", "--resume"],
            "path": _ROOT / "data" / "rulings" / "decisions",
            "phase": "collect",
        },
        {
            "key": "ruling_moef",
            "label": "기재부 법령해석 수집",
            "description": "기재부 법령해석 목록을 resume 모드로 수집합니다.",
            "args": ["src.ingestion.collect_rulings_moef", "--resume", "--no-detail"],
            "path": _ROOT / "data" / "rulings" / "moef",
            "phase": "collect",
        },
        {
            "key": "ruling_nts_interp",
            "label": "국세청 법령해석 수집",
            "description": "양도·증여·상속·상생임대·임대주택 키워드의 법령해석을 수집합니다.",
            "args": [
                "src.ingestion.collect_rulings_nts_interp",
                "--keywords", "양도", "증여", "상속", "상생임대", "임대주택",
                "--resume", "--no-detail",
            ],
            "path": _ROOT / "data" / "rulings" / "nts_interp",
            "phase": "collect",
            "long": True,
        },
    ]),
    ("PDF/행정 데이터 수집", [
        {
            "key": "pdf_collect",
            "label": "PDF 집행기준 파싱",
            "description": "data/rulings/pdf_source의 PDF를 로컬 JSON 레코드로 파싱합니다. Pinecone 업로드는 하지 않습니다.",
            "args": ["src.ingestion.collect_rulings_pdf"],
            "path": _ROOT / "data" / "rulings" / "pdf",
            "phase": "collect",
        },
        {
            "key": "admin_notices",
            "label": "행정 고시 수집",
            "description": "규제지역 관련 행정/금융 고시 데이터를 갱신합니다.",
            "args": ["src.ingestion.admin_notices"],
            "path": _ROOT / "data" / "area_designations",
            "phase": "collect",
        },
        {
            "key": "regulatory_changes",
            "label": "규제지역 변경 감지",
            "description": "규제지역 변경 후보를 감지해 인박스에 기록합니다.",
            "args": ["scripts.detect_regulatory_changes"],
            "path": _ROOT / "data" / "area_designations" / "detection_inbox.json",
            "phase": "collect",
        },
    ]),
]

_UPLOAD_COMMAND_GROUPS: list[tuple[str, list[dict]]] = [
    ("법령 조문 업로드", [
        {
            "key": "law_embed",
            "label": "법령 조문 임베딩/Pinecone 업로드",
            "description": "data/processed/all_chunks.json을 임베딩하고 Pinecone tax-law 네임스페이스에 업로드합니다.",
            "args": ["src.ingestion.embed"],
            "path": _ROOT / "data" / "processed" / "all_chunks.json",
            "namespace": "tax-law",
            "phase": "upload",
            "paid": True,
        },
    ]),
    ("유권해석 개별 업로드", [
        {
            "key": "embed_nts",
            "label": "국세청 질의회신 임베딩/Pinecone 업로드",
            "description": "국세청 질의회신을 임베딩하고 Pinecone에 업로드합니다.",
            "args": ["src.ingestion.embed_rulings", "nts"],
            "path": _ROOT / "data" / "rulings" / "nts",
            "namespace": "tax-ruling-nts",
            "phase": "upload",
            "paid": True,
        },
        {
            "key": "embed_decisions",
            "label": "심판청구 결정례 임베딩/Pinecone 업로드",
            "description": "결정례 데이터를 임베딩하고 Pinecone에 업로드합니다.",
            "args": ["src.ingestion.embed_rulings", "decisions"],
            "path": _ROOT / "data" / "rulings" / "decisions",
            "namespace": "tax-ruling-decisions",
            "phase": "upload",
            "paid": True,
        },
        {
            "key": "embed_moef",
            "label": "기재부 법령해석 임베딩/Pinecone 업로드",
            "description": "기재부 법령해석을 임베딩하고 Pinecone에 업로드합니다.",
            "args": ["src.ingestion.embed_rulings", "moef"],
            "path": _ROOT / "data" / "rulings" / "moef",
            "namespace": "tax-ruling-moef",
            "phase": "upload",
            "paid": True,
        },
        {
            "key": "embed_nts_interp",
            "label": "국세청 법령해석 임베딩/Pinecone 업로드",
            "description": "국세청 법령해석을 임베딩하고 Pinecone에 업로드합니다.",
            "args": ["src.ingestion.embed_rulings", "nts_interp"],
            "path": _ROOT / "data" / "rulings" / "nts_interp",
            "namespace": "tax-ruling-nts-interp",
            "phase": "upload",
            "paid": True,
        },
        {
            "key": "embed_pdf",
            "label": "PDF 집행기준 임베딩/Pinecone 업로드",
            "description": "PDF 집행기준을 임베딩하고 Pinecone에 업로드합니다.",
            "args": ["src.ingestion.embed_rulings", "pdf"],
            "path": _ROOT / "data" / "rulings" / "pdf",
            "namespace": "tax-ruling-pdf",
            "phase": "upload",
            "paid": True,
        },
    ]),
]

_AUTOMATION_COMMAND_GROUPS: list[tuple[str, list[dict]]] = [
    ("수집+업로드 통합 자동화", [
        {
            "key": "rulings_incremental",
            "label": "유권해석 증분 수집 + 신규 임베딩/Pinecone 업로드",
            "description": "수집 후 신규 파일이 있으면 임베딩까지 수행합니다. 신규 데이터가 없으면 업로드를 생략합니다.",
            "args": ["scripts.collect_and_embed_rulings"],
            "path": _ROOT / "data" / "rulings",
            "phase": "automation",
            "paid": True,
            "long": True,
        },
        {
            "key": "law_changes_embed",
            "label": "법령 개정 감지 + 신규 법령 Pinecone 업로드",
            "description": "개정 감지 후 신규 법령을 수집하고 Pinecone까지 업로드합니다.",
            "args": ["scripts.detect_law_changes", "--embed"],
            "path": _ROOT / "data" / "law_change_log.jsonl",
            "namespace": "tax-law",
            "phase": "automation",
            "paid": True,
        },
    ]),
]

_EVAL_COMMAND_GROUPS: list[tuple[str, list[dict]]] = [
    ("평가/골든셋", [
        {
            "key": "golden_eval",
            "label": "골든셋 평가",
            "description": "qa_pairs.json 전체를 현재 파이프라인으로 평가합니다.",
            "args": ["scripts.run_golden_eval"],
            "path": _ROOT / "data" / "eval_results" / "golden_eval_latest.json",
            "phase": "eval",
            "paid": True,
        },
        {
            "key": "baseline_eval",
            "label": "Baseline 평가",
            "description": "종합 baseline 평가를 워커 3개로 실행합니다.",
            "args": ["scripts.run_baseline_eval", "--workers", "3"],
            "path": _ROOT / "data" / "eval_results",
            "phase": "eval",
            "paid": True,
            "long": True,
            "timeout_s": 7200,
        },
        {
            "key": "baseline_debate",
            "label": "Baseline 평가 + Debate",
            "description": "비용과 시간이 큰 debate 포함 평가를 실행합니다.",
            "args": ["scripts.run_baseline_eval", "--debate", "--workers", "3"],
            "path": _ROOT / "data" / "eval_results",
            "phase": "eval",
            "paid": True,
            "long": True,
            "timeout_s": 7200,
        },
    ]),
    ("Reranker 루프", [
        {
            "key": "extract_reranker_pairs",
            "label": "Debate 훈련쌍 추출",
            "description": "debate 기록에서 reranker 훈련쌍을 생성합니다.",
            "args": ["scripts.extract_reranker_pairs"],
            "path": _ROOT / "data" / "reranker_pairs.jsonl",
            "phase": "eval",
        },
        {
            "key": "extract_ruling_pairs",
            "label": "유권해석 훈련쌍 추출",
            "description": "유권해석과 법령 검색 결과를 연결해 reranker 훈련쌍을 생성합니다.",
            "args": ["scripts.extract_ruling_pairs"],
            "path": _ROOT / "data" / "reranker_pairs.jsonl",
            "phase": "eval",
            "paid": True,
            "long": True,
        },
        {
            "key": "finetune_reranker",
            "label": "Reranker 파인튜닝",
            "description": "로컬 환경에서 BGE reranker 파인튜닝을 실행합니다.",
            "args": ["scripts.finetune_reranker"],
            "path": _ROOT / "data" / "models" / "bge-reranker-tax-rag",
            "phase": "eval",
            "paid": True,
            "long": True,
            "timeout_s": 7200,
        },
    ]),
]

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


def _load_expert_labels() -> dict[str, dict]:
    if not _LABELS_PATH.exists():
        return {}
    try:
        return json.loads(_LABELS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_expert_labels(labels: dict[str, dict]) -> None:
    _LABELS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _LABELS_PATH.write_text(json.dumps(labels, ensure_ascii=False, indent=2), encoding="utf-8")


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

st.markdown("""
<div style="padding:20px 0 10px 0; border-bottom:2px solid #e0e0e0; margin-bottom:20px">
    <div style="font-size:1.6em; font-weight:800; color:#1a1a2e">🛠️ 시스템 어드민</div>
    <div style="color:#666; font-size:0.9em; margin-top:4px">RAW Agent — 법령 RAG 파이프라인 운영 현황</div>
</div>
""", unsafe_allow_html=True)

import pandas as pd

# ── 공통 데이터 로드 ──────────────────────────────────────────────────────────
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

tab_dash, tab_law, tab_collect, tab_scenarios = st.tabs([
    "📊 대시보드",
    "📜 법령 데이터",
    "🧰 법령 수집",
    "🎯 평가 현황",
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

        _NS_MAP = {
            "tax-law":              "법령 조문",
            "tax-ruling-nts":       "국세청 질의회신",
            "tax-ruling-decisions": "심판청구 결정례",
            "tax-ruling-moef":      "기재부 법령해석",
            "tax-ruling-nts-interp":"국세청 법령해석",
        }
        _law_vec   = _pc_stats.get("tax-law", 0)
        _ruling_ns = ["tax-ruling-nts", "tax-ruling-decisions", "tax-ruling-moef", "tax-ruling-nts-interp"]
        _ruling_total = sum(_pc_stats.get(ns, 0) for ns in _ruling_ns)

        _law_sk      = "ok" if _law_vec > 0 else "error"
        _law_lbl     = "✅ Pinecone 인덱싱 완료" if _law_vec > 0 else "❌ 미인덱싱"
        _law_rel     = f"{_law_vec:,}개 벡터"
        _ruling_overall = "ok" if _ruling_total > 0 else "error"

        _area_status = "ok" if area_total > 0 else "warn"
        _ft_status   = "ok" if (red_wins >= red_target and red_target > 0) else ("warn" if red_wins > 0 else "error")

        _alerts: list[tuple[str, str]] = []
        if needs_review_cnt:
            _alerts.append(("warning", f"⚠️ 골든셋 재검토 {needs_review_cnt}건 (법령 개정 영향)"))
        if failed_cnt:
            _alerts.append(("warning", f"⚠️ 시나리오 평가 실패 {failed_cnt}건"))

        if _alerts:
            for _lvl, _msg in _alerts:
                if _lvl == "error":
                    st.error(_msg)
                else:
                    st.warning(_msg)
        else:
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
    st.caption("UI/API/MCP 런타임과 별도로 실행해야 하는 명령입니다. 수집과 Pinecone 업로드를 단계별로 분리했습니다.")

    _collect_pc_stats = _load_pinecone_stats()
    _confirm_paid_ops = st.checkbox(
        "임베딩/Pinecone 업로드/평가 등 비용 가능 작업 실행을 허용합니다.",
        key="admin_confirm_paid_ops",
        help="순수 수집 명령은 체크 없이 실행할 수 있습니다. 업로드, 통합 자동화, LLM 평가, debate, finetune 작업은 API 비용 또는 장시간 실행이 발생할 수 있습니다.",
    )

    if st.session_state.admin_command_running:
        st.info("명령 실행 중입니다. 완료될 때까지 페이지를 닫지 마세요.")

    _render_command_result(st.session_state.admin_command_result)

    st.divider()

    _sections = [
        ("1. 데이터 수집", "로컬 파일과 JSON 원천 데이터를 생성합니다. Pinecone 업로드는 하지 않습니다.", _COLLECT_COMMAND_GROUPS, True),
        ("2. 임베딩/Pinecone 업로드", "이미 수집된 로컬 데이터를 임베딩하고 Pinecone 네임스페이스에 업로드합니다.", _UPLOAD_COMMAND_GROUPS, True),
        ("3. 통합 자동화", "수집 후 신규 데이터가 있으면 업로드까지 이어서 수행하는 혼합 명령입니다.", _AUTOMATION_COMMAND_GROUPS, False),
        ("4. 평가/학습", "골든셋 평가, baseline 평가, reranker 학습 루프 명령입니다.", _EVAL_COMMAND_GROUPS, False),
    ]

    for _section_title, _section_caption, _groups, _expanded in _sections:
        st.markdown(f"#### {_section_title}")
        st.caption(_section_caption)
        for _group_name, _commands in _groups:
            with st.expander(_group_name, expanded=_expanded):
                _cols = st.columns(2)
                for _idx, _command in enumerate(_commands):
                    with _cols[_idx % 2]:
                        _render_command_card(_command, _confirm_paid_ops, _collect_pc_stats)
        st.divider()


# ══════════════════════════════════════════════════════════════════════════════
# 탭 4: 평가 현황
# ══════════════════════════════════════════════════════════════════════════════

with tab_scenarios:
    _GOLDEN_FILE = _ROOT / "data" / "golden" / "qa_pairs.json"

    st.markdown("""
<div style="padding:12px 0 16px 0">
    <div style="font-size:1.1em; font-weight:700; color:#1a1a2e">📊 골든셋 평가 현황</div>
    <div style="color:#888; font-size:0.82em">AI 합성 시나리오 기반 판단 정확도 측정</div>
</div>
""", unsafe_allow_html=True)

    _ev_c1, _ev_c2 = st.columns(2)
    _debate_lbl3 = f"✅ {debate_cnt}건" if debate_cnt > 0 else "⚠️ 없음"
    _ft_lbl3 = "✅ 완료" if (red_wins >= red_target and red_target > 0) else (f"⚠️ {red_wins}/{red_target}건 진행중" if red_wins > 0 else "🔘 대기 중")
    _sys_card(_ev_c1, "🧩", "케이스 생성", f"{debate_cnt}건", "논쟁 기반 골든셋 승격", "ok" if debate_cnt > 0 else "warn")
    _sys_card(_ev_c2, "🤖", "AI 학습 진행률", f"{red_wins}/{red_target}건 ({_red_pct}%)", _ft_lbl3, "ok" if red_wins >= red_target and red_target > 0 else "warn")
    st.markdown("<br>", unsafe_allow_html=True)

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
            st.dataframe(pd.DataFrame(sc_rows), use_container_width=True, hide_index=True)

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
