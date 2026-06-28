from __future__ import annotations

from pathlib import Path
from typing import Any

from soilflow_pflotran_modules.test_registry import verification_level_for_test
from soilflow_pflotran_modules.test_suite_artifacts import (
    TestResultLike,
    suite_result_rows,
    suite_status_lines,
    suite_status_summary,
    write_suite_status_file,
)


def pass_fail(passed: bool) -> str:
    return "PASS" if passed else "FAIL"


def solver_check_passed(solver: dict[str, Any]) -> bool:
    """Единое правило: solver должен завершиться без ERROR, diverged и timestep cuts."""

    return (
        int(solver.get("solver_error_count", 0)) == 0
        and not bool(solver.get("solver_diverged", False))
        and int(solver.get("solver_cuts", 0)) == 0
    )


def combined_test_status(physical_ok: bool, solver_ok: bool, warning_check: str) -> str:
    if not physical_ok or not solver_ok or warning_check == "FAIL":
        return "FAIL"
    if warning_check == "WARN":
        return "PASS_WITH_WARNINGS"
    return "PASS"


def write_unknown_status(path: Path, exc: Exception, *, stage: str = "evaluator") -> str:
    reason = f"{type(exc).__name__}: {exc}"
    path.write_text(f"TEST_STATUS=UNKNOWN\nfailure_stage={stage}\nreason={reason}\n", encoding="utf-8")
    return reason


def write_pflotran_error_status(path: Path, exit_code: int, *, status: str = "PFLOTRAN_ERROR") -> None:
    path.write_text(f"TEST_STATUS={status}\nfailure_stage=solver\nexit_code={exit_code}\n", encoding="utf-8")


def base_result_metrics(test_name: str, **extra_metrics: Any) -> dict[str, Any]:
    return {"verification_level": verification_level_for_test(test_name), **extra_metrics}


def failure_metrics(test_name: str, stage: str, reason: str | None = None, **extra_metrics: Any) -> dict[str, Any]:
    metrics = base_result_metrics(test_name, failure_stage=stage, **extra_metrics)
    if reason is not None:
        metrics["reason"] = reason
    return metrics


def direct_flux_output_file(direct_probe: dict[str, Any]) -> str:
    files = (
        list(direct_probe.get("conservation_files", []))
        + list(direct_probe.get("mass_balance_files", []))
        + list(direct_probe.get("velocity_files", []))
    )
    return str(files[0]) if files else "NA"


__all__ = [
    "TestResultLike",
    "base_result_metrics",
    "combined_test_status",
    "direct_flux_output_file",
    "failure_metrics",
    "pass_fail",
    "solver_check_passed",
    "suite_result_rows",
    "suite_status_lines",
    "suite_status_summary",
    "write_pflotran_error_status",
    "write_suite_status_file",
    "write_unknown_status",
]
