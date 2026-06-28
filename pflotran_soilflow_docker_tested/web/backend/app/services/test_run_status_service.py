from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .result_status_artifacts import existing_status_artifact, existing_status_artifact_names, parse_key_value_status

TEST_STATUS_TEXT = "TEST_STATUS.txt"
TEST_DIAGNOSTICS_JSON = "test_diagnostics.json"
TEST_ARTIFACTS = (
    TEST_STATUS_TEXT,
    TEST_DIAGNOSTICS_JSON,
    "analytical_test_summary.txt",
    "test_comparison.csv",
    "profile_overlay_comparison.csv",
)
INT_RE = re.compile(r"^[+-]?\d+$")
FLOAT_RE = re.compile(r"^[+-]?(?:\d+\.\d*|\d*\.\d+|\d+)(?:[eE][+-]?\d+)?$")


def _coerce_status_value(value: str) -> str | int | float | bool:
    lowered = value.strip().lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if INT_RE.fullmatch(value):
        return int(value)
    if FLOAT_RE.fullmatch(value) and any(marker in value for marker in (".", "e", "E")):
        return float(value)
    return value


def _coerce_fields(raw_fields: dict[str, str]) -> dict[str, str | int | float | bool]:
    return {key: _coerce_status_value(value) for key, value in raw_fields.items()}


def _read_diagnostics(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    try:
        with path.open(encoding="utf-8") as file_obj:
            payload = json.load(file_obj)
        if not isinstance(payload, dict):
            raise ValueError("test_diagnostics.json must contain an object")
        return payload
    except (json.JSONDecodeError, ValueError) as exc:
        # Diagnostics JSON пишется дополнительно к TEST_STATUS.txt и может быть
        # пойман в частично записанном состоянии. Основной статус при этом
        # остается полезным для UI/API, поэтому возвращаем явный partial marker.
        return {"artifact_readiness": "PARTIAL", "diagnostics_error": str(exc)}


def read_test_run_status(run_name: str, run_dir: Path) -> dict[str, Any]:
    status_path = existing_status_artifact(run_dir, TEST_STATUS_TEXT)
    if status_path is None:
        raise FileNotFoundError("Test status artifact was not found")
    diagnostic_path = existing_status_artifact(run_dir, TEST_DIAGNOSTICS_JSON)

    raw_fields, messages = parse_key_value_status(status_path)
    fields = _coerce_fields(raw_fields)
    status = str(fields.get("TEST_STATUS", "UNKNOWN"))
    test_id_value = fields.get("test_id")
    return {
        "run_name": run_name,
        "status": status,
        "test_id": str(test_id_value) if test_id_value else None,
        "fields": fields,
        "messages": messages,
        "diagnostics": _read_diagnostics(diagnostic_path),
        "source": TEST_STATUS_TEXT,
        "files": existing_status_artifact_names(run_dir, TEST_ARTIFACTS),
    }
