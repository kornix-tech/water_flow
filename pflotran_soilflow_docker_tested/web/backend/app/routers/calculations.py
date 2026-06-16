from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request

from ..job_lifecycle import ACTIVE_JOB_STATUSES
from ..schemas import CalculationRead, CalculationSummary, GenericMessage, JobCreated
from ..services.input_json_service import calculation_read, calculation_summary, read_seed_workbook

router = APIRouter()


def _job_store(request: Request):
    return request.app.state.job_store


@router.get("", response_model=list[CalculationSummary])
def list_calculations(
    request: Request,
    q: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[CalculationSummary]:
    return [calculation_summary(item) for item in _job_store(request).list_calculations(query=q, limit=limit)]


@router.get("/{calculation_id}", response_model=CalculationRead)
def get_calculation(calculation_id: int, request: Request) -> CalculationRead:
    calculation = _job_store(request).get_calculation(calculation_id)
    if calculation is None:
        raise HTTPException(status_code=404, detail="Расчет не найден")
    seed = read_seed_workbook(request.app.state.settings.bundled_default_input_json)
    return calculation_read(calculation, seed)


@router.delete("/{calculation_id}", response_model=GenericMessage)
def delete_calculation(calculation_id: int, request: Request) -> GenericMessage:
    project_job_store = _job_store(request)
    calculation = project_job_store.get_calculation(calculation_id)
    if calculation is None:
        raise HTTPException(status_code=404, detail="Расчет не найден")

    if calculation.job_id:
        job = project_job_store.get(calculation.job_id)
        if job is not None and job.status in ACTIVE_JOB_STATUSES:
            raise HTTPException(status_code=409, detail="Нельзя удалить расчет, пока его задание выполняется")

    result_dir = Path(calculation.result_dir) if calculation.result_dir else None
    if result_dir is not None and result_dir.exists():
        runs_dir = request.app.state.settings.runs_dir.resolve()
        resolved_result_dir = result_dir.resolve()
        if resolved_result_dir == runs_dir or runs_dir not in resolved_result_dir.parents:
            raise HTTPException(status_code=400, detail="Папка результатов находится вне допустимой директории")
        if result_dir.is_symlink() or not result_dir.is_dir():
            raise HTTPException(status_code=400, detail="Папка результатов имеет недопустимый тип")
        # Удаляем только папку конкретного расчета внутри output/runs; внешние пути и symlink запрещены выше.
        shutil.rmtree(resolved_result_dir)

    project_job_store.delete_calculation(calculation_id)
    return GenericMessage(status="deleted", detail=f"{calculation.title} удален")


@router.post("/{calculation_id}/run", response_model=JobCreated)
def run_calculation(calculation_id: int, request: Request) -> JobCreated:
    from .jobs import submit_calculation_run

    return submit_calculation_run(request, calculation_id)
