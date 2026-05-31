from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    service: str


class SystemInfo(BaseModel):
    soilflow_home: str
    workspace: str
    pflotran_exe: str
    pflotran_exists: bool
    job_workers: int
    auth_mode: str
    frontend_available: bool
    api_docs_enabled: bool
    hsts_enabled: bool
    api_rate_limit_per_minute: int


class ProjectInfo(BaseModel):
    id: str
    name: str
    workspace: str


class CreateProjectRequest(BaseModel):
    name: str = Field(default="default", min_length=1, max_length=80)


class JobRead(BaseModel):
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


class JobCreated(BaseModel):
    job_id: str
    status: str
    run_name: str | None = None


class RunInfo(BaseModel):
    run_name: str
    path: str
    has_test_status: bool
    has_suite_status: bool
    has_visualization: bool
    files: list[str]


class FileInfo(BaseModel):
    path: str
    name: str
    size: int
    is_dir: bool


class InputField(BaseModel):
    sheet: str
    row: int
    section: str | None = None
    key: str
    value: Any
    value_type: str
    unit: str | None = None
    description: str | None = None
    pflotran: str | None = None
    note: str | None = None


class WeatherRow(BaseModel):
    row: int | None = None
    date: str
    precipitation_mm_day: float = 0.0
    irrigation_mm_day: float = 0.0
    epot_mm_day: float = 0.0
    tpot_mm_day: float = 0.0
    groundwater_depth_m: float | None = None
    comment: str | None = None


class InputTab(BaseModel):
    id: str
    title: str
    kind: str
    description: str | None = None
    fields: list[InputField] = Field(default_factory=list)
    weather: list[WeatherRow] = Field(default_factory=list)


class InputWorkbook(BaseModel):
    filename: str
    updated_at: str | None = None
    tabs: list[InputTab]
    calculation_id: int | None = None
    calculation_title: str | None = None
    calculation_created_at: str | None = None
    calculation_status: str | None = None


class CustomRunRequest(BaseModel):
    run_name: str = Field(default="custom_richards", min_length=1, max_length=120)
    calculation_id: int | None = None


class CalculationSummary(BaseModel):
    id: int
    title: str
    created_at: datetime
    updated_at: datetime
    run_name: str | None = None
    job_id: str | None = None
    status: str
    result_dir: str | None = None
    has_results: bool = False


class CalculationRead(CalculationSummary):
    input: InputWorkbook


class GenericMessage(BaseModel):
    status: str
    detail: str | None = None
    data: dict[str, Any] | None = None
