from __future__ import annotations

import argparse
import sys
from pathlib import Path

from soilflow_pflotran_modules.extended_analytical import generate_extended_analytical_rows
from soilflow_pflotran_modules.profile_benchmarks import (
    evaluate_profile_test_after_run as evaluate_profile_benchmark_after_run,
    write_richards_profile_analytical_profiles,
)
from soilflow_pflotran_modules.profile_benchmark_cases import profile_benchmark_case_manifest, write_profile_benchmark_case_manifest
from soilflow_pflotran_modules.profile_carrier import generate_richards_profile_input
from soilflow_pflotran_modules.richards_mms_case import (
    RichardsMmsCase,
    generate_richards_mms_source_term_input,
    write_richards_mms_case_artifacts,
)
from soilflow_pflotran_modules.richards_test_cases import TestResult
from soilflow_pflotran_modules.test_artifacts import write_curve_svg, write_rows_csv
from soilflow_pflotran_modules.test_evaluation import base_result_metrics, write_unknown_status
from soilflow_pflotran_modules.test_registry import PFLOTRAN_PROFILE_TESTS
from soilflow_pflotran_modules.test_solver_execution import execute_test_solver


def generate_profile_test_files(test_name: str, workdir: Path) -> None:
    workdir.mkdir(parents=True, exist_ok=True)
    rows, x_key, y_key, title, analytical_note = generate_extended_analytical_rows(test_name)
    write_rows_csv(workdir / "analytical_solution.csv", rows)
    write_curve_svg(workdir / "analytical_solution.svg", title, x_key, y_key, rows, x_key, y_key)
    write_richards_profile_analytical_profiles(test_name, workdir)
    case_manifest = profile_benchmark_case_manifest(test_name)
    write_profile_benchmark_case_manifest(test_name, workdir)
    if test_name == "richards_mms":
        mms_case = RichardsMmsCase()
        write_richards_mms_case_artifacts(mms_case, workdir)
        (workdir / "pflotran.in").write_text(generate_richards_mms_source_term_input(mms_case), encoding="utf-8")
    else:
        (workdir / "pflotran.in").write_text(generate_richards_profile_input(test_name), encoding="utf-8")
    (workdir / "analytical_test_summary.txt").write_text(
        "\n".join(
            [
                title,
                "=" * len(title),
                "",
                f"test_name={test_name}",
                f"analytical_solution={analytical_note}",
                "numerical_status=pflotran_profile_enabled",
                f"profile_physics_family={case_manifest['profile_physics_family']}",
                f"profile_deck_kind={case_manifest['profile_deck_kind']}",
                f"strict_profile_evaluator={case_manifest['strict_profile_evaluator']}",
                f"strict_candidate_can_gate_suite={str(case_manifest['strict_candidate_can_gate_suite']).lower()}",
                "note=PFLOTRAN запускается для получения расчетных TECPLOT-профилей; строгая метрика сравнения будет добавлена отдельно.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def evaluate_profile_benchmark_result(test_name: str, workdir: Path) -> TestResult:
    try:
        result = evaluate_profile_benchmark_after_run(test_name, workdir, TestResult)
        print(f"[TEST] {result.status}: _test_{test_name} PFLOTRAN profile benchmark")
        return result
    except Exception as exc:
        reason = write_unknown_status(workdir / "TEST_STATUS.txt", exc)
        print(f"[TEST] UNKNOWN _test_{test_name}: {exc}", file=sys.stderr)
        return TestResult(f"_test_{test_name}", "UNKNOWN", workdir, {"reason": reason})


def run_profile_test(args: argparse.Namespace, test_name: str, workdir: Path) -> TestResult:
    if test_name not in PFLOTRAN_PROFILE_TESTS:
        raise ValueError(f"Для теста {test_name} не выбран profile runner")

    generate_profile_test_files(test_name, workdir)

    if args.dry_run or not args.run:
        return TestResult(f"_test_{test_name}", "GENERATED", workdir, base_result_metrics(test_name))

    execution = execute_test_solver(args, test_name, workdir, 1)
    if execution.status != "RAN":
        return TestResult(
            f"_test_{test_name}",
            execution.status,
            workdir,
            base_result_metrics(test_name, **execution.metrics),
        )
    return evaluate_profile_benchmark_result(test_name, workdir)
