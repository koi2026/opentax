"""
area_sources — 규제지역 변경 감지 소스 모듈 패키지

P0 (권위): gwanbo, molit_board, moef_board
P1 (조기경보): molit_press, lawmaking_api
P2 (약한보조): news_signal
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, date
from enum import Enum
from pathlib import Path
from typing import List, Optional

# ── 공통 타입 ──────────────────────────────────────────────────────────────────

STATE_DIR = Path("data/area_designations/source_state")
PROPOSALS_DIR = Path("data/area_designations/proposals")


class SourcePriority(str, Enum):
    P0 = "P0_authoritative"
    P1 = "P1_early_signal"
    P2 = "P2_weak_fallback"


class AlertLevel(str, Enum):
    CRITICAL = "critical"   # 현재 active 지역 지정/해제 감지
    WARNING  = "warning"    # 뉴스/RSS만, 공식 미확인
    ERROR    = "error"      # 스크래퍼 2일 이상 실패


@dataclass
class DesignationCandidate:
    """소스에서 추출한 지정/해제 후보 단건."""
    area_type: str                      # 조정대상지역|투기과열지구|투기지역|토지거래허가구역
    region: str                         # 지역명 (정규화 전)
    designated_at: Optional[str]        # YYYY-MM-DD
    released_at: Optional[str]          # YYYY-MM-DD (해제인 경우)
    announcement_no: str
    effective_date: Optional[str]       # YYYY-MM-DD
    source_url: str
    source_name: str
    confidence: float                   # 0.0~1.0
    raw_text: str = ""                  # 추출 원문 (감사용)
    attachment_paths: List[str] = field(default_factory=list)
    parser_warnings: List[str] = field(default_factory=list)

    def designation_hash(self) -> str:
        key = f"{self.area_type}|{self.region}|{self.designated_at}|{self.released_at}|{self.announcement_no}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SourceResult:
    """소스 실행 결과."""
    source_name: str
    priority: SourcePriority
    success: bool
    candidates: List[DesignationCandidate] = field(default_factory=list)
    alert_level: Optional[AlertLevel] = None
    error_message: str = ""
    page_hash: str = ""
    fetched_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["priority"] = self.priority.value if self.priority else None
        d["alert_level"] = self.alert_level.value if self.alert_level else None
        return d


# ── 소스 상태 관리 ─────────────────────────────────────────────────────────────

def load_source_state(source_name: str) -> dict:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = STATE_DIR / f"{source_name}.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_source_state(source_name: str, state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = STATE_DIR / f"{source_name}.json"
    state["updated_at"] = datetime.now().isoformat()
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def compute_page_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def has_page_changed(source_name: str, new_hash: str) -> bool:
    state = load_source_state(source_name)
    return state.get("last_page_hash") != new_hash
