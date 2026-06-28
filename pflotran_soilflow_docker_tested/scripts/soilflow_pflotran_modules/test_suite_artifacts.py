from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Protocol


class TestResultLike(Protocol):
    test_id: str
    status: str
    metrics: dict[str, Any]


SUITE_RESULT_CSV_FIELDS = [
    "test_id",
    "status",
    "verification_level",
    "output_dir",
    "warning_count",
    "unexpected_warning_count",
    "solver_error_count",
    "solver_diverged",
    "solver_cuts",
    "profile_overlay_comparison",
    "profile_overlay_points",
    "profile_overlay_quality_check",
    "profile_physics_family",
    "profile_carrier_status",
    "profile_deck_kind",
    "strict_candidate_can_gate_suite",
    "richards_mms_strict_candidate_check",
    "theta_overlay_rmse_m3_m3",
    "theta_overlay_max_abs_m3_m3",
    "pressure_head_overlay_rmse_m",
    "pressure_head_overlay_max_abs_m",
    "strict_profile_evaluator",
]


def accepted_suite_statuses(dry_run: bool = False) -> set[str]:
    accepted = {"PASS", "PASS_WITH_WARNINGS", "SKIP"}
    if dry_run:
        accepted.update({"GENERATED", "GENERATED_ONLY"})
    return accepted


def suite_status_summary(results: list[TestResultLike], dry_run: bool = False) -> dict[str, int | str]:
    accepted = accepted_suite_statuses(dry_run=dry_run)
    failed = [result for result in results if result.status not in accepted]
    warned = [result for result in results if result.status == "PASS_WITH_WARNINGS"]
    skipped = [result for result in results if result.status == "SKIP"]
    suite_status = (
        "DRY_RUN"
        if dry_run
        else ("FAIL" if failed else ("PASS_WITH_SKIPS" if skipped else ("PASS_WITH_WARNINGS" if warned else "PASS")))
    )
    return {
        "TEST_SUITE_STATUS": suite_status,
        "tests_total": len(results),
        "tests_passed": sum(1 for result in results if result.status == "PASS"),
        "tests_passed_with_warnings": sum(1 for result in results if result.status == "PASS_WITH_WARNINGS"),
        "tests_skipped": len(skipped),
        "tests_failed": len(failed),
        "strict_analytical_total": sum(
            1 for result in results if result.metrics.get("verification_level") == "strict_analytical"
        ),
        "strict_analytical_passed": sum(
            1
            for result in results
            if result.metrics.get("verification_level") == "strict_analytical" and result.status in accepted
        ),
        "partial_balance_total": sum(
            1 for result in results if result.metrics.get("verification_level") == "partial_balance"
        ),
        "partial_balance_passed": sum(
            1
            for result in results
            if result.metrics.get("verification_level") == "partial_balance" and result.status in accepted
        ),
        "profile_smoke_total": sum(
            1 for result in results if result.metrics.get("verification_level") == "profile_smoke"
        ),
        "profile_smoke_ready": sum(
            1
            for result in results
            if result.metrics.get("verification_level") == "profile_smoke" and result.status in accepted
        ),
        "warnings_total": sum(int(result.metrics.get("warning_count", 0)) for result in results),
        "unexpected_warnings_total": sum(
            int(result.metrics.get("unexpected_warning_count", 0)) for result in results
        ),
        "solver_errors_total": sum(int(result.metrics.get("solver_error_count", 0)) for result in results),
        "solver_divergences_total": sum(
            1 for result in results if bool(result.metrics.get("solver_diverged", False))
        ),
        "solver_cuts_total": sum(int(result.metrics.get("solver_cuts", 0)) for result in results),
    }


def suite_result_rows(results: list[TestResultLike]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for result in results:
        row = {
            "test_id": result.test_id,
            "status": result.status,
            "verification_level": result.metrics.get("verification_level", ""),
            "output_dir": str(getattr(result, "output_dir", "")),
        }
        for field_name in SUITE_RESULT_CSV_FIELDS:
            if field_name in row:
                continue
            value = result.metrics.get(field_name, "")
            if isinstance(value, bool):
                value = str(value).lower()
            row[field_name] = value
        rows.append(row)
    return rows


def suite_status_lines(results: list[TestResultLike], dry_run: bool = False) -> list[str]:
    summary = suite_status_summary(results, dry_run=dry_run)
    lines = [
        f"TEST_SUITE_STATUS={summary['TEST_SUITE_STATUS']}",
        f"tests_total={summary['tests_total']}",
        f"tests_passed={summary['tests_passed']}",
        f"tests_passed_with_warnings={summary['tests_passed_with_warnings']}",
        f"tests_skipped={summary['tests_skipped']}",
        f"tests_failed={summary['tests_failed']}",
        f"strict_analytical_total={summary['strict_analytical_total']}",
        f"strict_analytical_passed={summary['strict_analytical_passed']}",
        f"partial_balance_total={summary['partial_balance_total']}",
        f"partial_balance_passed={summary['partial_balance_passed']}",
        f"profile_smoke_total={summary['profile_smoke_total']}",
        f"profile_smoke_ready={summary['profile_smoke_ready']}",
        "",
    ]
    for result in results:
        lines.append(f"{result.test_id}={result.status}")
    lines.extend(
        [
            "",
            f"warnings_total={summary['warnings_total']}",
            f"unexpected_warnings_total={summary['unexpected_warnings_total']}",
            f"solver_errors_total={summary['solver_errors_total']}",
            f"solver_divergences_total={summary['solver_divergences_total']}",
            f"solver_cuts_total={summary['solver_cuts_total']}",
        ]
    )
    return lines


def write_suite_status_file(results: list[TestResultLike], suite_dir: Path, dry_run: bool = False) -> None:
    suite_dir.mkdir(parents=True, exist_ok=True)
    summary = suite_status_summary(results, dry_run=dry_run)
    rows = suite_result_rows(results)
    (suite_dir / "TEST_SUITE_STATUS.txt").write_text(
        "\n".join(suite_status_lines(results, dry_run=dry_run)) + "\n",
        encoding="utf-8",
    )
    (suite_dir / "TEST_SUITE_STATUS.json").write_text(
        json.dumps({"summary": summary, "results": rows}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    with (suite_dir / "TEST_SUITE_RESULTS.csv").open("w", newline="", encoding="utf-8") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=SUITE_RESULT_CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
