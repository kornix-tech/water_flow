from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from soilflow_pflotran_modules.richards_test_cases import (
    TEST_BUILDERS,
    LinearDarcyTest,
    TestResult,
    TransientStorageTest,
    VGRichardsTest,
    generate_pflotran_test_input,
    generate_pflotran_transient_storage_input,
    generate_pflotran_vg_test_input,
    write_analytical_solution,
    write_test_summary,
    write_transient_analytical_files,
    write_transient_test_summary,
    write_vg_analytical_solution,
    write_vg_test_summary,
)
from soilflow_pflotran_modules.richards_test_evaluators import (
    evaluate_test_after_run,
    evaluate_transient_storage_after_run,
    evaluate_vg_test_after_run,
)
from soilflow_pflotran_modules.test_evaluation import base_result_metrics
from soilflow_pflotran_modules.test_registry import PFLOTRAN_RICHARDS_TESTS
from soilflow_pflotran_modules.test_solver_execution import execute_test_solver


def generate_richards_test_files(
    test_name: str,
    params: dict[str, Any],
    workdir: Path,
) -> LinearDarcyTest | VGRichardsTest | TransientStorageTest:
    workdir.mkdir(parents=True, exist_ok=True)
    test = TEST_BUILDERS[test_name](params)
    if isinstance(test, LinearDarcyTest):
        (workdir / "pflotran.in").write_text(generate_pflotran_test_input(test), encoding="utf-8")
        write_analytical_solution(test, workdir / "analytical_solution.csv")
        write_test_summary(test, workdir / "analytical_test_summary.txt")
    elif isinstance(test, VGRichardsTest):
        (workdir / "pflotran.in").write_text(generate_pflotran_vg_test_input(test), encoding="utf-8")
        write_vg_analytical_solution(test, workdir / "analytical_solution.csv")
        write_vg_test_summary(test, workdir / "analytical_test_summary.txt")
    else:
        (workdir / "pflotran.in").write_text(generate_pflotran_transient_storage_input(test), encoding="utf-8")
        write_transient_analytical_files(test, workdir)
        write_transient_test_summary(test, workdir / "analytical_test_summary.txt")
    print(f"[OK] Generated {test_name} PFLOTRAN input: {workdir / 'pflotran.in'}")
    print(f"[OK] Generated analytical solution: {workdir / 'analytical_solution.csv'}")
    return test


def evaluate_richards_test_after_run(
    test: LinearDarcyTest | VGRichardsTest | TransientStorageTest,
    workdir: Path,
) -> TestResult:
    if isinstance(test, LinearDarcyTest):
        return evaluate_test_after_run(test, workdir)
    if isinstance(test, VGRichardsTest):
        return evaluate_vg_test_after_run(test, workdir)
    return evaluate_transient_storage_after_run(test, workdir)


def run_richards_test(
    args: argparse.Namespace,
    test_name: str,
    params: dict[str, Any],
    workdir: Path,
) -> TestResult:
    if test_name not in PFLOTRAN_RICHARDS_TESTS:
        raise ValueError(f"Для теста {test_name} не выбран Richards runner")

    test = generate_richards_test_files(test_name, params, workdir)

    if args.dry_run or not args.run:
        print(f"[INFO] {test_name} dry generation completed.")
        return TestResult(f"_test_{test_name}", "GENERATED", workdir, base_result_metrics(test_name))

    execution = execute_test_solver(args, test_name, workdir, test.mpi_processes)
    if execution.status != "RAN":
        return TestResult(
            f"_test_{test_name}",
            execution.status,
            workdir,
            base_result_metrics(test_name, **execution.metrics),
        )
    return evaluate_richards_test_after_run(test, workdir)
