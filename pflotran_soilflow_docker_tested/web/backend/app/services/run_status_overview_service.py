from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from .result_status_artifacts import existing_status_artifact, has_status_artifact, parse_key_value_status
from .test_run_status_service import TEST_ARTIFACTS, TEST_STATUS_TEXT, read_test_run_status
from .test_suite_summary_service import SUITE_ARTIFACTS, SUITE_STATUS_ARTIFACTS, read_test_suite_status

VISUALIZATION_STATUS_TEXT = "VISUALIZATION_STATUS.txt"
OVERVIEW_SIGNATURE_FILES = tuple(dict.fromkeys((*SUITE_ARTIFACTS, *TEST_ARTIFACTS, f"plots/{VISUALIZATION_STATUS_TEXT}")))
ArtifactSignature = tuple[tuple[str, int, int], ...]


def _metric(label: str, value: Any) -> dict[str, str]:
    return {"label": label, "value": "-" if value is None or value == "" else str(value)}


def _first_present(fields: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = fields.get(key)
        if value is not None and value != "":
            return value
    return None


def _suite_item(run_name: str, run_dir: Path) -> dict[str, Any] | None:
    if not any(has_status_artifact(run_dir, filename) for filename in SUITE_STATUS_ARTIFACTS):
        return None
    suite = read_test_suite_status(run_name, run_dir)
    summary = suite["summary"]
    return {
        "kind": "test-suite",
        "title": "Verification-suite",
        "status": suite["status"],
        "subtitle": f"{summary.get('tests_passed', 0)} из {summary.get('tests_total', 0)} без предупреждений",
        "metrics": [
            _metric("Всего тестов", summary.get("tests_total", 0)),
            _metric("С предупреждениями", summary.get("tests_passed_with_warnings", 0)),
            _metric("Ошибки", summary.get("tests_failed", 0)),
            _metric("Строгая аналитика", f"{summary.get('strict_analytical_passed', 0)}/{summary.get('strict_analytical_total', 0)}"),
            _metric("Profile smoke", f"{summary.get('profile_smoke_ready', 0)}/{summary.get('profile_smoke_total', 0)}"),
        ],
        "source": suite["source"],
        "files": suite["files"],
    }


def _test_item(run_name: str, run_dir: Path) -> dict[str, Any] | None:
    if existing_status_artifact(run_dir, TEST_STATUS_TEXT) is None:
        return None
    status = read_test_run_status(run_name, run_dir)
    fields = status["fields"]
    return {
        "kind": "test-run",
        "title": "Тестовый запуск",
        "status": status["status"],
        "subtitle": status["test_id"] or run_name,
        "metrics": [
            _metric("Давление", fields.get("pressure_check")),
            _metric("Насыщенность", fields.get("saturation_check")),
            _metric("Поток", fields.get("flux_check")),
            _metric("Solver", fields.get("solver_check")),
            _metric("Предупреждения", fields.get("warning_check")),
            _metric("TECPLOT-профиль", fields.get("profile_status")),
            _metric("Точек сравнения", fields.get("comparison_points")),
            _metric("Ошибка давления, Па", fields.get("max_abs_pressure_error_pa")),
            _metric("Ошибка потока, м/с", fields.get("q_error_m_s")),
            _metric("Откаты timestep", fields.get("solver_cuts")),
        ],
        "source": status["source"],
        "files": status["files"],
    }


def _visualization_item(run_dir: Path) -> dict[str, Any] | None:
    plots_dir = run_dir / "plots"
    status_path = existing_status_artifact(plots_dir, VISUALIZATION_STATUS_TEXT)
    if status_path is None:
        return None
    raw_fields, messages = parse_key_value_status(status_path)
    status = raw_fields.get("VISUALIZATION_STATUS", "UNKNOWN")
    return {
        "kind": "visualization",
        "title": "Графики",
        "status": status,
        "subtitle": raw_fields.get("interactive_html", "profiles_animation.html"),
        "metrics": [
            _metric("Кадров", raw_fields.get("frames_total")),
            _metric("Ось профиля", raw_fields.get("profile_axis")),
            _metric("Режим профиля", raw_fields.get("profile_mode")),
            _metric("Влажность min", _first_present(raw_fields, "theta_min", "saturation_min")),
            _metric("Влажность max", _first_present(raw_fields, "theta_max", "saturation_max")),
            _metric("Аналитический профиль", raw_fields.get("analytical_profile_overlay")),
        ],
        "source": f"plots/{VISUALIZATION_STATUS_TEXT}",
        "files": [f"plots/{VISUALIZATION_STATUS_TEXT}"],
        "messages": messages,
    }


def _artifact_signature(run_dir: Path) -> ArtifactSignature:
    signature: list[tuple[str, int, int]] = []
    for filename in OVERVIEW_SIGNATURE_FILES:
        artifact_path = existing_status_artifact(run_dir, filename)
        if artifact_path is None:
            continue
        stat_result = artifact_path.stat()
        signature.append((filename, stat_result.st_size, stat_result.st_mtime_ns))
    return tuple(signature)


@lru_cache(maxsize=512)
def _read_run_status_overview_cached(run_name: str, run_dir_value: str, signature: ArtifactSignature) -> dict[str, Any]:
    # Signature передается только как cache key. Если status artifact изменился,
    # вызов получит новый key и перечитает сводку без ручной инвалидации.
    del signature
    run_dir = Path(run_dir_value)
    items = [
        item
        for item in (
            _suite_item(run_name, run_dir),
            _test_item(run_name, run_dir),
            _visualization_item(run_dir),
        )
        if item is not None
    ]
    if not items:
        items.append(
            {
                "kind": "run-files",
                "title": "Файлы результата",
                "status": "READY" if run_dir.exists() else "UNKNOWN",
                "subtitle": "status-файлы не найдены",
                "metrics": [],
                "source": None,
                "files": [],
            }
        )
    return {"run_name": run_name, "items": items}


def read_run_status_overview(run_name: str, run_dir: Path) -> dict[str, Any]:
    resolved_run_dir = run_dir.resolve()
    return _read_run_status_overview_cached(run_name, str(resolved_run_dir), _artifact_signature(resolved_run_dir))
