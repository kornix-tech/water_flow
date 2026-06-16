from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from ..schemas import HealthResponse, ReadinessResponse

router = APIRouter()


@router.get("", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="soilflow-pflotran-web")


@router.get("/ready", response_model=ReadinessResponse)
def readiness(request: Request):
    settings = request.app.state.settings
    frontend_dist = Path(settings.soilflow_home) / "web" / "frontend" / "dist"
    checks: dict[str, bool] = {
        "pflotran_exe": settings.pflotran_exe.exists(),
        "workspace": settings.workspace.exists() and settings.workspace.is_dir(),
        "frontend_dist": frontend_dist.exists() and frontend_dist.is_dir(),
    }
    details: dict[str, str] = {}
    schema_version: int | None = None

    try:
        settings.tmp_dir.mkdir(parents=True, exist_ok=True)
        probe_path = settings.tmp_dir / ".soilflow_readiness_probe"
        probe_path.write_text("ok", encoding="utf-8")
        probe_path.unlink(missing_ok=True)
        checks["tmp_writable"] = True
    except OSError as exc:
        checks["tmp_writable"] = False
        details["tmp_writable"] = str(exc)

    try:
        request.app.state.job_store.ping()
        schema_version = request.app.state.job_store.schema_version()
        checks["database"] = schema_version > 0
    except Exception as exc:
        checks["database"] = False
        details["database"] = str(exc)

    response = ReadinessResponse(
        status="ready" if all(checks.values()) else "not_ready",
        service="soilflow-pflotran-web",
        checks=checks,
        details=details,
        schema_version=schema_version,
    )
    if response.status == "ready":
        return response
    return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=response.model_dump())
