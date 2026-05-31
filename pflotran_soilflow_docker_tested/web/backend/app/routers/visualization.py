from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from ..file_manager import safe_resolve_under

router = APIRouter()

VISUALIZATION_CSP = (
    "sandbox allow-scripts allow-downloads; "
    "default-src 'self' 'unsafe-inline' data: blob:; "
    "script-src 'self' 'unsafe-inline' data: blob:; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:"
)


@router.get("/{run_name}/html")
def visualization_html(run_name: str, request: Request):
    html_path = safe_resolve_under(request.app.state.file_manager.plots_dir(run_name), "profiles_animation.html")
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Visualization HTML was not found")
    return FileResponse(html_path, media_type="text/html", headers={"Content-Security-Policy": VISUALIZATION_CSP})


@router.get("/{run_name}/status")
def visualization_status(run_name: str, request: Request):
    status_path = safe_resolve_under(request.app.state.file_manager.plots_dir(run_name), "VISUALIZATION_STATUS.txt")
    if not status_path.exists():
        raise HTTPException(status_code=404, detail="Visualization status was not found")
    return FileResponse(status_path, media_type="text/plain")
