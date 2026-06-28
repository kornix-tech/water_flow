from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from soilflow_pflotran_modules.solver_runner import (
    find_pflotran_native,
    find_pflotran_wsl,
    run_native_solver,
    run_wsl_solver,
)
from soilflow_pflotran_modules.test_evaluation import write_pflotran_error_status


@dataclass(frozen=True)
class TestSolverExecution:
    status: str
    executed: bool
    exit_code: int | None = None
    timed_out: bool = False

    @property
    def metrics(self) -> dict[str, Any]:
        if self.exit_code is None:
            return {}
        metrics = {"exit_code": self.exit_code}
        if self.timed_out:
            metrics["solver_timed_out"] = True
        return metrics


def solver_timeout_seconds(args: argparse.Namespace) -> float | None:
    value = getattr(args, "solver_timeout_seconds", None)
    if value in (None, "", 0):
        return None
    timeout = float(value)
    if timeout <= 0:
        return None
    return timeout


def execute_test_solver(
    args: argparse.Namespace,
    test_name: str,
    workdir: Path,
    mpi_processes: int,
) -> TestSolverExecution:
    native = find_pflotran_native({}, args.pflotran_exe)
    timeout_seconds = solver_timeout_seconds(args)
    if native:
        print(f"[INFO] Running native PFLOTRAN for {test_name}: {native}")
        result = run_native_solver(workdir, native, mpi_processes, timeout_seconds=timeout_seconds)
        exit_code = result.return_code
        print(f"[INFO] PFLOTRAN exit code: {exit_code}")
        print(f"[INFO] Log: {result.log_path}")
        if result.timed_out:
            write_pflotran_error_status(workdir / "TEST_STATUS.txt", exit_code, status="PFLOTRAN_TIMEOUT")
            return TestSolverExecution("PFLOTRAN_TIMEOUT", True, exit_code, timed_out=True)
        if exit_code != 0:
            write_pflotran_error_status(workdir / "TEST_STATUS.txt", exit_code)
            return TestSolverExecution("PFLOTRAN_ERROR", True, exit_code)
        return TestSolverExecution("RAN", True, exit_code)

    if args.prefer_wsl:
        wsl_exe = find_pflotran_wsl()
        if wsl_exe:
            print(f"[INFO] Running PFLOTRAN via WSL for {test_name}: {wsl_exe}")
            result = run_wsl_solver(workdir, wsl_exe, mpi_processes, timeout_seconds=timeout_seconds)
            exit_code = result.return_code
            print(f"[INFO] PFLOTRAN WSL exit code: {exit_code}")
            print(f"[INFO] Log: {result.log_path}")
            if result.timed_out:
                write_pflotran_error_status(workdir / "TEST_STATUS.txt", exit_code, status="PFLOTRAN_TIMEOUT")
                return TestSolverExecution("PFLOTRAN_TIMEOUT", True, exit_code, timed_out=True)
            if exit_code != 0:
                write_pflotran_error_status(workdir / "TEST_STATUS.txt", exit_code)
                return TestSolverExecution("PFLOTRAN_ERROR", True, exit_code)
            return TestSolverExecution("RAN", True, exit_code)

    (workdir / "TEST_STATUS.txt").write_text(
        "TEST_STATUS=GENERATED_ONLY\nPFLOTRAN executable was not found; analytical files and pflotran.in were generated only.\n",
        encoding="utf-8",
    )
    print("[WARN] PFLOTRAN executable was not found. _test files generated only.")
    return TestSolverExecution("GENERATED_ONLY", False)
