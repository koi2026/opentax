"""Admin operation routes."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.api.admin_jobs import get_admin_job, list_admin_commands, start_admin_job


router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


class AdminJobRequest(BaseModel):
    command_key: str
    confirm_paid: bool = False


@router.get("/commands")
def admin_commands() -> dict[str, list[dict[str, Any]]]:
    return {"commands": list_admin_commands()}


@router.post("/jobs", status_code=202)
def create_admin_job(req: AdminJobRequest) -> dict[str, Any]:
    try:
        return start_admin_job(req.command_key, confirm_paid=req.confirm_paid)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="unknown command_key") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="paid command requires confirm_paid=true") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=f"admin job already running: {exc}") from exc


@router.get("/jobs/{job_id}")
def admin_job(job_id: str) -> dict[str, Any]:
    job = get_admin_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job
