from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from ..services.archive_service import build_run_archive

router = APIRouter()

PUBLIC_WORKSPACE_ROOTS = {
    ("input",),
    ("uploads",),
    ("output", "runs"),
}


def _file_manager(request: Request):
    return request.app.state.file_manager


def _is_public_workspace_path(path: str) -> bool:
    if "\\" in path:
        return False
    parts = Path(path).parts
    return any(parts[: len(root)] == root for root in PUBLIC_WORKSPACE_ROOTS)


@router.get("/download-zip/{run_id}")
def download_zip(run_id: str, request: Request):
    archive = build_run_archive(_file_manager(request), run_id)
    return FileResponse(archive, filename=archive.name, media_type="application/zip")


@router.get("/{path:path}")
def get_workspace_file(path: str, request: Request):
    if not _is_public_workspace_path(path):
        raise HTTPException(status_code=403, detail="Workspace file is not public")
    target = _file_manager(request).workspace_file(path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File was not found")
    return FileResponse(target, filename=Path(target).name)
