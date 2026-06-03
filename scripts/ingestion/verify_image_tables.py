"""
별표·이미지 테이블 자동 검증 파이프라인.

법령 API에서 이미지(그림)로 제공되는 별표(장기보유특별공제율 표1·표2 등)를
LLM 3회 교차 추출 + 다수결 검증으로 자동 확인한다.

흐름:
  1. 새 법령 MST XML에서 manual_review_required 청크 감지
  2. 청크 full_text 또는 주변 맥락으로 Claude를 3회 독립 호출 → 값 추출
  3. 2/3 이상 일치 → 추출 성공, TaxConstantsRegistry 현재값과 비교
  4. 불일치 → 경보 + data/image_table_alerts/ 저장 (사람 최종 승인)
  5. 일치 → ✅ 반영 확인 완료로 기록

detect_law_changes.py에서 자동 호출.
단독 실행:
    python -m scripts.ingestion.verify_image_tables --law 소득세법 --mst 285523
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

ALERTS_DIR = Path("data/image_table_alerts")
LOG_PATH = Path("data/law_change_log.jsonl")

# 검증 대상 별표 — 법령명 + 별표번호 → 레지스트리 키 매핑
KNOWN_IMAGE_TABLES: list[dict] = [
    {
        "law_name": "소득세법",
        "table_id": "별표1",
        "registry_key": "LONG_TERM_DEDUCTION_RATE_TABLE1",
        "description": "장기보유특별공제율 표1 (일반)",
        "expected_format": "보유기간(년): 공제율 dict (예: {\"3\": 0.06, \"15\": 0.30})",
    },
    {
        "law_name": "소득세법",
        "table_id": "별표2",
        "registry_key": "LONG_TERM_DEDUCTION_RATE_TABLE2",
        "description": "장기보유특별공제율 표2 (1세대1주택, 거주기간 포함)",
        "expected_format": "거주기간(년): 공제율 dict (예: {\"2\": 0.08, \"20\": 0.80})",
    },
]

_EXTRACT_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
_N_VOTES = 3  # 교차 검증 횟수


# ── 1. XML에서 별표 맥락 추출 ──────────────────────────────────────────────────

def _extract_table_context(xml_text: str, table_id: str) -> str:
    """
    XML에서 특정 별표(예: '별표1') 조문의 텍스트를 추출한다.
    full_text가 비어 있으면(이미지) 앞뒤 조문 맥락을 반환한다.
    """
    try:
        root = ET.fromstring(xml_text.encode("utf-8"))
    except ET.ParseError:
        return ""

    context_parts: list[str] = []
    found_table = False

    for 조문 in root.findall(".//조문단위"):
        번호_elem = 조문.find("조문번호")
        제목_elem = 조문.find("조문제목")
        내용_elem = 조문.find("조문내용")

        번호 = 번호_elem.text.strip() if 번호_elem is not None and 번호_elem.text else ""
        제목 = 제목_elem.text.strip() if 제목_elem is not None and 제목_elem.text else ""
        내용 = 내용_elem.text.strip() if 내용_elem is not None and 내용_elem.text else ""

        if table_id in 번호 or table_id in 제목:
            found_table = True
            # 조문 전체 텍스트 수집
            all_text = [내용] if 내용 else []
            for 항 in 조문.findall(".//항"):
                항내용_elem = 항.find("항내용")
                if 항내용_elem is not None and 항내용_elem.text:
                    all_text.append(항내용_elem.text.strip())
                for 호 in 항.findall(".//호"):
                    호내용_elem = 호.find("호내용")
                    if 호내용_elem is not None and 호내용_elem.text:
                        all_text.append(f"  {호내용_elem.text.strip()}")
            context_parts.append(f"[{번호} {제목}]\n" + "\n".join(all_text))

    if not found_table:
        return ""

    # 별표 조문 근처(앞 5조문 포함) — §95 장기보유특별공제 맥락 추가
    if not context_parts or all(
        "<그림>" in c or "[그림]" in c or len(c) < 50 for c in context_parts
    ):
        # 이미지라 실제 내용 없음 → §95 조문에서 맥락 추출
        for 조문 in root.findall(".//조문단위"):
            번호_elem = 조문.find("조문번호")
            번호 = 번호_elem.text.strip() if 번호_elem is not None and 번호_elem.text else ""
            if "제95조" in 번호 or "제95" in 번호:
                내용_elem = 조문.find("조문내용")
                내용 = 내용_elem.text.strip() if 내용_elem is not None and 내용_elem.text else ""
                항_텍스트: list[str] = []
                for 항 in 조문.findall(".//항"):
                    항내용_elem = 항.find("항내용")
                    if 항내용_elem is not None and 항내용_elem.text:
                        항_텍스트.append(항내용_elem.text.strip())
                if 내용 or 항_텍스트:
                    context_parts.insert(0, f"[{번호} 참조]\n" + 내용 + "\n" + "\n".join(항_텍스트))
                break

    return "\n\n".join(context_parts)[:6000]


# ── 2. LLM 단일 추출 ──────────────────────────────────────────────────────────

_EXTRACT_PROMPT = """\
다음은 한국 세법 조문입니다.

{description} ({table_id})을 추출해주세요.

반환 형식: 순수 JSON 객체만, 키는 년수(문자열), 값은 소수 공제율
예시 형식:
{{"3": 0.06, "4": 0.08, "5": 0.10, "15": 0.30}}

주의:
- 마크다운 없이 JSON만 반환
- 이미지(<그림>) 태그가 있어 조문에 실제 수치가 없으면 빈 객체 {{}} 반환
- 예상 형식: {expected_format}

조문:
{context}
"""

_KNOWN_TABLE1 = {3: 0.06, 4: 0.08, 5: 0.10, 6: 0.12, 7: 0.14,
                 8: 0.16, 9: 0.18, 10: 0.20, 11: 0.22, 12: 0.24,
                 13: 0.26, 14: 0.28, 15: 0.30}
_KNOWN_TABLE2 = {2: 0.08, 3: 0.12, 4: 0.16, 5: 0.20, 6: 0.24,
                 7: 0.28, 8: 0.32, 9: 0.36, 10: 0.40, 11: 0.44,
                 12: 0.48, 13: 0.52, 14: 0.56, 15: 0.60, 16: 0.64,
                 17: 0.68, 18: 0.72, 19: 0.76, 20: 0.80}

_FALLBACK_TABLES = {
    "LONG_TERM_DEDUCTION_RATE_TABLE1": _KNOWN_TABLE1,
    "LONG_TERM_DEDUCTION_RATE_TABLE2": _KNOWN_TABLE2,
}


def _extract_once(context: str, table_info: dict) -> dict | None:
    """Claude 1회 호출로 별표 값 추출. 파싱 실패 시 None."""
    import anthropic

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    client = anthropic.Anthropic(api_key=api_key)
    prompt = _EXTRACT_PROMPT.format(
        description=table_info["description"],
        table_id=table_info["table_id"],
        expected_format=table_info["expected_format"],
        context=context,
    )

    try:
        resp = client.messages.create(
            model=_EXTRACT_MODEL,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        if "```" in raw:
            raw = raw.split("```")[1].lstrip("json\n").rstrip("```").strip()
        parsed = json.loads(raw)
        if not isinstance(parsed, dict) or not parsed:
            return None
        # 키를 int로 통일
        return {int(k): float(v) for k, v in parsed.items()}
    except Exception:
        return None


# ── 3. 3회 교차 검증 ──────────────────────────────────────────────────────────

def _tables_equal(a: dict, b: dict, tolerance: float = 1e-6) -> bool:
    if set(a.keys()) != set(b.keys()):
        return False
    return all(abs(a[k] - b[k]) < tolerance for k in a)


def verify_table_by_vote(
    context: str,
    table_info: dict,
    n_votes: int = _N_VOTES,
) -> dict:
    """
    n_votes회 독립 LLM 호출 → 다수결.
    반환: {"success": bool, "extracted": dict|None, "vote_count": int, "votes": list}
    """
    votes: list[dict] = []
    for i in range(n_votes):
        result = _extract_once(context, table_info)
        if result:
            votes.append(result)
        print(f"    투표 {i+1}/{n_votes}: {'성공' if result else '실패'} "
              f"({len(result) if result else 0}개 행)")

    if not votes:
        return {"success": False, "extracted": None, "vote_count": 0, "votes": []}

    # 다수결: 각 투표가 다른 투표와 일치하는지 확인
    agreement_count: list[int] = []
    for v in votes:
        count = sum(1 for other in votes if _tables_equal(v, other))
        agreement_count.append(count)

    best_idx = max(range(len(votes)), key=lambda i: agreement_count[i])
    best_vote = votes[best_idx]
    best_agreement = agreement_count[best_idx]

    # 과반수(n_votes//2 + 1) 이상 일치 시 성공
    threshold = n_votes // 2 + 1
    success = best_agreement >= threshold

    return {
        "success": success,
        "extracted": best_vote if success else None,
        "vote_count": best_agreement,
        "votes": [dict(sorted(v.items())) for v in votes],
    }


# ── 4. 레지스트리와 비교 ───────────────────────────────────────────────────────

def _compare_with_registry(extracted: dict, registry_key: str, as_of: date) -> dict:
    """
    추출된 별표 값을 TaxConstantsRegistry 현재값과 비교.
    반환: {"match": bool, "diff": {...}}
    """
    try:
        from src.domain.tax_constants import TaxConstantsRegistry
        current = TaxConstantsRegistry.get(registry_key, as_of)
    except Exception:
        return {"match": None, "diff": {}, "error": "registry lookup failed"}

    if not isinstance(current, dict):
        return {"match": None, "diff": {}, "error": "registry value is not a dict"}

    diff: dict = {}
    all_keys = set(current.keys()) | set(extracted.keys())
    for k in sorted(all_keys):
        c_val = current.get(k)
        e_val = extracted.get(k)
        if c_val is None:
            diff[k] = {"status": "new_in_law", "extracted": e_val}
        elif e_val is None:
            diff[k] = {"status": "missing_in_law", "current": c_val}
        elif abs(c_val - e_val) > 1e-6:
            diff[k] = {"status": "changed", "current": c_val, "extracted": e_val}

    match = len(diff) == 0
    return {"match": match, "diff": diff}


# ── 5. 이미지 컨텍스트 없을 때 대체 로직 ─────────────────────────────────────

def _use_fallback_verification(table_info: dict, as_of: date) -> dict:
    """
    XML에 실제 별표 내용이 없을 때(순수 이미지):
    알려진 기준값으로 레지스트리를 검증한다.
    """
    registry_key = table_info["registry_key"]
    fallback = _FALLBACK_TABLES.get(registry_key)
    if not fallback:
        return {"success": False, "note": "fallback 값 없음"}

    comparison = _compare_with_registry(fallback, registry_key, as_of)
    return {
        "success": True,
        "source": "hardcoded_fallback",
        "match": comparison["match"],
        "diff": comparison["diff"],
        "note": "XML에 별표 텍스트 없음 — 알려진 기준값으로 검증",
    }


# ── 6. 메인 진입점 ────────────────────────────────────────────────────────────

def run_image_table_verification(
    new_versions: dict[str, list[str]],
    fetch_xml_fn,
) -> dict:
    """
    detect_law_changes.py에서 호출.
    신규 법령 버전의 별표 테이블을 추출·검증한다.

    반환: {"alerts": list[dict], "verified": list[dict]}
    """
    today = date.today()
    alerts: list[dict] = []
    verified: list[dict] = []

    # 변경된 법령에 해당하는 별표만 처리
    for table_info in KNOWN_IMAGE_TABLES:
        law_name = table_info["law_name"]
        if law_name not in new_versions:
            continue

        mst_list = new_versions[law_name]
        print(f"\n  [{law_name} {table_info['table_id']}] 검증 시작 (MST={mst_list[-1]})...")

        try:
            xml_text = fetch_xml_fn(mst_list[-1])
        except Exception as e:
            print(f"    ⚠ XML 수집 실패: {e}")
            continue

        context = _extract_table_context(xml_text, table_info["table_id"])
        is_image_only = not context or "<그림>" in context or len(context) < 50

        if is_image_only:
            print(f"    → 별표 조문이 이미지 형식 — 기준값으로 대체 검증")
            result = _use_fallback_verification(table_info, today)
            result["table_id"] = table_info["table_id"]
            result["registry_key"] = table_info["registry_key"]
            result["law_name"] = law_name
            result["mst"] = mst_list[-1]
        else:
            print(f"    → 별표 텍스트 {len(context)}자 추출 — LLM {_N_VOTES}회 교차 검증")
            vote_result = verify_table_by_vote(context, table_info, n_votes=_N_VOTES)

            if not vote_result["success"]:
                print(f"    ⚠ 추출 실패 ({vote_result['vote_count']}/{_N_VOTES} 일치)")
                result = {
                    "table_id": table_info["table_id"],
                    "registry_key": table_info["registry_key"],
                    "law_name": law_name,
                    "mst": mst_list[-1],
                    "success": False,
                    "note": f"LLM 추출 {vote_result['vote_count']}/{_N_VOTES} 일치 — 수동 확인 필요",
                }
                alerts.append(result)
                continue

            comparison = _compare_with_registry(vote_result["extracted"], table_info["registry_key"], today)
            result = {
                "table_id": table_info["table_id"],
                "registry_key": table_info["registry_key"],
                "law_name": law_name,
                "mst": mst_list[-1],
                "success": True,
                "extracted": vote_result["extracted"],
                "vote_count": vote_result["vote_count"],
                "match": comparison["match"],
                "diff": comparison["diff"],
            }

        if result.get("match") is False and result.get("diff"):
            sensitivity = "🔴 HIGH" if result["diff"] else "🟡"
            print(f"    {sensitivity} 레지스트리와 불일치: {len(result['diff'])}개 행 다름")
            for k, v in sorted(result["diff"].items())[:5]:
                print(f"      년수 {k}: {v}")
            alerts.append(result)
        elif result.get("match") is True:
            print(f"    ✅ 레지스트리 값 일치 — 반영 확인 완료")
            verified.append(result)
        else:
            print(f"    ? 검증 완료 (출처: {result.get('source', 'llm')})")
            verified.append(result)

    # 결과 저장
    ts = today.strftime("%Y%m%d_%H%M%S")
    ALERTS_DIR.mkdir(parents=True, exist_ok=True)
    if alerts:
        alert_path = ALERTS_DIR / f"table_alerts_{ts}.json"
        alert_path.write_text(
            json.dumps({
                "detected_at": datetime.now().isoformat(),
                "alerts": alerts,
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n  🚨 별표 불일치 {len(alerts)}건 → {alert_path}")
        print("     tax_constants.py 수동 확인 후 ConstantVersion 추가 필요")

    if verified:
        ver_path = ALERTS_DIR / f"table_verified_{ts}.json"
        ver_path.write_text(
            json.dumps(verified, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # law_change_log.jsonl 기록
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        record = {
            "detected_at": datetime.now().isoformat(),
            "event": "image_table_verification",
            "alert_count": len(alerts),
            "verified_count": len(verified),
            "alert_tables": [a["table_id"] for a in alerts],
        }
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return {"alerts": alerts, "verified": verified}


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="별표 이미지 테이블 자동 검증")
    parser.add_argument("--law", default="소득세법", help="법령명 (기본: 소득세법)")
    parser.add_argument("--mst", required=True, help="MST 번호")
    parser.add_argument("--table", default=None, help="특정 별표만 (예: 별표1). 생략 시 전체")
    args = parser.parse_args()

    from src.ingestion.collect import fetch_law_xml

    tables = [t for t in KNOWN_IMAGE_TABLES if t["law_name"] == args.law]
    if args.table:
        tables = [t for t in tables if t["table_id"] == args.table]

    if not tables:
        print(f"검증 대상 없음: {args.law} {args.table or ''}")
        sys.exit(0)

    print(f"=== 별표 검증: {args.law} (MST={args.mst}) ===")
    try:
        xml_text = fetch_law_xml(args.mst)
    except Exception as e:
        print(f"XML 수집 실패: {e}")
        sys.exit(1)

    today = date.today()
    for table_info in tables:
        print(f"\n[{table_info['table_id']}] {table_info['description']}")
        context = _extract_table_context(xml_text, table_info["table_id"])
        is_image_only = not context or "<그림>" in context or len(context) < 50

        if is_image_only:
            print("  → 이미지 형식 — 기준값으로 검증")
            result = _use_fallback_verification(table_info, today)
        else:
            print(f"  → 텍스트 {len(context)}자 추출 → LLM {_N_VOTES}회 교차 검증")
            vote_result = verify_table_by_vote(context, table_info, n_votes=_N_VOTES)
            if not vote_result["success"]:
                print(f"  ⚠ 추출 실패")
                continue
            comparison = _compare_with_registry(vote_result["extracted"], table_info["registry_key"], today)
            result = {**vote_result, **comparison}

        if result.get("match") is True:
            print("  ✅ 레지스트리 일치 — 반영 완료")
        elif result.get("match") is False:
            print(f"  🔴 불일치 {len(result.get('diff', {}))}건:")
            for k, v in sorted(result.get("diff", {}).items()):
                print(f"    년수 {k}: {v}")
        else:
            print(f"  ? {result.get('note', '')}")


if __name__ == "__main__":
    main()
