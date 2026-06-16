from __future__ import annotations

from typing import Literal


JobStatus = Literal["queued", "running", "success", "failed", "cancelled"]
CalculationStatus = Literal["draft", "queued", "running", "success", "failed", "cancelled"]

JOB_STATUS_QUEUED: JobStatus = "queued"
JOB_STATUS_RUNNING: JobStatus = "running"
JOB_STATUS_SUCCESS: JobStatus = "success"
JOB_STATUS_FAILED: JobStatus = "failed"
JOB_STATUS_CANCELLED: JobStatus = "cancelled"

CALCULATION_STATUS_DRAFT: CalculationStatus = "draft"

ACTIVE_JOB_STATUSES = frozenset({JOB_STATUS_QUEUED, JOB_STATUS_RUNNING})
TERMINAL_JOB_STATUSES = frozenset({JOB_STATUS_SUCCESS, JOB_STATUS_FAILED, JOB_STATUS_CANCELLED})
