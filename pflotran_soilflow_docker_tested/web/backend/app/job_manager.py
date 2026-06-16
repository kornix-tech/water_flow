from __future__ import annotations

import subprocess
import threading
import uuid
import re
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from fastapi import HTTPException

from .config import Settings
from .job_lifecycle import (
    JOB_STATUS_CANCELLED,
    JOB_STATUS_FAILED,
    JOB_STATUS_QUEUED,
    JOB_STATUS_RUNNING,
    JOB_STATUS_SUCCESS,
)
from .job_store import JobStore
from .models import Job
from .services.command_runner import CommandRunner


JOB_ID_RE = re.compile(r"^[a-f0-9]{32}$")
LOG_ERROR_RE = re.compile(r"(ERROR|Error|Traceback|Exception)[:\s].*")


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _job_failure_message(exit_code: int, log_path: Path) -> str:
    default_message = f"Command exited with code {exit_code}"
    if not log_path.exists():
        return default_message
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")[-120_000:]
    except OSError:
        return default_message
    # Для PFLOTRAN и Python-обвязки первая строка ERROR/Traceback обычно
    # содержит предметную причину; код выхода сам по себе пользователю мало помогает.
    for line in reversed(text.splitlines()):
        stripped = line.strip()
        if stripped and LOG_ERROR_RE.search(stripped):
            return stripped[:500]
    return default_message


class JobManager:
    def __init__(self, settings: Settings, store: JobStore) -> None:
        self.settings = settings
        self.store = store
        self.runner = CommandRunner()
        self.executor = ThreadPoolExecutor(max_workers=settings.job_workers)
        self._lock = threading.Lock()
        self._futures: dict[str, Future[int]] = {}
        self._processes: dict[str, subprocess.Popen[str]] = {}

    def submit(
        self,
        kind: str,
        command: list[str],
        output_dir: Path,
        run_name: str | None = None,
        calculation_id: int | None = None,
    ) -> Job:
        job_id = uuid.uuid4().hex
        job_dir = self.settings.jobs_dir / job_id
        log_path = job_dir / "job.log"
        job = Job(
            id=job_id,
            kind=kind,
            status=JOB_STATUS_QUEUED,
            command=command,
            run_name=run_name,
            created_at=_utcnow(),
            started_at=None,
            finished_at=None,
            exit_code=None,
            log_path=str(log_path),
            output_dir=str(output_dir),
            error_message=None,
            calculation_id=calculation_id,
        )
        self.store.create(job)
        future = self.executor.submit(self._run_job, job_id, command, output_dir, log_path)
        with self._lock:
            self._futures[job_id] = future
        return job

    def list_jobs(self) -> list[Job]:
        return self.store.list()

    def get_job(self, job_id: str) -> Job:
        if not JOB_ID_RE.fullmatch(job_id):
            raise HTTPException(status_code=400, detail="Invalid job id")
        job = self.store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job was not found")
        return job

    def cancel(self, job_id: str) -> Job:
        job = self.get_job(job_id)
        with self._lock:
            process = self._processes.get(job_id)
            future = self._futures.get(job_id)
        if process is not None and process.poll() is None:
            process.terminate()
            self.store.update(job_id, status=JOB_STATUS_CANCELLED, error_message="Cancelled by user")
            if job.calculation_id is not None:
                self.store.update_calculation_status(job.calculation_id, JOB_STATUS_CANCELLED)
        elif future is not None and future.cancel():
            self.store.update(
                job_id,
                status=JOB_STATUS_CANCELLED,
                finished_at=_utcnow(),
                error_message="Cancelled before start",
            )
            if job.calculation_id is not None:
                self.store.update_calculation_status(job.calculation_id, JOB_STATUS_CANCELLED)
        else:
            raise HTTPException(status_code=409, detail=f"Job cannot be cancelled from status {job.status}")
        return self.get_job(job_id)

    def _run_job(self, job_id: str, command: list[str], output_dir: Path, log_path: Path) -> int:
        self.store.update(job_id, status=JOB_STATUS_RUNNING, started_at=_utcnow())

        def remember_process(process: subprocess.Popen[str]) -> None:
            with self._lock:
                self._processes[job_id] = process

        try:
            exit_code = self.runner.run(
                command=command,
                cwd=self.settings.workspace,
                log_path=log_path,
                on_process=remember_process,
                timeout=self.settings.job_timeout_seconds,
            )
            current = self.store.get(job_id)
            if current and current.status == JOB_STATUS_CANCELLED:
                status = JOB_STATUS_CANCELLED
                error_message = "Cancelled by user"
            else:
                status = JOB_STATUS_SUCCESS if exit_code == 0 else JOB_STATUS_FAILED
                error_message = None if exit_code == 0 else _job_failure_message(exit_code, log_path)
            self.store.update(
                job_id,
                status=status,
                finished_at=_utcnow(),
                exit_code=exit_code,
                error_message=error_message,
            )
            if current and current.calculation_id is not None:
                self.store.update_calculation_status(current.calculation_id, status)
            return exit_code
        except Exception as exc:
            current = self.store.get(job_id)
            self.store.update(
                job_id,
                status=JOB_STATUS_FAILED,
                finished_at=_utcnow(),
                error_message=str(exc),
            )
            if current and current.calculation_id is not None:
                self.store.update_calculation_status(current.calculation_id, JOB_STATUS_FAILED)
            return 1
        finally:
            with self._lock:
                self._processes.pop(job_id, None)
