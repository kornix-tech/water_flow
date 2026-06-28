from __future__ import annotations

import re
import uuid
import zipfile
from pathlib import Path

from fastapi import HTTPException

from .config import Settings


RUN_NAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$")
def safe_resolve_under(base_dir: Path, user_path: str) -> Path:
    if not user_path:
        raise HTTPException(status_code=400, detail="Empty path is not allowed")
    candidate = Path(user_path)
    if candidate.is_absolute():
        raise HTTPException(status_code=400, detail="Absolute paths are not allowed")
    resolved_base = base_dir.resolve()
    resolved = (resolved_base / candidate).resolve()
    if resolved != resolved_base and resolved_base not in resolved.parents:
        raise HTTPException(status_code=403, detail="Path escapes allowed directory")
    return resolved


def safe_run_name(run_name: str) -> str:
    if not run_name or ".." in run_name or not RUN_NAME_RE.fullmatch(run_name):
        raise HTTPException(status_code=400, detail="Invalid run name")
    return run_name


def is_safe_child_file(base_dir: Path, path: Path) -> bool:
    if path.is_symlink() or not path.is_file():
        return False
    resolved_base = base_dir.resolve()
    resolved_path = path.resolve()
    return resolved_path == resolved_base or resolved_base in resolved_path.parents


def safe_child_file(base_dir: Path, user_path: str, *, max_bytes: int | None = None) -> Path:
    candidate = Path(user_path)
    if candidate.is_absolute():
        raise HTTPException(status_code=400, detail="Absolute paths are not allowed")
    cursor = base_dir.resolve()
    for part in candidate.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise HTTPException(status_code=404, detail="File was not found")
    path = safe_resolve_under(base_dir, user_path)
    if not is_safe_child_file(base_dir, path):
        raise HTTPException(status_code=404, detail="File was not found")
    if max_bytes is not None and path.stat().st_size > max_bytes:
        raise HTTPException(status_code=413, detail="File is too large")
    return path


_is_safe_child_file = is_safe_child_file


class FileManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def workspace_file(self, user_path: str) -> Path:
        return safe_resolve_under(self.settings.workspace, user_path)

    def run_dir(self, run_name: str) -> Path:
        return safe_resolve_under(self.settings.runs_dir, safe_run_name(run_name))

    def plots_dir(self, run_name: str) -> Path:
        return self.run_dir(run_name) / "plots"

    def list_files(self, base_dir: Path, max_depth: int = 2) -> list[dict[str, object]]:
        base = base_dir.resolve()
        if not base.exists():
            return []
        items: list[dict[str, object]] = []
        for path in sorted(base.rglob("*")):
            if path.is_symlink():
                continue
            relative = path.relative_to(base)
            if len(relative.parts) > max_depth:
                continue
            if path.is_file() and not _is_safe_child_file(base, path):
                continue
            items.append(
                {
                    "path": relative.as_posix(),
                    "name": path.name,
                    "size": path.stat().st_size if path.is_file() else 0,
                    "is_dir": path.is_dir(),
                }
            )
        return items

    def list_relative_files(self, base_dir: Path, max_files: int = 500) -> list[str]:
        base = base_dir.resolve()
        if not base.exists():
            return []
        files: list[str] = []
        for path in sorted(base.rglob("*")):
            if not _is_safe_child_file(base, path):
                continue
            files.append(path.relative_to(base).as_posix())
            if len(files) >= max_files:
                break
        return files

    def make_run_zip(self, run_name: str) -> Path:
        run_dir = self.run_dir(run_name)
        if not run_dir.exists():
            raise HTTPException(status_code=404, detail="Run directory was not found")
        archive_path = self.settings.archives_dir / f"{run_name}.zip"
        tmp_archive_path = self.settings.tmp_dir / f"{uuid.uuid4().hex}.zip"
        excluded_parts = {"__pycache__"}
        excluded_suffixes = {".tmp", ".cache"}
        total_size = 0
        file_count = 0
        with zipfile.ZipFile(tmp_archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(run_dir.rglob("*")):
                if not _is_safe_child_file(run_dir, path):
                    continue
                relative = path.relative_to(run_dir)
                if any(part in excluded_parts for part in relative.parts):
                    continue
                if path.suffix in excluded_suffixes:
                    continue
                total_size += path.stat().st_size
                file_count += 1
                if total_size > self.settings.max_archive_bytes or file_count > self.settings.max_archive_files:
                    tmp_archive_path.unlink(missing_ok=True)
                    raise HTTPException(status_code=413, detail="Run archive is too large")
                archive.write(path, relative.as_posix())
        tmp_archive_path.replace(archive_path)
        return archive_path
