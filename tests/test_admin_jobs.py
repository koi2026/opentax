from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from src.api.admin_jobs import list_admin_commands
from src.api.main import app
import src.api.routes.admin as admin_routes


def test_admin_commands_exclude_eval_but_include_automation() -> None:
    commands = list_admin_commands()
    text = "\n".join(
        " ".join(str(value) for value in command.values())
        for command in commands
    )
    command_keys = {command["key"] for command in commands}

    assert "scripts.run_golden_eval" not in text
    assert "scripts.run_baseline_eval" not in text
    assert "scripts.finetune_reranker" not in text
    assert "law_changes" not in command_keys
    assert "rulings_incremental" in command_keys
    assert "law_changes_embed" in command_keys
    assert {command["phase"] for command in commands} == {"collect", "upload", "automation"}


def test_admin_create_job_accepts_valid_command(monkeypatch) -> None:
    def fake_start(command_key: str, confirm_paid: bool = False):
        return {
            "job_id": "job-1",
            "command_key": command_key,
            "status": "running",
            "confirm_paid": confirm_paid,
        }

    monkeypatch.setattr(admin_routes, "start_admin_job", fake_start)
    client = TestClient(app)

    response = client.post("/api/v1/admin/jobs", json={"command_key": "law_collect"})

    assert response.status_code == 202
    assert response.json()["job_id"] == "job-1"
    assert response.json()["command_key"] == "law_collect"


def test_admin_paid_command_requires_confirmation() -> None:
    client = TestClient(app)

    response = client.post("/api/v1/admin/jobs", json={"command_key": "law_embed", "confirm_paid": False})

    assert response.status_code == 403


def test_admin_rejects_unknown_command() -> None:
    client = TestClient(app)

    response = client.post("/api/v1/admin/jobs", json={"command_key": "scripts.run_baseline_eval"})

    assert response.status_code == 404


def test_admin_rejects_concurrent_job(monkeypatch) -> None:
    def fake_start(command_key: str, confirm_paid: bool = False):
        raise RuntimeError("already-running")

    monkeypatch.setattr(admin_routes, "start_admin_job", fake_start)
    client = TestClient(app)

    response = client.post("/api/v1/admin/jobs", json={"command_key": "law_collect"})

    assert response.status_code == 409


def test_admin_page_removed_eval_ui_text() -> None:
    text = Path("src/pages/admin.py").read_text(encoding="utf-8")
    banned = [
        "평가 현황",
        "Baseline",
        "Debate",
        "Reranker 파인튜닝",
        "scripts.run_golden_eval",
        "scripts.run_baseline_eval",
        "scripts.finetune_reranker",
    ]

    assert [item for item in banned if item in text] == []
    assert "통합 자동화" in text
