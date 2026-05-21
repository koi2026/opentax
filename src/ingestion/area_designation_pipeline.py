"""
규제지역 변경 감지 파이프라인 오케스트레이터

실행 흐름:
1. 모든 소스(P0~P2) 순차 실행
2. 후보 취합 → proposed_changes_{ts}.json 생성
3. 알림 발송 (Slack / 이메일)
4. 고신뢰(P0 + confidence>=0.8) 조건 충족 시 auto-apply 옵션
5. 그 외 → admin 승인 대기

환경변수:
  SLACK_WEBHOOK_URL    — Slack 알림 webhook
  ALERT_EMAIL_TO       — 이메일 수신자
  ALERT_EMAIL_FROM     — 발신자
  ALERT_EMAIL_PASSWORD — 발신 SMTP 비밀번호 (Gmail 앱 비밀번호)
  AREA_AUTO_APPLY      — "1"이면 고신뢰 조건에서 auto-apply
"""
from __future__ import annotations

import json
import os
import smtplib
import ssl
from dataclasses import asdict
from datetime import datetime, date, timedelta
from email.mime.text import MIMEText
from pathlib import Path
from typing import List, Optional, Tuple

from dotenv import load_dotenv

load_dotenv()

from src.ingestion.area_sources import (
    AlertLevel, DesignationCandidate, SourceResult,
    PROPOSALS_DIR, STATE_DIR,
)
from src.ingestion.area_sources import gwanbo, molit_board, moef_board
from src.ingestion.area_sources import molit_press, lawmaking_api, news_signal

MANUAL_TABLE_PATH = Path("data/area_designations/manual_table.json")
SCRAPER_HEALTH_PATH = STATE_DIR / "scraper_health.json"

_SLACK_WEBHOOK = os.getenv("SLACK_WEBHOOK_URL", "")
_EMAIL_TO = os.getenv("ALERT_EMAIL_TO", "")
_EMAIL_FROM = os.getenv("ALERT_EMAIL_FROM", "")
_EMAIL_PASSWORD = os.getenv("ALERT_EMAIL_PASSWORD", "")
_AUTO_APPLY = os.getenv("AREA_AUTO_APPLY", "0") == "1"

# confidence 임계값 — 이 이상이면 auto-apply 후보
_AUTO_APPLY_THRESHOLD = 0.80
# 스크래퍼 health 경보 기준 (시간)
_HEALTH_WARN_HOURS = 72


# ── 알림 ───────────────────────────────────────────────────────────────────────

def _send_slack(message: str) -> None:
    if not _SLACK_WEBHOOK:
        return
    try:
        import requests
        requests.post(_SLACK_WEBHOOK, json={"text": message}, timeout=10)
    except Exception as e:
        print(f"  [알림] Slack 전송 실패: {e}")


def _send_email(subject: str, body: str) -> None:
    if not (_EMAIL_TO and _EMAIL_FROM and _EMAIL_PASSWORD):
        return
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = _EMAIL_FROM
        msg["To"] = _EMAIL_TO
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx) as server:
            server.login(_EMAIL_FROM, _EMAIL_PASSWORD)
            server.sendmail(_EMAIL_FROM, _EMAIL_TO, msg.as_string())
    except Exception as e:
        print(f"  [알림] 이메일 전송 실패: {e}")


def _alert(level: AlertLevel, candidates: List[DesignationCandidate], proposal_path: Path) -> None:
    if not candidates:
        return

    emoji = {"critical": "🚨", "warning": "⚠️", "error": "❌"}.get(level.value, "ℹ️")
    lines = [f"{emoji} [TaxRAG] 규제지역 변경 감지 — {level.value.upper()}"]
    for c in candidates[:5]:
        action = "해제" if c.released_at else "신규 지정"
        lines.append(
            f"  • {c.area_type} {action} | 신뢰도:{c.confidence:.0%} | 출처:{c.source_name}"
        )
        lines.append(f"    URL: {c.source_url}")
    if len(candidates) > 5:
        lines.append(f"  ... 외 {len(candidates)-5}건")
    lines.append(f"  📄 제안서: {proposal_path}")
    if level == AlertLevel.WARNING:
        lines.append("  ※ 공식 고시 확인 후 admin 페이지에서 승인 필요")

    message = "\n".join(lines)
    print(message)
    _send_slack(message)
    _send_email(f"[TaxRAG] 규제지역 변경 감지 {level.value}", message)


# ── 스크래퍼 health 관리 ────────────────────────────────────────────────────────

def _update_scraper_health(results: List[SourceResult]) -> Optional[str]:
    """실패한 P0 소스가 72시간 이상이면 경고 메시지 반환."""
    health: dict = {}
    if SCRAPER_HEALTH_PATH.exists():
        try:
            health = json.loads(SCRAPER_HEALTH_PATH.read_text(encoding="utf-8"))
        except Exception:
            health = {}

    now = datetime.now()
    for r in results:
        if r.success:
            health[r.source_name] = {"last_success": now.isoformat(), "status": "ok"}
        else:
            if r.source_name not in health:
                health[r.source_name] = {"first_fail": now.isoformat(), "status": "fail"}
            else:
                health[r.source_name]["status"] = "fail"

    SCRAPER_HEALTH_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCRAPER_HEALTH_PATH.write_text(
        json.dumps(health, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    warn_sources = []
    for name, info in health.items():
        if info.get("status") == "fail":
            first_fail = info.get("first_fail", now.isoformat())
            hours_down = (now - datetime.fromisoformat(first_fail)).total_seconds() / 3600
            if hours_down >= _HEALTH_WARN_HOURS:
                warn_sources.append(f"{name}({hours_down:.0f}h)")

    if warn_sources:
        return f"스크래퍼 장기 실패: {', '.join(warn_sources)}"
    return None


# ── 제안서 생성 ────────────────────────────────────────────────────────────────

def _save_proposal(candidates: List[DesignationCandidate], results: List[SourceResult]) -> Path:
    PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = PROPOSALS_DIR / f"proposed_changes_{ts}.json"

    payload = {
        "detected_at": datetime.now().isoformat(),
        "status": "pending",
        "candidates": [c.to_dict() for c in candidates],
        "source_results": [r.to_dict() for r in results],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  📄 제안서 저장: {path}")
    return path


# ── manual_table.json 패치 ─────────────────────────────────────────────────────

def _load_manual_table() -> list:
    if not MANUAL_TABLE_PATH.exists():
        return []
    return json.loads(MANUAL_TABLE_PATH.read_text(encoding="utf-8"))


def apply_proposal(proposal_path: Path) -> int:
    """
    승인된 제안서를 manual_table.json에 반영한다.
    admin 페이지 또는 CLI에서 호출.
    반환: 추가된 행 수
    """
    payload = json.loads(proposal_path.read_text(encoding="utf-8"))
    candidates = payload.get("candidates", [])
    table = _load_manual_table()

    existing_sigs = {
        (r["region"], r["area_type"], r.get("designated_at", ""), r.get("released_at", ""))
        for r in table
    }

    added = 0
    for c in candidates:
        region = c.get("region", "")
        if not region:
            continue
        area_type = c.get("area_type", "")
        sig = (region, area_type, c.get("designated_at") or "", c.get("released_at") or "")
        if sig in existing_sigs:
            continue
        # 기존 active 행의 released_at 채우기 (해제인 경우)
        if c.get("released_at"):
            for row in table:
                if row["region"] == region and row["area_type"] == area_type and not row.get("released_at"):
                    row["released_at"] = c["released_at"]
        else:
            table.append({
                "region": region,
                "area_type": area_type,
                "designated_at": c.get("designated_at") or "",
                "released_at": c.get("released_at"),
                "announcement_no": c.get("announcement_no", ""),
                "source_url": c.get("source_url", ""),
                "source": c.get("source_name", "auto"),
            })
            existing_sigs.add(sig)
            added += 1

    MANUAL_TABLE_PATH.write_text(
        json.dumps(table, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    payload["status"] = "applied"
    payload["applied_at"] = datetime.now().isoformat()
    proposal_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  ✅ {added}건 반영 완료 → {MANUAL_TABLE_PATH}")
    return added


def get_pending_proposals() -> List[Path]:
    """승인 대기 중인 제안서 목록."""
    if not PROPOSALS_DIR.exists():
        return []
    paths = sorted(PROPOSALS_DIR.glob("proposed_changes_*.json"), reverse=True)
    pending = []
    for p in paths:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if data.get("status") == "pending":
                pending.append(p)
        except Exception:
            pass
    return pending


# ── 메인 실행 ──────────────────────────────────────────────────────────────────

def _is_degraded(results: List[SourceResult]) -> bool:
    """P0 소스가 모두 실패한 상태."""
    p0_results = [r for r in results if "P0" in r.priority.value]
    return p0_results and all(not r.success for r in p0_results)


def run_pipeline(dry_run: bool = False) -> dict:
    """
    전체 규제지역 감지 파이프라인 실행.
    반환: 실행 요약 dict
    """
    print("\n=== 규제지역 변경 감지 파이프라인 시작 ===")
    now = datetime.now()

    # ── 소스 실행 ──────────────────────────────────────────────────────────────
    sources = [
        ("gwanbo",       gwanbo.run),
        ("molit_board",  molit_board.run),
        ("moef_board",   moef_board.run),
        ("molit_press",  molit_press.run),
        ("lawmaking_api",lawmaking_api.run),
        ("news_signal",  news_signal.run),
    ]

    results: List[SourceResult] = []
    for name, runner in sources:
        print(f"  [{name}] 실행 중...")
        try:
            r = runner()
            results.append(r)
            status = "✓" if r.success else "✗"
            print(f"  {status} {name}: 후보 {len(r.candidates)}건" + (f" | {r.error_message}" if r.error_message else ""))
        except Exception as e:
            print(f"  ✗ {name}: 예외 발생 — {e}")

    # ── 후보 취합 ──────────────────────────────────────────────────────────────
    all_candidates: List[DesignationCandidate] = []
    for r in results:
        all_candidates.extend(r.candidates)

    # 중복 제거 (designation_hash 기준)
    seen_hashes: set = set()
    deduped: List[DesignationCandidate] = []
    for c in all_candidates:
        h = c.designation_hash()
        if h not in seen_hashes:
            seen_hashes.add(h)
            deduped.append(c)

    # 최고 alert level 결정
    alert_levels = [r.alert_level for r in results if r.alert_level]
    max_alert: Optional[AlertLevel] = None
    for level in [AlertLevel.CRITICAL, AlertLevel.WARNING, AlertLevel.ERROR]:
        if level in alert_levels:
            max_alert = level
            break

    # 스크래퍼 health 체크
    health_warn = _update_scraper_health(results)
    if health_warn and not max_alert:
        max_alert = AlertLevel.ERROR

    summary = {
        "run_at": now.isoformat(),
        "total_candidates": len(deduped),
        "alert_level": max_alert.value if max_alert else None,
        "health_warning": health_warn,
        "applied": False,
        "proposal_path": None,
        "source_results": {r.source_name: {"success": r.success, "candidates": len(r.candidates)} for r in results},
    }

    if not deduped and not health_warn:
        print("  → 변경 없음")
        return summary

    if dry_run:
        print(f"  [dry-run] 후보 {len(deduped)}건 — 저장/알림 생략")
        return summary

    # ── 제안서 저장 ────────────────────────────────────────────────────────────
    proposal_path = _save_proposal(deduped, results)
    summary["proposal_path"] = str(proposal_path)

    # ── 알림 ──────────────────────────────────────────────────────────────────
    if max_alert:
        _alert(max_alert, deduped, proposal_path)

    if health_warn:
        msg = f"❌ [TaxRAG] {health_warn}\n규제지역 데이터 수동 확인 필요"
        print(msg)
        _send_slack(msg)
        _send_email("[TaxRAG] 스크래퍼 장기 실패 경보", msg)

    # ── auto-apply (P0 + 고신뢰 조건) ─────────────────────────────────────────
    if _AUTO_APPLY and deduped:
        high_conf = [
            c for c in deduped
            if c.confidence >= _AUTO_APPLY_THRESHOLD
            and c.source_name in ("gwanbo", "molit_board", "moef_board")
            and c.announcement_no
            and c.region
        ]
        if high_conf:
            print(f"  → auto-apply 조건 충족: {len(high_conf)}건")
            applied = apply_proposal(proposal_path)
            summary["applied"] = True
        else:
            print("  → auto-apply 조건 미충족 — admin 승인 대기")

    print(f"=== 규제지역 감지 완료: 후보 {len(deduped)}건 ===\n")
    return summary


def get_degraded_warning() -> Optional[str]:
    """
    RAG 파이프라인에서 호출 — 스크래퍼가 오래 실패했으면 경고문 반환.
    TaxAnswer.warnings에 삽입 용도.
    """
    if not SCRAPER_HEALTH_PATH.exists():
        return None
    try:
        health = json.loads(SCRAPER_HEALTH_PATH.read_text(encoding="utf-8"))
        now = datetime.now()
        for name, info in health.items():
            if info.get("status") == "fail":
                first_fail = info.get("first_fail", now.isoformat())
                hours = (now - datetime.fromisoformat(first_fail)).total_seconds() / 3600
                if hours >= _HEALTH_WARN_HOURS:
                    days = int(hours // 24)
                    return (
                        f"규제지역 현황 데이터가 {days}일 이상 미갱신 상태입니다. "
                        "최신 지정 여부를 국토교통부(molit.go.kr) 또는 기획재정부(moef.go.kr)에서 직접 확인하시길 권고합니다."
                    )
    except Exception:
        pass
    return None
