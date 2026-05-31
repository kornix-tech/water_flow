from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Job:
    id: str
    kind: str
    status: str
    command: list[str]
    run_name: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    exit_code: int | None
    log_path: str
    output_dir: str
    error_message: str | None
    calculation_id: int | None = None


@dataclass
class Calculation:
    id: int
    title: str
    created_at: datetime
    updated_at: datetime
    input_json: dict
    run_name: str | None
    job_id: str | None
    status: str
    result_dir: str | None
