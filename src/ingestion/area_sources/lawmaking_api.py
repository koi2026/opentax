"""
P1 — 국민참여입법센터 입법예고 모니터링 (조기 경보)

주택법·소득세법 시행령 입법예고는 규제지역 지정/해제 전 선행 신호다.
접근 가능 확인됨(200 OK). WARNING 신호 전용 — truth source 아님.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import List, Optional
from urllib.parse import urlencode

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

from src.ingestion.area_sources import (
    AlertLevel, DesignationCandidate, SourcePriority, SourceResult,
    compute_page_hash, load_source_state, save_source_state,
)

SOURCE_NAME = "lawmaking_api"

_BASE = "https://opinion.lawmaking.go.kr"
_SEARCH_API = f"{_BASE}/ogc/pc/lawPhases/list.do"

_TARGET_LAWS = ["주택법", "소득세법 시행령", "조세특례제한법 시행령"]
_AREA_KEYWORDS = ["조정대상지역", "투기과열지구", "투기지역", "규제지역", "지정", "해제"]

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TaxRAG/1.0)",
    "Accept": "application/json, text/html",
    "Accept-Language": "ko-KR,ko;q=0.9",
}


def _search_lawmaking(law_name: str) -> Optional[dict]:
    params = {
        "searchStr": law_name,
        "searchType": "TITLE",
        "pageIndex": "1",
        "pageSize": "10",
    }
    try:
        resp = requests.get(_SEARCH_API, params=params, headers=_HEADERS, timeout=15)
        if resp.status_code == 200:
            try:
                return resp.json()
            except Exception:
                return {"html": resp.text}
    except Exception:
        pass
    return None


def _extract_notices(data: dict, law_name: str) -> List[dict]:
    notices = []
    if not data:
        return notices

    items = data.get("result", data.get("list", []))
    if not isinstance(items, list):
        return notices

    for item in items:
        title = item.get("lawNm", item.get("title", ""))
        if not any(kw in title for kw in _AREA_KEYWORDS):
            continue
        notices.append({
            "title": title,
            "law_name": law_name,
            "url": f"{_BASE}/ogc/pc/lawPhases/view.do?lawPhrId={item.get('lawPhrId', '')}",
            "date": item.get("pblcRqstDt", item.get("date", "")),
        })
    return notices


def run() -> SourceResult:
    if not HAS_REQUESTS:
        return SourceResult(
            source_name=SOURCE_NAME,
            priority=SourcePriority.P1,
            success=False,
            error_message="requests 미설치",
        )

    all_notices: List[dict] = []
    errors = []
    for law in _TARGET_LAWS:
        data = _search_lawmaking(law)
        if data:
            all_notices.extend(_extract_notices(data, law))
        else:
            errors.append(law)

    page_hash = compute_page_hash("|".join(n["url"] + n["title"] for n in all_notices))
    state = load_source_state(SOURCE_NAME)
    known_urls = set(state.get("last_seen_urls", []))
    all_urls = {n["url"] for n in all_notices}
    new_notices = [n for n in all_notices if n["url"] not in known_urls]

    candidates: List[DesignationCandidate] = []
    for n in new_notices:
        is_release = "해제" in n["title"]
        candidates.append(DesignationCandidate(
            area_type="규제지역",
            region="",
            designated_at=None if is_release else n["date"][:10] if n["date"] else "",
            released_at=n["date"][:10] if (is_release and n["date"]) else None,
            announcement_no="",
            effective_date=n["date"][:10] if n["date"] else "",
            source_url=n["url"],
            source_name=SOURCE_NAME,
            confidence=0.35,
            raw_text=n["title"],
            parser_warnings=["입법예고 단계 — 실제 고시 전 선행 신호만"],
        ))

    save_source_state(SOURCE_NAME, {
        "last_page_hash": page_hash,
        "last_seen_urls": list(all_urls | known_urls),
        "last_success_at": datetime.now().isoformat(),
    })

    return SourceResult(
        source_name=SOURCE_NAME,
        priority=SourcePriority.P1,
        success=True,
        candidates=candidates,
        alert_level=AlertLevel.WARNING if candidates else None,
        page_hash=page_hash,
        error_message=f"일부 법령 조회 실패: {errors}" if errors else "",
    )
