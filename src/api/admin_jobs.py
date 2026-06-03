"""Admin command job runner.

Only commands declared in ``ADMIN_COMMANDS`` can be started from the API.
"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
JOBS_DIR = ROOT / "data" / "admin_jobs"
DEFAULT_TIMEOUT_S = 1800
LOG_TAIL_LINES = 300


@dataclass(frozen=True)
class AdminCommand:
    key: str
    label: str
    description: str
    args: list[str]
    path: str
    phase: str
    group: str
    namespace: str | None = None
    paid: bool = False
    long: bool = False
    timeout_s: int = DEFAULT_TIMEOUT_S

    @property
    def command_text(self) -> str:
        return " ".join(["python", "-m", *self.args])


ADMIN_COMMANDS: dict[str, AdminCommand] = {
    "law_collect": AdminCommand(
        key="law_collect",
        label="법령 조문 수집",
        description="law.go.kr DRF API에서 법령 XML을 수집하고 로컬 청크 파일을 갱신합니다.",
        args=["src.ingestion.collect"],
        path="data/processed/all_chunks.json",
        phase="collect",
        group="법령 조문",
    ),
    "ruling_revision": AdminCommand(
        key="ruling_revision",
        label="폐지 예규 목록 수집",
        description="세법해석정비 목록을 수집해 폐지 예규 필터의 원천 데이터를 갱신합니다.",
        args=["src.ingestion.collect_rulings_revision", "--tax", "transfer"],
        path="data/rulings/deprecated_ids.json",
        phase="collect",
        group="유권해석 개별 수집",
    ),
    "ruling_nts": AdminCommand(
        key="ruling_nts",
        label="국세청 질의회신 수집",
        description="양도소득세 질의회신/쟁점별 사례를 resume 모드로 수집합니다.",
        args=["src.ingestion.collect_rulings_nts", "--tax", "양도소득세", "--resume"],
        path="data/rulings/nts",
        phase="collect",
        group="유권해석 개별 수집",
    ),
    "ruling_decisions": AdminCommand(
        key="ruling_decisions",
        label="심판청구 결정례 수집",
        description="조세심판원 결정례를 양도 키워드로 수집합니다.",
        args=["src.ingestion.collect_rulings_decisions", "--type", "tax_tribunal", "--keyword", "양도", "--resume"],
        path="data/rulings/decisions",
        phase="collect",
        group="유권해석 개별 수집",
    ),
    "ruling_moef": AdminCommand(
        key="ruling_moef",
        label="기재부 법령해석 수집",
        description="기재부 법령해석 목록을 resume 모드로 수집합니다.",
        args=["src.ingestion.collect_rulings_moef", "--resume", "--no-detail"],
        path="data/rulings/moef",
        phase="collect",
        group="유권해석 개별 수집",
    ),
    "ruling_nts_interp": AdminCommand(
        key="ruling_nts_interp",
        label="국세청 법령해석 수집",
        description="양도·증여·상속·상생임대·임대주택 키워드의 법령해석을 수집합니다.",
        args=[
            "src.ingestion.collect_rulings_nts_interp",
            "--keywords",
            "양도",
            "증여",
            "상속",
            "상생임대",
            "임대주택",
            "--resume",
            "--no-detail",
        ],
        path="data/rulings/nts_interp",
        phase="collect",
        group="유권해석 개별 수집",
        long=True,
    ),
    "pdf_collect": AdminCommand(
        key="pdf_collect",
        label="PDF 집행기준 파싱",
        description="data/rulings/pdf_source의 PDF를 로컬 JSON 레코드로 파싱합니다. Pinecone 업로드는 하지 않습니다.",
        args=["src.ingestion.collect_rulings_pdf"],
        path="data/rulings/pdf",
        phase="collect",
        group="PDF/행정 데이터 수집",
    ),
    "admin_notices": AdminCommand(
        key="admin_notices",
        label="행정 고시 수집",
        description="규제지역 관련 행정/금융 고시 데이터를 갱신합니다.",
        args=["src.ingestion.admin_notices"],
        path="data/area_designations",
        phase="collect",
        group="PDF/행정 데이터 수집",
    ),
    "regulatory_changes": AdminCommand(
        key="regulatory_changes",
        label="규제지역 변경 감지",
        description="규제지역 변경 후보를 감지해 인박스에 기록합니다.",
        args=["scripts.detect_regulatory_changes"],
        path="data/area_designations/detection_inbox.json",
        phase="collect",
        group="PDF/행정 데이터 수집",
    ),
    "law_embed": AdminCommand(
        key="law_embed",
        label="법령 조문 임베딩/Pinecone 업로드",
        description="data/processed/all_chunks.json을 임베딩하고 Pinecone tax-law 네임스페이스에 업로드합니다.",
        args=["src.ingestion.embed"],
        path="data/processed/all_chunks.json",
        namespace="tax-law",
        phase="upload",
        group="법령 조문 업로드",
        paid=True,
    ),
    "embed_nts": AdminCommand(
        key="embed_nts",
        label="국세청 질의회신 임베딩/Pinecone 업로드",
        description="국세청 질의회신을 임베딩하고 Pinecone에 업로드합니다.",
        args=["src.ingestion.embed_rulings", "nts"],
        path="data/rulings/nts",
        namespace="tax-ruling-nts",
        phase="upload",
        group="유권해석 개별 업로드",
        paid=True,
    ),
    "embed_decisions": AdminCommand(
        key="embed_decisions",
        label="심판청구 결정례 임베딩/Pinecone 업로드",
        description="결정례 데이터를 임베딩하고 Pinecone에 업로드합니다.",
        args=["src.ingestion.embed_rulings", "decisions"],
        path="data/rulings/decisions",
        namespace="tax-ruling-decisions",
        phase="upload",
        group="유권해석 개별 업로드",
        paid=True,
    ),
    "embed_moef": AdminCommand(
        key="embed_moef",
        label="기재부 법령해석 임베딩/Pinecone 업로드",
        description="기재부 법령해석을 임베딩하고 Pinecone에 업로드합니다.",
        args=["src.ingestion.embed_rulings", "moef"],
        path="data/rulings/moef",
        namespace="tax-ruling-moef",
        phase="upload",
        group="유권해석 개별 업로드",
        paid=True,
    ),
    "embed_nts_interp": AdminCommand(
        key="embed_nts_interp",
        label="국세청 법령해석 임베딩/Pinecone 업로드",
        description="국세청 법령해석을 임베딩하고 Pinecone에 업로드합니다.",
        args=["src.ingestion.embed_rulings", "nts_interp"],
        path="data/rulings/nts_interp",
        namespace="tax-ruling-nts-interp",
        phase="upload",
        group="유권해석 개별 업로드",
        paid=True,
    ),
    "embed_pdf": AdminCommand(
        key="embed_pdf",
        label="PDF 집행기준 임베딩/Pinecone 업로드",
        description="PDF 집행기준을 임베딩하고 Pinecone에 업로드합니다.",
        args=["src.ingestion.embed_rulings", "pdf"],
        path="data/rulings/pdf",
        namespace="tax-ruling-pdf",
        phase="upload",
        group="유권해석 개별 업로드",
        paid=True,
    ),
    "rulings_incremental": AdminCommand(
        key="rulings_incremental",
        label="유권해석 증분 수집 + 신규 임베딩/Pinecone 업로드",
        description="수집 후 신규 파일이 있으면 임베딩까지 수행합니다. 신규 데이터가 없으면 업로드를 생략합니다.",
        args=["scripts.collect_and_embed_rulings"],
        path="data/rulings",
        phase="automation",
        group="수집+업로드 통합 자동화",
        paid=True,
        long=True,
    ),
    "law_changes_embed": AdminCommand(
        key="law_changes_embed",
        label="법령 개정 감지 + 신규 법령 Pinecone 업로드",
        description="개정 감지 후 신규 법령을 수집하고 Pinecone까지 업로드합니다.",
        args=["scripts.detect_law_changes", "--embed"],
        path="data/law_change_log.jsonl",
        namespace="tax-law",
        phase="automation",
        group="수집+업로드 통합 자동화",
        paid=True,
    ),
}

_running_job_id: str | None = None
_lock = threading.Lock()


def list_admin_commands() -> list[dict[str, Any]]:
    return [asdict(command) | {"command_text": command.command_text} for command in ADMIN_COMMANDS.values()]


def _job_path(job_id: str) -> Path:
    return JOBS_DIR / f"{job_id}.json"


def _save_job(job: dict[str, Any]) -> None:
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    _job_path(job["job_id"]).write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_job(job_id: str) -> dict[str, Any] | None:
    path = _job_path(job_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _append_log(job: dict[str, Any], line: str) -> None:
    log_lines = job.setdefault("log_lines", [])
    log_lines.append(line)
    if len(log_lines) > LOG_TAIL_LINES:
        job["log_lines"] = log_lines[-LOG_TAIL_LINES:]


def start_admin_job(command_key: str, confirm_paid: bool = False) -> dict[str, Any]:
    command = ADMIN_COMMANDS.get(command_key)
    if command is None:
        raise KeyError(command_key)
    if command.paid and not confirm_paid:
        raise PermissionError(command_key)

    global _running_job_id
    with _lock:
        if _running_job_id is not None:
            running = _load_job(_running_job_id)
            if running and running.get("status") == "running":
                raise RuntimeError(_running_job_id)
            _running_job_id = None

        job_id = uuid.uuid4().hex[:12]
        now = datetime.now().isoformat()
        job = {
            "job_id": job_id,
            "command_key": command.key,
            "label": command.label,
            "cmd": command.command_text,
            "args": command.args,
            "status": "running",
            "started_at": now,
            "finished_at": None,
            "elapsed_s": 0.0,
            "returncode": None,
            "timed_out": False,
            "log_lines": [f"$ {command.command_text}"],
        }
        _save_job(job)
        _running_job_id = job_id

    thread = threading.Thread(target=_run_job_thread, args=(job_id, command), daemon=True)
    thread.start()
    return job


def get_admin_job(job_id: str) -> dict[str, Any] | None:
    return _load_job(job_id)


def _run_job_thread(job_id: str, command: AdminCommand) -> None:
    global _running_job_id
    t0 = time.monotonic()
    job = _load_job(job_id)
    if job is None:
        return

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    process: subprocess.Popen[str] | None = None
    try:
        process = subprocess.Popen(
            [sys.executable, "-m", *command.args],
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
        )
        assert process.stdout is not None
        output_queue: queue.Queue[str | None] = queue.Queue()

        def _read_output() -> None:
            try:
                assert process is not None and process.stdout is not None
                for output_line in process.stdout:
                    output_queue.put(output_line.rstrip("\n"))
            finally:
                output_queue.put(None)

        threading.Thread(target=_read_output, daemon=True).start()
        reader_done = False
        while True:
            if time.monotonic() - t0 > command.timeout_s:
                job["timed_out"] = True
                _append_log(job, f"명령이 {command.timeout_s}초 제한을 초과해 중단되었습니다.")
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                break

            updated = False
            while True:
                try:
                    line = output_queue.get_nowait()
                except queue.Empty:
                    break
                if line is None:
                    reader_done = True
                    continue
                _append_log(job, line)
                updated = True

            if updated:
                job["elapsed_s"] = time.monotonic() - t0
                _save_job(job)

            if process.poll() is not None and reader_done:
                break
            time.sleep(0.1)

        while True:
            try:
                line = output_queue.get_nowait()
            except queue.Empty:
                break
            if line is not None:
                _append_log(job, line)

        returncode = process.returncode if process.returncode is not None else -1
        if job.get("timed_out"):
            returncode = -1
        job["returncode"] = returncode
        job["status"] = "succeeded" if returncode == 0 else "failed"
    except Exception as exc:
        job["returncode"] = -1
        job["status"] = "failed"
        _append_log(job, f"실행 오류: {exc}")
    finally:
        job["finished_at"] = datetime.now().isoformat()
        job["elapsed_s"] = time.monotonic() - t0
        _save_job(job)
        with _lock:
            if _running_job_id == job_id:
                _running_job_id = None
