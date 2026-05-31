from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from ..schemas import CustomRunRequest, JobCreated, JobRead
from ..services import soilflow_cli
from ..services.input_json_service import calculation_to_workbook, read_seed_workbook, seed_workbook_to_json, write_workbook_json
from ..services.log_service import tail_text

router = APIRouter()


def _manager(request: Request):
    return request.app.state.job_manager


def _settings(request: Request):
    return request.app.state.settings


@router.post("/run-demo", response_model=JobCreated)
def run_demo(request: Request) -> JobCreated:
    latest = request.app.state.job_store.latest_calculation()
    if latest is None:
        workbook = read_seed_workbook(_settings(request).default_input_json)
        latest = request.app.state.job_store.create_calculation(seed_workbook_to_json(workbook))
    return submit_calculation_run(request, latest.id)


@router.post("/run-test-suite", response_model=JobCreated)
def run_test_suite(request: Request) -> JobCreated:
    command, run_name, output_dir = soilflow_cli.test_command(_settings(request), "all")
    job = _manager(request).submit("test-suite", command, output_dir, run_name)
    return JobCreated(job_id=job.id, status=job.status, run_name=job.run_name)


@router.post("/run-test/{test_name}", response_model=JobCreated)
def run_test(test_name: str, request: Request) -> JobCreated:
    command, run_name, output_dir = soilflow_cli.test_command(_settings(request), test_name)
    job = _manager(request).submit("test", command, output_dir, run_name)
    return JobCreated(job_id=job.id, status=job.status, run_name=job.run_name)


@router.post("/run-visualization/{run_name}", response_model=JobCreated)
def run_visualization(run_name: str, request: Request) -> JobCreated:
    command, normalized_run_name, output_dir = soilflow_cli.visualization_command(_settings(request), run_name)
    calculation = request.app.state.job_store.get_calculation_by_run_name(normalized_run_name)
    if calculation is not None:
        input_json = _settings(request).tmp_dir / "calculations" / f"calculation_{calculation.id:06d}.json"
        write_workbook_json(calculation_to_workbook(calculation), input_json)
        command.extend(["--input-json", str(input_json)])
    job = _manager(request).submit("visualization", command, output_dir, normalized_run_name)
    return JobCreated(job_id=job.id, status=job.status, run_name=job.run_name)


@router.post("/run-custom", response_model=JobCreated)
def run_custom(payload: CustomRunRequest, request: Request) -> JobCreated:
    if payload.calculation_id is None:
        return run_demo(request)
    return submit_calculation_run(request, payload.calculation_id, payload.run_name)


def submit_calculation_run(request: Request, calculation_id: int, run_name: str | None = None) -> JobCreated:
    settings = _settings(request)
    calculation = request.app.state.job_store.get_calculation(calculation_id)
    if calculation is None:
        raise HTTPException(status_code=404, detail="Расчет не найден")
    workbook = calculation_to_workbook(calculation)
    input_json = settings.tmp_dir / "calculations" / f"calculation_{calculation.id:06d}.json"
    write_workbook_json(workbook, input_json)
    normalized_run_name = run_name or f"calculation_{calculation.id:06d}"
    command, command_run_name, output_dir = soilflow_cli.demo_command(settings, normalized_run_name, input_json=input_json)
    job = _manager(request).submit("calculation", command, output_dir, command_run_name, calculation_id=calculation.id)
    request.app.state.job_store.set_calculation_job(
        calculation.id,
        run_name=command_run_name,
        job_id=job.id,
        result_dir=str(output_dir),
        status=job.status,
    )
    return JobCreated(job_id=job.id, status=job.status, run_name=job.run_name)


@router.get("", response_model=list[JobRead])
def list_jobs(request: Request) -> list[JobRead]:
    return [JobRead(**job.__dict__) for job in _manager(request).list_jobs()]


@router.get("/{job_id}", response_model=JobRead)
def get_job(job_id: str, request: Request) -> JobRead:
    return JobRead(**_manager(request).get_job(job_id).__dict__)


@router.get("/{job_id}/log", response_model=str)
def get_job_log(job_id: str, request: Request) -> str:
    job = _manager(request).get_job(job_id)
    return tail_text(Path(job.log_path))


@router.post("/{job_id}/cancel", response_model=JobRead)
def cancel_job(job_id: str, request: Request) -> JobRead:
    return JobRead(**_manager(request).cancel(job_id).__dict__)
