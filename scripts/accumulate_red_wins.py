"""
Red-Win 누적 배치 러너

Phase 1 (방법3): 골든케이스 30개 → debate 실행
Phase 2 (방법2): 합성 경계케이스 → debate 실행

사용법:
    python -m scripts.accumulate_red_wins              # Phase 1+2 전체
    python -m scripts.accumulate_red_wins --phase 1    # 골든케이스만
    python -m scripts.accumulate_red_wins --phase 2    # 합성케이스만
    python -m scripts.accumulate_red_wins --dry-run    # API 미호출, 케이스 목록만 출력
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

RED_WINS_DIR = Path("data/red_wins")


# ── 골든케이스 → fact_json 변환 ────────────────────────────────────────────────

def _to_date8(d: str) -> str:
    """'2019-04-10' → '20190410'"""
    return d.replace("-", "") if d else ""


def golden_case_to_fact_json(case: dict) -> dict:
    """RAG_GOLDEN_CASES 단건을 chat_turn() fact_json 포맷으로 변환.

    FactInput 스키마에 맞게 special_cases 중첩 구조를 명시적으로 생성한다.
    flat merge 방식은 Pydantic이 unknown fields를 무시하므로 사용 불가.
    """
    up = case.get("user_property", {})
    op = case.get("owner_profile", {})
    fl = case.get("fact_ledger", {})

    fact: dict = {
        "transfer_date": _to_date8(up.get("transfer_date", "")),
        "acquisition_date": _to_date8(up.get("acquisition_date", "")),
        "property_type": up.get("asset_kind", "아파트"),
        "acquisition_reason": up.get("acquisition_cause", "매매"),
        "household_house_count": op.get("household_house_count", 1),
        "transfer_price": up.get("sale_price_total", 0),
        "acquisition_price": up.get("acquisition_price", 0),
        "residence_years": up.get("residence_period_years", 0),
        "holding_years": up.get("holding_period_years", 0),
        "is_adjustment_area_at_transfer": up.get("adjustment_area_at_transfer", False),
        "is_adjustment_area_at_acquisition": up.get("adjustment_area_at_acquisition", False),
        "joint_ownership": up.get("joint_ownership_yn", False),
        "is_non_resident": op.get("overseas_residence_yn", False),  # FIX: overseas_resident → is_non_resident
    }

    # ── special_cases 중첩 구조 명시적 생성 ────────────────────────────────────
    special_cases: dict = {}

    # 일시적 2주택
    if fl.get("is_temporary_two_house") and fl.get("temp_new_acquisition_date"):
        special_cases["temp_two_house"] = {
            "new_acquisition_date": _to_date8(fl.get("temp_new_acquisition_date", "")),
            "old_house_must_sell_by": _to_date8(fl.get("temp_old_must_sell_by", "")),
            "new_is_adjustment_area": fl.get("temp_new_is_adjustment_area", False),
        }

    # 상속주택
    raw_death = up.get("death_date") or fl.get("death_date")
    death_date8 = _to_date8(raw_death) if raw_death and "-" in str(raw_death) else (raw_death or "")
    if death_date8 or fl.get("selling_inherited_house") or fl.get("inherited_as_only_house"):
        inh: dict = {
            "same_household_at_death": fl.get("deceased_same_household", False),
            "inherited_as_only_house": fl.get("inherited_as_only_house", False),
            "selling_inherited_house": fl.get("selling_inherited_house", True),
        }
        if death_date8:
            inh["death_date"] = death_date8
        raw_donor = fl.get("donor_acquisition_date")
        if raw_donor:
            inh["donor_acquisition_date"] = _to_date8(raw_donor) if "-" in str(raw_donor) else raw_donor
        special_cases["inheritance"] = inh

    # 증여 이월과세
    if fl.get("is_gift_from_spouse_or_lineal"):
        gift: dict = {"is_gift_from_spouse_or_lineal": True}
        raw_orig = fl.get("original_donor_acquisition_date")
        if raw_orig:
            gift["donor_acquisition_date"] = _to_date8(raw_orig) if "-" in str(raw_orig) else raw_orig
        if fl.get("original_donor_acquisition_price"):
            gift["donor_acquisition_price"] = fl["original_donor_acquisition_price"]
        special_cases["gift"] = gift

    # 재건축·입주권
    rc_data = fl.get("reconstruction")
    if isinstance(rc_data, dict):
        mgmt_raw = rc_data.get("management_disposal_date", "")
        mgmt8 = _to_date8(mgmt_raw) if mgmt_raw and "-" in str(mgmt_raw) else mgmt_raw
        if mgmt8:
            special_cases["reconstruction"] = {
                "management_disposal_date": mgmt8,
                "is_original_member": rc_data.get("is_original_member", True),
            }

    # 농어촌주택
    rh_data = fl.get("rural_house")
    if isinstance(rh_data, dict):
        special_cases["rural_house"] = {
            "is_eligible": rh_data.get("is_rural_house", False),
            "region": rh_data.get("region"),
        }

    if special_cases:
        fact["special_cases"] = special_cases

    # ── flat pass-through (FactInput 최상위 필드) ──────────────────────────────
    for key in ("is_related_party_transaction", "related_party_relationship", "market_value",
                "bunyang_acquired_before_2021", "sangsaeng_rental"):
        if key in fl:
            fact[key] = fl[key]

    # 날짜 pass-through (YYYY-MM-DD → YYYYMMDD 변환)
    for key in ("overseas_departure_date", "gift_date"):
        val = fl.get(key) or up.get(key)
        if val:
            fact[key] = _to_date8(val) if "-" in str(val) else val

    return {k: v for k, v in fact.items() if v is not None and v != ""}


# ── 실행 ───────────────────────────────────────────────────────────────────────

async def _run_one(case_id: str, fact_json: dict, expected_verdict: str) -> dict:
    from src.api.chat_api import chat_turn
    t0 = time.time()
    result = await chat_turn(fact_json=fact_json, enable_debate=True)
    elapsed = round(time.time() - t0, 1)

    verdict = result.get("verdict", "—")
    match = verdict == expected_verdict if expected_verdict else None
    red_won = result.get("debate_record", {}).get("winner") == "red" if result.get("debate_record") else False

    status = "🔴" if red_won else ("✓" if match else ("✗" if match is False else "?"))
    print(f"  {status} [{case_id}] verdict={verdict} expected={expected_verdict or '—'} ({elapsed}s)")
    if red_won:
        print(f"    └─ Red 승리 → data/red_wins/ 저장됨")

    return {"case_id": case_id, "verdict": verdict, "expected": expected_verdict, "red_won": red_won, "elapsed": elapsed}


async def run_phase1(dry_run: bool = False) -> list[dict]:
    """Phase 1: 골든케이스 30개."""
    from tests.rag_golden_cases import RAG_GOLDEN_CASES

    print(f"\n=== Phase 1: 골든케이스 {len(RAG_GOLDEN_CASES)}개 ===")
    results = []

    for case in RAG_GOLDEN_CASES:
        case_id = case.get("case_id", "?")
        expected = case.get("expected", {}).get("verdict", "")
        fact_json = golden_case_to_fact_json(case)

        # blocked_at_l2 예상 케이스는 debate 의미 없으므로 스킵
        if case.get("expected", {}).get("blocked_at_l2"):
            print(f"  ⏭ [{case_id}] blocked_at_l2 예상 → 스킵")
            continue

        if dry_run:
            print(f"  [DRY] [{case_id}] expected={expected} fact_keys={list(fact_json.keys())[:5]}...")
            continue

        result = await _run_one(case_id, fact_json, expected)
        results.append(result)
        await asyncio.sleep(1)  # API rate limit 여유

    return results


async def run_phase2(dry_run: bool = False, n_per_type: int = 15) -> list[dict]:
    """Phase 2: 합성 경계케이스."""
    from src.eval.case_generator import generate_all_boundary_cases

    cases = generate_all_boundary_cases(n_per_type=n_per_type)
    print(f"\n=== Phase 2: 합성 경계케이스 {len(cases)}개 ===")
    results = []

    for case in cases:
        case_id = case.case_id
        expected = case.expected_verdict or ""
        fact_json = case.fact_json

        # 필수 필드 보정
        if "is_adjustment_area_at_transfer" not in fact_json:
            fact_json["is_adjustment_area_at_transfer"] = False
        if "is_adjustment_area_at_acquisition" not in fact_json:
            fact_json["is_adjustment_area_at_acquisition"] = False

        if dry_run:
            print(f"  [DRY] [{case_id}] {case.description} expected={expected}")
            continue

        result = await _run_one(case_id, fact_json, expected)
        result["description"] = case.description
        results.append(result)
        await asyncio.sleep(1)

    return results


def _print_summary(results: list[dict]) -> None:
    total = len(results)
    if not total:
        return
    red_wins = sum(1 for r in results if r.get("red_won"))
    matches = sum(1 for r in results if r.get("verdict") == r.get("expected") and r.get("expected"))
    current_total = len(list(RED_WINS_DIR.glob("*.json"))) if RED_WINS_DIR.exists() else 0

    print(f"\n=== 결과 요약 ===")
    print(f"  실행: {total}건")
    print(f"  정답 일치: {matches}/{total}")
    print(f"  🔴 Red 승리 (이번 배치): {red_wins}건")
    print(f"  누적 Red wins: {current_total}건 / 목표 50건")
    remaining = max(0, 50 - current_total)
    print(f"  남은 목표: {remaining}건")


async def main(phase: int, dry_run: bool, n_synthetic: int) -> None:
    all_results = []

    if phase in (0, 1):
        r1 = await run_phase1(dry_run=dry_run)
        all_results.extend(r1)

    if phase in (0, 2):
        r2 = await run_phase2(dry_run=dry_run, n_per_type=n_synthetic)
        all_results.extend(r2)

    if not dry_run:
        _print_summary(all_results)

        # 결과 저장
        out = Path("data/eval_results")
        out.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        out_path = out / f"red_win_batch_{ts}.json"
        out_path.write_text(json.dumps(all_results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n결과 저장: {out_path}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Red-Win 누적 배치 러너")
    parser.add_argument("--phase", type=int, default=0, choices=[0, 1, 2],
                        help="0=전체, 1=골든케이스만, 2=합성케이스만")
    parser.add_argument("--dry-run", action="store_true", help="API 미호출, 케이스 목록만 출력")
    parser.add_argument("--n-synthetic", type=int, default=15, help="타입별 합성케이스 수 (기본 15)")
    args = parser.parse_args()

    asyncio.run(main(phase=args.phase, dry_run=args.dry_run, n_synthetic=args.n_synthetic))
