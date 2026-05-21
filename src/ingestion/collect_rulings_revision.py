"""
세법해석정비 수집기 (taxlaw.nts.go.kr/qt/USEQTE001M.do)

삭제사례(폐지 예규) ID를 추출하고 deprecated_ids.json에 저장한다.
예규 수집 시 이 목록을 참조해 Pinecone에 deprecated=True 표시.

사용법:
    python -m src.ingestion.collect_rulings_revision              # 양도소득세
    python -m src.ingestion.collect_rulings_revision --tax all    # 전 세목
    python -m src.ingestion.collect_rulings_revision --dry-run
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
LIST_URL = f"{BASE_URL}/qt/USEQTE001M.do"

RULINGS_DIR = Path("data/rulings")
DEPRECATED_FILE = RULINGS_DIR / "deprecated_ids.json"
REVISION_FILE = RULINGS_DIR / "revision_cases.json"

# 세목구분 코드 (페이지 드롭다운 기준)
TAX_CODES = {
    "transfer": "양도소득세",
    "gift":     "증여세",
    "inherit":  "상속세",
    "all":      "",          # 전체
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


# ── HTML 파싱 ──────────────────────────────────────────────────────────────────

def _extract_doc_ids(text: str) -> list[str]:
    """텍스트에서 예규 문서번호 패턴을 추출한다.

    예: "사전-2023-법규재산-0604", "법규재산2014-384", "재일01254-100"
    """
    patterns = [
        r"사전-\d{4}-[가-힣]+-\d+",
        r"[가-힣]+\d{4}-\d+",
        r"[가-힣]+재산\d{4}-\d+",
        r"서면-\d{4}-[가-힣]+-\d+",
        r"기획재정부\s+[가-힣]+-\d+",
        r"재일\d+-\d+",
    ]
    found = []
    for pat in patterns:
        found.extend(re.findall(pat, text))
    return list(set(found))


def _parse_row(row) -> dict | None:
    """테이블 행 하나를 파싱해 revision case dict 반환."""
    cols = row.find_all("td")
    if len(cols) < 5:
        return None

    # 번호
    num_text = cols[0].get_text(strip=True)
    try:
        num = int(num_text)
    except ValueError:
        return None

    # 요약정보 (제목 + 태그)
    summary_col = cols[1]
    title_tag = summary_col.find("a") or summary_col
    title = title_tag.get_text(strip=True)

    # 유지사례
    maintained_col = cols[2]
    maintained_text = maintained_col.get_text(" ", strip=True)
    maintained_ids = _extract_doc_ids(maintained_text)

    # 삭제사례
    deleted_col = cols[3]
    deleted_text = deleted_col.get_text(" ", strip=True)
    deleted_ids = _extract_doc_ids(deleted_text)

    # "외 N건" 파싱
    extra_match = re.search(r"외\s*(\d+)건", deleted_text)
    deleted_extra = int(extra_match.group(1)) if extra_match else 0

    # 정비유형
    revision_type = cols[4].get_text(strip=True) if len(cols) > 4 else ""

    # 등록일자
    reg_date = cols[5].get_text(strip=True) if len(cols) > 5 else ""
    reg_date_clean = reg_date.replace(".", "").replace(" ", "")

    return {
        "num": num,
        "title": title,
        "maintained_ids": maintained_ids,
        "maintained_raw": maintained_text,
        "deleted_ids": deleted_ids,
        "deleted_extra": deleted_extra,
        "deleted_raw": deleted_text,
        "revision_type": revision_type,
        "registered_at": reg_date_clean,
    }


def _fetch_page(session: requests.Session, page: int, tax_name: str) -> tuple[list[dict], int]:
    """목록 페이지 1장 수집. (rows, total_count) 반환."""
    params = {
        "pageIndex": page,
        "pageUnit": 100,       # 한 페이지 최대
        "searchSeMkNm": tax_name,
        "searchJngbGbCd": "",
        "searchJngbFlNm": "",
        "searchContents": "",
    }
    try:
        resp = session.get(LIST_URL, params=params, headers=_HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  요청 오류 (page={page}): {e}")
        return [], 0

    soup = BeautifulSoup(resp.text, "html.parser")

    # 총 건수
    total = 0
    count_tag = soup.find(string=re.compile(r"총\s+[\d,]+\s*건"))
    if count_tag:
        m = re.search(r"([\d,]+)", count_tag)
        if m:
            total = int(m.group(1).replace(",", ""))

    # 테이블 행
    rows = []
    table = soup.find("table")
    if not table:
        return [], total

    for tr in table.find_all("tr"):
        parsed = _parse_row(tr)
        if parsed:
            rows.append(parsed)

    return rows, total


# ── 메인 수집 ──────────────────────────────────────────────────────────────────

def collect_revision_cases(tax_key: str = "transfer", dry_run: bool = False) -> dict:
    """
    세법해석정비 목록 전체 수집.

    Returns:
        {
            "cases": [...],
            "deprecated_ids": [...],  # 전체 삭제사례 ID 목록
        }
    """
    tax_name = TAX_CODES.get(tax_key, TAX_CODES["transfer"])
    print(f"세법해석정비 수집 시작 (세목={tax_name or '전체'})")

    session = requests.Session()
    all_cases: list[dict] = []

    # 첫 페이지로 총 건수 확인
    first_page, total = _fetch_page(session, 1, tax_name)
    all_cases.extend(first_page)

    if total == 0:
        print("  건수를 확인할 수 없습니다 (HTML 구조 변경 가능성)")
        total = len(first_page) * 10  # 안전 추정

    pages = max(1, (total + 99) // 100)
    print(f"  총 {total}건 / {pages}페이지")

    for page in range(2, pages + 1):
        rows, _ = _fetch_page(session, page, tax_name)
        all_cases.extend(rows)
        print(f"  page {page}/{pages}: {len(rows)}건")
        time.sleep(0.8)

    # 삭제사례 ID 집계
    deprecated: set[str] = set()
    for case in all_cases:
        for did in case["deleted_ids"]:
            deprecated.add(did.strip())

    result = {
        "tax_key": tax_key,
        "tax_name": tax_name or "전체",
        "total_cases": len(all_cases),
        "cases": all_cases,
        "deprecated_ids": sorted(deprecated),
    }

    if dry_run:
        print(f"\n[DRY] 수집 예상: {len(all_cases)}건, deprecated ID: {len(deprecated)}개")
        return result

    # 저장
    RULINGS_DIR.mkdir(parents=True, exist_ok=True)

    REVISION_FILE.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n정비사례 저장: {REVISION_FILE} ({len(all_cases)}건)")

    # deprecated_ids.json — 기존 파일과 머지
    _merge_deprecated(deprecated)

    return result


def _merge_deprecated(new_ids: set[str]) -> None:
    """기존 deprecated_ids.json에 새 ID를 머지해 저장."""
    existing: dict = {}
    if DEPRECATED_FILE.exists():
        try:
            existing = json.loads(DEPRECATED_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = {}

    existing_set = set(existing.get("ids", []))
    merged = sorted(existing_set | new_ids)

    DEPRECATED_FILE.write_text(
        json.dumps({"ids": merged, "count": len(merged)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    added = len(merged) - len(existing_set)
    print(f"deprecated_ids.json 업데이트: {len(merged)}개 (신규 {added}개)")


# ── deprecated 여부 조회 ───────────────────────────────────────────────────────

def load_deprecated_ids() -> set[str]:
    """저장된 deprecated ID 세트 반환. 파일 없으면 빈 세트."""
    if not DEPRECATED_FILE.exists():
        return set()
    try:
        data = json.loads(DEPRECATED_FILE.read_text(encoding="utf-8"))
        return set(data.get("ids", []))
    except (json.JSONDecodeError, OSError):
        return set()


def is_deprecated(doc_id: str) -> bool:
    """단건 deprecated 여부 확인."""
    return doc_id in load_deprecated_ids()


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="세법해석정비 수집기")
    parser.add_argument(
        "--tax",
        default="transfer",
        choices=list(TAX_CODES.keys()),
        help="세목 (기본: transfer=양도소득세)",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    result = collect_revision_cases(tax_key=args.tax, dry_run=args.dry_run)
    print(f"\n완료: {result['total_cases']}건 수집, deprecated {len(result['deprecated_ids'])}개")
