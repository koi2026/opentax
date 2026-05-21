"""
P0 — 기획재정부 고시·공고·지침 게시판 감시 (Playwright headless)

투기지역(소득세법 §104의2) 지정·해제는 기획재정부 장관 권한이다.
moef.go.kr 게시판 역시 WAF로 plain requests를 막으므로 Playwright 우선.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import List, Optional

from src.ingestion.area_sources import (
    AlertLevel, DesignationCandidate, SourcePriority, SourceResult,
    compute_page_hash, load_source_state, save_source_state,
)

SOURCE_NAME = "moef_board"

_BOARD_URL = (
    "https://www.moef.go.kr/lw/pblanc/TbPblancList.do"
    "?bbsId=MOSFBBS_000000000060&menuNo=7090200"
    "&searchCondition3=1&searchKeyword3=%EC%A7%80%EC%A0%95%EC%A7%80%EC%97%AD"
)

_ANNOUNCE_PATTERN = re.compile(r"기획재정부\s*고시\s*제\s*(\d{4}[-–]\d+호)")
_DATE_PATTERN = re.compile(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})")


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
                "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
            ),
            "Referer": "https://www.moef.go.kr/",
            "Accept-Language": "ko-KR,ko;q=0.9",
        }
        resp = requests.get(url, headers=headers, timeout=20)
        if resp.status_code == 200:
            return resp.text
        return None
    except Exception:
        return None


def _parse_items(html: str) -> List[dict]:
    items = []
    link_pattern = re.compile(
        r'<a[^>]+href="([^"]+)"[^>]*>\s*([^<]*(?:투기지역|지정지역|규제지역)[^<]*)\s*</a>',
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
        base = "https://www.moef.go.kr"
        items.append({
            "title": title,
            "url": f"{base}{href}" if href.startswith("/") else href,
            "date": date_str,
            "announcement_no": f"기획재정부고시 제{announces[0]}" if announces else "",
        })
    return items


def run() -> SourceResult:
    html = _try_requests(_BOARD_URL) or _try_playwright(_BOARD_URL)
    if not html:
        return SourceResult(
            source_name=SOURCE_NAME,
            priority=SourcePriority.P0,
            success=False,
            error_message="MoEF 게시판 접근 실패",
            alert_level=AlertLevel.ERROR,
        )

    page_hash = compute_page_hash(html)
    state = load_source_state(SOURCE_NAME)
    known_urls = set(state.get("last_seen_urls", []))

    items = _parse_items(html)
    all_urls = {i["url"] for i in items}
    new_items = [i for i in items if i["url"] not in known_urls]

    candidates: List[DesignationCandidate] = []
    for item in new_items:
        is_release = any(w in item["title"] for w in ["해제", "제외"])
        candidates.append(DesignationCandidate(
            area_type="투기지역",
            region="",
            designated_at=None if is_release else item["date"],
            released_at=item["date"] if is_release else None,
            announcement_no=item["announcement_no"],
            effective_date=item["date"],
            source_url=item["url"],
            source_name=SOURCE_NAME,
            confidence=0.75,
            raw_text=item["title"],
            parser_warnings=["region 미추출 — 첨부 파일 수동 확인 필요"],
        ))

    save_source_state(SOURCE_NAME, {
        "last_page_hash": page_hash,
        "last_seen_urls": list(all_urls | known_urls),
        "last_success_at": datetime.now().isoformat(),
        "last_http_status": 200,
    })

    return SourceResult(
        source_name=SOURCE_NAME,
        priority=SourcePriority.P0,
        success=True,
        candidates=candidates,
        alert_level=AlertLevel.CRITICAL if candidates else None,
        page_hash=page_hash,
    )
