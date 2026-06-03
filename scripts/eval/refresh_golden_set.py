"""
골든셋 자동 갱신 스크립트.

구조:
  합성케이스 (source: synthetic / ruling_synthetic) — 자동 생성, 훈련/퍼징용
  디베이트   (source: debate)                       — 논쟁 엔진 출력
  골든셋     (expert_labels.json reviewed=True)      — 세무사 검토 완료

유권해석 교차탐지 역할 제한:
  - "판정이 바뀌는가?" 를 묻지 않는다.
  - "이 유권해석과 쟁점이 겹치는가?" 만 묻는다.
  - 출력은 invalidated=True + ruling_signals 기록이며 판단이 아니다.

사용법:
    python -m scripts.eval.refresh_golden_set                 # 전체 실행
    python -m scripts.eval.refresh_golden_set --dry-run       # 변경 없이 결과 출력
    python -m scripts.eval.refresh_golden_set --generate-only # 합성케이스 생성만
    python -m scripts.eval.refresh_golden_set --cross-check-only # 교차탐지만
"""
from __future__ import annotations

import argparse
import json
import sys
import io
import time
from dataclasses import asdict
from datetime import datetime, date
from pathlib import Path
from typing import Optional

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent.parent))

GOLDEN_FILE       = Path("data/golden/qa_pairs.json")
CHANGE_LOG        = Path("data/law_change_log.jsonl")
CROSS_CHECK_STATE = Path("data/golden/.cross_check_state.json")

RULINGS_DIRS = [
    Path("data/rulings/nts_interp"),
    Path("data/rulings/moef"),
    Path("data/rulings/nts"),
    Path("data/rulings/decisions"),
]

_SYNTHETIC_SOURCES = {"synthetic", "ruling_synthetic"}


# ── 데이터 로드 / 저장 ─────────────────────────────────────────────────────────

def _load_golden() -> list[dict]:
    if not GOLDEN_FILE.exists():
        return []
    return json.loads(GOLDEN_FILE.read_text(encoding="utf-8"))


def _save_golden(cases: list[dict], dry_run: bool) -> None:
    if dry_run:
        return
    GOLDEN_FILE.write_text(
        json.dumps(cases, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _append_log(record: dict) -> None:
    CHANGE_LOG.parent.mkdir(parents=True, exist_ok=True)
    with CHANGE_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _load_cross_check_state() -> dict:
    if not CROSS_CHECK_STATE.exists():
        return {}
    try:
        return json.loads(CROSS_CHECK_STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cross_check_state(state: dict) -> None:
    CROSS_CHECK_STATE.parent.mkdir(parents=True, exist_ok=True)
    CROSS_CHECK_STATE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ── 합성케이스 생성 ──────────────────────────────────────────────────────────

def _generate_synthetic_cases(as_of: Optional[date] = None) -> list[dict]:
    """case_generator + ruling_case_generator 전체 실행 → dict 변환."""
    from src.eval.case_generator import generate_all_comprehensive_cases
    from src.eval.ruling_case_generator import generate_all_ruling_cases

    today = as_of or date.today()
    result = []
    for sc in generate_all_comprehensive_cases(as_of=today):
        d = asdict(sc)
        d.setdefault("source", "synthetic")
        result.append(d)
    for sc in generate_all_ruling_cases():
        d = asdict(sc)
        d.setdefault("source", "ruling_synthetic")
        result.append(d)
    return result


def _merge_into_golden(
    new_cases: list[dict],
    existing: list[dict],
    dry_run: bool,
) -> tuple[list[dict], int]:
    """기존 케이스와 중복 제거 후 병합. (updated_list, added_count) 반환."""
    existing_ids = {c.get("id") or c.get("case_id", "") for c in existing}
    added = 0
    merged = list(existing)
    for c in new_cases:
        cid = c.get("case_id") or c.get("id", "")
        if cid and cid not in existing_ids:
            entry = {
                "id": cid,
                "description": c.get("description", ""),
                "fact_json": c.get("fact_json", {}),
                "expected_verdict": c.get("expected_verdict"),
                "boundary_type": c.get("boundary_type", ""),
                "tags": c.get("tags", []),
                "source": c.get("source", "synthetic"),
                "registry_deps": c.get("registry_deps", []),
                "registry_snapshot": c.get("registry_snapshot", {}),
                "gold_chunk_ids": c.get("gold_chunk_ids", []),
            }
            merged.append(entry)
            existing_ids.add(cid)
            added += 1
    return merged, added


# ── 유권해석 교차탐지 ────────────────────────────────────────────────────────

def _load_new_rulings(last_checked_ts: float) -> list[dict]:
    rulings: list[dict] = []
    for d in RULINGS_DIRS:
        if not d.exists():
            continue
        for f in d.glob("*.json"):
            if f.stat().st_mtime <= last_checked_ts:
                continue
            try:
                raw = json.loads(f.read_text(encoding="utf-8"))
                items = raw if isinstance(raw, list) else [raw]
                for item in items[:3]:
                    if isinstance(item, dict):
                        item["_source_file"] = str(f)
                        item["_source_dir"] = d.name
                        rulings.append(item)
            except Exception:
                pass
    return rulings


def _ruling_summary(ruling: dict) -> str:
    title  = ruling.get("title") or ruling.get("question") or ""
    answer = (ruling.get("answer") or ruling.get("content") or "")[:400]
    doc_id = ruling.get("doc_number") or ruling.get("doc_id") or ruling.get("ruling_id") or ""
    src    = ruling.get("_source_dir", "")
    return f"[{src}] {doc_id}\n제목: {title}\n내용요약: {answer}"


def _cross_check_batch(ruling: dict, golden_cases: list[dict], client) -> list[int]:
    """
    단일 유권해석 × 골든셋 교차탐지.
    반환: 쟁점이 겹치는 케이스 인덱스 목록 (판단 변경 여부 아님).
    """
    from src.agents.prompts import RULING_CROSS_CHECK_PROMPT
    from src.config import CLAUDE_FAST_MODEL

    cases_block = "\n".join(
        f"[{i}] {c.get('description', '')} | 태그: {','.join(c.get('tags', []))}"
        for i, c in enumerate(golden_cases)
    )
    prompt = RULING_CROSS_CHECK_PROMPT.format(
        ruling_summary=_ruling_summary(ruling),
        cases_block=cases_block,
    )
    try:
        resp = client.messages.create(
            model=CLAUDE_FAST_MODEL,
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip()
        if "```" in text:
            text = text.split("```")[1].lstrip("json").strip()
        data = json.loads(text)
        indices = data.get("related_indices", [])
        return [i for i in indices if isinstance(i, int) and 0 <= i < len(golden_cases)]
    except Exception:
        return []


def run_cross_check(
    golden: list[dict],
    dry_run: bool,
    verbose: bool = True,
) -> tuple[list[dict], int]:
    """
    신규 유권해석 스캔 → 쟁점 겹치는 케이스에 invalidated=True + ruling_signals 기록.
    합성케이스는 교차탐지 대상에서 제외 (세무사 검토 대상 아님).
    """
    state   = _load_cross_check_state()
    last_ts = state.get("last_checked_ts", 0.0)

    new_rulings = _load_new_rulings(last_ts)
    if not new_rulings:
        if verbose:
            print("교차탐지: 신규 유권해석 없음")
        return golden, 0

    if verbose:
        print(f"교차탐지: 신규 유권해석 {len(new_rulings)}건 스캔 시작")

    try:
        import anthropic
        from src.config import ANTHROPIC_API_KEY
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    except Exception as e:
        print(f"교차탐지 건너뜀 (LLM 초기화 실패): {e}")
        return golden, 0

    # 합성케이스 제외한 대상만 교차탐지
    check_targets = [
        (i, c) for i, c in enumerate(golden)
        if c.get("source") not in _SYNTHETIC_SOURCES
    ]
    id_map: dict[int, str] = {i: (c.get("id") or c.get("case_id", "")) for i, c in check_targets}
    target_list = [c for _, c in check_targets]

    flagged: dict[str, list[dict]] = {}

    for ruling in new_rulings:
        try:
            related_local = _cross_check_batch(ruling, target_list, client)
            for local_idx in related_local:
                orig_idx = check_targets[local_idx][0]
                cid = id_map.get(orig_idx, "")
                if not cid:
                    continue
                signal = {
                    "ruling_doc":   ruling.get("doc_number") or ruling.get("doc_id") or "",
                    "ruling_title": (ruling.get("title") or "")[:80],
                    "source_dir":   ruling.get("_source_dir", ""),
                    "detected_at":  datetime.now().isoformat(),
                }
                flagged.setdefault(cid, []).append(signal)
            time.sleep(0.3)
        except Exception:
            continue

    if not flagged:
        if verbose:
            print("교차탐지: 영향 후보 케이스 없음")
        new_ts = max(
            (f.stat().st_mtime for d in RULINGS_DIRS if d.exists() for f in d.glob("*.json")),
            default=last_ts,
        )
        if not dry_run:
            _save_cross_check_state({"last_checked_ts": new_ts})
        return golden, 0

    updated = []
    for case in golden:
        cid = case.get("id") or case.get("case_id", "")
        if cid in flagged:
            case = dict(case)
            case["invalidated"] = True
            existing = case.get("ruling_signals", [])
            case["ruling_signals"] = existing + flagged[cid]
        updated.append(case)

    if not dry_run:
        new_ts = max(
            (f.stat().st_mtime for d in RULINGS_DIRS if d.exists() for f in d.glob("*.json")),
            default=last_ts,
        )
        _save_cross_check_state({"last_checked_ts": new_ts})
        _append_log({
            "event":               "cross_check_flagged",
            "detected_at":         datetime.now().isoformat(),
            "new_rulings_scanned": len(new_rulings),
            "flagged_case_ids":    list(flagged.keys()),
        })

    if verbose:
        print(f"교차탐지 완료: {len(flagged)}건 재검토 필요 표시")
        for cid, signals in flagged.items():
            case = next((c for c in golden if (c.get("id") or c.get("case_id", "")) == cid), {})
            print(f"  [{cid}] {case.get('description', '')[:50]}")
            for s in signals:
                print(f"    ← {s['source_dir']} {s['ruling_doc']} {s['ruling_title'][:40]}")

    return updated, len(flagged)


# ── 메인 ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="골든셋 자동 갱신")
    parser.add_argument("--dry-run", action="store_true", help="변경 없이 결과만 출력")
    parser.add_argument("--generate-only", action="store_true", help="합성케이스 생성만")
    parser.add_argument("--cross-check-only", action="store_true", help="유권해석 교차탐지만")
    args = parser.parse_args()

    golden      = _load_golden()
    total_added = 0
    total_flagged = 0

    # ── Step 1: 합성케이스 생성
    if not args.cross_check_only:
        print("=== Step 1: 합성케이스 생성 ===")
        try:
            new_cases = _generate_synthetic_cases()
            print(f"  생성됨: {len(new_cases)}건")
            golden, added = _merge_into_golden(new_cases, golden, dry_run=args.dry_run)
            total_added += added
            print(f"  신규 추가: {added}건 (중복 제외)")
            if not args.dry_run:
                _save_golden(golden, dry_run=False)
        except Exception as e:
            print(f"  합성케이스 생성 실패: {e}")

    # ── Step 2: 유권해석 교차탐지
    if not args.generate_only:
        print("=== Step 2: 유권해석 교차탐지 ===")
        try:
            golden, flagged = run_cross_check(golden, dry_run=args.dry_run)
            total_flagged += flagged
            if flagged and not args.dry_run:
                _save_golden(golden, dry_run=False)
        except Exception as e:
            print(f"  교차탐지 실패: {e}")

    # ── 결과 요약
    print("\n=== 완료 ===")
    source_counts: dict[str, int] = {}
    for c in golden:
        s = c.get("source", "unknown")
        source_counts[s] = source_counts.get(s, 0) + 1
    print(f"  전체: {len(golden)}건")
    for src, cnt in sorted(source_counts.items()):
        print(f"  {src}: {cnt}건")
    if args.dry_run:
        print("  (dry-run: 실제 저장 없음)")
    else:
        _append_log({
            "event":         "golden_set_refreshed",
            "refreshed_at":  datetime.now().isoformat(),
            "added":         total_added,
            "flagged":       total_flagged,
            "total":         len(golden),
            "source_counts": source_counts,
        })


if __name__ == "__main__":
    main()
