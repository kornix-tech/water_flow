from __future__ import annotations

from pathlib import Path


def tail_text(path: Path, max_bytes: int = 200_000) -> str:
    if not path.exists():
        return ""
    size = path.stat().st_size
    with path.open("rb") as src:
        if size > max_bytes:
            src.seek(size - max_bytes)
        data = src.read()
    return data.decode("utf-8", errors="replace")
