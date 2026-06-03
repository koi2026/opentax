"""
TaxConstantsRegistry 자동 업데이트 + GitHub PR 생성.

detect_law_changes.py의 step 8(개정 케이스 검증) 이후 step 11로 호출:
  1. 추출된 임계값 → 레지스트리 키 규칙 기반 매핑
  2. tax_constants.py 패치 (ConstantVersion 추가, 구버전 effective_to 업데이트)
  3. pytest tests/test_no_hardcoded_constants.py 검증
  4. git branch + commit + gh pr create (draft — 인간 review 필수)

수동 실행:
    python -m scripts.ops.auto_update_registry --law 소득세법 --mst 285523 --effective 20260101

반환값 (run_registry_update_pr):
    {"pr_url": str | None, "patched": [key, ...], "manual_review": [key, ...]}
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv()

REGISTRY_PATH = Path("src/domain/tax_constants.py")
PATCHES_DIR = Path("data/registry_patches")


# ── 1. 임계값 → 레지스트리 키 매핑 ──────────────────────────────────────────

# (article 포함 패턴 목록, description 키워드 목록, registry_key, value_type)
# value_type: "price_won" | "period_years" | "period_months" | "rate_decimal" | "date_yyyymmdd" | "manual"
_MAPPING_RULES: list[tuple[list[str], list[str], str, str]] = [
    (["89"],          ["고가주택", "비과세", "가격"],         "HIGH_VALUE_THRESHOLD",                "price_won"),
    (["104"],         ["중과배제", "일몰", "배제 기한"],       "HEAVY_TAX_SUSPENSION_END",            "date_yyyymmdd"),
    (["104"],         ["단기"],                               "SHORT_TERM_RATES",                    "manual"),  # dict — manual
    (["104"],         ["중과", "추가세율"],                   "HEAVY_TAX_ADDITIONAL",                "manual"),  # dict — manual
    (["97의2"],       ["이월과세", "기간"],                   "IOTA_PERIOD_YEARS",                   "period_years"),
    (["155의3"],      ["임대기간", "임대 기간", "개월"],       "SANGSAENG_MIN_PERIOD_MONTHS",         "period_months"),
    (["155의3"],      ["거주요건", "거주 기간"],               "SANGSAENG_RESIDENCE_YEARS",           "period_years"),
    (["155의3"],      ["증액", "상한"],                       "SANGSAENG_MAX_INCREASE_RATE",         "rate_decimal"),
    (["155의3"],      ["일몰", "종료일", "적용 기한"],        "SANGSAENG_WINDOW_END",                "date_yyyymmdd"),
    (["154"],         ["거주", "요건", "연수"],                "RESIDENCE_REQUIRED_YEARS_ADJUSTMENT", "period_years"),
    (["155②", "155제2항", "155 ②"], ["상속", "주택"],        "INHERITANCE_EXEMPT_YEARS",            "period_years"),
    (["155④", "155제4항", "155 ④"], ["동거봉양", "합가"],    "COHABITATION_EXEMPT_YEARS",           "period_years"),
    (["155⑤", "155제5항", "155 ⑤"], ["혼인"],               "MARRIAGE_MERGE_EXEMPT_YEARS",         "period_years"),
    (["95"],          ["장기보유특별공제", "표1"],             "LONG_TERM_DEDUCTION_RATE_TABLE1",     "manual"),
    (["95"],          ["장기보유특별공제", "표2"],             "LONG_TERM_DEDUCTION_RATE_TABLE2",     "manual"),
    (["56"],          ["증여세율"],                           "GIFT_TAX_BRACKETS",                   "manual"),
    (["53"],          ["증여재산공제"],                        "GIFT_DEDUCTIONS",                     "manual"),
]


def match_registry_key(threshold: dict) -> tuple[str | None, str | None]:
    """
    추출된 임계값을 레지스트리 키에 매핑한다.
    반환: (registry_key, value_type) — 매핑 불가 시 (None, None).
    """
    article = threshold.get("article", "")
    description = threshold.get("description", "")
    verdict = threshold.get("verdict_affected", "")
    combined = f"{article} {description} {verdict}"

    best_score = 0
    best_key: str | None = None
    best_type: str | None = None

    for art_patterns, desc_keywords, reg_key, val_type in _MAPPING_RULES:
        art_score = sum(1 for p in art_patterns if p in combined)
        if not art_score:
            continue
        desc_score = sum(1 for kw in desc_keywords if kw in combined)
        total = art_score * 10 + desc_score
        if total > best_score:
            best_score = total
            best_key = reg_key
            best_type = val_type

    return best_key, best_type


def convert_value(threshold: dict, value_type: str) -> tuple[Any, bool]:
    """
    threshold의 value를 레지스트리 Python 타입으로 변환.
    반환: (converted_value, can_auto_patch) — manual 이면 (None, False).
    """
    if value_type == "manual":
        return None, False

    raw = threshold.get("value")
    unit = threshold.get("unit", "")

    try:
        if value_type == "price_won":
            return int(raw), True
        elif value_type == "period_years":
            return float(raw) if "." in str(raw) else int(raw), True
        elif value_type == "period_months":
            return int(raw), True
        elif value_type == "rate_decimal":
            v = float(raw) / 100 if unit == "%" else float(raw)
            return round(v, 4), True
        elif value_type == "date_yyyymmdd":
            s = str(int(raw))
            if len(s) == 8:
                return date(int(s[:4]), int(s[4:6]), int(s[6:])), True
            return None, False
    except (TypeError, ValueError, AttributeError):
        return None, False

    return None, False


# ── 2. tax_constants.py 소스 패치 ───────────────────────────────────────────

def _format_value(v: Any) -> str:
    """레지스트리 값을 Python 소스 리터럴로 포맷한다."""
    if isinstance(v, date):
        return f"date({v.year}, {v.month}, {v.day})"
    elif isinstance(v, int):
        # 1억 이상: 조 단위까지 언더스코어
        if v >= 100_000_000:
            return f"{v:_}"
        return str(v)
    elif isinstance(v, float):
        return repr(v)
    return repr(v)


# 레지스트리 소스에서 key의 첫 번째 ConstantVersion(date.max 포함) 블록을 찾는다.
_ACTIVE_CV_PATTERN = re.compile(
    r"( {8}ConstantVersion\(\n"
    r" {12}date\((\d+),\s*(\d+),\s*(\d+)\),\s*date\.max,\n"
    r"( {12}[^\n]+,\n)"          # value line (capture group 5)
    r'( {12}"[^"]+",\n)'         # source_law line (capture group 6)
    r"((?:(?: {12}[^\n]+,\n))*)" # optional extra kwargs (group 7)
    r" {8}\))",
)


def patch_registry_source(
    source: str,
    key: str,
    new_value: Any,
    new_effective_from: date,
    source_law_suffix: str = "",
) -> str:
    """
    레지스트리 소스 텍스트에서 key의 현행 ConstantVersion을 업데이트한다.
      - 현행 버전: effective_to를 (new_effective_from - 1일)로 수정
      - 신규 버전: list 맨 앞에 삽입

    raises ValueError: key 미발견 또는 date.max 버전 미발견.
    """
    # 1. key 블록 시작점 (목록 [ 직전)
    key_marker = f'    "{key}": ['
    key_pos = source.find(key_marker)
    if key_pos == -1:
        raise ValueError(f"Key {key!r} not found in registry source")

    list_open = source.index("[", key_pos)

    # 2. key 블록 내에서만 active ConstantVersion 탐색
    # 블록 끝 찾기 (배열 닫힘 ],)
    depth = 0
    i = list_open
    while i < len(source):
        if source[i] == "[":
            depth += 1
        elif source[i] == "]":
            depth -= 1
            if depth == 0:
                list_close = i  # index of closing ]
                break
        i += 1
    else:
        raise ValueError(f"Unbalanced brackets for key {key!r}")

    block = source[list_open : list_close + 1]

    # 3. active CV 패턴 매칭
    m = _ACTIVE_CV_PATTERN.search(block)
    if not m:
        raise ValueError(
            f"No active ConstantVersion (date.max) found for key {key!r}. "
            "Only simple single-line scalar values are auto-patchable."
        )

    old_year, old_month, old_day = int(m.group(2)), int(m.group(3)), int(m.group(4))
    old_value_line = m.group(5)           # "            OLD_VALUE,\n"
    old_source_law_line = m.group(6)      # "            \"SOURCE_LAW\",\n"
    old_kwargs = m.group(7) or ""         # anchor_key=... etc.

    # 구버전 source_law 추출 (따옴표 내부)
    sl_match = re.search(r'"([^"]+)"', old_source_law_line)
    old_source_law = sl_match.group(1) if sl_match else "소득세법"

    # 신규 source_law: 기존 법령 + suffix 주석
    if source_law_suffix:
        new_source_law = f"{old_source_law} ({source_law_suffix})"
    else:
        new_source_law = old_source_law

    old_effective_to = new_effective_from - timedelta(days=1)
    new_val_line = f"            {_format_value(new_value)},\n"

    # 4. 신규 ConstantVersion 블록 생성
    new_cv = (
        "        ConstantVersion(\n"
        f"            date({new_effective_from.year}, {new_effective_from.month}, {new_effective_from.day}), date.max,\n"
        f"{new_val_line}"
        f'            "{new_source_law}",\n'
        f"{old_kwargs}"
        "        ),\n"
    )

    # 5. 기존 CV: date.max → 구버전 effective_to 로 교체
    old_cv_text = m.group(0)
    updated_old_cv = old_cv_text.replace(
        "date.max",
        f"date({old_effective_to.year}, {old_effective_to.month}, {old_effective_to.day})",
        1,
    )

    # 6. 블록 내 교체: 기존 CV 앞에 신규 CV 삽입
    new_block = block.replace(old_cv_text, new_cv + updated_old_cv, 1)

    return source[:list_open] + new_block + source[list_close + 1:]


# ── 3. 전체 패치 + 검증 + PR ─────────────────────────────────────────────────

def _run_tests() -> bool:
    """드리프트 방지 테스트 실행. 통과 여부 반환."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_no_hardcoded_constants.py", "-q", "--tb=short"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    passed = result.returncode == 0
    if not passed:
        print("  ✗ 테스트 실패:\n" + result.stdout[-2000:])
    return passed


def _git(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git"] + args,
        capture_output=True, text=True, encoding="utf-8", check=check,
    )


def _gh(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["gh"] + args,
        capture_output=True, text=True, encoding="utf-8", check=False,
    )


def run_registry_update_pr(
    thresholds: list[dict],
    law_name: str,
    mst: str,
    effective_date: date,
) -> dict:
    """
    추출된 임계값 목록을 기반으로 TaxConstantsRegistry를 패치하고 PR을 생성한다.

    detect_law_changes.py main() 에서 직접 호출.
    반환: {"pr_url": str | None, "patched": [key, ...], "manual_review": [key, ...]}
    """
    if not thresholds:
        return {"pr_url": None, "patched": [], "manual_review": []}

    print(f"\n  [auto_update_registry] {law_name} MST={mst} 개정일={effective_date}")

    source = REGISTRY_PATH.read_text(encoding="utf-8")
    original_source = source

    patched_keys: list[str] = []
    manual_review_items: list[dict] = []
    skipped: list[dict] = []
    source_law_note = f"{effective_date.year}년 개정"

    for th in thresholds:
        reg_key, val_type = match_registry_key(th)
        if not reg_key:
            skipped.append(th)
            print(f"    ? 매핑 불가: {th.get('article')} {th.get('description')}")
            continue

        if val_type == "manual":
            manual_review_items.append({**th, "registry_key": reg_key})
            print(f"    ⊘ 수동 확인 필요 [{reg_key}]: {th.get('description')}")
            continue

        new_value, can_patch = convert_value(th, val_type)
        if not can_patch or new_value is None:
            manual_review_items.append({**th, "registry_key": reg_key})
            print(f"    ⊘ 값 변환 실패 [{reg_key}]: {th.get('value')} {th.get('unit')}")
            continue

        try:
            source = patch_registry_source(
                source, reg_key, new_value, effective_date, source_law_note
            )
            patched_keys.append(reg_key)
            print(f"    ✓ 패치: [{reg_key}] {th.get('value')} {th.get('unit')} → {new_value!r}")
        except ValueError as e:
            manual_review_items.append({**th, "registry_key": reg_key, "error": str(e)})
            print(f"    ✗ 패치 오류 [{reg_key}]: {e}")

    if not patched_keys:
        print("  → 자동 패치 가능한 항목 없음 (모두 수동 검토 필요)")
        _save_patch_record(thresholds, law_name, mst, effective_date, [], manual_review_items)
        return {"pr_url": None, "patched": [], "manual_review": [i["registry_key"] for i in manual_review_items]}

    # 패치 적용
    REGISTRY_PATH.write_text(source, encoding="utf-8")
    print(f"  ✓ tax_constants.py 패치 완료 ({len(patched_keys)}개 키)")

    # 테스트 검증
    print("  pytest 검증 중...")
    if not _run_tests():
        print("  ⚠ 테스트 실패 — 패치 롤백")
        REGISTRY_PATH.write_text(original_source, encoding="utf-8")
        _save_patch_record(thresholds, law_name, mst, effective_date, [], manual_review_items,
                           error="테스트 실패로 롤백")
        return {"pr_url": None, "patched": [], "manual_review": [i["registry_key"] for i in manual_review_items]}
    print("  ✓ 테스트 통과")

    # PR 생성
    pr_url = _create_pr(
        law_name=law_name,
        mst=mst,
        effective_date=effective_date,
        patched_keys=patched_keys,
        manual_review_items=manual_review_items,
        thresholds=thresholds,
    )

    _save_patch_record(thresholds, law_name, mst, effective_date, patched_keys, manual_review_items,
                       pr_url=pr_url)

    return {
        "pr_url": pr_url,
        "patched": patched_keys,
        "manual_review": [i["registry_key"] for i in manual_review_items],
    }


def _create_pr(
    law_name: str,
    mst: str,
    effective_date: date,
    patched_keys: list[str],
    manual_review_items: list[dict],
    thresholds: list[dict],
) -> str | None:
    """git branch + commit + gh pr create (draft). PR URL 반환."""

    branch = f"chore/registry-update-{law_name[:4]}-{mst}-{effective_date.strftime('%Y%m%d')}"
    branch = re.sub(r"[^\w\-]", "-", branch)

    # 현재 브랜치 저장
    current_branch_r = _git(["rev-parse", "--abbrev-ref", "HEAD"], check=False)
    current_branch = current_branch_r.stdout.strip() if current_branch_r.returncode == 0 else "master"

    try:
        # 이미 존재하는 브랜치면 스킵
        existing = _git(["branch", "--list", branch], check=False)
        if branch in (existing.stdout or ""):
            print(f"  ⚠ 브랜치 이미 존재: {branch} — PR 생성 건너뜀")
            return None

        _git(["checkout", "-b", branch])
        _git(["add", str(REGISTRY_PATH)])

        patched_summary = "\n".join(f"- `{k}`" for k in patched_keys)
        manual_summary = (
            "\n".join(f"- `{i['registry_key']}`: {i.get('description', '')} (수동 확인 필요)"
                      for i in manual_review_items)
            if manual_review_items else "_없음_"
        )
        threshold_detail = "\n".join(
            f"- {t.get('article')} {t.get('description')}: `{t.get('value')}` {t.get('unit')}"
            for t in thresholds
        )

        commit_msg = (
            f"chore: {law_name} 개정 반영 — TaxConstantsRegistry 자동 업데이트\n\n"
            f"법령: {law_name}  MST: {mst}  시행일: {effective_date}\n"
            f"패치 키: {', '.join(patched_keys)}\n\n"
            f"⚠ 이 커밋은 자동 생성입니다. 병합 전 반드시 검토하세요."
        )
        _git(["commit", "-m", commit_msg])

        # gh pr create (draft)
        pr_body = f"""## 법령 개정 자동 감지 — TaxConstantsRegistry 업데이트

**법령:** {law_name}
**MST:** {mst}
**시행일:** {effective_date}
**감지 시각:** 자동 감지

---

### 추출된 임계값

{threshold_detail}

---

### 자동 패치된 레지스트리 키

{patched_summary}

### 수동 확인 필요 (auto-patch 불가)

{manual_summary}

---

### 검증

- [x] `tests/test_no_hardcoded_constants.py` 전체 통과
- [ ] 수동 확인 필요 항목 검토
- [ ] 골든셋 재실행: `python -m scripts.eval.run_baseline_eval --workers 3`
- [ ] 프롬프트 내 수치 변경 반영 확인

> ⚠ 이 PR은 자동 생성입니다. **병합 전 반드시 세무사 또는 담당자가 검토해야 합니다.**
> `manual_review_required` 항목은 별표 이미지 또는 복합 구조체이므로 별도 확인 필요.
"""

        r = _gh([
            "pr", "create",
            "--draft",
            "--title", f"chore: {law_name} 개정 반영 — TaxConstantsRegistry 자동 업데이트 (MST={mst})",
            "--body", pr_body,
            "--base", current_branch,
            "--head", branch,
        ])

        if r.returncode == 0:
            pr_url = r.stdout.strip()
            print(f"  ✓ PR 생성 (draft): {pr_url}")
            return pr_url
        else:
            print(f"  ⚠ PR 생성 실패: {r.stderr.strip()}")
            # 브랜치는 남겨둠 — 수동 PR 가능
            return None

    except Exception as e:
        print(f"  ⚠ PR 생성 중 오류: {e}")
        return None
    finally:
        # 원래 브랜치로 복귀
        _git(["checkout", current_branch], check=False)


def _save_patch_record(
    thresholds: list[dict],
    law_name: str,
    mst: str,
    effective_date: date,
    patched_keys: list[str],
    manual_review_items: list[dict],
    pr_url: str | None = None,
    error: str | None = None,
) -> None:
    """패치 결과를 data/registry_patches/ 에 저장한다."""
    PATCHES_DIR.mkdir(parents=True, exist_ok=True)
    ts = effective_date.strftime("%Y%m%d")
    out_path = PATCHES_DIR / f"patch_{law_name[:4]}_{mst}_{ts}.json"
    out_path.write_text(
        json.dumps({
            "law_name": law_name,
            "mst": mst,
            "effective_date": str(effective_date),
            "thresholds": thresholds,
            "patched_keys": patched_keys,
            "manual_review_keys": [i["registry_key"] for i in manual_review_items],
            "manual_review_items": manual_review_items,
            "pr_url": pr_url,
            "error": error,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"  패치 기록 저장: {out_path}")


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="TaxConstantsRegistry 자동 업데이트 + PR 생성")
    parser.add_argument("--law", required=True, help="법령명 (예: 소득세법)")
    parser.add_argument("--mst", required=True, help="MST 번호")
    parser.add_argument("--effective", required=True, help="시행일 YYYYMMDD")
    parser.add_argument("--thresholds-file", help="임계값 JSON 파일 경로 (없으면 --law/--mst로 재추출)")
    parser.add_argument("--dry-run", action="store_true", help="패치 및 PR 생성 없이 매핑 결과만 출력")
    args = parser.parse_args()

    sys.stdout.reconfigure(encoding="utf-8")

    s = args.effective
    effective_date = date(int(s[:4]), int(s[4:6]), int(s[6:]))

    if args.thresholds_file:
        thresholds = json.loads(Path(args.thresholds_file).read_text(encoding="utf-8"))
    else:
        from src.ingestion.collect import fetch_law_xml
        from scripts.ingestion.generate_amendment_cases import extract_thresholds
        print(f"XML 수집 중: {args.law} MST={args.mst}")
        xml_text = fetch_law_xml(args.mst)
        thresholds = extract_thresholds(xml_text, args.law)

    if not thresholds:
        print("추출된 임계값 없음.")
        return

    print(f"\n추출된 임계값 {len(thresholds)}개:")
    for th in thresholds:
        key, vtype = match_registry_key(th)
        print(f"  {th.get('article')} {th.get('description')} = {th.get('value')} {th.get('unit')}"
              f"  → [{key or '매핑불가'}, {vtype}]")

    if args.dry_run:
        print("\n[dry-run] 패치/PR 생성 생략")
        return

    result = run_registry_update_pr(thresholds, args.law, args.mst, effective_date)
    print(f"\n결과: 패치={result['patched']} | 수동={result['manual_review']} | PR={result['pr_url']}")


if __name__ == "__main__":
    main()
