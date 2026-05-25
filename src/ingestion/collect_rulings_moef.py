"""
기획재정부 법령해석 수집기

수집 경로:
  1단계: law.go.kr DRF API (target=moefCgmExpc)
         → 목록 (안건명, 법령해석일련번호, ntstDcmId, 해석일자)
  2단계: taxlaw.nts.go.kr action.do (actionId=ASIQTA002MR01)
         → 상세 본문 (질의 내용 + 회신 내용)

저장 위치: data/rulings/moef/{id}.json  (embed_rulings.py 호환 포맷)

필요 환경변수:
  LAW_API_OC      — law.go.kr DRF API 인증키 (공공데이터포털 발급)
  LAW_API_BASE_URL — (선택) 기본값 https://www.law.go.kr/DRF

사용법:
    python -m src.ingestion.collect_rulings_moef
    python -m src.ingestion.collect_rulings_moef --query 양도소득세 --dry-run
    python -m src.ingestion.collect_rulings_moef --resume
    python -m src.ingestion.collect_rulings_moef --no-detail   # 목록만 저장
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
MOEF_DIR = Path("data/rulings/moef")

_DRF_PAGE_SIZE = 100   # max 100
_MAX_RETRIES = 3
_RETRY_DELAY = 2.0

# taxlaw.nts.go.kr 기재부 질의회신 상세 액션 ID
# USEQTA002P 상세 화면 대응 액션
_DETAIL_ACTION_IDS = [
    "ASIQTA002MR01",   # 기재부 법령해석 상세 (추정 1순위)
    "ASIQTB001MR01",   # 대안 1
    "ASIQTH001MR01",   # hotissue 상세 (호환 fallback)
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

def _fetch_drf_page(page: int, display: int = _DRF_PAGE_SIZE) -> tuple[list[dict], int]:
    """law.go.kr DRF API로 기재부 법령해석 목록 한 페이지 수집.
    (items, totalCnt) 반환.
    query 파라미터 없이 전체 수집 후 클라이언트 측에서 세목/기관 필터링.
    """
    url = f"{LAW_API_BASE_URL}/lawSearch.do"
    params = {
        "OC": LAW_API_OC,
        "target": "moefCgmExpc",
        "type": "JSON",
        "display": display,
        "page": page,
    }
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            resp = requests.get(url, params=params, timeout=20, verify=False)
            resp.raise_for_status()
            data = resp.json()
            # 응답 루트가 'CgmExpc' 또는 'cgmExpc'일 수 있음
            outer = data.get("CgmExpc") or data.get("cgmExpc") or data
            if outer.get("resultCode") != "00":
                print(f"  DRF API 오류: {outer.get('resultMsg', '알 수 없는 오류')}")
                return [], 0
            items = outer.get("cgmExpc", [])
            total = int(outer.get("totalCnt", 0))
            return items, total
        except Exception as e:
            print(f"  DRF 요청 오류 (page={page}, 시도 {attempt}/{_MAX_RETRIES}): {e}")
        if attempt < _MAX_RETRIES:
            time.sleep(_RETRY_DELAY * attempt)
    return [], 0


def _extract_ntst_dcm_id(link_url: str) -> str:
    """법령해석상세링크 URL에서 ntstDcmId 추출.
    예: https://taxlaw.nts.go.kr/qt/USEQTA002P.do?ntstDcmId=010000000000505015
        → '010000000000505015'
    """
    m = re.search(r"ntstDcmId=([A-Za-z0-9]+)", link_url or "")
    return m.group(1) if m else ""


# ── taxlaw.nts.go.kr 상세 수집 ───────────────────────────────────────────────

def _fetch_detail(session: requests.Session, ntst_dcm_id: str) -> dict | None:
    """ntstDcmId로 taxlaw.nts.go.kr action.do에서 상세 본문 조회.

    여러 actionId를 순서대로 시도해 성공한 것을 반환.
    실패 시 None 반환.
    """
    if not ntst_dcm_id:
        return None

    params = {
        "ntstDcmId": ntst_dcm_id,
        "wnSessionUuid": str(uuid.uuid4()),
    }

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
    """상세 응답에서 (question, answer) 추출.
    actionId별로 필드명이 다를 수 있어 여러 키를 시도.
    """
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

def _build_record(
    drf_item: dict,
    detail: dict | None,
) -> dict:
    """DRF 목록 항목 + (선택) 상세 데이터 → embed_rulings.py 호환 레코드."""
    link = drf_item.get("법령해석상세링크", "")
    ntst_dcm_id = _extract_ntst_dcm_id(link)
    serial = drf_item.get("법령해석일련번호", "")
    doc_id = f"moef_{ntst_dcm_id or serial}"

    title = (drf_item.get("안건명") or "").strip()
    doc_number = (drf_item.get("안건번호") or "").strip()
    agency = (drf_item.get("해석기관명") or "").strip()

    raw_date = (drf_item.get("해석일자") or "").replace(".", "")
    issued_at = re.sub(r"[^\d]", "", raw_date)[:8]

    # 상세 본문 우선, 없으면 안건명만 사용
    if detail:
        question, answer = _extract_content_from_detail(detail)
    else:
        question = title
        answer = ""

    # question이 비어있으면 안건명으로 보완
    if not question:
        question = title

    # 관련 법령 추출 (기본 키워드 기반)
    related_articles: list[str] = []
    full_text = f"{title} {question} {answer}"
    for art in ["소득세법", "조세특례제한법", "소득세법 시행령", "지방세법"]:
        if art in full_text:
            related_articles.append(art)

    return {
        "id": doc_id,
        "title": f"[기재부 법령해석] {title}" if title else doc_id,
        "question": question,
        "answer": answer,
        "issued_at": issued_at,
        "related_articles": related_articles,
        "keywords": [],
        "source_type": "moef",
        "dcm_type": "moef_interpretation",
        "doc_number": doc_number,
        "agency": agency,
        "url": link,
        "ntst_dcm_id": ntst_dcm_id,
        "deprecated": False,
    }


# ── 메인 수집 함수 ────────────────────────────────────────────────────────────

def collect_moef(
    tax_keyword: str = "양도소득세",
    dry_run: bool = False,
    resume: bool = False,
    fetch_detail: bool = True,
) -> int:
    """기재부 법령해석 수집. 저장 건수 반환.

    DRF API가 한국어 query 파라미터 검색을 지원하지 않아
    전체(2,305건) 수집 후 안건명/해석기관에서 tax_keyword 클라이언트 필터링.
    """
    if not LAW_API_OC:
        print("LAW_API_OC 환경변수 미설정 — .env에 LAW_API_OC=인증키 추가 필요")
        return 0

    print(f"=== 기재부 법령해석 수집 (세목 필터={tax_keyword!r}) ===")
    MOEF_DIR.mkdir(parents=True, exist_ok=True)

    # 1단계: DRF 목록 전체 수집 (query 파라미터 없이 — 클라이언트 필터링)
    first_items, total = _fetch_drf_page(1)
    if total == 0:
        print("  데이터 없음 (OC 키 또는 네트워크 확인 필요)")
        return 0

    pages = max(1, (total + _DRF_PAGE_SIZE - 1) // _DRF_PAGE_SIZE)
    print(f"  DRF 전체 {total}건 / {pages}페이지")

    all_items: list[dict] = list(first_items)
    for page in range(2, pages + 1):
        items, _ = _fetch_drf_page(page)
        all_items.extend(items)
        if page % 5 == 0:
            print(f"  DRF page {page}/{pages} ({len(all_items)}건 누적)")
        time.sleep(0.5)

    # 클라이언트 세목 필터: 안건명에 tax_keyword 포함 또는 양도 관련 키워드
    _TRANSFER_KEYWORDS = ["양도", "비과세", "1세대1주택", "세대", "취득", "이월과세", "양수"]
    if tax_keyword == "양도소득세":
        filtered = [
            item for item in all_items
            if any(kw in (item.get("안건명") or "") for kw in _TRANSFER_KEYWORDS)
        ]
    else:
        filtered = [item for item in all_items if tax_keyword in (item.get("안건명") or "")]

    print(f"  세목 필터 후: {len(filtered)}건 (전체 {len(all_items)}건 중)")

    print(f"  DRF 수집 완료: {len(all_items)}건")

    # 2단계: 상세 본문 + 저장
    session = _make_nts_session() if fetch_detail else None
    saved = 0
    skipped = 0
    detail_ok = 0
    detail_fail = 0

    for item in all_items:
        link = item.get("법령해석상세링크", "")
        ntst_dcm_id = _extract_ntst_dcm_id(link)
        serial = item.get("법령해석일련번호", "")
        doc_id = f"moef_{ntst_dcm_id or serial}"

        out_path = MOEF_DIR / f"{doc_id}.json"
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
            time.sleep(0.6)

        record = _build_record(item, detail)

        if dry_run:
            saved += 1
            print(f"  [dry-run] {doc_id}: {record['title'][:60]}")
            continue

        out_path.write_text(
            json.dumps(record, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        saved += 1

    print(f"\n완료: 저장={saved}, 스킵={skipped}")
    if fetch_detail:
        print(f"  상세 조회 성공={detail_ok}, 실패={detail_fail}")
        if detail_fail > 0:
            print("  ※ 상세 조회 실패분은 안건명만 저장됨 (나중에 --no-detail 없이 재실행 가능)")

    return saved


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="기재부 법령해석 수집기")
    parser.add_argument("--query", default="양도소득세", help="검색 키워드 (기본: 양도소득세)")
    parser.add_argument("--dry-run", action="store_true", help="저장하지 않고 수집만 확인")
    parser.add_argument("--resume", action="store_true", help="기존 파일 스킵")
    parser.add_argument("--no-detail", action="store_true", help="상세 본문 조회 생략 (목록만)")
    args = parser.parse_args()

    saved = collect_moef(
        tax_keyword=args.query,
        dry_run=args.dry_run,
        resume=args.resume,
        fetch_detail=not args.no_detail,
    )
    sys.exit(0 if saved >= 0 else 1)


if __name__ == "__main__":
    main()
