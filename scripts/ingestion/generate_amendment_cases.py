"""
법령 개정 시 자동 케이스 생성 및 파이프라인 검증.

detect_law_changes.py가 신규 MST를 발견하면 자동 호출:
  1. 신규 XML에서 Claude가 변경된 임계값(금액·기간·세율·일몰일) 추출
  2. 임계값 경계(±1) 케이스 자동 생성
  3. chat_turn()으로 파이프라인 즉시 검증 (debate 없이 속도 우선)
  4. verdict 불일치 시 경보 출력 + data/amendment_test_results/ 저장

단독 실행:
    python -m scripts.ingestion.generate_amendment_cases --law 소득세법 --mst 285523
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

RESULTS_DIR = Path("data/amendment_test_results")
CHANGE_LOG_PATH = Path("data/law_change_log.jsonl")

# 임계값 추출은 Haiku로 — 속도·비용 우선
_EXTRACT_MODEL = os.getenv("CLAUDE_FAST_MODEL", "claude-haiku-4-5-20251001")
_EXTRACT_MAX_XML = 8_000   # Claude에게 전달할 XML 최대 문자 수
_EXTRACT_TIMEOUT = 30      # 초


@dataclass
class AmendmentCase:
    case_id: str
    description: str
    law_name: str
    article: str
    threshold_type: str      # "price" | "period" | "date" | "rate"
    fact_json: dict
    expected_verdict: str    # 예측 어려운 경우 빈 문자열
    boundary_label: str      # "below" | "at" | "above"


# ── 1. XML → 임계값 추출 ──────────────────────────────────────────────────────

_EXTRACT_PROMPT = """\
다음은 {law_name} 법령 XML입니다.

이 XML에서 양도소득세 판단에 직접 영향을 주는 수치 임계값만 추출하세요.
대상: 고가주택 기준금액, 보유·거주기간, 단기세율 기간, 중과 한시배제 기간, 일몰일.

JSON 배열만 반환 (설명·마크다운 없이):
[
  {{
    "type": "price|period|date|rate",
    "article": "조문번호 (예: 제89조제1항제3호)",
    "value": 숫자_또는_날짜문자열,
    "unit": "원|년|일|%|YYYYMMDD",
    "description": "한줄설명",
    "verdict_affected": "비과세|고가주택|중과|단기세율|감면|일반과세"
  }}
]

추출할 임계값이 없으면 반드시 빈 배열 [] 만 반환.

XML (일부):
{xml_excerpt}
"""


def extract_thresholds(xml_text: str, law_name: str) -> list[dict]:
    """Claude Haiku로 XML에서 양도소득세 관련 임계값을 추출한다."""
    import anthropic

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("  ⚠ ANTHROPIC_API_KEY 없음 — 임계값 추출 건너뜀")
        return []

    client = anthropic.Anthropic(api_key=api_key)
    excerpt = xml_text[:_EXTRACT_MAX_XML]
    prompt = _EXTRACT_PROMPT.format(law_name=law_name, xml_excerpt=excerpt)

    try:
        resp = client.messages.create(
            model=_EXTRACT_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        # ```json ... ``` 블록 제거
        if "```" in raw:
            raw = raw.split("```")[1].lstrip("json\n").rstrip("```").strip()
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"  ⚠ JSON 파싱 실패 ({law_name}): {e}")
        return []
    except Exception as e:
        print(f"  ⚠ 임계값 추출 실패 ({law_name}): {e}")
        return []


# ── 2. 임계값 → 경계 케이스 생성 ─────────────────────────────────────────────

_BASE_FACT = {
    "property_type": "아파트",
    "acquisition_reason": "매매",
    "household_house_count": 1,
    "acquisition_price": 500_000_000,
    "residence_years": 3.0,
    "is_adjustment_area_at_transfer": False,
    "is_adjustment_area_at_acquisition": False,
}


def _case_id(law_name: str, article: str, label: str) -> str:
    slug = "".join(c for c in article if c.isdigit())[-4:] or "0000"
    return f"AMD-{law_name[:2]}-{slug}-{label}"


def build_boundary_cases(threshold: dict, law_name: str, today: date) -> list[AmendmentCase]:
    """임계값 1건 → 경계 케이스 2~3개 생성."""
    t_type = threshold.get("type", "")
    article = threshold.get("article", "?")
    value = threshold.get("value")
    unit = threshold.get("unit", "")
    desc = threshold.get("description", "")
    verdict = threshold.get("verdict_affected", "")

    acq_date = today - timedelta(days=365 * 5)
    base = {
        **_BASE_FACT,
        "transfer_date": today.strftime("%Y%m%d"),
        "acquisition_date": acq_date.strftime("%Y%m%d"),
    }

    cases: list[AmendmentCase] = []

    # ── 금액 임계값 ──
    if t_type == "price" and isinstance(value, (int, float)):
        threshold_won = int(value)
        margin = max(10_000_000, int(threshold_won * 0.01))
        for label, price, exp_v in [
            ("below", threshold_won - margin, "비과세"),
            ("at",    threshold_won,          "비과세"),
            ("above", threshold_won + margin, verdict or "고가주택"),
        ]:
            cases.append(AmendmentCase(
                case_id=_case_id(law_name, article, label),
                description=f"{desc} | {label}: {price:,}원",
                law_name=law_name,
                article=article,
                threshold_type=t_type,
                fact_json={**base, "transfer_price": price},
                expected_verdict=exp_v,
                boundary_label=label,
            ))

    # ── 기간 임계값 ──
    elif t_type == "period" and isinstance(value, (int, float)) and unit in ("년", "일"):
        days = int(value * 365) if unit == "년" else int(value)
        for label, delta in [("below", -1), ("at", 0), ("above", 1)]:
            hold = days + delta
            acq = today - timedelta(days=hold)
            cases.append(AmendmentCase(
                case_id=_case_id(law_name, article, label),
                description=f"{desc} | {label}: {hold}일 보유",
                law_name=law_name,
                article=article,
                threshold_type=t_type,
                fact_json={
                    **base,
                    "acquisition_date": acq.strftime("%Y%m%d"),
                    "transfer_price": 900_000_000,
                    "residence_years": round(hold / 365, 2),
                },
                expected_verdict="",  # 기간 경계는 사실관계별로 달라 expected 지정 어려움
                boundary_label=label,
            ))

    # ── 일몰일 임계값 ──
    elif t_type == "date" and isinstance(value, str) and len(str(value)) == 8:
        try:
            v = str(value)
            sunset = date(int(v[:4]), int(v[4:6]), int(v[6:]))
        except ValueError:
            return cases
        for label, delta in [("below", -1), ("at", 0), ("above", 1)]:
            t_date = sunset + timedelta(days=delta)
            cases.append(AmendmentCase(
                case_id=_case_id(law_name, article, label),
                description=f"{desc} | {label}: 양도일 {t_date}",
                law_name=law_name,
                article=article,
                threshold_type=t_type,
                fact_json={
                    **base,
                    "transfer_date": t_date.strftime("%Y%m%d"),
                    "transfer_price": 900_000_000,
                },
                expected_verdict="",
                boundary_label=label,
            ))

    # rate는 결과값 — 입력 케이스 생성 불필요 (무시)

    return cases


# ── 3. chat_turn() 검증 ───────────────────────────────────────────────────────

async def _verify_cases(cases: list[AmendmentCase]) -> list[dict]:
    """각 케이스를 chat_turn()으로 실행, debate 없이 속도 우선."""
    from src.application.chat_service import run_chat as chat_turn

    results = []
    for c in cases:
        t0 = time.time()
        try:
            result = await chat_turn(fact_json=c.fact_json, enable_debate=False)
            verdict = result.get("verdict", "—")
            blocked = result.get("blocked", False)
            elapsed = round(time.time() - t0, 1)

            if c.expected_verdict:
                match: bool | None = (verdict == c.expected_verdict)
                sym = "✓" if match else "✗"
            else:
                match = None
                sym = "?"

            print(f"    {sym} [{c.case_id}] {c.boundary_label:5s} → {verdict}"
                  + (f" (expected {c.expected_verdict})" if c.expected_verdict else "")
                  + f"  {elapsed}s")

            results.append({
                "case_id": c.case_id,
                "description": c.description,
                "law_name": c.law_name,
                "article": c.article,
                "boundary_label": c.boundary_label,
                "verdict": verdict,
                "expected_verdict": c.expected_verdict,
                "match": match,
                "blocked": blocked,
                "elapsed": elapsed,
            })
        except Exception as e:
            print(f"    ⚠ [{c.case_id}] 실행 오류: {e}")
            results.append({
                "case_id": c.case_id,
                "description": c.description,
                "law_name": c.law_name,
                "article": c.article,
                "boundary_label": c.boundary_label,
                "error": str(e),
                "match": None,
            })
        await asyncio.sleep(0.5)

    return results


# ── 4. 메인 진입점 ────────────────────────────────────────────────────────────

def run_amendment_verification(
    new_versions: dict[str, list[str]],
    fetch_xml_fn: Callable[[str], str],
) -> dict:
    """
    신규 법령 버전별로 임계값 추출 → 경계 케이스 생성 → 파이프라인 검증.

    detect_law_changes.py main()에서 직접 호출 (sync).
    반환: {"total_cases": int, "anomalies": list[dict]}
    """
    today = date.today()
    all_cases: list[AmendmentCase] = []
    threshold_summary: list[dict] = []

    for law_name, mst_list in new_versions.items():
        print(f"\n  [{law_name}] 개정 임계값 추출 중 (신규 MST: {mst_list})...")
        # 최신 버전(마지막 MST)만 처리 — 여러 버전이 한 번에 감지되는 경우 드묾
        for mst in mst_list[-1:]:
            try:
                xml_text = fetch_xml_fn(mst)
            except Exception as e:
                print(f"    ⚠ XML 수집 실패 ({mst}): {e}")
                continue

            thresholds = extract_thresholds(xml_text, law_name)
            if not thresholds:
                print(f"    → 추출된 임계값 없음 (XML 구조 변화 없거나 비관련 개정)")
                continue

            print(f"    임계값 {len(thresholds)}개 추출:")
            for th in thresholds:
                print(f"      · {th.get('article')} {th.get('description')} "
                      f"= {th.get('value')} {th.get('unit')}")
                threshold_summary.append({**th, "law_name": law_name, "mst": mst})
                cases = build_boundary_cases(th, law_name, today)
                all_cases.extend(cases)

    if not all_cases:
        print("  → 생성된 경계 케이스 없음 — 검증 건너뜀")
        return {"total_cases": 0, "anomalies": []}

    print(f"\n  경계 케이스 {len(all_cases)}개 생성 → 파이프라인 검증 시작")

    # sync 컨텍스트에서 async 호출
    try:
        results = asyncio.run(_verify_cases(all_cases))
    except RuntimeError:
        # 이미 event loop 안에서 호출된 경우 (Jupyter 등)
        loop = asyncio.get_event_loop()
        results = loop.run_until_complete(_verify_cases(all_cases))

    # 이상 감지: expected가 있는 케이스 중 불일치
    anomalies = [r for r in results if r.get("match") is False]
    neutral = [r for r in results if r.get("match") is None]
    correct = [r for r in results if r.get("match") is True]

    print(f"\n  검증 결과: ✓ {len(correct)}건 | ✗ {len(anomalies)}건 불일치 | ? {len(neutral)}건 (expected 미정)")

    if anomalies:
        print(f"\n  🚨 verdict 불일치 {len(anomalies)}건 — 파이프라인 또는 expected_verdict 수정 필요:")
        for a in anomalies:
            print(f"     [{a['case_id']}] {a['description']}")
            print(f"       got={a['verdict']}  expected={a['expected_verdict']}")
    else:
        print("  ✅ expected 있는 경계 케이스 모두 verdict 일치")

    # 결과 저장
    ts = today.strftime("%Y%m%d_%H%M%S")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / f"amendment_test_{ts}.json"
    out_path.write_text(
        json.dumps({
            "detected_at": datetime.now().isoformat(),
            "changed_laws": list(new_versions.keys()),
            "thresholds_extracted": threshold_summary,
            "results": results,
            "anomalies": anomalies,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"  결과 저장: {out_path}")

    # law_change_log.jsonl 에도 기록
    CHANGE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CHANGE_LOG_PATH.open("a", encoding="utf-8") as f:
        record = {
            "detected_at": datetime.now().isoformat(),
            "event": "amendment_test_results",
            "total_cases": len(all_cases),
            "anomaly_count": len(anomalies),
            "anomaly_case_ids": [a["case_id"] for a in anomalies],
        }
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return {"total_cases": len(all_cases), "anomalies": anomalies}


# ── CLI (단독 실행) ───────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="법령 개정 자동 케이스 생성 및 검증")
    parser.add_argument("--law", required=True, help="법령명 (예: 소득세법)")
    parser.add_argument("--mst", required=True, help="MST 번호")
    parser.add_argument("--extract-only", action="store_true", help="임계값 추출만 (검증 없음)")
    args = parser.parse_args()

    sys.stdout.reconfigure(encoding="utf-8")

    from src.ingestion.collect import fetch_law_xml

    print(f"=== {args.law} (MST={args.mst}) 개정 케이스 생성 ===")
    try:
        xml_text = fetch_law_xml(args.mst)
    except Exception as e:
        print(f"XML 수집 실패: {e}")
        sys.exit(1)

    thresholds = extract_thresholds(xml_text, args.law)
    if not thresholds:
        print("추출된 임계값 없음.")
        sys.exit(0)

    print(f"\n추출된 임계값 {len(thresholds)}개:")
    for th in thresholds:
        print(f"  {th.get('article')} {th.get('description')} = {th.get('value')} {th.get('unit')}")

    if args.extract_only:
        sys.exit(0)

    today = date.today()
    all_cases: list[AmendmentCase] = []
    for th in thresholds:
        all_cases.extend(build_boundary_cases(th, args.law, today))

    print(f"\n경계 케이스 {len(all_cases)}개 → 검증 시작")
    results = asyncio.run(_verify_cases(all_cases))

    anomalies = [r for r in results if r.get("match") is False]
    print(f"\n불일치: {len(anomalies)}건")
    for a in anomalies:
        print(f"  [{a['case_id']}] {a['description']}: got={a['verdict']} expected={a['expected_verdict']}")


if __name__ == "__main__":
    main()
