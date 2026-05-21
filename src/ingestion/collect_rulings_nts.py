"""
국세법령정보시스템(taxlaw.nts.go.kr) 유권해석 수집기

수집 대상:
  - 질의회신 (qt): /qt/USEQTJ001M.do (목록) → /qt/USEQTJ002P.do (상세)
  - 판단사례 (pd): /pd/USEPDI001M.do (목록) → /pd/USEPDI002P.do (상세)
  - 세법해석례 (해석): /ic/USEICI001M.do (목록) → /ic/USEICI002P.do (상세)

저장 위치: data/rulings/nts/{type}_{ntstBscId}.json

JSON 스키마 (embed_rulings.py 호환):
  id, title, question, answer, issued_at, related_articles, keywords,
  source_type, doc_number, url, deprecated

사용법:
    python -m src.ingestion.collect_rulings_nts                     # 전체
    python -m src.ingestion.collect_rulings_nts --type qt           # 질의회신만
    python -m src.ingestion.collect_rulings_nts --type ic           # 세법해석례만
    python -m src.ingestion.collect_rulings_nts --tax 양도소득세     # 세목 필터
    python -m src.ingestion.collect_rulings_nts --dry-run
    python -m src.ingestion.collect_rulings_nts --resume            # 기존 파일 스킵
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://taxlaw.nts.go.kr"
NTS_DIR = Path("data/rulings/nts")

# 수집 유형 설정
RULING_TYPES = {
    "qt": {
        "name": "질의회신",
        "list_path": "/qt/USEQTJ001M.do",
        "detail_path": "/qt/USEQTJ002P.do",
    },
    "pd": {
        "name": "판단사례",
        "list_path": "/pd/USEPDI001M.do",
        "detail_path": "/pd/USEPDI002P.do",
    },
    "ic": {
        "name": "세법해석례",
        "list_path": "/ic/USEICI001M.do",
        "detail_path": "/ic/USEICI002P.do",
    },
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": BASE_URL,
    "Accept-Language": "ko-KR,ko;q=0.9",
}

_TAX_KEYWORDS = {
    "양도소득세": ["양도", "양도세", "양도소득"],
    "상속세":    ["상속"],
    "증여세":    ["증여"],
}


# ── 목록 페이지 수집 ──────────────────────────────────────────────────────────

def _fetch_list_page(
    session: requests.Session,
    ruling_type: str,
    page: int,
    tax_name: str,
) -> tuple[list[str], int]:
    """목록 페이지에서 ntstBscId 목록과 총 건수 반환."""
    cfg = RULING_TYPES[ruling_type]
    url = BASE_URL + cfg["list_path"]

    params = {
        "pageIndex": page,
        "pageUnit": 100,
        "searchSeMkNm": tax_name,
        "searchContents": "",
    }

    try:
        resp = session.get(url, params=params, headers=_HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  목록 요청 오류 (page={page}): {e}")
        return [], 0

    soup = BeautifulSoup(resp.text, "html.parser")

    # 총 건수 파싱
    total = 0
    count_tag = soup.find(string=re.compile(r"총\s+[\d,]+\s*건"))
    if count_tag:
        m = re.search(r"([\d,]+)", count_tag)
        if m:
            total = int(m.group(1).replace(",", ""))

    # ntstBscId 추출 — href 패턴에서
    ids: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        m = re.search(r"ntstBscId=(\d+)", href)
        if m:
            ids.append(m.group(1))

    # onclick 패턴도 체크 (일부 사이트는 JS onclick으로 링크)
    if not ids:
        for tag in soup.find_all(attrs={"onclick": True}):
            m = re.search(r"ntstBscId['\"]?\s*[,=]\s*['\"]?(\d+)", tag["onclick"])
            if m:
                ids.append(m.group(1))

    return list(dict.fromkeys(ids)), total  # 중복 제거, 순서 유지


# ── 상세 페이지 파싱 ──────────────────────────────────────────────────────────

def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _extract_table_value(soup: BeautifulSoup, label: str) -> str:
    """th에 label이 포함된 행의 td 값 반환."""
    for th in soup.find_all("th"):
        if label in th.get_text():
            td = th.find_next_sibling("td")
            if td:
                return _clean(td.get_text())
    return ""


def _extract_articles(soup: BeautifulSoup) -> list[str]:
    """관련법령 섹션에서 조문 목록 추출."""
    articles: list[str] = []

    # 관련법령 컨테이너 탐색
    for tag in soup.find_all(["th", "dt", "strong"]):
        text = tag.get_text()
        if "관련법령" in text or "관련조문" in text:
            container = tag.find_next_sibling() or tag.parent
            if container:
                for item in container.find_all(["li", "span", "p"]):
                    t = _clean(item.get_text())
                    if t and len(t) < 80:
                        articles.append(t)
            break

    # fallback: 조문 패턴 직접 추출
    if not articles:
        full_text = soup.get_text()
        for m in re.finditer(
            r"(?:소득세법|조세특례제한법|지방세법|상속세|증여세)[^\n]{0,60}(?:제\d+조[^\n]{0,40})?",
            full_text,
        ):
            t = _clean(m.group())
            if t not in articles:
                articles.append(t)

    return articles[:10]


def _parse_detail(html: str, ruling_type: str, ntstBscId: str) -> dict | None:
    """상세 페이지 HTML을 파싱해 ruling dict 반환. 빈 페이지면 None."""
    soup = BeautifulSoup(html, "html.parser")
    full_text = soup.get_text()

    # 존재하지 않는 ID 감지
    if any(kw in full_text for kw in ["해당 자료가 없습니다", "존재하지 않습니다", "조회된 자료가 없습니다"]):
        return None

    # 제목
    title = ""
    for sel in ["h3.tit", "h2.tit", ".view-tit", ".board-view-title", "h3", "h2"]:
        tag = soup.select_one(sel)
        if tag:
            title = _clean(tag.get_text())
            break
    if not title:
        title = _extract_table_value(soup, "제목") or _extract_table_value(soup, "요약")

    # 문서번호
    doc_number = (
        _extract_table_value(soup, "문서번호")
        or _extract_table_value(soup, "사건번호")
        or _extract_table_value(soup, "회신번호")
    )

    # 발행일
    issued_raw = (
        _extract_table_value(soup, "회신일")
        or _extract_table_value(soup, "발행일")
        or _extract_table_value(soup, "등록일")
        or _extract_table_value(soup, "결정일")
    )
    issued_at = re.sub(r"[^\d]", "", issued_raw)[:8]

    # 질의내용 / 회신내용
    question = (
        _extract_table_value(soup, "질의내용")
        or _extract_table_value(soup, "질의요지")
        or _extract_table_value(soup, "사실관계")
    )
    answer = (
        _extract_table_value(soup, "회신내용")
        or _extract_table_value(soup, "답변내용")
        or _extract_table_value(soup, "결정요지")
        or _extract_table_value(soup, "해석")
    )

    # 본문 전체 fallback — view-content 또는 유사 컨테이너
    if not question and not answer:
        for sel in [".view-content", ".board-view-content", ".content-area", "#contents"]:
            tag = soup.select_one(sel)
            if tag:
                content = _clean(tag.get_text())
                # 질의/회신 키워드로 분리 시도
                if "질의" in content and "회신" in content:
                    parts = re.split(r"(?:질의내용|질의요지)\s*[:：]?", content, maxsplit=1)
                    if len(parts) == 2:
                        answer_parts = re.split(r"(?:회신내용|답변)\s*[:：]?", parts[1], maxsplit=1)
                        question = _clean(answer_parts[0]) if answer_parts else parts[1]
                        answer = _clean(answer_parts[1]) if len(answer_parts) > 1 else ""
                else:
                    answer = content[:3000]
                break

    if not title and not answer:
        return None

    related_articles = _extract_articles(soup)

    # 키워드 — 제목 + 관련조문에서 단순 추출
    keywords: list[str] = []
    for kw in ["1세대1주택", "비과세", "중과", "감면", "조정대상지역", "양도소득세",
               "이월과세", "상생임대", "일시적2주택", "장기보유특별공제"]:
        if kw in (title + " " + answer):
            keywords.append(kw)

    detail_url = f"{BASE_URL}{RULING_TYPES[ruling_type]['detail_path']}?ntstBscId={ntstBscId}"

    return {
        "id": f"{ruling_type}_{ntstBscId}",
        "title": title,
        "question": question[:2000],
        "answer": answer[:2000],
        "issued_at": issued_at,
        "related_articles": related_articles,
        "keywords": keywords,
        "source_type": ruling_type,
        "doc_number": doc_number,
        "url": detail_url,
        "deprecated": False,
    }


# ── 상세 페이지 요청 ──────────────────────────────────────────────────────────

def _fetch_detail(
    session: requests.Session,
    ruling_type: str,
    ntstBscId: str,
) -> dict | None:
    """상세 페이지 1건 수집·파싱. 실패 시 None."""
    url = BASE_URL + RULING_TYPES[ruling_type]["detail_path"]
    try:
        resp = session.get(url, params={"ntstBscId": ntstBscId}, headers=_HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"    상세 요청 오류 ({ntstBscId}): {e}")
        return None

    return _parse_detail(resp.text, ruling_type, ntstBscId)


# ── deprecated 마킹 ────────────────────────────────────────────────────────────

def _mark_deprecated_files() -> int:
    """저장된 파일 중 deprecated_ids.json에 있는 doc_number를 deprecated=True로 업데이트."""
    deprecated_file = Path("data/rulings/deprecated_ids.json")
    if not deprecated_file.exists():
        return 0

    deprecated_ids: set[str] = set(
        json.loads(deprecated_file.read_text(encoding="utf-8")).get("ids", [])
    )
    updated = 0

    for fpath in NTS_DIR.glob("*.json"):
        try:
            record = json.loads(fpath.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        doc_num = record.get("doc_number", "")
        if doc_num and any(d in doc_num for d in deprecated_ids):
            if not record.get("deprecated"):
                record["deprecated"] = True
                fpath.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
                updated += 1

    return updated


# ── 메인 수집 ──────────────────────────────────────────────────────────────────

def collect_rulings(
    ruling_types: list[str] | None = None,
    tax_name: str = "양도소득세",
    dry_run: bool = False,
    resume: bool = True,
    delay: float = 1.0,
) -> dict:
    """
    taxlaw.nts.go.kr 유권해석 수집.

    Args:
        ruling_types: ["qt", "pd", "ic"] 중 선택. None이면 전체.
        tax_name: 세목 필터 ("양도소득세", "" for 전체)
        dry_run: True이면 목록만 확인, 파일 저장 안 함
        resume: True이면 이미 저장된 ID 스킵
        delay: 요청 간 대기 시간(초)

    Returns:
        {"saved": N, "skipped": N, "failed": N}
    """
    types = ruling_types or list(RULING_TYPES.keys())
    NTS_DIR.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    stats = {"saved": 0, "skipped": 0, "failed": 0}

    for rtype in types:
        cfg = RULING_TYPES[rtype]
        print(f"\n=== {cfg['name']} ({rtype}) 수집 ===")

        # 기존 저장 파일 ID 목록
        existing_ids: set[str] = set()
        if resume:
            for f in NTS_DIR.glob(f"{rtype}_*.json"):
                existing_ids.add(f.stem.removeprefix(f"{rtype}_"))

        # 목록 수집
        all_ids: list[str] = []
        first_ids, total = _fetch_list_page(session, rtype, 1, tax_name)
        all_ids.extend(first_ids)

        pages = max(1, (total + 99) // 100) if total else 1
        print(f"  총 {total}건 / {pages}페이지")

        for page in range(2, pages + 1):
            ids, _ = _fetch_list_page(session, rtype, page, tax_name)
            all_ids.extend(ids)
            time.sleep(delay * 0.5)

        all_ids = list(dict.fromkeys(all_ids))  # 중복 제거
        print(f"  수집된 ID: {len(all_ids)}개")

        if dry_run:
            print(f"  [DRY] 저장 대상: {len(all_ids) - len(existing_ids & set(all_ids))}건")
            continue

        # 상세 수집
        for i, nid in enumerate(all_ids, 1):
            if nid in existing_ids:
                stats["skipped"] += 1
                continue

            record = _fetch_detail(session, rtype, nid)
            if record is None:
                stats["failed"] += 1
                continue

            out_path = NTS_DIR / f"{rtype}_{nid}.json"
            out_path.write_text(
                json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            stats["saved"] += 1

            if i % 20 == 0:
                print(f"  진행: {i}/{len(all_ids)} (저장:{stats['saved']} 실패:{stats['failed']})")

            time.sleep(delay)

    if not dry_run:
        # deprecated 마킹
        updated = _mark_deprecated_files()
        if updated:
            print(f"\ndeprecated 마킹: {updated}건")

    print(f"\n완료: 저장={stats['saved']}, 스킵={stats['skipped']}, 실패={stats['failed']}")
    return stats


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="국세법령정보시스템 유권해석 수집기")
    parser.add_argument(
        "--type",
        dest="rtype",
        choices=list(RULING_TYPES.keys()) + ["all"],
        default="all",
        help="수집 유형 (기본: all)",
    )
    parser.add_argument("--tax", default="양도소득세", help="세목 필터 (기본: 양도소득세, 빈 문자열=전체)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true", default=True, help="기존 파일 스킵 (기본: True)")
    parser.add_argument("--delay", type=float, default=1.0, help="요청 간 대기 시간(초)")
    args = parser.parse_args()

    types = list(RULING_TYPES.keys()) if args.rtype == "all" else [args.rtype]
    collect_rulings(
        ruling_types=types,
        tax_name=args.tax,
        dry_run=args.dry_run,
        resume=args.resume,
        delay=args.delay,
    )
