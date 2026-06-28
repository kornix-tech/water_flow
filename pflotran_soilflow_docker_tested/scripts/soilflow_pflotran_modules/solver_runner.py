from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SolverExecutionResult:
    """Единый результат запуска внешнего расчетного ядра."""

    return_code: int
    log_path: Path
    command_label: str
    timed_out: bool = False


def find_pflotran_native(params: dict[str, Any], cli_exe: str | None) -> str | None:
    candidates: list[str] = []
    if cli_exe:
        candidates.append(cli_exe)
    env_exe = os.environ.get("PFLOTRAN_EXE")
    if env_exe:
        candidates.append(env_exe)
    configured_exe = params.get("pflotran_exe") if params else None
    if configured_exe not in (None, ""):
        candidates.append(str(configured_exe))
    path_exe = shutil.which("pflotran")
    if path_exe:
        candidates.append(path_exe)

    for candidate in candidates:
        path = Path(str(candidate).strip('"'))
        if path.exists():
            return str(path)
        if shutil.which(str(candidate)):
            return str(candidate)
    return None


def has_wsl() -> bool:
    return shutil.which("wsl") is not None


def wsl_path(path: Path) -> str:
    completed = subprocess.run(
        ["wsl", "wslpath", "-a", str(path)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"wslpath failed: {completed.stderr}")
    return completed.stdout.strip()


def find_pflotran_wsl() -> str | None:
    if not has_wsl():
        return None
    cmd = (
        "if command -v pflotran >/dev/null 2>&1; then command -v pflotran; "
        "elif [ -x \"$HOME/pflotran/src/pflotran/pflotran\" ]; then echo \"$HOME/pflotran/src/pflotran/pflotran\"; "
        "elif [ -x \"$HOME/pflotran_build/pflotran/src/pflotran/pflotran\" ]; then echo \"$HOME/pflotran_build/pflotran/src/pflotran/pflotran\"; "
        "else true; fi"
    )
    completed = subprocess.run(["wsl", "bash", "-lc", cmd], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if completed.returncode != 0:
        return None
    output = completed.stdout.strip()
    return output if output else None


def run_native(workdir: Path, pflotran_exe: str, mpi_processes: int, timeout_seconds: float | None = None) -> int:
    return run_native_solver(workdir, pflotran_exe, mpi_processes, timeout_seconds=timeout_seconds).return_code


def run_native_solver(
    workdir: Path,
    pflotran_exe: str,
    mpi_processes: int,
    timeout_seconds: float | None = None,
) -> SolverExecutionResult:
    log_path = workdir / "run_pflotran.log"
    mpirun = shutil.which("mpirun") or shutil.which("mpiexec")
    if mpirun and mpi_processes >= 1:
        cmd = [mpirun, "-n", str(mpi_processes), pflotran_exe, "-pflotranin", "pflotran.in"]
    else:
        cmd = [pflotran_exe, "-pflotranin", "pflotran.in"]

    with log_path.open("w", encoding="utf-8", errors="replace") as log:
        log.write("COMMAND: " + " ".join(shlex.quote(part) for part in cmd) + "\n\n")
        try:
            process = subprocess.run(
                cmd,
                cwd=workdir,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=timeout_seconds,
            )
            return SolverExecutionResult(process.returncode, log_path, "native PFLOTRAN")
        except subprocess.TimeoutExpired:
            log.write(f"\n[TIMEOUT] PFLOTRAN exceeded solver timeout: {timeout_seconds} seconds\n")
            return SolverExecutionResult(124, log_path, "native PFLOTRAN", timed_out=True)


def run_wsl(workdir: Path, pflotran_wsl: str, mpi_processes: int, timeout_seconds: float | None = None) -> int:
    return run_wsl_solver(workdir, pflotran_wsl, mpi_processes, timeout_seconds=timeout_seconds).return_code


def run_wsl_solver(
    workdir: Path,
    pflotran_wsl: str,
    mpi_processes: int,
    timeout_seconds: float | None = None,
) -> SolverExecutionResult:
    log_path = workdir / "run_pflotran_wsl.log"
    workdir_wsl = wsl_path(workdir)

    run_line = (
        f"cd {shlex.quote(workdir_wsl)} && "
        f"if command -v mpirun >/dev/null 2>&1; then "
        f"mpirun -n {int(mpi_processes)} {shlex.quote(pflotran_wsl)} -pflotranin pflotran.in; "
        f"else {shlex.quote(pflotran_wsl)} -pflotranin pflotran.in; fi"
    )

    with log_path.open("w", encoding="utf-8", errors="replace") as log:
        log.write("WSL COMMAND: " + run_line + "\n\n")
        try:
            process = subprocess.run(
                ["wsl", "bash", "-lc", run_line],
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=timeout_seconds,
            )
            return SolverExecutionResult(process.returncode, log_path, "PFLOTRAN via WSL")
        except subprocess.TimeoutExpired:
            log.write(f"\n[TIMEOUT] PFLOTRAN via WSL exceeded solver timeout: {timeout_seconds} seconds\n")
            return SolverExecutionResult(124, log_path, "PFLOTRAN via WSL", timed_out=True)
