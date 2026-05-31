from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request

from ..schemas import SystemInfo

router = APIRouter()


@router.get("/info", response_model=SystemInfo)
def system_info(request: Request) -> SystemInfo:
    settings = request.app.state.settings
    frontend_dist = Path(settings.soilflow_home) / "web" / "frontend" / "dist"
    return SystemInfo(
        soilflow_home=str(settings.soilflow_home),
        workspace=str(settings.workspace),
        pflotran_exe=str(settings.pflotran_exe),
        pflotran_exists=settings.pflotran_exe.exists(),
        job_workers=settings.job_workers,
        auth_mode=settings.auth_mode,
        frontend_available=frontend_dist.exists(),
        api_docs_enabled=settings.enable_api_docs,
        hsts_enabled=settings.enable_hsts,
        api_rate_limit_per_minute=settings.api_rate_limit_per_minute,
    )
