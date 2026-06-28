from __future__ import annotations

from functools import lru_cache
from pathlib import Path

MAX_STATUS_ARTIFACT_BYTES = 2 * 1024 * 1024


def status_artifact_path(run_dir: Path, filename: str) -> Path:
    base_dir = run_dir.resolve()
    raw_path = base_dir / filename
    if raw_path.is_symlink():
        raise ValueError(f"Status artifact must not be a symlink: {filename}")
    resolved_path = raw_path.resolve()
    if resolved_path != base_dir and base_dir not in resolved_path.parents:
        raise ValueError(f"Status artifact escapes run directory: {filename}")
    return resolved_path


def existing_status_artifact(run_dir: Path, filename: str) -> Path | None:
    path = status_artifact_path(run_dir, filename)
    if not path.exists() or not path.is_file():
        return None
    if path.stat().st_size > MAX_STATUS_ARTIFACT_BYTES:
        raise ValueError(f"Status artifact is too large: {filename}")
    return path


def existing_status_artifact_names(run_dir: Path, filenames: tuple[str, ...]) -> list[str]:
    return [filename for filename in filenames if existing_status_artifact(run_dir, filename) is not None]


def has_status_artifact(run_dir: Path, filename: str) -> bool:
    return existing_status_artifact(run_dir, filename) is not None


@lru_cache(maxsize=1024)
def _read_text_cached(path_value: str, size_bytes: int, mtime_ns: int) -> str:
    return Path(path_value).read_text(encoding="utf-8", errors="replace")


def read_status_artifact_text(path: Path) -> str:
    stat_result = path.stat()
    if stat_result.st_size > MAX_STATUS_ARTIFACT_BYTES:
        raise ValueError(f"Status artifact is too large: {path.name}")
    # Ключ кэша включает размер и mtime_ns: после дозаписи status artifact
    # следующий API-запрос перечитает файл, но повторные overview/status запросы
    # на неизменном artifact не делают лишний disk read.
    return _read_text_cached(str(path.resolve()), stat_result.st_size, stat_result.st_mtime_ns)


def parse_key_value_status(path: Path) -> tuple[dict[str, str], list[str]]:
    fields: dict[str, str] = {}
    messages: list[str] = []
    for raw_line in read_status_artifact_text(path).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if "=" not in line:
            messages.append(line)
            continue
        key, value = line.split("=", 1)
        fields[key.strip()] = value.strip()
    return fields, messages
