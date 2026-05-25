"""
국세청 법령해석 수집기 (law.go.kr DRF API)

수집 경로:
  1단계: law.go.kr DRF API (target=ntsCgmExpc)
         → 서버 사이드 query 필터로 세목별 목록 수집
  2단계: taxlaw.nts.go.kr action.do
         → 상세 본문 (질의 내용 + 회신 내용)

저장 위치: data/rulings/nts_interp/{id}.json  (embed_rulings.py 호환 포맷)

기재부 법령해석(moef)와 달리 DRF query 파라미터가 서버 사이드 필터로 동작함:
  query=양도 → 24,408건 / query=증여 → 8,819건 / query=상속 → 7,743건

필요 환경변수:
  LAW_API_OC      — law.go.kr DRF API 인증키 (공공데이터포털 발급)

사용법:
    python -m src.ingestion.collect_rulings_nts_interp
    python -m src.ingestion.collect_rulings_nts_interp --keywords 양도 증여 상속
    python -m src.ingestion.collect_rulings_nts_interp --keywords 양도 --dry-run
    python -m src.ingestion.collect_rulings_nts_interp --resume --no-detail
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
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

load_dotenv()
import os

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ── 설정 ─────────────────────────────────────────────────────────────────────

LAW_API_OC = os.getenv("LAW_API_OC", "")
LAW_API_BASE_URL = os.getenv("LAW_API_BASE_URL", "https://www.law.go.kr/DRF")

NTS_ACTION_URL = "https://taxlaw.nts.go.kr/action.do"
NTS_INTERP_DIR = Path("data/rulings/nts_interp")

_DRF_PAGE_SIZE = 100   # max 100
_MAX_RETRIES = 3
_RETRY_DELAY = 2.0

# 기본 수집 키워드
# 양도/증여/상속: 세목 핵심 + 향후 확장 대상
# 상생임대/임대주택: "양도" 쿼리에서 누락 가능한 특례·감면 보완
DEFAULT_KEYWORDS = ["양도", "증여", "상속", "상생임대", "임대주택"]

# taxlaw.nts.go.kr 상세 액션 ID 순서 (국세청 법령해석)
_DETAIL_ACTION_IDS = [
    "ASIQTA002MR01",   # 기재부/국세청 법령해석 상세
    "ASIQTB001MR01",   # 대안 1
    "ASIQTH001MR01",   # hotissue 상세 (fallback)
]


# ── HTTP 세션 ─────────────────────────────────────────────────────────────────

class _LegacySSLAdapter(HTTPAdapter):
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


_NTS_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://taxlaw.nts.go.kr/qt/USEQTA001M.do",
}


def _make_nts_session() -> requests.Session:
    s = requests.Session()
    s.mount("https://", _LegacySSLAdapter())
    s.headers.update(_NTS_HEADERS)
    return s


# ── DRF 목록 수집 ─────────────────────────────────────────────────────────────

def _fetch_drf_page(
    query: str,
    page: int,
    display: int = _DRF_PAGE_SIZE,
) -> tuple[list[dict], int]:
    """law.go.kr DRF API로 국세청 법령해석 목록 한 페이지 수집.
    서버 사이드 query 필터가 동작함 (moef와 달리).
    (items, totalCnt) 반환.
    """
    url = f"{LAW_API_BASE_URL}/lawSearch.do"
    params: dict = {
        "OC": LAW_API_OC,
        "target": "ntsCgmExpc",
        "type": "JSON",
        "display": display,
        "page": page,
        "query": query,
    }
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            resp = requests.get(url, params=params, timeout=20, verify=False)
            resp.raise_for_status()
            resp.encoding = "utf-8"
            data = resp.json()
            outer = data.get("CgmExpc") or data.get("cgmExpc") or data
            if outer.get("resultCode") not in ("00", None):
                print(f"  DRF API 오류: {outer.get('resultMsg', '알 수 없는 오류')}")
                return [], 0
            raw_items = outer.get("cgmExpc", [])
            items: list[dict] = raw_items if isinstance(raw_items, list) else [raw_items]
            total = int(outer.get("totalCnt", 0))
            return items, total
        except Exception as e:
            print(f"  DRF 요청 오류 (query={query!r}, page={page}, 시도 {attempt}/{_MAX_RETRIES}): {e}")
        if attempt < _MAX_RETRIES:
            time.sleep(_RETRY_DELAY * attempt)
    return [], 0


def _extract_ntst_dcm_id(link_url: str) -> str:
    m = re.search(r"ntstDcmId=([A-Za-z0-9]+)", link_url or "")
    return m.group(1) if m else ""


# ── taxlaw.nts.go.kr 상세 수집 ───────────────────────────────────────────────

def _fetch_detail(session: requests.Session, ntst_dcm_id: str) -> dict | None:
    if not ntst_dcm_id:
        return None
    params = {"ntstDcmId": ntst_dcm_id, "wnSessionUuid": str(uuid.uuid4())}
    for action_id in _DETAIL_ACTION_IDS:
        payload = {
            "actionId": action_id,
            "paramData": json.dumps(params, ensure_ascii=False),
        }
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                resp = session.post(NTS_ACTION_URL, data=payload, timeout=20)
                resp.encoding = "utf-8"
                data = resp.json()
                if data.get("status") == "SUCCESS":
                    inner = (data.get("data") or {}).get(action_id)
                    if inner:
                        return {"action_id": action_id, "data": inner}
            except Exception:
                pass
            if attempt < _MAX_RETRIES:
                time.sleep(0.5)
    return None


def _extract_content_from_detail(detail: dict) -> tuple[str, str]:
    d = detail.get("data", {})
    if isinstance(d, list):
        d = d[0] if d else {}

    def _clean(v: str | None) -> str:
        if not v:
            return ""
        t = re.sub(r"<!H[SE]>", "", str(v))
        return re.sub(r"\s+", " ", t).strip()

    question = _clean(
        d.get("PRTS_BRKD_CNTN")
        or d.get("qstnCntn")
        or d.get("question")
        or d.get("ntstDcmTtl")
        or ""
    )
    answer = _clean(
        d.get("CNTN")
        or d.get("GIST_CNTN")
        or d.get("ansCntn")
        or d.get("answer")
        or d.get("ntstDcmGistCntn")
        or ""
    )
    return question, answer


# ── 레코드 구성 ───────────────────────────────────────────────────────────────

def _build_record(drf_item: dict, detail: dict | None, tax_category: str) -> dict:
    """DRF 목록 항목 + (선택) 상세 데이터 → embed_rulings.py 호환 레코드."""
    link = drf_item.get("법령해석상세링크", "")
    ntst_dcm_id = _extract_ntst_dcm_id(link)
    serial = drf_item.get("법령해석일련번호", "")
    doc_id = f"nts_interp_{ntst_dcm_id or serial}"

    title = (drf_item.get("안건명") or "").strip()
    doc_number = (drf_item.get("안건번호") or "").strip()
    agency = (drf_item.get("해석기관명") or "").strip()

    raw_date = (drf_item.get("해석일자") or "").replace(".", "")
    issued_at = re.sub(r"[^\d]", "", raw_date)[:8]

    if detail:
        question, answer = _extract_content_from_detail(detail)
    else:
        question = title
        answer = ""

    if not question:
        question = title

    related_articles: list[str] = []
    full_text = f"{title} {question} {answer}"
    for art in ["소득세법", "조세특례제한법", "소득세법 시행령", "상속세 및 증여세법", "지방세법"]:
        if art in full_text:
            related_articles.append(art)

    return {
        "id": doc_id,
        "title": f"[국세청 법령해석] {title}" if title else doc_id,
        "question": question,
        "answer": answer,
        "issued_at": issued_at,
        "related_articles": related_articles,
        "keywords": [],
        "source_type": "nts_interp",
        "dcm_type": "nts_interpretation",
        "tax_category": tax_category,      # 양도 | 증여 | 상속
        "doc_number": doc_number,
        "agency": agency,
        "url": link,
        "ntst_dcm_id": ntst_dcm_id,
        "deprecated": False,
    }


# ── 단일 키워드 수집 ──────────────────────────────────────────────────────────

def _collect_by_keyword(
    keyword: str,
    dry_run: bool,
    resume: bool,
    fetch_detail: bool,
    session: requests.Session | None,
) -> tuple[int, int]:
    """단일 키워드로 DRF 목록 수집 후 저장. (saved, skipped) 반환."""
    first_items, total = _fetch_drf_page(keyword, 1)
    if total == 0:
        print(f"  [{keyword}] 데이터 없음")
        return 0, 0

    pages = max(1, (total + _DRF_PAGE_SIZE - 1) // _DRF_PAGE_SIZE)
    print(f"  [{keyword}] 총 {total}건 / {pages}페이지")

    all_items: list[dict] = list(first_items)
    for page in range(2, pages + 1):
        items, _ = _fetch_drf_page(keyword, page)
        all_items.extend(items)
        if page % 10 == 0:
            print(f"  [{keyword}] page {page}/{pages} ({len(all_items)}건 누적)")
        time.sleep(0.4)

    saved = skipped = detail_ok = detail_fail = 0

    for item in all_items:
        link = item.get("법령해석상세링크", "")
        ntst_dcm_id = _extract_ntst_dcm_id(link)
        serial = item.get("법령해석일련번호", "")
        doc_id = f"nts_interp_{ntst_dcm_id or serial}"
        out_path = NTS_INTERP_DIR / f"{doc_id}.json"

        if resume and out_path.exists():
            skipped += 1
            continue

        detail: dict | None = None
        if fetch_detail and session and ntst_dcm_id:
            detail = _fetch_detail(session, ntst_dcm_id)
            if detail:
                detail_ok += 1
            else:
                detail_fail += 1
            time.sleep(0.5)

        record = _build_record(item, detail, tax_category=keyword)

        if dry_run:
            saved += 1
            print(f"  [dry-run][{keyword}] {doc_id}: {record['title'][:60]}")
            continue

        out_path.write_text(
            json.dumps(record, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        saved += 1

    print(f"  [{keyword}] 저장={saved}, 스킵={skipped}, 상세OK={detail_ok}, 상세실패={detail_fail}")
    return saved, skipped


# ── 메인 수집 함수 ────────────────────────────────────────────────────────────

def collect_nts_interp(
    keywords: list[str] | None = None,
    dry_run: bool = False,
    resume: bool = False,
    fetch_detail: bool = True,
) -> int:
    """국세청 법령해석 수집. 총 저장 건수 반환.

    keywords: 수집할 세목 키워드 목록 (기본: ["양도", "증여", "상속"])
    같은 ntst_dcm_id가 여러 키워드에 매칭되면 먼저 저장된 것 유지 (resume=True 동작).
    """
    if not LAW_API_OC:
        print("LAW_API_OC 환경변수 미설정 — .env에 LAW_API_OC=인증키 추가 필요")
        return 0

    keywords = keywords or DEFAULT_KEYWORDS
    print(f"=== 국세청 법령해석 수집 (키워드: {keywords}) ===")
    NTS_INTERP_DIR.mkdir(parents=True, exist_ok=True)

    session = _make_nts_session() if fetch_detail else None

    total_saved = total_skipped = 0
    for kw in keywords:
        saved, skipped = _collect_by_keyword(kw, dry_run, resume, fetch_detail, session)
        total_saved += saved
        total_skipped += skipped
        # 키워드 간 잠시 대기
        if kw != keywords[-1]:
            time.sleep(2.0)

    print(f"\n완료: 총 저장={total_saved}, 총 스킵={total_skipped}")
    return total_saved


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="국세청 법령해석 수집기 (law.go.kr DRF)")
    parser.add_argument(
        "--keywords",
        nargs="+",
        default=DEFAULT_KEYWORDS,
        help=f"수집 키워드 목록 (기본: {DEFAULT_KEYWORDS})",
    )
    parser.add_argument("--dry-run", action="store_true", help="저장하지 않고 건수만 확인")
    parser.add_argument("--resume", action="store_true", help="기존 파일 스킵")
    parser.add_argument("--no-detail", action="store_true", help="상세 본문 조회 생략")
    args = parser.parse_args()

    saved = collect_nts_interp(
        keywords=args.keywords,
        dry_run=args.dry_run,
        resume=args.resume,
        fetch_detail=not args.no_detail,
    )
    sys.exit(0 if saved >= 0 else 1)


if __name__ == "__main__":
    main()
