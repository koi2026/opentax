"""
유권해석·예규·결정례 증분 수집 + 신규 파일이 있을 때만 임베딩.

스케줄: 매일 02:00 (setup_scheduler.ps1에서 등록)

동작:
  1. 각 수집기를 --resume 모드로 실행 (이미 저장된 파일 스킵 → 무료)
  2. 수집 전후 파일 수 비교
  3. 신규 파일이 1건 이상이면 해당 namespace만 embed_rulings 실행 (유료 API)
  4. 신규 없으면 임베딩 생략

비용 절감: 신규 예규가 없는 날 임베딩 API 비용 0원
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

NTS_DIR           = PROJECT_ROOT / "data" / "rulings" / "nts"
DECISIONS_DIR     = PROJECT_ROOT / "data" / "rulings" / "decisions"
PDF_DIR           = PROJECT_ROOT / "data" / "rulings" / "pdf"
MOEF_DIR          = PROJECT_ROOT / "data" / "rulings" / "moef"
NTS_INTERP_DIR    = PROJECT_ROOT / "data" / "rulings" / "nts_interp"

COLLECT_TASKS = [
    {
        "label": "NTS 질의회신",
        "cmd": [sys.executable, "-m", "src.ingestion.collect_rulings_nts",
                "--tax", "양도소득세", "--resume"],
        "dir": NTS_DIR,
        "embed_source": "nts",
    },
    {
        "label": "결정례·판례",
        "cmd": [sys.executable, "-m", "src.ingestion.collect_rulings_decisions",
                "--type", "tax_tribunal", "--keyword", "양도", "--resume"],
        "dir": DECISIONS_DIR,
        "embed_source": "decisions",
    },
    {
        "label": "기재부 법령해석",
        "cmd": [sys.executable, "-m", "src.ingestion.collect_rulings_moef",
                "--resume", "--no-detail"],
        "dir": MOEF_DIR,
        "embed_source": "moef",
    },
    {
        "label": "국세청 법령해석 (양도·증여·상속·상생임대·임대주택)",
        "cmd": [sys.executable, "-m", "src.ingestion.collect_rulings_nts_interp",
                "--keywords", "양도", "증여", "상속", "상생임대", "임대주택", "--resume", "--no-detail"],
        "dir": NTS_INTERP_DIR,
        "embed_source": "nts_interp",
    },
]


def _count_files(directory: Path) -> int:
    if not directory.exists():
        return 0
    return sum(1 for _ in directory.glob("*.json"))


def _run(cmd: list[str], label: str) -> bool:
    print(f"\n[{label}] 실행: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        print(f"[{label}] 오류 (exit {result.returncode}) — 임베딩 생략")
        return False
    return True


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    print("=== 유권해석 증분 수집 ===")

    sources_to_embed: list[str] = []

    for task in COLLECT_TASKS:
        before = _count_files(task["dir"])
        ok = _run(task["cmd"], task["label"])
        if not ok:
            continue
        after = _count_files(task["dir"])
        new_count = after - before
        if new_count > 0:
            print(f"  [{task['label']}] 신규 {new_count}건 → 임베딩 예약")
            sources_to_embed.append(task["embed_source"])
        else:
            print(f"  [{task['label']}] 신규 없음 — 임베딩 생략 (비용 절감)")

    if sources_to_embed:
        print(f"\n=== 임베딩 시작: {sources_to_embed} ===")
        for source in sources_to_embed:
            embed_cmd = [sys.executable, "-m", "src.ingestion.embed_rulings", source]
            _run(embed_cmd, f"embed:{source}")
    else:
        print("\n신규 데이터 없음 — 임베딩 전체 생략")

    print("\n=== 완료 ===")


if __name__ == "__main__":
    main()
