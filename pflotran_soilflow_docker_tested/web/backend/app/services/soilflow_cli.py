from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from ..config import Settings
from ..file_manager import safe_run_name


TEST_OUTPUT_DIRS = {
    "linear_darcy": "_test_linear_darcy",
    "hydrostatic_vg_no_flow": "_test_hydrostatic_vg_no_flow",
    "unit_gradient_unsat": "_test_unit_gradient_unsat",
    "transient_uniform_storage_vg": "_test_transient_uniform_storage_vg",
}


def _python_script(settings: Settings, script_name: str) -> list[str]:
    return ["python3", str(settings.scripts_dir / script_name)]


def default_input_json(settings: Settings) -> Path:
    return settings.default_input_json


def demo_command(settings: Settings, run_name: str = "demo_richards", input_json: Path | None = None) -> tuple[list[str], str, Path]:
    run_name = safe_run_name(run_name)
    output_dir = settings.runs_dir / run_name
    command = _python_script(settings, "soilflow_pflotran.py") + [
        "--mode",
        "demo",
        "--input-json",
        str(input_json or default_input_json(settings)),
        "--workdir",
        str(output_dir),
        "--run",
        "--pflotran-exe",
        str(settings.pflotran_exe),
    ]
    return command, run_name, output_dir


def test_command(settings: Settings, test_name: str) -> tuple[list[str], str | None, Path]:
    if test_name != "all" and test_name not in TEST_OUTPUT_DIRS:
        raise HTTPException(status_code=400, detail=f"Unknown test: {test_name}")
    run_name = None if test_name == "all" else TEST_OUTPUT_DIRS[test_name]
    output_dir = settings.output_dir
    command = _python_script(settings, "soilflow_pflotran.py") + [
        "--mode",
        "_test",
        "--test",
        test_name,
        "--input-json",
        str(default_input_json(settings)),
        "--output-dir",
        str(settings.output_dir),
        "--run",
        "--pflotran-exe",
        str(settings.pflotran_exe),
    ]
    return command, run_name, output_dir


def visualization_command(settings: Settings, run_name: str) -> tuple[list[str], str, Path]:
    run_name = safe_run_name(run_name)
    run_dir = settings.runs_dir / run_name
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail="Run directory was not found")
    output_dir = run_dir / "plots"
    command = _python_script(settings, "soilflow_visualize.py") + [
        "--run-dir",
        str(run_dir),
        "--output-dir",
        str(output_dir),
        "--speed-ms",
        "400",
    ]
    return command, run_name, output_dir
