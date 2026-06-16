from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol


class TestResultLike(Protocol):
    test_id: str
    status: str
    metrics: dict[str, Any]


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


def write_unknown_status(path: Path, exc: Exception) -> str:
    reason = f"{type(exc).__name__}: {exc}"
    path.write_text(f"TEST_STATUS=UNKNOWN\nreason={reason}\n", encoding="utf-8")
    return reason


def write_pflotran_error_status(path: Path, exit_code: int) -> None:
    path.write_text(f"TEST_STATUS=PFLOTRAN_ERROR\nexit_code={exit_code}\n", encoding="utf-8")


def direct_flux_output_file(direct_probe: dict[str, Any]) -> str:
    files = (
        list(direct_probe.get("conservation_files", []))
        + list(direct_probe.get("mass_balance_files", []))
        + list(direct_probe.get("velocity_files", []))
    )
    return str(files[0]) if files else "NA"


def suite_status_lines(results: list[TestResultLike], dry_run: bool = False) -> list[str]:
    accepted = {"PASS", "PASS_WITH_WARNINGS", "SKIP"}
    if dry_run:
        accepted = accepted | {"GENERATED", "GENERATED_ONLY"}
    failed = [result for result in results if result.status not in accepted]
    warned = [result for result in results if result.status == "PASS_WITH_WARNINGS"]
    skipped = [result for result in results if result.status == "SKIP"]
    suite_status = (
        "DRY_RUN"
        if dry_run
        else ("FAIL" if failed else ("PASS_WITH_SKIPS" if skipped else ("PASS_WITH_WARNINGS" if warned else "PASS")))
    )
    lines = [
        f"TEST_SUITE_STATUS={suite_status}",
        f"tests_total={len(results)}",
        f"tests_passed={sum(1 for result in results if result.status == 'PASS')}",
        f"tests_passed_with_warnings={sum(1 for result in results if result.status == 'PASS_WITH_WARNINGS')}",
        f"tests_skipped={len(skipped)}",
        f"tests_failed={len(failed)}",
        "",
    ]
    for result in results:
        lines.append(f"{result.test_id}={result.status}")
    lines.extend(
        [
            "",
            f"warnings_total={sum(int(result.metrics.get('warning_count', 0)) for result in results)}",
            f"unexpected_warnings_total={sum(int(result.metrics.get('unexpected_warning_count', 0)) for result in results)}",
            f"solver_errors_total={sum(int(result.metrics.get('solver_error_count', 0)) for result in results)}",
            f"solver_divergences_total={sum(1 for result in results if bool(result.metrics.get('solver_diverged', False)))}",
            f"solver_cuts_total={sum(int(result.metrics.get('solver_cuts', 0)) for result in results)}",
        ]
    )
    return lines


def write_suite_status_file(results: list[TestResultLike], suite_dir: Path, dry_run: bool = False) -> None:
    suite_dir.mkdir(parents=True, exist_ok=True)
    (suite_dir / "TEST_SUITE_STATUS.txt").write_text(
        "\n".join(suite_status_lines(results, dry_run=dry_run)) + "\n",
        encoding="utf-8",
    )
