"""
법령 개정 자동 감지 스크립트

매일 저녁 실행 → fetch_law_version_list로 현행 MST 목록 조회
→ 스냅샷과 비교 → 새 버전 발견 시 XML 수집 + Pinecone reindex

사용법:
    python -m scripts.detect_law_changes              # 감지만
    python -m scripts.detect_law_changes --embed      # 감지 + Pinecone 업로드
    python -m scripts.detect_law_changes --dry-run    # API 호출 없이 스냅샷만 출력

Windows Task Scheduler 등록:
    schtasks /create /tn "TaxLawChanges" /tr "python -m scripts.detect_law_changes --embed" /sc DAILY /st 23:00
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
        print(f"업로드하려면:  python -m scripts.detect_law_changes --embed")


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

    # 5. 스냅샷 갱신 (신규 버전이 없어도 현행 목록으로 업데이트)
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

    # 6. 규제지역 변경 감지
    print("\n--- 규제지역 변경 감지 ---")
    try:
        from src.ingestion.area_designation_pipeline import run_pipeline
        area_summary = run_pipeline(dry_run=args.dry_run)
        if area_summary.get("alert_level"):
            print(f"  ⚠ 규제지역 알림: {area_summary['alert_level']}")
    except Exception as e:
        print(f"  ⚠ 규제지역 감지 오류: {e}")

    print("\n=== 완료 ===")


if __name__ == "__main__":
    main()
