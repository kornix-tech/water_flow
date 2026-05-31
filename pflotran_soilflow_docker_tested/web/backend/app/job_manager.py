from __future__ import annotations

import subprocess
import threading
import uuid
import re
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException

from .config import Settings
from .job_store import JobStore
from .models import Job
from .services.command_runner import CommandRunner


JOB_ID_RE = re.compile(r"^[a-f0-9]{32}$")


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
            status="queued",
            command=command,
            run_name=run_name,
            created_at=datetime.utcnow(),
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
            self.store.update(job_id, status="cancelled", error_message="Cancelled by user")
            if job.calculation_id is not None:
                self.store.update_calculation_status(job.calculation_id, "cancelled")
        elif future is not None and future.cancel():
            self.store.update(job_id, status="cancelled", finished_at=datetime.utcnow(), error_message="Cancelled before start")
            if job.calculation_id is not None:
                self.store.update_calculation_status(job.calculation_id, "cancelled")
        else:
            raise HTTPException(status_code=409, detail=f"Job cannot be cancelled from status {job.status}")
        return self.get_job(job_id)

    def _run_job(self, job_id: str, command: list[str], output_dir: Path, log_path: Path) -> int:
        self.store.update(job_id, status="running", started_at=datetime.utcnow())

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
            if current and current.status == "cancelled":
                status = "cancelled"
                error_message = "Cancelled by user"
            else:
                status = "success" if exit_code == 0 else "failed"
                error_message = None if exit_code == 0 else f"Command exited with code {exit_code}"
            self.store.update(
                job_id,
                status=status,
                finished_at=datetime.utcnow(),
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
                status="failed",
                finished_at=datetime.utcnow(),
                error_message=str(exc),
            )
            if current and current.calculation_id is not None:
                self.store.update_calculation_status(current.calculation_id, "failed")
            return 1
        finally:
            with self._lock:
                self._processes.pop(job_id, None)
