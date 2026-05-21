"""
P0 — 국토교통부 공고/행정규칙 게시판 감시 (Playwright headless)

조정대상지역·투기과열지구 지정·해제 공고가 첨부 PDF/HWP와 함께 게시된다.
plain requests로는 WAF에 막히므로 Playwright를 우선 사용한다.
"""
from __future__ import annotations

import re
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from src.ingestion.area_sources import (
    AlertLevel, DesignationCandidate, SourcePriority, SourceResult,
    compute_page_hash, load_source_state, save_source_state,
)

SOURCE_NAME = "molit_board"

# 국토교통부 훈령·예규·고시 목록 (파라미터 기반 JSP)
_BOARD_URL = (
    "https://www.molit.go.kr/USR/I0204/m_45/lst.jsp"
    "?searchKeyword=%EC%A1%B0%EC%A0%95%EB%8C%80%EC%83%81%EC%A7%80%EC%97%AD"
    "&bbsId=094&pageIndex=1"
)
_PRESS_URL = (
    "https://www.molit.go.kr/USR/NEWS/m_71/lst.jsp"
    "?searchKeyword=%EC%A3%BC%EA%B1%B0%EC%A0%95%EC%B1%85%EC%8B%AC%EC%9D%98%EC%9C%84%EC%9B%90%ED%9A%8C"
    "&pageIndex=1"
)
_DOWNLOAD_DIR = Path("data/area_designations/raw")

_AREA_KEYWORDS = ["조정대상지역", "투기과열지구", "지정", "해제"]

_ANNOUNCE_PATTERN = re.compile(
    r"국토교통부\s*고시\s*제\s*(\d{4}[-–]\d+호)"
)
_DATE_PATTERN = re.compile(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})")
_REGION_PATTERN = re.compile(
    r"([가-힣]+(?:특별시|광역시|특별자치시|도|특별자치도)(?:\s+[가-힣]+(?:시|군|구))?)"
)


def _try_playwright(url: str) -> Optional[str]:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_extra_http_headers({"Accept-Language": "ko-KR,ko;q=0.9"})
            page.goto(url, timeout=30000, wait_until="networkidle")
            content = page.content()
            browser.close()
            return content
    except Exception:
        return None


def _try_requests(url: str) -> Optional[str]:
    try:
        import requests
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Referer": "https://www.molit.go.kr/",
            "Accept-Language": "ko-KR,ko;q=0.9",
        }
        resp = requests.get(url, headers=headers, timeout=20)
        if resp.status_code == 200:
            return resp.text
        return None
    except Exception:
        return None


def _fetch(url: str) -> Optional[str]:
    html = _try_requests(url)
    if html:
        return html
    return _try_playwright(url)


def _parse_items(html: str) -> List[dict]:
    """공고 목록에서 관련 항목 추출."""
    items = []
    link_pattern = re.compile(
        r'<a[^>]+href="([^"]+)"[^>]*>\s*([^<]*(?:조정대상지역|투기과열지구)[^<]*)\s*</a>',
        re.IGNORECASE,
    )
    for m in link_pattern.finditer(html):
        href, title = m.group(1), m.group(2).strip()
        ctx = html[max(0, m.start()-100):m.end()+300]
        dates = _DATE_PATTERN.findall(ctx)
        announces = _ANNOUNCE_PATTERN.findall(ctx)
        date_str = ""
        if dates:
            y, mo, d = dates[0]
            date_str = f"{y}-{mo.zfill(2)}-{d.zfill(2)}"
        items.append({
            "title": title,
            "url": f"https://www.molit.go.kr{href}" if href.startswith("/") else href,
            "date": date_str,
            "announcement_no": f"국토교통부고시 제{announces[0]}" if announces else "",
        })
    return items


def _extract_candidates(items: List[dict], known_urls: set) -> List[DesignationCandidate]:
    candidates = []
    for item in items:
        if item["url"] in known_urls:
            continue
        is_release = any(w in item["title"] for w in ["해제", "제외"])
        area_type = (
            "투기과열지구" if "투기과열지구" in item["title"]
            else "조정대상지역"
        )
        candidates.append(DesignationCandidate(
            area_type=area_type,
            region="",
            designated_at=None if is_release else item["date"],
            released_at=item["date"] if is_release else None,
            announcement_no=item["announcement_no"],
            effective_date=item["date"],
            source_url=item["url"],
            source_name=SOURCE_NAME,
            confidence=0.75,
            raw_text=item["title"],
            parser_warnings=["region 미추출 — 첨부 파일 수동 확인 필요"] if not item["announcement_no"] else [],
        ))
    return candidates


def run() -> SourceResult:
    html = _fetch(_BOARD_URL)
    if not html:
        return SourceResult(
            source_name=SOURCE_NAME,
            priority=SourcePriority.P0,
            success=False,
            error_message="MOLIT 게시판 접근 실패 (WAF 차단 가능성)",
            alert_level=AlertLevel.ERROR,
        )

    page_hash = compute_page_hash(html)
    state = load_source_state(SOURCE_NAME)
    known_urls = set(state.get("last_seen_urls", []))

    items = _parse_items(html)
    candidates = _extract_candidates(items, known_urls)

    all_urls = {i["url"] for i in items}
    save_source_state(SOURCE_NAME, {
        "last_page_hash": page_hash,
        "last_seen_urls": list(all_urls | known_urls),
        "last_success_at": datetime.now().isoformat(),
        "last_http_status": 200,
    })

    alert = AlertLevel.CRITICAL if candidates else None
    return SourceResult(
        source_name=SOURCE_NAME,
        priority=SourcePriority.P0,
        success=True,
        candidates=candidates,
        alert_level=alert,
        page_hash=page_hash,
    )
