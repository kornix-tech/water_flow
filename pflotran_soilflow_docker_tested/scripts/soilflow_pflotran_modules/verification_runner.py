"""
Оркестрация verification-suite для CLI режима `_test`.

Модуль намеренно не хранит физические формулы тестов: он выбирает сценарии,
создает рабочие каталоги, передает управление family runner'ам и пишет suite
status. Такой слой можно заменить или расширить без возврата тестовой логики в
`soilflow_pflotran.py` или центральный router.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from soilflow_pflotran_modules.profile_test_runner import run_profile_test
from soilflow_pflotran_modules.richards_test_cases import TestResult
from soilflow_pflotran_modules.richards_test_runner import run_richards_test
from soilflow_pflotran_modules.test_evaluation import failure_metrics, write_suite_status_file, write_unknown_status
from soilflow_pflotran_modules.test_registry import (
    PFLOTRAN_PROFILE_TESTS,
    PFLOTRAN_RICHARDS_TESTS,
    selected_test_names,
    suite_workdir_for,
    test_params_from_document,
    test_workdir_for,
)


def read_input_document(input_json: Path) -> dict[str, Any]:
    with input_json.open(encoding="utf-8") as file_obj:
        data = json.load(file_obj)
    if not isinstance(data, dict):
        raise ValueError("JSON исходных данных должен быть объектом")
    return data


def read_test_params(input_json: Path, test_name: str = "linear_darcy") -> dict[str, Any]:
    data = read_input_document(input_json)
    return test_params_from_document(data, test_name)


def resolve_test_workdir(args: argparse.Namespace, test_name: str) -> Path:
    return test_workdir_for(
        test_name=test_name,
        output_dir=args.output_dir,
        workdir=args.workdir,
        selected_test=args.test,
    )


def write_suite_status(results: list[TestResult], suite_dir: Path, dry_run: bool = False) -> None:
    write_suite_status_file(results, suite_dir, dry_run=dry_run)


def run_single_test(args: argparse.Namespace, test_name: str) -> TestResult:
    if test_name in PFLOTRAN_PROFILE_TESTS:
        return run_profile_test(args, test_name, resolve_test_workdir(args, test_name))
    if test_name not in PFLOTRAN_RICHARDS_TESTS:
        raise ValueError(f"Для теста {test_name} не выбран PFLOTRAN runner")

    input_json = args.input_json.resolve()
    if not input_json.exists():
        raise FileNotFoundError(f"input JSON not found: {input_json}")

    params = read_test_params(input_json, test_name)
    workdir = resolve_test_workdir(args, test_name)
    return run_richards_test(args, test_name, params, workdir)


def run_single_test_safely(args: argparse.Namespace, test_name: str) -> TestResult:
    try:
        return run_single_test(args, test_name)
    except Exception as exc:
        workdir = resolve_test_workdir(args, test_name)
        workdir.mkdir(parents=True, exist_ok=True)
        reason = write_unknown_status(workdir / "TEST_STATUS.txt", exc, stage="generation")
        return TestResult(
            f"_test_{test_name}",
            "UNKNOWN",
            workdir,
            failure_metrics(test_name, "generation", reason),
        )


def run_test_mode(args: argparse.Namespace) -> int:
    test_names = selected_test_names(args.test)
    results = [run_single_test_safely(args, name) for name in test_names]
    suite_dir = suite_workdir_for(args.output_dir)
    write_suite_status(results, suite_dir, dry_run=args.dry_run or not args.run)
    if args.dry_run or not args.run:
        return 0
    return 0 if all(r.status in {"PASS", "PASS_WITH_WARNINGS", "SKIP"} for r in results) else 1
