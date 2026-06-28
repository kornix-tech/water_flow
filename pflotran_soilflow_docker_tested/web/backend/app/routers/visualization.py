from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from ..file_manager import safe_child_file

router = APIRouter()

MAX_VISUALIZATION_HTML_BYTES = 100 * 1024 * 1024
MAX_VISUALIZATION_STATUS_BYTES = 2 * 1024 * 1024

VISUALIZATION_CSP = (
    "sandbox allow-scripts allow-downloads; "
    "default-src 'self' 'unsafe-inline' data: blob:; "
    "script-src 'self' 'unsafe-inline' data: blob:; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:"
)


@router.get("/{run_name}/html")
def visualization_html(run_name: str, request: Request):
    try:
        html_path = safe_child_file(
            request.app.state.file_manager.plots_dir(run_name),
            "profiles_animation.html",
            max_bytes=MAX_VISUALIZATION_HTML_BYTES,
        )
    except HTTPException as exc:
        if exc.status_code == 404:
            raise HTTPException(status_code=404, detail="Visualization HTML was not found") from exc
        raise
    return FileResponse(html_path, media_type="text/html", headers={"Content-Security-Policy": VISUALIZATION_CSP})


@router.get("/{run_name}/status")
def visualization_status(run_name: str, request: Request):
    try:
        status_path = safe_child_file(
            request.app.state.file_manager.plots_dir(run_name),
            "VISUALIZATION_STATUS.txt",
            max_bytes=MAX_VISUALIZATION_STATUS_BYTES,
        )
    except HTTPException as exc:
        if exc.status_code == 404:
            raise HTTPException(status_code=404, detail="Visualization status was not found") from exc
        raise
    return FileResponse(status_path, media_type="text/plain")
