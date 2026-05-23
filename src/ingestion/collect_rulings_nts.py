"""
국세법령정보시스템(taxlaw.nts.go.kr) 유권해석 수집기

수집 대상:
  - 자주찾는쟁점별사례 (hotissue): action.do API (ASIQTH001MR01)
    → 양도소득세 관련 1,085건+ 자주 인용 사례

  ※ 질의회신(qt), 판단사례(pd), 세법해석례(ic) 목록 API 미공개.
     판례·결정례는 collect_rulings_decisions.py 참조.

저장 위치: data/rulings/nts/{type}_{ntstDcmId}.json

JSON 스키마 (embed_rulings.py 호환):
  id, title, question, answer, issued_at, related_articles, keywords,
  source_type, doc_number, url, deprecated

사용법:
    python -m src.ingestion.collect_rulings_nts                    # 전체 (hotissue)
    python -m src.ingestion.collect_rulings_nts --tax 양도소득세    # 세목 필터
    python -m src.ingestion.collect_rulings_nts --dry-run
    python -m src.ingestion.collect_rulings_nts --resume           # 기존 파일 스킵
"""
from __future__ import annotations

import argparse
import json
import re
import ssl
import sys
import time
import uuid
from pathlib import Path

import requests
import urllib3
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://taxlaw.nts.go.kr"
ACTION_URL = f"{BASE_URL}/action.do"
NTS_DIR = Path("data/rulings/nts")

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
    "Accept-Language": "ko-KR,ko;q=0.9",
}

_PAGE_SIZE = 100
_MAX_RETRIES = 3
_RETRY_DELAY = 2.0

_TAX_KEYWORDS = {
    "양도소득세": ["양도", "양도세", "비과세", "중과"],
    "상속세": ["상속"],
    "증여세": ["증여"],
}


# ── SSL 어댑터 ──────────────────────────────────────────────────────────────────

class _LegacySSLAdapter(HTTPAdapter):
    """ECDH 재협상 문제를 우회하는 레거시 SSL 어댑터."""

    def init_poolmanager(self, *args, **kwargs):
        ctx = create_urllib3_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ctx.set_ciphers("DEFAULT@SECLEVEL=1")
        kwargs["ssl_context"] = ctx
        super().init_poolmanager(*args, **kwargs)

    def send(self, request, **kwargs):
        kwargs["verify"] = False
        return super().send(request, **kwargs)


def _make_session() -> requests.Session:
    s = requests.Session()
    s.mount("https://", _LegacySSLAdapter())
    s.headers.update(_HEADERS)
    s.headers["Referer"] = f"{BASE_URL}/qt/USEQTH001M.do"
    return s


def _post_with_retry(
    session: requests.Session,
    action_id: str,
    params: dict,
    max_retries: int = _MAX_RETRIES,
) -> dict | None:
    """action.do POST 요청. 실패 시 재시도."""
    payload = {
        "actionId": action_id,
        "wnSessionUuid": str(uuid.uuid4()),
        "paramData": json.dumps(params),
    }
    for attempt in range(1, max_retries + 1):
        try:
            resp = session.post(ACTION_URL, data=payload, timeout=25)
            resp.encoding = "utf-8"
            data = resp.json()
            if data.get("status") == "SUCCESS":
                return data.get("data", {}).get(action_id)
            print(f"  API FAIL (시도 {attempt}/{max_retries}): status={data.get('status')}")
        except Exception as e:
            print(f"  요청 오류 (시도 {attempt}/{max_retries}): {e}")
        if attempt < max_retries:
            time.sleep(_RETRY_DELAY * attempt)
    return None


# ── 자주찾는쟁점별사례 수집 ────────────────────────────────────────────────────

def _fetch_hotissue_page(
    session: requests.Session,
    page: int,
    tax_name: str,
) -> tuple[list[dict], int]:
    """hotissue 한 페이지 수집. (items, total) 반환."""
    params = {
        "recordCountPerPage": _PAGE_SIZE,
        "pageIndex": page,
        "stttInfpClCdList": ["01"],  # 공개
        "searchSeMkNm": tax_name,
        "searchJngtNm": "",
    }
    inner = _post_with_retry(session, "ASIQTH001MR01", params)
    if inner is None:
        return [], 0

    total = inner.get("recordCount", 0)
    items = inner.get("pntThanBkmrDVOList", [])

    # 클라이언트 세목 재필터 (서버 필터가 불완전할 수 있음)
    if tax_name:
        items = [x for x in items if x.get("ntstTlawClNm") == tax_name]

    return items, total


def _item_to_record(item: dict, tax_name: str) -> dict:
    """API 응답 item → embedding 호환 dict."""
    ntst_dcm_id = item.get("ntstDcmId", "")
    doc_number = item.get("ntstDcmDscmCntn", "")
    title = item.get("ntstDcmTtl", "")
    gist = item.get("ntstDcmGistCntn", "")
    doc_class = item.get("ntstDcmClNm", "")  # "사전", "서면" 등
    reg_dt = item.get("frsRgtDtm", "")[:8] if item.get("frsRgtDtm") else ""

    # 키워드 추출
    keywords: list[str] = []
    full_text = f"{title} {gist}"
    tax_kws = _TAX_KEYWORDS.get(tax_name, [])
    for kw in tax_kws + ["비과세", "중과", "1세대1주택", "양도", "이월과세", "장기보유"]:
        if kw in full_text and kw not in keywords:
            keywords.append(kw)

    return {
        "id": f"hotissue_{ntst_dcm_id}",
        "title": f"[{doc_class}] {title}" if doc_class else title,
        "question": title,
        "answer": gist,
        "issued_at": reg_dt,
        "related_articles": [],
        "keywords": keywords[:10],
        "source_type": "nts",
        "dcm_type": "hotissue",
        "doc_number": doc_number,
        "url": f"{BASE_URL}/qt/USEQTH001M.do",
        "deprecated": False,
    }


def collect_hotissue(
    tax_name: str = "양도소득세",
    dry_run: bool = False,
    resume: bool = False,
) -> int:
    """자주찾는쟁점별사례 수집. 저장된 레코드 수 반환."""
    print(f"=== 자주찾는쟁점별사례 (hotissue) 수집 (세목={tax_name}) ===")
    NTS_DIR.mkdir(parents=True, exist_ok=True)

    session = _make_session()
    first_items, total = _fetch_hotissue_page(session, 1, tax_name)
    pages = max(1, (total + _PAGE_SIZE - 1) // _PAGE_SIZE)
    print(f"  총 {total}건 / {pages}페이지")

    all_items = list(first_items)
    for page in range(2, pages + 1):
        items, _ = _fetch_hotissue_page(session, page, tax_name)
        all_items.extend(items)
        print(f"  page {page}/{pages}: {len(items)}건")
        time.sleep(0.8)

    saved = 0
    for item in all_items:
        ntst_dcm_id = item.get("ntstDcmId", "")
        if not ntst_dcm_id:
            continue
        out_path = NTS_DIR / f"hotissue_{ntst_dcm_id}.json"
        if resume and out_path.exists():
            continue
        record = _item_to_record(item, tax_name)
        if dry_run:
            saved += 1
            continue
        out_path.write_text(
            json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        saved += 1

    suffix = " [DRY]" if dry_run else ""
    print(f"  → {saved}건 저장{suffix}\n")
    return saved


# ── 메인 수집 ──────────────────────────────────────────────────────────────────

def collect_rulings(
    ruling_type: str = "hotissue",
    tax_name: str = "양도소득세",
    dry_run: bool = False,
    resume: bool = False,
) -> int:
    if ruling_type == "hotissue":
        return collect_hotissue(tax_name=tax_name, dry_run=dry_run, resume=resume)
    print(f"  ⚠ 미지원 유형: {ruling_type} (hotissue만 지원)")
    return 0


def _mark_deprecated_files(deprecated_ids: set[str]) -> int:
    """저장된 파일 중 deprecated ID 매칭 시 deprecated=True 표시."""
    marked = 0
    if not NTS_DIR.exists():
        return 0
    for f in NTS_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            doc_num = data.get("doc_number", "")
            if doc_num and doc_num in deprecated_ids:
                data["deprecated"] = True
                f.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                marked += 1
        except (json.JSONDecodeError, OSError):
            pass
    return marked


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="NTS 유권해석 수집기 (hotissue)")
    parser.add_argument("--type", default="hotissue", choices=["hotissue"],
                        help="수집 유형")
    parser.add_argument("--tax", default="양도소득세", help="세목 이름")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true", help="기존 파일 스킵")
    args = parser.parse_args()

    n = collect_rulings(
        ruling_type=args.type,
        tax_name=args.tax,
        dry_run=args.dry_run,
        resume=args.resume,
    )
    print(f"\n완료: 저장={n}")
