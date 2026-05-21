"""
판례·결정례 JSON API 수집기 (taxlaw.nts.go.kr/action.do)

엔드포인트: POST https://taxlaw.nts.go.kr/action.do
actionId: ASIPDI002PR01

수집 대상 (dcmClCdCtl 코드):
  001_08 = 심판청구 (24,904건)     ← 기본 수집 대상
  001_05 = 심사청구 (8,828건)
  001_03 = 이의신청 (404건)
  001_01 = 과세적부 (125건)
  court  = 판례/헌재 (별도 collectionName)

필터 전략:
  - icldVcbCtl: ["양도"] — 양도소득세 관련만 수집
  - dcmClCdCtl: ["001_08"] — 심판청구 우선
  - rltnStttCtl: [] — 특정 조문 제한 없이 전체

저장 위치: data/rulings/decisions/{dcm_cl}_{doc_id}.json

사용법:
    python -m src.ingestion.collect_rulings_decisions                   # 심판청구
    python -m src.ingestion.collect_rulings_decisions --type all        # 전체 유형
    python -m src.ingestion.collect_rulings_decisions --dry-run
    python -m src.ingestion.collect_rulings_decisions --resume
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import uuid
from pathlib import Path

import requests

BASE_URL = "https://taxlaw.nts.go.kr"
ACTION_URL = f"{BASE_URL}/action.do"
DECISIONS_DIR = Path("data/rulings/decisions")

# 문서 유형 코드
DECISION_TYPES = {
    "tax_tribunal": {
        "name": "심판청구",
        "dcmClCdCtl": ["001_08"],
        "collectionName": "precedent,precedent_gr",
    },
    "review": {
        "name": "심사청구",
        "dcmClCdCtl": ["001_05"],
        "collectionName": "precedent,precedent_gr",
    },
    "objection": {
        "name": "이의신청",
        "dcmClCdCtl": ["001_03"],
        "collectionName": "precedent,precedent_gr",
    },
    "assessment": {
        "name": "과세적부",
        "dcmClCdCtl": ["001_01"],
        "collectionName": "precedent,precedent_gr",
    },
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/148.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Content-Type": "application/x-www-form-urlencoded",
    "Origin": BASE_URL,
    "Referer": f"{BASE_URL}/pd/USEPDI002P.do",
    "X-Requested-With": "XMLHttpRequest",
}

PAGE_SIZE = 50


# ── API 호출 ───────────────────────────────────────────────────────────────────

def _post_action(
    session: requests.Session,
    dcm_cl_codes: list[str],
    collection_name: str,
    keyword: str,
    start: int,
) -> dict:
    """action.do POST 호출. 빈 dict 반환 시 오류."""
    param_data = {
        "prtsPrdcOrgnClCtl": [],
        "prtsDcsTypeClCtl": [],
        "prtsCncrDcsClCtl": [],
        "prtsHpnnClCtl": [],
        "dcsThanTxtnPprtClCtl": [],
        "dcsThanRsltClCtl": [],
        "dcsThanPrdcOrgnClCtl": [],
        "icldVcbCtl": [keyword] if keyword else [],
        "rltnStttCtl": [],           # 특정 조문 제한 없음
        "schDtBase": "DCM_RGT_DTM",
        "prtsSprcChiefJdgmYn": "",
        "prtsLwsDfntYn": "",
        "bltnStrtDt": "",
        "bltnEndDt": "",
        "dcmClCdCtl": dcm_cl_codes,
        "collectionName": collection_name,
        "sortField": "FRS_RGT_DTM/DESC",
        "startCount": start,
        "viewCount": PAGE_SIZE,
        "nowCnt": 0,
        "wnSessionUuid": str(uuid.uuid4()),
    }

    form_data = {
        "actionId": "ASIPDI002PR01",
        "paramData": json.dumps(param_data, ensure_ascii=False),
    }

    try:
        resp = session.post(ACTION_URL, data=form_data, headers=_HEADERS, timeout=20)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        print(f"  API 요청 오류 (start={start}): {e}")
        return {}
    except json.JSONDecodeError as e:
        print(f"  JSON 파싱 오류 (start={start}): {e}")
        return {}


# ── 레코드 파싱 ────────────────────────────────────────────────────────────────

def _clean(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", str(text)).strip()


def _parse_record(item: dict, dcm_type: str) -> dict | None:
    """API 응답 단건을 embed_rulings.py 호환 포맷으로 변환."""
    # 공통 ID 필드 탐색
    doc_id = (
        item.get("ntstBscId")
        or item.get("dcmId")
        or item.get("id")
        or item.get("DCM_ID")
    )
    if not doc_id:
        return None

    doc_id = str(doc_id)

    # 제목
    title = _clean(
        item.get("dcmTitl")
        or item.get("DCM_TITL")
        or item.get("title")
        or item.get("TITL")
    )

    # 요지 / 내용 (answer 역할)
    answer = _clean(
        item.get("dcmRgznRsumDcrt")
        or item.get("rsumDcrt")
        or item.get("RSUM_DCRT")
        or item.get("summary")
        or item.get("content")
    )

    # 요약 (question 역할)
    question = _clean(
        item.get("prts")
        or item.get("PRTS")
        or item.get("point")
        or ""
    )

    # 발행일
    issued_raw = _clean(
        item.get("frsRgtDtm")
        or item.get("FRS_RGT_DTM")
        or item.get("dcmDt")
        or item.get("date")
        or ""
    )
    issued_at = re.sub(r"[^\d]", "", issued_raw)[:8]

    # 문서번호
    doc_number = _clean(
        item.get("dcmNo")
        or item.get("DCM_NO")
        or item.get("docNo")
        or ""
    )

    # 결정 유형명
    dcm_cl_nm = _clean(
        item.get("dcmClNm")
        or item.get("DCM_CL_NM")
        or DECISION_TYPES.get(dcm_type, {}).get("name", "")
    )

    # 결과 (각하/기각/인용)
    result = _clean(
        item.get("dcmRslt")
        or item.get("DCM_RSLT")
        or item.get("result")
        or ""
    )

    if not title and not answer:
        return None

    keywords: list[str] = []
    combined = title + " " + answer + " " + question
    for kw in ["1세대1주택", "비과세", "중과", "감면", "조정대상지역",
               "이월과세", "상생임대", "일시적2주택", "장기보유특별공제",
               "양도소득세", "양도", "취득", "보유기간"]:
        if kw in combined:
            keywords.append(kw)

    return {
        "id": f"{dcm_type}_{doc_id}",
        "title": title,
        "question": question[:2000],
        "answer": answer[:2000],
        "issued_at": issued_at,
        "related_articles": [],
        "keywords": keywords,
        "source_type": "decisions",
        "doc_number": doc_number,
        "dcm_type": dcm_type,
        "dcm_cl_nm": dcm_cl_nm,
        "result": result,
        "url": f"{BASE_URL}/pd/USEPDI002P.do?ntstBscId={doc_id}",
        "deprecated": False,
    }


def _extract_items(resp_data: dict) -> tuple[list[dict], int]:
    """API 응답에서 item 리스트와 총 건수 추출. 키 이름을 탐색적으로 처리."""
    total = 0
    items: list[dict] = []

    for total_key in ["totalCount", "total_count", "TOTAL_COUNT", "totCnt", "cnt"]:
        if total_key in resp_data:
            try:
                total = int(resp_data[total_key])
            except (ValueError, TypeError):
                pass
            break

    for list_key in ["resultList", "result_list", "list", "data", "items", "rows"]:
        if list_key in resp_data and isinstance(resp_data[list_key], list):
            items = resp_data[list_key]
            break

    # 응답이 바로 리스트인 경우
    if not items and isinstance(resp_data, list):
        items = resp_data

    return items, total


# ── 메인 수집 ──────────────────────────────────────────────────────────────────

def collect_decisions(
    decision_types: list[str] | None = None,
    keyword: str = "양도",
    dry_run: bool = False,
    resume: bool = True,
    delay: float = 0.8,
    max_per_type: int = 0,
) -> dict:
    """
    판례·결정례 JSON API 수집.

    Args:
        decision_types: DECISION_TYPES 키 목록. None이면 ["tax_tribunal"].
        keyword: 키워드 필터 (기본: "양도" → 양도소득세 관련)
        dry_run: True이면 총 건수 확인만
        resume: True이면 이미 저장된 ID 스킵
        delay: 요청 간 대기 시간(초)
        max_per_type: 0이면 전체. 양수이면 해당 건수에서 중단 (테스트용)

    Returns:
        {"saved": N, "skipped": N, "failed": N}
    """
    types = decision_types or ["tax_tribunal"]
    DECISIONS_DIR.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    stats = {"saved": 0, "skipped": 0, "failed": 0}

    for dtype in types:
        cfg = DECISION_TYPES[dtype]
        print(f"\n=== {cfg['name']} ({dtype}) — 키워드: '{keyword}' ===")

        # 기존 저장 파일 ID 목록
        existing_ids: set[str] = set()
        if resume:
            for f in DECISIONS_DIR.glob(f"{dtype}_*.json"):
                existing_ids.add(f.stem)

        # 첫 요청으로 총 건수 파악
        first_resp = _post_action(session, cfg["dcmClCdCtl"], cfg["collectionName"], keyword, 1)
        items, total = _extract_items(first_resp)

        if not total and not items:
            print(f"  응답 없음 또는 0건 — 응답 키 확인 필요")
            print(f"  응답 키: {list(first_resp.keys())[:10]}")
            continue

        limit = min(total, max_per_type) if max_per_type > 0 else total
        print(f"  총 {total}건 (수집 대상: {limit}건)")

        if dry_run:
            continue

        # 첫 페이지 처리
        all_items = list(items)

        # 나머지 페이지 수집
        start = PAGE_SIZE + 1
        while start <= limit:
            resp = _post_action(session, cfg["dcmClCdCtl"], cfg["collectionName"], keyword, start)
            batch, _ = _extract_items(resp)
            if not batch:
                break
            all_items.extend(batch)
            start += PAGE_SIZE
            time.sleep(delay)

            if start % 500 == 1:
                print(f"  진행: {start}/{limit}")

        # 저장
        for item in all_items:
            record = _parse_record(item, dtype)
            if not record:
                stats["failed"] += 1
                continue

            file_id = record["id"]
            if file_id in existing_ids:
                stats["skipped"] += 1
                continue

            out_path = DECISIONS_DIR / f"{file_id}.json"
            out_path.write_text(
                json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            stats["saved"] += 1

        print(f"  [{dtype}] 저장={stats['saved']} 스킵={stats['skipped']} 실패={stats['failed']}")

    print(f"\n완료: 저장={stats['saved']}, 스킵={stats['skipped']}, 실패={stats['failed']}")
    return stats


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="판례·결정례 JSON API 수집기")
    parser.add_argument(
        "--type",
        dest="dtype",
        choices=list(DECISION_TYPES.keys()) + ["all"],
        default="tax_tribunal",
        help="수집 유형 (기본: tax_tribunal=심판청구)",
    )
    parser.add_argument("--keyword", default="양도", help="키워드 필터 (기본: 양도)")
    parser.add_argument("--dry-run", action="store_true", help="총 건수 확인만")
    parser.add_argument("--resume", action="store_true", default=True)
    parser.add_argument("--delay", type=float, default=0.8)
    parser.add_argument("--max", type=int, default=0, dest="max_per_type",
                        help="타입별 최대 수집 건수 (0=전체)")
    args = parser.parse_args()

    types = list(DECISION_TYPES.keys()) if args.dtype == "all" else [args.dtype]
    collect_decisions(
        decision_types=types,
        keyword=args.keyword,
        dry_run=args.dry_run,
        resume=args.resume,
        delay=args.delay,
        max_per_type=args.max_per_type,
    )
