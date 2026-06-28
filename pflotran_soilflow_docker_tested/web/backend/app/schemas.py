from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    service: str


class ReadinessResponse(BaseModel):
    status: str
    service: str
    checks: dict[str, bool]
    details: dict[str, str] = Field(default_factory=dict)
    schema_version: int | None = None


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


class TestSuiteResult(BaseModel):
    test_id: str
    status: str
    verification_level: str | None = None
    output_dir: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)


class TestSuiteStatus(BaseModel):
    run_name: str
    status: str
    summary: dict[str, str | int]
    results: list[TestSuiteResult]
    strict_readiness_plan: dict[str, Any] | None = None
    source: str
    files: list[str]


class TestRunStatus(BaseModel):
    run_name: str
    status: str
    test_id: str | None = None
    fields: dict[str, str | int | float | bool]
    messages: list[str] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    source: str
    files: list[str]


class StatusSummaryMetric(BaseModel):
    label: str
    value: str


class StatusSummaryItem(BaseModel):
    kind: str
    title: str
    status: str
    subtitle: str | None = None
    metrics: list[StatusSummaryMetric] = Field(default_factory=list)
    source: str | None = None
    files: list[str] = Field(default_factory=list)
    messages: list[str] = Field(default_factory=list)


class RunStatusOverview(BaseModel):
    run_name: str
    items: list[StatusSummaryItem]


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


class SoilCurvePointBase(BaseModel):
    point_index: int = Field(ge=0)
    pressure_head_m: float | None = None
    pressure_pa: float | None = None
    water_content: float | None = Field(default=None, ge=0.0)
    saturation: float | None = Field(default=None, ge=0.0, le=1.0)
    relative_permeability: float | None = Field(default=None, ge=0.0)
    hydraulic_conductivity_m_s: float | None = Field(default=None, ge=0.0)
    comment: str | None = Field(default=None, max_length=500)


class SoilCurvePointRead(SoilCurvePointBase):
    id: int
    table_id: int


class SoilCurveTableBase(BaseModel):
    curve_name: str = Field(min_length=1, max_length=120)
    curve_kind: str = Field(default="retention", min_length=1, max_length=80)
    retention_model: str | None = Field(default=None, max_length=80)
    conductivity_model: str | None = Field(default=None, max_length=80)
    pressure_unit: str = Field(default="Pa", min_length=1, max_length=40)
    saturation_unit: str = Field(default="m3/m3", min_length=1, max_length=40)
    conductivity_unit: str | None = Field(default=None, max_length=40)
    comment: str | None = Field(default=None, max_length=1000)


class SoilCurveTableCreate(SoilCurveTableBase):
    points: list[SoilCurvePointBase] = Field(default_factory=list)


class SoilCurveTableRead(SoilCurveTableBase):
    id: int
    calculation_id: int
    created_at: datetime
    updated_at: datetime
    points: list[SoilCurvePointRead] = Field(default_factory=list)


class GenericMessage(BaseModel):
    status: str
    detail: str | None = None
    data: dict[str, Any] | None = None
