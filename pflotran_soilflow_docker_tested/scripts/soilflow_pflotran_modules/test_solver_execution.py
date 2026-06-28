from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from soilflow_pflotran_modules.solver_runner import (
    find_pflotran_native,
    find_pflotran_wsl,
    run_native,
    run_wsl,
)
from soilflow_pflotran_modules.test_evaluation import write_pflotran_error_status


@dataclass(frozen=True)
class TestSolverExecution:
    status: str
    executed: bool
    exit_code: int | None = None

    @property
    def metrics(self) -> dict[str, Any]:
        if self.exit_code is None:
            return {}
        return {"exit_code": self.exit_code}


def execute_test_solver(
    args: argparse.Namespace,
    test_name: str,
    workdir: Path,
    mpi_processes: int,
) -> TestSolverExecution:
    native = find_pflotran_native({}, args.pflotran_exe)
    if native:
        print(f"[INFO] Running native PFLOTRAN for {test_name}: {native}")
        exit_code = run_native(workdir, native, mpi_processes)
        print(f"[INFO] PFLOTRAN exit code: {exit_code}")
        print(f"[INFO] Log: {workdir / 'run_pflotran.log'}")
        if exit_code != 0:
            write_pflotran_error_status(workdir / "TEST_STATUS.txt", exit_code)
            return TestSolverExecution("PFLOTRAN_ERROR", True, exit_code)
        return TestSolverExecution("RAN", True, exit_code)

    if args.prefer_wsl:
        wsl_exe = find_pflotran_wsl()
        if wsl_exe:
            print(f"[INFO] Running PFLOTRAN via WSL for {test_name}: {wsl_exe}")
            exit_code = run_wsl(workdir, wsl_exe, mpi_processes)
            print(f"[INFO] PFLOTRAN WSL exit code: {exit_code}")
            print(f"[INFO] Log: {workdir / 'run_pflotran_wsl.log'}")
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
