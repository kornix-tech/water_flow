from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Callable


ProcessCallback = Callable[[subprocess.Popen[str]], None]


class CommandRunner:
    def run(
        self,
        command: list[str],
        cwd: Path,
        log_path: Path,
        on_process: ProcessCallback | None = None,
        timeout: float | None = None,
    ) -> int:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        cwd.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8", errors="replace") as log:
            log.write(f"$ {' '.join(command)}\n")
            log.write(f"cwd={cwd}\n\n")
            log.flush()
            process = subprocess.Popen(
                command,
                cwd=str(cwd),
                env=self._child_environment(),
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )
            if on_process is not None:
                on_process(process)
            try:
                return process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                log.write(f"\n[TIMEOUT] Command exceeded job timeout: {timeout} seconds\n")
                log.flush()
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    log.write("[TIMEOUT] Command did not terminate gracefully; killing process\n")
                    log.flush()
                    process.kill()
                    process.wait()
                return 124

    def _child_environment(self) -> dict[str, str]:
        env = dict(os.environ)
        # Дочерние расчёты не должны наследовать токен web API: он не нужен PFLOTRAN
        # и может случайно попасть в диагностические дампы внешних процессов.
        env.pop("SOILFLOW_API_TOKEN", None)
        return env
