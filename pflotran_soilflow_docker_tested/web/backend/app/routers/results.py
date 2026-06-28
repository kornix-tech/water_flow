from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from ..file_manager import safe_resolve_under, safe_run_name
from ..schemas import RunInfo, RunStatusOverview, TestRunStatus, TestSuiteStatus
from ..services.run_status_overview_service import read_run_status_overview
from ..services.test_run_status_service import read_test_run_status
from ..services.test_suite_summary_service import read_test_suite_status

router = APIRouter()


def _run_info(run_dir: Path, file_manager, *, include_files: bool = True) -> RunInfo:
    files = file_manager.list_relative_files(run_dir, max_files=500) if include_files else []
    return RunInfo(
        run_name=run_dir.name,
        path=str(run_dir),
        has_test_status=(run_dir / "TEST_STATUS.txt").exists(),
        has_suite_status=(run_dir / "TEST_SUITE_STATUS.txt").exists(),
        has_visualization=(run_dir / "plots" / "profiles_animation.html").exists(),
        files=files[:500],
    )


@router.get("/runs", response_model=list[RunInfo])
def list_runs(request: Request) -> list[RunInfo]:
    runs_dir = request.app.state.settings.runs_dir
    if not runs_dir.exists():
        return []
    return [
        _run_info(path, request.app.state.file_manager, include_files=False)
        for path in sorted(runs_dir.iterdir())
        if path.is_dir() and not path.is_symlink()
    ]


@router.get("/runs/{run_name}", response_model=RunInfo)
def get_run(run_name: str, request: Request) -> RunInfo:
    run_dir = request.app.state.file_manager.run_dir(run_name)
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail="Run directory was not found")
    return _run_info(run_dir, request.app.state.file_manager)


@router.get("/runs/{run_name}/status")
def get_run_status(run_name: str, request: Request):
    run_dir = request.app.state.file_manager.run_dir(run_name)
    for filename in ("TEST_STATUS.txt", "TEST_SUITE_STATUS.txt", "VISUALIZATION_STATUS.txt"):
        path = safe_resolve_under(run_dir, filename)
        if path.exists():
            return FileResponse(path, media_type="text/plain")
    raise HTTPException(status_code=404, detail="Status file was not found")


@router.get("/runs/{run_name}/test-suite", response_model=TestSuiteStatus)
def get_run_test_suite_status(run_name: str, request: Request) -> TestSuiteStatus:
    run_dir = request.app.state.file_manager.run_dir(run_name)
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail="Run directory was not found")
    try:
        return TestSuiteStatus(**read_test_suite_status(run_name, run_dir))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Test-suite status was not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/runs/{run_name}/test-status", response_model=TestRunStatus)
def get_run_test_status(run_name: str, request: Request) -> TestRunStatus:
    run_dir = request.app.state.file_manager.run_dir(run_name)
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail="Run directory was not found")
    try:
        return TestRunStatus(**read_test_run_status(run_name, run_dir))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Test status was not found") from exc
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/runs/{run_name}/overview", response_model=RunStatusOverview)
def get_run_status_overview(run_name: str, request: Request) -> RunStatusOverview:
    run_dir = request.app.state.file_manager.run_dir(run_name)
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail="Run directory was not found")
    try:
        return RunStatusOverview(**read_run_status_overview(run_name, run_dir))
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/runs/{run_name}/plots")
def get_run_plots(run_name: str, request: Request):
    plots_dir = request.app.state.file_manager.plots_dir(run_name)
    if not plots_dir.exists():
        return []
    return request.app.state.file_manager.list_relative_files(plots_dir, max_files=500)


@router.get("/runs/{run_name}/file/{file_path:path}")
def get_run_file(run_name: str, file_path: str, request: Request):
    safe_run_name(run_name)
    run_dir = request.app.state.file_manager.run_dir(run_name)
    target = safe_resolve_under(run_dir, file_path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File was not found")
    return FileResponse(target, filename=target.name)
