"""
P0 — 전자관보(gwanbo.go.kr) 키워드 검색

전자관보는 법령 효력의 최종 공식 채널이다.
조정대상지역·투기과열지구·투기지역 관련 고시가 게재되면 이 소스가 감지한다.
"""
from __future__ import annotations

import re
import time
from datetime import datetime
from typing import List
from urllib.parse import urlencode

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

from src.ingestion.area_sources import (
    AlertLevel, DesignationCandidate, SourcePriority, SourceResult,
    compute_page_hash, has_page_changed, load_source_state, save_source_state,
)

SOURCE_NAME = "gwanbo"

_AREA_KEYWORDS = [
    "조정대상지역", "투기과열지구", "투기지역", "토지거래허가구역",
    "주거정책심의위원회", "지정지역 해제", "규제지역",
]

_AREA_TYPE_MAP = {
    "조정대상지역": "조정대상지역",
    "투기과열지구": "투기과열지구",
    "투기지역": "투기지역",
    "토지거래허가구역": "토지거래허가구역",
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
}

_SEARCH_URL = "https://www.gwanbo.go.kr/search/searchList.do"


def _search_gwanbo(keyword: str, page: int = 1) -> str:
    """전자관보 검색 결과 HTML 반환."""
    params = {
        "searchKeyword": keyword,
        "searchType": "1",
        "pageIndex": str(page),
        "pageUnit": "20",
    }
    resp = requests.get(_SEARCH_URL, params=params, headers=_HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.text


def _extract_items(html: str, keyword: str) -> List[dict]:
    """검색 결과 HTML에서 공고 목록 추출."""
    items = []
    # 공고 제목 패턴: 링크 텍스트 + 날짜
    title_pattern = re.compile(
        r'<a[^>]+href="([^"]+)"[^>]*>\s*([^<]*(?:' + re.escape(keyword) + r')[^<]*)\s*</a>',
        re.IGNORECASE,
    )
    date_pattern = re.compile(r'(\d{4}[-./]\d{2}[-./]\d{2})')
    announce_pattern = re.compile(r'((?:국토교통부|기획재정부|서울특별시)[^\s]*\s*제\d{4}-\d+호)')

    for m in title_pattern.finditer(html):
        href, title = m.group(1), m.group(2).strip()
        ctx_start = max(0, m.start() - 200)
        ctx_end = min(len(html), m.end() + 400)
        ctx = html[ctx_start:ctx_end]
        dates = date_pattern.findall(ctx)
        announces = announce_pattern.findall(ctx)
        items.append({
            "title": title,
            "url": f"https://www.gwanbo.go.kr{href}" if href.startswith("/") else href,
            "date": dates[0].replace("/", "-").replace(".", "-") if dates else "",
            "announcement_no": announces[0] if announces else "",
        })
    return items


def _detect_area_type(title: str) -> str:
    for kw, area_type in _AREA_TYPE_MAP.items():
        if kw in title:
            return area_type
    return ""


def _detect_is_release(title: str) -> bool:
    return any(w in title for w in ["해제", "제외", "완화"])


def run() -> SourceResult:
    if not HAS_REQUESTS:
        return SourceResult(
            source_name=SOURCE_NAME,
            priority=SourcePriority.P0,
            success=False,
            error_message="requests 미설치",
        )

    all_items: List[dict] = []
    try:
        for kw in _AREA_KEYWORDS[:4]:
            html = _search_gwanbo(kw)
            items = _extract_items(html, kw)
            all_items.extend(items)
            time.sleep(0.5)
    except Exception as e:
        return SourceResult(
            source_name=SOURCE_NAME,
            priority=SourcePriority.P0,
            success=False,
            error_message=str(e),
            alert_level=AlertLevel.ERROR,
        )

    seen_urls = set()
    deduped = []
    for item in all_items:
        if item["url"] not in seen_urls:
            seen_urls.add(item["url"])
            deduped.append(item)

    page_content = "|".join(i["url"] + i["title"] for i in deduped)
    page_hash = compute_page_hash(page_content)
    changed = has_page_changed(SOURCE_NAME, page_hash)

    state = load_source_state(SOURCE_NAME)
    known_urls = set(state.get("last_seen_urls", []))

    candidates: List[DesignationCandidate] = []
    new_items = [i for i in deduped if i["url"] not in known_urls]

    for item in new_items:
        area_type = _detect_area_type(item["title"])
        if not area_type:
            continue
        is_release = _detect_is_release(item["title"])
        candidates.append(DesignationCandidate(
            area_type=area_type,
            region="",
            designated_at=None if is_release else item["date"],
            released_at=item["date"] if is_release else None,
            announcement_no=item["announcement_no"],
            effective_date=item["date"],
            source_url=item["url"],
            source_name=SOURCE_NAME,
            confidence=0.6,
            raw_text=item["title"],
        ))

    save_source_state(SOURCE_NAME, {
        "last_page_hash": page_hash,
        "last_seen_urls": list(seen_urls),
        "last_success_at": datetime.now().isoformat(),
        "last_http_status": 200,
    })

    alert = AlertLevel.CRITICAL if candidates else (AlertLevel.WARNING if changed else None)

    return SourceResult(
        source_name=SOURCE_NAME,
        priority=SourcePriority.P0,
        success=True,
        candidates=candidates,
        alert_level=alert,
        page_hash=page_hash,
    )
