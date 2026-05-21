"""
P2 — 네이버 뉴스 API 키워드 모니터링 (약한 경보)

진실 소스가 아님 — "공식 사이트 재확인 필요" 경보 전용.
NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 환경변수 필요.
"""
from __future__ import annotations

import os
import re
from datetime import datetime
from typing import List, Optional

from dotenv import load_dotenv

load_dotenv()

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

from src.ingestion.area_sources import (
    AlertLevel, DesignationCandidate, SourcePriority, SourceResult,
    compute_page_hash, load_source_state, save_source_state,
)

SOURCE_NAME = "news_signal"

_NAVER_API = "https://openapi.naver.com/v1/search/news.json"
_QUERIES = [
    "조정대상지역 지정 해제",
    "투기과열지구 지정 해제",
    "주거정책심의위원회 규제지역",
]
_NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID", "")
_NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET", "")

_EXCLUDE_WORDS = ["분석", "전망", "예측", "칼럼", "오피니언", "의견"]
_DATE_PATTERN = re.compile(r"(\d{4})[.\-](\d{2})[.\-](\d{2})")


def _search_naver(query: str) -> Optional[list]:
    if not (_NAVER_CLIENT_ID and _NAVER_CLIENT_SECRET):
        return None
    headers = {
        "X-Naver-Client-Id": _NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": _NAVER_CLIENT_SECRET,
    }
    params = {"query": query, "display": 10, "sort": "date"}
    try:
        resp = requests.get(_NAVER_API, headers=headers, params=params, timeout=10)
        if resp.status_code == 200:
            return resp.json().get("items", [])
    except Exception:
        pass
    return None


def _is_signal_article(title: str, description: str) -> bool:
    text = title + description
    if any(w in text for w in _EXCLUDE_WORDS):
        return False
    return any(w in text for w in ["지정", "해제", "발표", "결정", "심의위원회 결과"])


def _clean_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text)


def run() -> SourceResult:
    if not HAS_REQUESTS:
        return SourceResult(
            source_name=SOURCE_NAME,
            priority=SourcePriority.P2,
            success=False,
            error_message="requests 미설치",
        )

    if not (_NAVER_CLIENT_ID and _NAVER_CLIENT_SECRET):
        return SourceResult(
            source_name=SOURCE_NAME,
            priority=SourcePriority.P2,
            success=False,
            error_message="NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 미설정 — .env에 추가 필요",
        )

    all_articles: List[dict] = []
    for query in _QUERIES:
        items = _search_naver(query)
        if items:
            for item in items:
                all_articles.append({
                    "title": _clean_html(item.get("title", "")),
                    "description": _clean_html(item.get("description", "")),
                    "url": item.get("link", item.get("originallink", "")),
                    "pub_date": item.get("pubDate", ""),
                })

    page_hash = compute_page_hash("|".join(a["url"] for a in all_articles))
    state = load_source_state(SOURCE_NAME)
    known_urls = set(state.get("last_seen_urls", []))
    all_urls = {a["url"] for a in all_articles}
    new_articles = [a for a in all_articles if a["url"] not in known_urls]

    candidates: List[DesignationCandidate] = []
    for art in new_articles:
        if not _is_signal_article(art["title"], art["description"]):
            continue
        area_type = (
            "투기과열지구" if "투기과열지구" in art["title"]
            else "투기지역" if "투기지역" in art["title"]
            else "조정대상지역"
        )
        is_release = "해제" in art["title"]
        candidates.append(DesignationCandidate(
            area_type=area_type,
            region="",
            designated_at=None if is_release else "",
            released_at="" if is_release else None,
            announcement_no="",
            effective_date="",
            source_url=art["url"],
            source_name=SOURCE_NAME,
            confidence=0.25,
            raw_text=art["title"] + " | " + art["description"],
            parser_warnings=[
                "뉴스 신호 — 진실 소스 아님. 국토교통부/기획재정부 공식 공고 확인 필요",
            ],
        ))

    save_source_state(SOURCE_NAME, {
        "last_page_hash": page_hash,
        "last_seen_urls": list(all_urls | known_urls),
        "last_success_at": datetime.now().isoformat(),
    })

    return SourceResult(
        source_name=SOURCE_NAME,
        priority=SourcePriority.P2,
        success=True,
        candidates=candidates,
        alert_level=AlertLevel.WARNING if candidates else None,
        page_hash=page_hash,
    )
