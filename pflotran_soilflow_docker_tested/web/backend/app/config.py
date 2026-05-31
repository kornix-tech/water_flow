from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path


def _int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < minimum or value > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _bool_env(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    soilflow_home: Path
    workspace: Path
    pflotran_exe: Path
    port: int
    job_workers: int
    auth_mode: str
    api_token: str | None
    max_archive_bytes: int
    max_archive_files: int
    job_timeout_seconds: int | None
    api_rate_limit_per_minute: int
    max_json_body_bytes: int
    enable_api_docs: bool
    enable_hsts: bool

    @property
    def scripts_dir(self) -> Path:
        return self.soilflow_home / "scripts"

    @property
    def docs_dir(self) -> Path:
        return self.soilflow_home / "docs"

    @property
    def bundled_input_dir(self) -> Path:
        return self.soilflow_home / "input"

    @property
    def input_dir(self) -> Path:
        return self.workspace / "input"

    @property
    def output_dir(self) -> Path:
        return self.workspace / "output"

    @property
    def runs_dir(self) -> Path:
        return self.output_dir / "runs"

    @property
    def uploads_dir(self) -> Path:
        return self.workspace / "uploads"

    @property
    def jobs_dir(self) -> Path:
        return self.workspace / "jobs"

    @property
    def archives_dir(self) -> Path:
        return self.workspace / "archives"

    @property
    def tmp_dir(self) -> Path:
        return self.workspace / "tmp"

    @property
    def database_path(self) -> Path:
        return self.workspace / "jobs.sqlite"

    @property
    def default_input_json(self) -> Path:
        return self.input_dir / "soilflow_pflotran_demo.json"


def load_settings() -> Settings:
    auth_mode = os.getenv("SOILFLOW_AUTH_MODE", "none").lower()
    if auth_mode not in {"none", "token"}:
        raise ValueError("SOILFLOW_AUTH_MODE must be 'none' or 'token'")
    api_token = os.getenv("SOILFLOW_API_TOKEN") or None
    if auth_mode == "token" and not api_token:
        raise ValueError("SOILFLOW_API_TOKEN is required when SOILFLOW_AUTH_MODE=token")
    timeout_seconds = _int_env("SOILFLOW_JOB_TIMEOUT_SECONDS", 21_600, 0, 604_800)
    return Settings(
        soilflow_home=Path(os.getenv("SOILFLOW_HOME", "/opt/soilflow")).resolve(),
        workspace=Path(os.getenv("SOILFLOW_WORKSPACE", "/workspace")).resolve(),
        pflotran_exe=Path(os.getenv("PFLOTRAN_EXE", "/opt/pflotran/src/pflotran/pflotran")).resolve(),
        port=_int_env("PORT", 8080, 1, 65_535),
        job_workers=_int_env("JOB_WORKERS", 1, 1, 32),
        auth_mode=auth_mode,
        api_token=api_token,
        max_archive_bytes=_int_env("SOILFLOW_MAX_ARCHIVE_MB", 2048, 1, 10240) * 1024 * 1024,
        max_archive_files=_int_env("SOILFLOW_MAX_ARCHIVE_FILES", 20_000, 1, 200_000),
        job_timeout_seconds=timeout_seconds if timeout_seconds > 0 else None,
        api_rate_limit_per_minute=_int_env("SOILFLOW_API_RATE_LIMIT_PER_MINUTE", 120, 1, 10_000),
        max_json_body_bytes=_int_env("SOILFLOW_MAX_JSON_BODY_KB", 512, 1, 10_240) * 1024,
        enable_api_docs=_bool_env("SOILFLOW_ENABLE_API_DOCS", False),
        enable_hsts=_bool_env("SOILFLOW_ENABLE_HSTS", False),
    )


def ensure_workspace(settings: Settings) -> None:
    for directory in (
        settings.input_dir,
        settings.runs_dir,
        settings.uploads_dir,
        settings.jobs_dir,
        settings.archives_dir,
        settings.tmp_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)

    bundled_json = settings.bundled_input_dir / "soilflow_pflotran_demo.json"
    if not settings.default_input_json.exists() and bundled_json.exists():
        shutil.copy2(bundled_json, settings.default_input_json)
