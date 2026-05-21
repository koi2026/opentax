"""
P1 — 국토교통부 보도자료 감시 (조기 경보)

주거정책심의위원회 결과는 공식 고시보다 보도자료에서 먼저 발표된다.
여기서 잡힌 신호는 WARNING 등급 — 공식 공고 확인 후 manual_table 반영.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import List, Optional

from src.ingestion.area_sources import (
    AlertLevel, DesignationCandidate, SourcePriority, SourceResult,
    compute_page_hash, load_source_state, save_source_state,
)

SOURCE_NAME = "molit_press"

_PRESS_SEARCH_URL = (
    "https://www.molit.go.kr/USR/NEWS/m_71/lst.jsp"
    "?searchKeyword=%EC%A3%BC%EA%B1%B0%EC%A0%95%EC%B1%85%EC%8B%AC%EC%9D%98%EC%9C%84%EC%9B%90%ED%9A%8C"
    "&pageIndex=1"
)
_KEYWORDS = ["조정대상지역", "투기과열지구", "규제지역", "주거정책심의위원회"]


def _fetch(url: str) -> Optional[str]:
    # requests 먼저, 실패시 Playwright
    try:
        import requests
        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "ko-KR"},
            timeout=20,
        )
        if resp.status_code == 200:
            return resp.text
    except Exception:
        pass
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, timeout=30000, wait_until="networkidle")
            html = page.content()
            browser.close()
            return html
    except Exception:
        return None


def _parse_press_items(html: str) -> List[dict]:
    items = []
    link_pat = re.compile(
        r'<a[^>]+href="([^"]+)"[^>]*>\s*([^<]*(?:'
        + "|".join(_KEYWORDS)
        + r')[^<]*)\s*</a>',
        re.IGNORECASE,
    )
    date_pat = re.compile(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})")
    for m in link_pat.finditer(html):
        href, title = m.group(1), m.group(2).strip()
        ctx = html[max(0, m.start()-50):m.end()+200]
        dates = date_pat.findall(ctx)
        date_str = ""
        if dates:
            y, mo, d = dates[0]
            date_str = f"{y}-{mo.zfill(2)}-{d.zfill(2)}"
        items.append({
            "title": title,
            "url": f"https://www.molit.go.kr{href}" if href.startswith("/") else href,
            "date": date_str,
        })
    return items


def run() -> SourceResult:
    html = _fetch(_PRESS_SEARCH_URL)
    if not html:
        return SourceResult(
            source_name=SOURCE_NAME,
            priority=SourcePriority.P1,
            success=False,
            error_message="MOLIT 보도자료 접근 실패",
            alert_level=AlertLevel.ERROR,
        )

    page_hash = compute_page_hash(html)
    state = load_source_state(SOURCE_NAME)
    known_urls = set(state.get("last_seen_urls", []))

    items = _parse_press_items(html)
    all_urls = {i["url"] for i in items}
    new_items = [i for i in items if i["url"] not in known_urls]

    candidates: List[DesignationCandidate] = []
    for item in new_items:
        area_type = (
            "투기과열지구" if "투기과열지구" in item["title"]
            else "조정대상지역" if "조정대상지역" in item["title"]
            else "규제지역"
        )
        is_release = any(w in item["title"] for w in ["해제", "완화"])
        candidates.append(DesignationCandidate(
            area_type=area_type,
            region="",
            designated_at=None if is_release else item["date"],
            released_at=item["date"] if is_release else None,
            announcement_no="",
            effective_date=item["date"],
            source_url=item["url"],
            source_name=SOURCE_NAME,
            confidence=0.45,
            raw_text=item["title"],
            parser_warnings=["보도자료 단계 — 공식 고시 확인 필요"],
        ))

    save_source_state(SOURCE_NAME, {
        "last_page_hash": page_hash,
        "last_seen_urls": list(all_urls | known_urls),
        "last_success_at": datetime.now().isoformat(),
    })

    # 보도자료는 WARNING 등급
    alert = AlertLevel.WARNING if candidates else None
    return SourceResult(
        source_name=SOURCE_NAME,
        priority=SourcePriority.P1,
        success=True,
        candidates=candidates,
        alert_level=alert,
        page_hash=page_hash,
    )
