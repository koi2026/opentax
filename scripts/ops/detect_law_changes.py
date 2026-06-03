"""
법령 개정 자동 감지 스크립트

매일 저녁 실행 → fetch_law_version_list로 현행 MST 목록 조회
→ 스냅샷과 비교 → 새 버전 발견 시 XML 수집 + Pinecone reindex

사용법:
    python -m scripts.ops.detect_law_changes              # 감지만
    python -m scripts.ops.detect_law_changes --embed      # 감지 + Pinecone 업로드
    python -m scripts.ops.detect_law_changes --dry-run    # API 호출 없이 스냅샷만 출력

Windows Task Scheduler 등록:
    schtasks /create /tn "TaxLawChanges" /tr "python -m scripts.ops.detect_law_changes --embed" /sc DAILY /st 23:00
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# 프로젝트 루트를 PYTHONPATH에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ingestion.collect import (
    TARGET_LAWS,
    fetch_law_version_list,
    fetch_law_xml,
    parse_xml_to_chunks,
    PROCESSED_DIR,
    RAW_DIR,
)

SNAPSHOT_PATH = PROCESSED_DIR / "law_version_snapshots.json"
CHANGE_LOG_PATH = Path("data") / "law_change_log.jsonl"


# ── 스냅샷 로드/저장 ─────────────────────────────────────────────────────────

def load_snapshot() -> dict[str, list[str]]:
    """law_name → [mst, ...] 스냅샷 로드. 없으면 빈 dict."""
    if not SNAPSHOT_PATH.exists():
        return {}
    try:
        return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_snapshot(snapshot: dict[str, list[str]]) -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ── 변경 감지 ─────────────────────────────────────────────────────────────────

def detect_changes(
    snapshot: dict[str, list[str]],
) -> dict[str, list[str]]:
    """
    각 법령의 현행 MST 목록을 API로 조회하고 스냅샷과 비교한다.
    반환: {law_name: [new_mst, ...]} — 스냅샷에 없는 신규 MST만 포함.
    """
    new_versions: dict[str, list[str]] = {}

    for law in TARGET_LAWS:
        name = law["name"]
        print(f"\n[{name}] 버전 목록 조회 중...")
        try:
            versions = fetch_law_version_list(name)
        except Exception as e:
            print(f"  ⚠ API 오류: {e}")
            continue

        if not versions:
            print("  → 버전 목록 없음 (이력 API 미지원 또는 법령명 불일치)")
            continue

        current_msts = {v["mst"] for v in versions}
        known_msts = set(snapshot.get(name, []))
        added = current_msts - known_msts

        print(f"  현행 버전: {len(current_msts)}개 | 신규: {len(added)}개")

        if added:
            new_versions[name] = sorted(added)
            for mst in sorted(added):
                v = next((v for v in versions if v["mst"] == mst), {})
                print(f"  ★ 신규 MST={mst} (시행일: {v.get('effective_date', '불명')})")

    return new_versions


# ── 신규 버전 수집 + 선택적 임베딩 ───────────────────────────────────────────

def collect_new_versions(
    new_versions: dict[str, list[str]],
    snapshot: dict[str, list[str]],
    do_embed: bool,
) -> None:
    """신규 MST의 XML을 수집하고, do_embed=True 이면 Pinecone에 업로드한다."""

    if do_embed:
        # 임베딩 모듈은 무거우므로 필요할 때만 import
        from src.ingestion.embed import embed_and_upload_chunks

    all_new_chunks: list[dict] = []
    law_info_map = {law["name"]: law for law in TARGET_LAWS}

    for law_name, mst_list in new_versions.items():
        law = law_info_map[law_name]
        # 전체 버전 목록 재조회 (effective_date 등 메타 필요)
        try:
            all_versions = fetch_law_version_list(law_name)
        except Exception:
            all_versions = []
        version_map = {v["mst"]: v for v in all_versions}

        for mst in mst_list:
            raw_path = RAW_DIR / f"{law_name.replace(' ', '_')}_{mst}.xml"
            version = version_map.get(mst, {
                "mst": mst,
                "effective_date": "",
                "promulgation_date": "",
                "expiration_date": "",
            })

            try:
                xml_text = fetch_law_xml(mst)
                RAW_DIR.mkdir(parents=True, exist_ok=True)
                raw_path.write_text(xml_text, encoding="utf-8")
                print(f"  → XML 저장: {law_name} MST={mst}")
            except Exception as e:
                print(f"  ⚠ XML 수집 실패 {mst}: {e}")
                continue

            chunks = parse_xml_to_chunks(xml_text, law, version)
            all_new_chunks.extend(chunks)
            print(f"     청크: {len(chunks)}개")

    if not all_new_chunks:
        print("\n신규 청크 없음.")
        return

    # 신규 청크 JSON 저장 (감사 로그)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    new_chunks_path = PROCESSED_DIR / f"new_chunks_{ts}.json"
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    new_chunks_path.write_text(
        json.dumps(all_new_chunks, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n신규 청크 {len(all_new_chunks)}개 → {new_chunks_path}")

    if do_embed:
        print("Pinecone 업로드 중...")
        embed_and_upload_chunks(all_new_chunks)
        print("Pinecone 업로드 완료")
    else:
        print("--embed 없이 실행: Pinecone 업로드 건너뜀.")
        print(f"업로드하려면:  python -m scripts.ops.detect_law_changes --embed")


# ── 변경 이력 기록 ────────────────────────────────────────────────────────────

def append_change_log(new_versions: dict[str, list[str]]) -> None:
    """data/law_change_log.jsonl 에 감지 결과를 한 줄씩 기록."""
    CHANGE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CHANGE_LOG_PATH.open("a", encoding="utf-8") as f:
        for law_name, mst_list in new_versions.items():
            record = {
                "detected_at": datetime.now().isoformat(),
                "law_name": law_name,
                "new_msts": mst_list,
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ── 골든케이스 stale 탐지 ─────────────────────────────────────────────────────

def flag_stale_golden_cases(new_versions: dict[str, list[str]]) -> list[dict]:
    """
    개정된 법령에 의존하는 골든케이스를 추출해 stale 후보로 기록한다.

    반환: stale 후보 케이스 목록 (law_change_log.jsonl에도 append)
    sensitivity=high 케이스는 즉시 전문가 리뷰 필요.
    """
    try:
        from tests.golden_case_legal_deps import get_deps_by_law
    except ImportError:
        print("  ⚠ golden_case_legal_deps 미발견 — stale 탐지 건너뜀")
        return []

    changed_law_names = list(new_versions.keys())
    stale_candidates: list[dict] = []
    seen: set[str] = set()

    for law_name in changed_law_names:
        for dep in get_deps_by_law(law_name):
            case_id = dep["case_id"]
            if case_id in seen:
                continue
            seen.add(case_id)
            stale_candidates.append({
                "case_id": case_id,
                "sensitivity": dep["sensitivity"],
                "triggered_by": law_name,
                "notes": dep["notes"],
            })

    if not stale_candidates:
        return []

    # 심각도 순 정렬 후 출력
    order = {"high": 0, "medium": 1, "low": 2}
    stale_candidates.sort(key=lambda x: order.get(x["sensitivity"], 9))

    print(f"\n⚠ 골든케이스 Stale 후보: {len(stale_candidates)}건")
    for c in stale_candidates:
        mark = "🔴" if c["sensitivity"] == "high" else "🟡"
        print(f"  {mark} [{c['case_id']}] ({c['sensitivity']}) ← {c['triggered_by']}")
        print(f"       {c['notes']}")

    # law_change_log에 stale 기록 추가
    CHANGE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CHANGE_LOG_PATH.open("a", encoding="utf-8") as f:
        record = {
            "detected_at": datetime.now().isoformat(),
            "event": "golden_stale_candidates",
            "stale_cases": stale_candidates,
            "triggered_by_laws": changed_law_names,
        }
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    high_count = sum(1 for c in stale_candidates if c["sensitivity"] == "high")
    if high_count:
        print(f"\n  🚨 HIGH sensitivity {high_count}건 — 전문가 즉시 검토 필요")
        print(f"     tests/golden_case_legal_deps.py → expected_verdict 재확인 후 rag_golden_cases.py 수정")

    return stale_candidates


def _flag_stale_synthetic_cases(new_versions: dict[str, list[str]]) -> None:
    """
    TaxConstantsRegistry 연동 합성 케이스의 expected_verdict stale 탐지.

    법령 개정 → TaxConstantsRegistry 업데이트 → 케이스를 재생성해 expected_verdict 비교.
    verdict가 달라진 케이스를 law_change_log.jsonl에 기록하고 화면에 출력한다.
    """
    from src.eval.case_generator import generate_all_comprehensive_cases
    from dataclasses import asdict
    from datetime import date as _date

    # 변경된 법령이 직접 연관된 registry_deps 추출
    LAW_TO_REGISTRY_DEPS: dict[str, list[str]] = {
        "소득세법": ["HIGH_VALUE_THRESHOLD", "HEAVY_TAX_SUSPENSION_END", "IOTA_PERIOD_YEARS"],
        "소득세법 시행령": ["HIGH_VALUE_THRESHOLD", "IOTA_PERIOD_YEARS"],
        "조세특례제한법": ["SANGSAENG_WINDOW_END"],
        "지방세법": [],
    }

    affected_deps: set[str] = set()
    for law_name in new_versions:
        affected_deps.update(LAW_TO_REGISTRY_DEPS.get(law_name, []))

    if not affected_deps:
        print("  → 연관된 registry_deps 없음, stale 탐지 건너뜀")
        return

    print(f"  영향받는 레지스트리 키: {sorted(affected_deps)}")

    # 현재 시점 기준으로 케이스 재생성
    today = _date.today()
    cases = generate_all_comprehensive_cases(as_of=today)

    # registry_deps와 교집합이 있는 케이스만 필터
    affected = [c for c in cases if set(c.registry_deps) & affected_deps]
    if not affected:
        print("  → stale 후보 합성 케이스 없음")
        return

    print(f"  stale 후보 합성 케이스: {len(affected)}건")

    # 이전 베이스라인 체크포인트에서 verdict 비교
    checkpoint_path = Path("data/eval_results/baseline_checkpoint.json")
    prev_verdicts: dict[str, str] = {}
    if checkpoint_path.exists():
        try:
            ck = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            prev_verdicts = {r["case_id"]: r.get("verdict", "") for r in ck.get("results", [])}
        except Exception:
            pass

    stale_found: list[dict] = []
    for case in affected:
        if case.expected_verdict is None:
            continue
        prev_verdict = prev_verdicts.get(case.case_id)
        if prev_verdict and prev_verdict != case.expected_verdict:
            stale_found.append({
                "case_id": case.case_id,
                "description": case.description,
                "registry_deps": case.registry_deps,
                "prev_expected": prev_verdict,
                "new_expected": case.expected_verdict,
            })
        elif case.expected_verdict:
            # 체크포인트 없어도 현재 expected_verdict 출력
            print(
                f"  ↻ [{case.case_id}] {case.description[:50]}"
                f" → expected={case.expected_verdict} ({', '.join(case.registry_deps)})"
            )

    if stale_found:
        print(f"\n  ★ expected_verdict 변동 {len(stale_found)}건:")
        for s in stale_found:
            print(
                f"    [{s['case_id']}] {s['prev_expected']} → {s['new_expected']}"
                f" ({', '.join(s['registry_deps'])})"
            )
        CHANGE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with CHANGE_LOG_PATH.open("a", encoding="utf-8") as f:
            record = {
                "detected_at": datetime.now().isoformat(),
                "event": "synthetic_case_expected_verdict_changed",
                "affected": stale_found,
                "triggered_by_laws": list(new_versions.keys()),
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    else:
        print("  → expected_verdict 변동 없음 (레지스트리 상수 그대로)")


async def shadow_eval_case(case_id: str, fact_json: dict) -> dict:
    """
    Stale 후보 케이스를 현재 법령 기준으로 재실행해 verdict 변동 여부를 확인한다.

    Hard Stale: verdict가 바뀜 → expected_verdict 수정 필요
    Soft Stale: verdict 동일 → 법 개정이 이 케이스에 실질 영향 없음

    사용법:
        result = await shadow_eval_case("CASE-16", fact_json)
    """
    try:
        from src.application.chat_service import run_chat as chat_turn
    except ImportError:
        return {"case_id": case_id, "error": "chat_turn import 실패"}

    result = await chat_turn(fact_json=fact_json, enable_debate=False)
    return {
        "case_id": case_id,
        "shadow_verdict": result.get("verdict"),
        "shadow_confidence": result.get("confidence"),
        "blocked": result.get("blocked", False),
    }


# ── 메인 ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="법령 개정 자동 감지")
    parser.add_argument("--embed", action="store_true", help="신규 버전 Pinecone 업로드")
    parser.add_argument("--dry-run", action="store_true", help="스냅샷만 출력, API 호출 없음")
    parser.add_argument("--reset-snapshot", action="store_true", help="스냅샷 초기화 후 전체 재수집")
    args = parser.parse_args()

    print(f"=== 법령 개정 감지 시작 ({datetime.now().strftime('%Y-%m-%d %H:%M')}) ===")
    print(f"대상 법령: {len(TARGET_LAWS)}개\n")

    if args.dry_run:
        snapshot = load_snapshot()
        print("--- 현재 스냅샷 ---")
        if snapshot:
            for name, msts in snapshot.items():
                print(f"  {name}: {len(msts)}개 버전")
        else:
            print("  (스냅샷 없음 - 첫 실행 시 전체 수집)")
        return

    snapshot = {} if args.reset_snapshot else load_snapshot()
    if args.reset_snapshot:
        print("스냅샷 초기화: 전체 버전 재수집합니다.\n")

    # 1. 변경 감지
    new_versions = detect_changes(snapshot)

    # 2. 결과 요약
    total_new = sum(len(v) for v in new_versions.values())
    print(f"\n=== 감지 완료: {total_new}개 신규 버전 ===")

    if not new_versions:
        print("변경 없음.")
    else:
        for name, msts in new_versions.items():
            print(f"  {name}: {msts}")

        # 3. 수집 + 선택적 임베딩
        collect_new_versions(new_versions, snapshot, do_embed=args.embed)

        # 4. 변경 이력 기록
        append_change_log(new_versions)

        # 5. 골든케이스 stale 탐지 + invalidated 플래그
        flag_stale_golden_cases(new_versions)
        try:
            from src.eval.golden_injector import flag_for_review as _flag_golden
            _n = _flag_golden(list(new_versions.keys()))
            if _n:
                print(f"\n  ⚠ 골든셋 재검토 플래그: {_n}건 → data/golden/qa_pairs.json")
                print(f"     python -m scripts.eval.run_golden_eval  # 재평가 실행")
        except Exception as _e:
            print(f"  ⚠ 골든셋 플래그 오류: {_e}")

    # 6. 스냅샷 갱신 (신규 버전이 없어도 현행 목록으로 업데이트)
    try:
        updated_snapshot = dict(snapshot)
        for law in TARGET_LAWS:
            name = law["name"]
            try:
                versions = fetch_law_version_list(name)
                if versions:
                    updated_snapshot[name] = sorted({v["mst"] for v in versions})
            except Exception:
                pass  # 갱신 실패해도 기존 값 유지
        save_snapshot(updated_snapshot)
        print(f"\n스냅샷 저장 완료: {SNAPSHOT_PATH}")
    except Exception as e:
        print(f"\n⚠ 스냅샷 저장 실패: {e}")

    # 7. 규제지역 변경 감지
    print("\n--- 규제지역 변경 감지 ---")
    try:
        from src.ingestion.area_designation_pipeline import run_pipeline
        area_summary = run_pipeline(dry_run=args.dry_run)
        if area_summary.get("alert_level"):
            print(f"  ⚠ 규제지역 알림: {area_summary['alert_level']}")
    except Exception as e:
        print(f"  ⚠ 규제지역 감지 오류: {e}")

    # 8. 개정 임계값 기반 자동 케이스 생성 + 파이프라인 검증
    if new_versions and not args.dry_run:
        print("\n--- 개정 임계값 경계 케이스 자동 검증 ---")
        try:
            from scripts.ingestion.generate_amendment_cases import run_amendment_verification
            amd = run_amendment_verification(new_versions, fetch_law_xml)
            if amd.get("anomalies"):
                print(f"\n  🚨 {len(amd['anomalies'])}건 verdict 불일치 — 즉시 확인 필요")
                print(f"     data/amendment_test_results/ 에서 상세 내역 확인")
        except Exception as e:
            print(f"  ⚠ 자동 검증 오류: {e}")

    # 9. 별표·이미지 테이블 LLM 교차 검증 (장기보유특별공제율 표1/표2 등)
    if new_versions and not args.dry_run:
        print("\n--- 별표 이미지 테이블 자동 검증 ---")
        try:
            from scripts.verify_image_tables import run_image_table_verification
            img = run_image_table_verification(new_versions, fetch_law_xml)
            if img.get("alerts"):
                print(f"\n  🔴 별표 불일치 {len(img['alerts'])}건 — 수동 확인 필요")
                print(f"     data/image_table_alerts/ 에서 상세 내역 확인")
        except Exception as e:
            print(f"  ⚠ 별표 검증 오류: {e}")

    # 10. 합성 케이스 registry_deps 기반 stale 탐지
    # TaxConstantsRegistry 상수가 바뀌면 expected_verdict가 자동으로 달라지므로
    # 이전 체크포인트 결과와 비교해 verdict가 flip된 케이스를 표시한다.
    if new_versions and not args.dry_run:
        print("\n--- 합성 케이스 expected_verdict stale 탐지 ---")
        try:
            _flag_stale_synthetic_cases(new_versions)
        except Exception as e:
            print(f"  ⚠ 합성 케이스 stale 탐지 오류: {e}")

    # 11. TaxConstantsRegistry 자동 패치 + GitHub PR 생성
    # extract_thresholds()로 추출된 수치가 있으면 tax_constants.py를 직접 패치하고
    # draft PR을 생성한다. 병합은 인간이 검토 후 수행.
    if new_versions and not args.dry_run:
        print("\n--- TaxConstantsRegistry 자동 업데이트 ---")
        try:
            from scripts.ingestion.generate_amendment_cases import extract_thresholds
            from scripts.ops.auto_update_registry import run_registry_update_pr
            from src.ingestion.collect import fetch_law_version_list

            for law_name, mst_list in new_versions.items():
                mst = mst_list[-1]  # 최신 MST만 처리
                try:
                    xml_text = fetch_law_xml(mst)
                except Exception as e:
                    print(f"  ⚠ XML 수집 실패 ({mst}): {e}")
                    continue

                thresholds = extract_thresholds(xml_text, law_name)
                if not thresholds:
                    print(f"  [{law_name}] 추출된 임계값 없음 — 레지스트리 업데이트 건너뜀")
                    continue

                # 시행일: 버전 목록에서 가져오거나 오늘 날짜 사용
                try:
                    versions = fetch_law_version_list(law_name)
                    ver = next((v for v in versions if v.get("mst") == mst), {})
                    eff_str = ver.get("effective_date", "")
                    if eff_str and len(eff_str) == 8:
                        eff_date = datetime.strptime(eff_str, "%Y%m%d").date()
                    else:
                        eff_date = datetime.now().date()
                except Exception:
                    eff_date = datetime.now().date()

                reg_result = run_registry_update_pr(thresholds, law_name, mst, eff_date)
                if reg_result.get("pr_url"):
                    print(f"  ✓ PR 생성: {reg_result['pr_url']}")
                if reg_result.get("manual_review"):
                    print(f"  ⊘ 수동 확인 필요 키: {reg_result['manual_review']}")
        except Exception as e:
            print(f"  ⚠ 레지스트리 자동 업데이트 오류: {e}")

    print("\n=== 완료 ===")


if __name__ == "__main__":
    main()
