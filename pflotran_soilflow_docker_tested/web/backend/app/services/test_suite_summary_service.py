from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .result_status_artifacts import existing_status_artifact, existing_status_artifact_names, parse_key_value_status

SUITE_STATUS_TEXT = "TEST_SUITE_STATUS.txt"
SUITE_STATUS_JSON = "TEST_SUITE_STATUS.json"
SUITE_RESULTS_CSV = "TEST_SUITE_RESULTS.csv"
SUITE_ARTIFACTS = (SUITE_STATUS_JSON, SUITE_RESULTS_CSV, SUITE_STATUS_TEXT)

SUMMARY_INT_FIELDS = {
    "tests_total",
    "tests_passed",
    "tests_passed_with_warnings",
    "tests_skipped",
    "tests_failed",
    "strict_analytical_total",
    "strict_analytical_passed",
    "partial_balance_total",
    "partial_balance_passed",
    "profile_smoke_total",
    "profile_smoke_ready",
    "warnings_total",
    "unexpected_warnings_total",
    "solver_errors_total",
    "solver_divergences_total",
    "solver_cuts_total",
}
RESULT_INT_FIELDS = {
    "warning_count",
    "unexpected_warning_count",
    "solver_error_count",
    "solver_cuts",
    "profile_overlay_points",
}
RESULT_BOOL_FIELDS = {"solver_diverged"}
RESULT_BASE_FIELDS = {"test_id", "status", "verification_level", "output_dir"}


def _coerce_int(value: Any) -> int:
    if value is None or str(value).strip() == "":
        return 0
    return int(float(str(value).strip()))


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _coerce_metric(key: str, value: Any) -> str | int | bool | None:
    if value is None:
        return None
    if key in RESULT_INT_FIELDS:
        return _coerce_int(value)
    if key in RESULT_BOOL_FIELDS:
        return _coerce_bool(value)
    return str(value).strip()


def _normalize_summary(raw_summary: dict[str, Any]) -> dict[str, str | int]:
    summary: dict[str, str | int] = {}
    for key, value in raw_summary.items():
        if key in SUMMARY_INT_FIELDS:
            summary[key] = _coerce_int(value)
        else:
            summary[key] = str(value).strip()
    summary.setdefault("TEST_SUITE_STATUS", "UNKNOWN")
    for key in SUMMARY_INT_FIELDS:
        summary.setdefault(key, 0)
    return summary


def _normalize_result(row: dict[str, Any]) -> dict[str, Any]:
    metrics: dict[str, str | int | bool | None] = {}
    normalized = {
        "test_id": str(row.get("test_id", "")).strip(),
        "status": str(row.get("status", "")).strip(),
        "verification_level": str(row.get("verification_level", "")).strip() or None,
        "output_dir": str(row.get("output_dir", "")).strip() or None,
        "metrics": metrics,
    }
    for key, value in row.items():
        if key in RESULT_BASE_FIELDS:
            continue
        metrics[key] = _coerce_metric(key, value)
    return normalized


def _normalize_results(raw_results: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_results, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in raw_results:
        if isinstance(item, dict):
            rows.append(_normalize_result(item))
    return rows


def _read_json_summary(path: Path) -> tuple[dict[str, str | int], list[dict[str, Any]]]:
    with path.open(encoding="utf-8") as file_obj:
        payload = json.load(file_obj)
    if not isinstance(payload, dict):
        raise ValueError("TEST_SUITE_STATUS.json must contain an object")
    raw_summary = payload.get("summary", {})
    if not isinstance(raw_summary, dict):
        raise ValueError("TEST_SUITE_STATUS.json summary must contain an object")
    return _normalize_summary(raw_summary), _normalize_results(payload.get("results", []))


def _read_csv_results(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as file_obj:
        return _normalize_results(list(csv.DictReader(file_obj)))


def _read_text_summary(path: Path) -> tuple[dict[str, str | int], list[dict[str, Any]]]:
    fields, _ = parse_key_value_status(path)
    summary: dict[str, str] = {}
    results: list[dict[str, str]] = []
    for key, value in fields.items():
        # Строки `_test_...=STATUS` являются результатами отдельных сценариев,
        # остальные пары key=value сохраняются как агрегированная сводка suite.
        if key.startswith("_test_"):
            results.append({"test_id": key, "status": value})
        else:
            summary[key] = value
    return _normalize_summary(summary), _normalize_results(results)


def read_test_suite_status(run_name: str, run_dir: Path) -> dict[str, Any]:
    json_path = existing_status_artifact(run_dir, SUITE_STATUS_JSON)
    csv_path = existing_status_artifact(run_dir, SUITE_RESULTS_CSV)
    text_path = existing_status_artifact(run_dir, SUITE_STATUS_TEXT)
    if json_path is None and text_path is None:
        raise FileNotFoundError("Test-suite status artifact was not found")

    if json_path is not None:
        try:
            summary, results = _read_json_summary(json_path)
            source = SUITE_STATUS_JSON
        except (json.JSONDecodeError, ValueError):
            if text_path is None:
                raise
            # JSON может быть прочитан во время записи suite. В этом случае
            # откатываемся к текстовой сводке и CSV-строкам, чтобы API не
            # отвечал 500/422 для частично записанной run-директории.
            summary, results = _read_text_summary(text_path)
            summary["artifact_readiness"] = "PARTIAL"
            summary["artifact_fallback"] = SUITE_STATUS_TEXT
            source = SUITE_STATUS_TEXT
    else:
        assert text_path is not None
        summary, results = _read_text_summary(text_path)
        source = SUITE_STATUS_TEXT

    if csv_path is not None:
        try:
            csv_results = _read_csv_results(csv_path)
            if csv_results:
                results = csv_results
        except (csv.Error, ValueError):
            summary["artifact_readiness"] = "PARTIAL"
            summary["csv_fallback"] = "SKIPPED"

    return {
        "run_name": run_name,
        "status": str(summary.get("TEST_SUITE_STATUS", "UNKNOWN")),
        "summary": summary,
        "results": results,
        "source": source,
        "files": existing_status_artifact_names(run_dir, SUITE_ARTIFACTS),
    }
