"""
세법해석정비 수집기 (taxlaw.nts.go.kr action.do API)

삭제사례(폐지 예규) ID를 추출하고 deprecated_ids.json에 저장한다.
예규 수집 시 이 목록을 참조해 Pinecone에 deprecated=True 표시.

actionId: ASIQTF001MR01

사용법:
    python -m src.ingestion.collect_rulings_revision              # 양도소득세
    python -m src.ingestion.collect_rulings_revision --tax all    # 전 세목
    python -m src.ingestion.collect_rulings_revision --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
import warnings
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://taxlaw.nts.go.kr"
ACTION_URL = f"{BASE_URL}/action.do"
ACTION_ID = "ASIQTF001MR01"

RULINGS_DIR = Path("data/rulings")
DEPRECATED_FILE = RULINGS_DIR / "deprecated_ids.json"
REVISION_FILE = RULINGS_DIR / "revision_cases.json"

TAX_CODES = {
    "transfer": "양도소득세",
    "gift":     "증여세",
    "inherit":  "상속세",
    "all":      "",
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Referer": f"{BASE_URL}/qt/USEQTE001M.do",
    "X-Requested-With": "XMLHttpRequest",
    "Accept-Language": "ko-KR,ko;q=0.9",
}

_PAGE_SIZE = 100


def _post_action(session: requests.Session, page: int, tax_name: str) -> dict:
    """action.do 호출 → 응답 data 반환."""
    payload = {
        "actionId": ACTION_ID,
        "wnSessionUuid": str(uuid.uuid4()),
        "paramData": json.dumps({
            "ntstItrpMntcClCd": "01",
            "bltnStrtDt": "",
            "bltnEndDt": "",
            "cntsPrtsNo": "",
            "stttInfpClCdList": ["01", "06"],
            "recordCountPerPage": _PAGE_SIZE,
            "pageIndex": page,
            "ntstTlawClCd": "",
            "searchSeMkNm": tax_name,
        }),
    }
    resp = session.post(ACTION_URL, data=payload, headers=_HEADERS, verify=False, timeout=20)
    resp.encoding = "utf-8"
    resp.raise_for_status()
    return resp.json().get("data", {}).get(ACTION_ID, {})


def _extract_item(item: dict) -> dict:
    """API 응답 item → revision case dict."""
    def split_ids(s: str) -> list[str]:
        return [x.strip() for x in (s or "").split(",") if x.strip() and x.strip() != " "]

    return {
        "id": item.get("ntstItrpMntcId", ""),
        "title": item.get("ntstItrpMntcTtl", ""),
        "tax_class": item.get("ntstTlawClNm", ""),
        "revision_content": item.get("ntstItrpMntcCntn", ""),
        "maintained_cases": split_ids(item.get("mntnCase", "")),
        "maintained_ids": split_ids(item.get("mntnCaseDcmId", "")),
        "deleted_cases": split_ids(item.get("dltCase", "")),
        "deleted_ids": split_ids(item.get("dltCaseDcmId", "")),
        "registered_at": item.get("frsRgtDtm", ""),
    }


def collect_revision_cases(tax_key: str = "transfer", dry_run: bool = False) -> dict:
    """
    세법해석정비 목록 전체 수집.

    Returns:
        {
            "cases": [...],
            "deprecated_ids": [...],
        }
    """
    tax_name = TAX_CODES.get(tax_key, TAX_CODES["transfer"])
    print(f"세법해석정비 수집 시작 (세목={tax_name or '전체'})")

    session = requests.Session()
    all_items: list[dict] = []

    # 첫 페이지 — 총 건수 확인
    try:
        first_data = _post_action(session, 1, tax_name)
    except Exception as e:
        print(f"  API 오류: {e}")
        return {"cases": [], "deprecated_ids": []}

    total = first_data.get("recordCount", 0)
    raw_list = first_data.get("itlMntcDVOList", [])

    # tax_name 필터 (서버 필터가 불완전할 수 있어 클라이언트 재필터)
    if tax_name:
        raw_list = [x for x in raw_list if x.get("ntstTlawClNm") == tax_name]

    all_items.extend(raw_list)
    pages = max(1, (total + _PAGE_SIZE - 1) // _PAGE_SIZE)
    print(f"  총 {total}건 / {pages}페이지")

    for page in range(2, pages + 1):
        try:
            data = _post_action(session, page, tax_name)
            raw = data.get("itlMntcDVOList", [])
            if tax_name:
                raw = [x for x in raw if x.get("ntstTlawClNm") == tax_name]
            all_items.extend(raw)
            print(f"  page {page}/{pages}: {len(raw)}건")
        except Exception as e:
            print(f"  page {page} 오류: {e}")
        time.sleep(0.5)

    cases = [_extract_item(x) for x in all_items]

    # 삭제사례 ID 집계 (ntstBscId 형태)
    deprecated: set[str] = set()
    for c in cases:
        for did in c["deleted_ids"]:
            deprecated.add(did)
        # 삭제사례 문서번호도 추가 (예규 번호 형식)
        for dc in c["deleted_cases"]:
            deprecated.add(dc)

    result = {
        "tax_key": tax_key,
        "tax_name": tax_name or "전체",
        "total_cases": len(cases),
        "cases": cases,
        "deprecated_ids": sorted(deprecated),
    }

    if dry_run:
        print(f"\n[DRY] 수집 예상: {len(cases)}건, deprecated ID: {len(deprecated)}개")
        return result

    RULINGS_DIR.mkdir(parents=True, exist_ok=True)
    REVISION_FILE.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n정비사례 저장: {REVISION_FILE} ({len(cases)}건)")
    _merge_deprecated(deprecated)

    return result


def _merge_deprecated(new_ids: set[str]) -> None:
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


def load_deprecated_ids() -> set[str]:
    if not DEPRECATED_FILE.exists():
        return set()
    try:
        data = json.loads(DEPRECATED_FILE.read_text(encoding="utf-8"))
        return set(data.get("ids", []))
    except (json.JSONDecodeError, OSError):
        return set()


def is_deprecated(doc_id: str) -> bool:
    return doc_id in load_deprecated_ids()


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
