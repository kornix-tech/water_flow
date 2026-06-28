#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
soilflow_pflotran.py

Минимальная Python-обвязка для исследовательской программы SoilFlow/PFLOTRAN:
1) читает JSON-снимок параметров почвенной задачи;
2) генерирует PFLOTRAN input deck для RICHARDS mode;
3) пишет вспомогательный CSV с погодным форсингом;
4) при наличии PFLOTRAN запускает расчёт;
5) передаёт специальный режим _test в verification runner.

Режим demo:
- формирует структурированную сетку 1D/2D/3D;
- верхний поток задаётся как средний чистый поток по таблице Weather:
  precipitation + irrigation - potential soil evaporation;
- root uptake, динамические грунтовые воды и дренаж представлены в JSON
  как контракт расширения.

Режим _test обслуживается модулем soilflow_pflotran_modules.verification_runner,
чтобы набор проверочных расчётов можно было развивать независимо от demo-mode.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from soilflow_pflotran_modules.floodplain_deck_writer import (
    generate_floodplain_drainage_input,
    write_floodplain_drainage_summary,
)
from soilflow_pflotran_modules.demo_deck_writer import (
    DIMENSION_LABELS,
    build_demo_grid,
    generate_standard_pflotran_input,
)
from soilflow_pflotran_modules.input_contract import as_bool, as_float, as_int, clean_key
from soilflow_pflotran_modules.physical_models import (
    model_pair_label,
    normalize_model_token,
)
from soilflow_pflotran_modules.solver_runner import (
    find_pflotran_native,
    find_pflotran_wsl,
    run_native,
    run_wsl,
)
from soilflow_pflotran_modules.surface_balance import (
    Derived,
    compute_derived,
    normalize_weather_row,
    write_weather_csv,
)
from soilflow_pflotran_modules.tabular_curves import (
    build_tabular_characteristic_curve_assets,
    build_tabular_permeability_assets,
)
from soilflow_pflotran_modules.test_registry import TEST_REGISTRY
from soilflow_pflotran_modules.verification_runner import run_test_mode

CONFIG_SHEETS = {
    "01_Project",
    "02_Domain",
    "03_Soil",
    "04_Initial_BC",
    "05_Time_Forcing",
    "06_ET_Roots",
    "07_Irrigation_Drainage",
    "08_Groundwater",
    "09_Solver",
}


def read_input_document(input_json: Path) -> dict[str, Any]:
    with input_json.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("JSON исходных данных должен быть объектом")
    return data


def read_params(input_json: Path) -> dict[str, Any]:
    data = read_input_document(input_json)
    params: dict[str, Any] = {}
    for tab in data.get("tabs", []):
        if tab.get("kind") != "fields" or tab.get("id") not in CONFIG_SHEETS:
            continue
        for field in tab.get("fields", []):
            key = field.get("key")
            if key in (None, ""):
                continue
            params[clean_key(key)] = field.get("value")
    return params


def read_soil_curve_tables(input_json: Path) -> list[dict[str, Any]]:
    data = read_input_document(input_json)
    tables = data.get("soil_curve_tables", [])
    return tables if isinstance(tables, list) else []


def read_weather(input_json: Path) -> list[dict[str, Any]]:
    data = read_input_document(input_json)
    rows: list[dict[str, Any]] = []
    for tab in data.get("tabs", []):
        if tab.get("id") != "10_Weather_Daily":
            continue
        for row in tab.get("weather", []):
            normalized_row = normalize_weather_row(row)
            if normalized_row is not None:
                rows.append(normalized_row)
    if not rows:
        raise ValueError("JSON исходных данных не содержит строк погодного форсинга")
    return rows


# -----------------------------------------------------------------------------
# Demo mode
# -----------------------------------------------------------------------------
def generate_pflotran_input(
    params: dict[str, Any],
    derived: Derived,
    characteristic_curve_lines: list[str] | None = None,
    permeability_function_lines: list[str] | None = None,
) -> str:
    if normalize_model_token(params.get("scenario_type"), "standard") == "floodplain_controlled_drainage":
        return generate_floodplain_drainage_input(params)
    return generate_standard_pflotran_input(
        params,
        derived,
        characteristic_curve_lines=characteristic_curve_lines,
        permeability_function_lines=permeability_function_lines,
    )


def write_summary(
    params: dict[str, Any],
    derived: Derived,
    weather: list[dict[str, Any]],
    path: Path,
    soil_curve_table_count: int = 0,
) -> None:
    if normalize_model_token(params.get("scenario_type"), "standard") == "floodplain_controlled_drainage":
        write_floodplain_drainage_summary(params, weather, path)
        return

    grid = build_demo_grid(params)
    lines = [
        "SoilFlow/PFLOTRAN run summary",
        "=============================",
        "",
        f"Project: {params.get('project_name')}",
        f"Model mode: {params.get('model_mode')}",
        f"Dimension: {DIMENSION_LABELS[grid.dimension]}",
        f"Grid NXYZ: {grid.nx} {grid.ny} {grid.nz}",
        f"Grid DXYZ: {grid.dx_m:.8g} {grid.dy_m:.8g} {grid.dz_m:.8g} m",
        "",
        "Derived parameters:",
        f"  soil_model_pair     = {model_pair_label(derived.retention_model, derived.conductivity_model)}",
        f"  soil_curve_tables   = {soil_curve_table_count}",
        f"  residual_saturation = {derived.residual_saturation:.8g}",
        f"  vg_m                = {derived.vg_m:.8g}",
        f"  bc_lambda           = {derived.bc_lambda:.8g}",
        f"  alpha_pa_inv        = {derived.alpha_pa_inv:.8e} 1/Pa",
        f"  perm_x              = {derived.intrinsic_perm_x_m2:.8e} m2",
        f"  perm_y              = {derived.intrinsic_perm_y_m2:.8e} m2",
        f"  perm_z              = {derived.intrinsic_perm_z_m2:.8e} m2",
        f"  mean_top_flux       = {derived.mean_top_flux_m_s:.8e} m/s",
        "",
        "Weather summary:",
        f"  days                = {len(weather)}",
        f"  mean net input      = {sum(r['net_surface_input_mm_day'] for r in weather)/len(weather):.4g} mm/day",
        "",
        "Note:",
        "  The current demo maps Weather to a constant mean top flux.",
        "  Root uptake, drainage and dynamic groundwater are configured in JSON as extension contracts.",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")

# -----------------------------------------------------------------------------
# _test mode: analytical saturated column / linearized Richards-Darcy solution
# -----------------------------------------------------------------------------







# -----------------------------------------------------------------------------
# Main modes
# -----------------------------------------------------------------------------
def run_demo_mode(args: argparse.Namespace) -> int:
    input_json = args.input_json.resolve()
    if not input_json.exists():
        print(f"ERROR: input JSON not found: {input_json}", file=sys.stderr)
        return 2

    params = read_params(input_json)
    weather = read_weather(input_json)
    soil_curve_tables = read_soil_curve_tables(input_json)
    derived = compute_derived(params, weather)

    workdir = args.workdir
    workdir.mkdir(parents=True, exist_ok=True)

    write_weather_csv(weather, workdir / "forcing_daily.csv")
    characteristic_curve_lines = None
    permeability_function_lines = None
    if derived.retention_model == "tabular":
        tabular_assets = build_tabular_characteristic_curve_assets(
            tables=soil_curve_tables,
            workdir=workdir,
            theta_s=as_float(params.get("theta_s")),
            ksat_m_s=as_float(params.get("ksat_m_s")),
            rho=as_float(params.get("rho_water_kg_m3"), 997.0),
            gravity=as_float(params.get("gravity_m_s2"), 9.80665),
            curve_name="cc_soil",
        )
        characteristic_curve_lines = tabular_assets.characteristic_curve_lines
    elif derived.conductivity_model == "tabular":
        tabular_assets = build_tabular_permeability_assets(
            tables=soil_curve_tables,
            workdir=workdir,
            theta_s=as_float(params.get("theta_s")),
            ksat_m_s=as_float(params.get("ksat_m_s")),
        )
        permeability_function_lines = tabular_assets.permeability_function_lines

    input_text = generate_pflotran_input(
        params,
        derived,
        characteristic_curve_lines=characteristic_curve_lines,
        permeability_function_lines=permeability_function_lines,
    )
    (workdir / "pflotran.in").write_text(input_text, encoding="utf-8")
    write_summary(params, derived, weather, workdir / "soilflow_run_summary.txt", soil_curve_table_count=len(soil_curve_tables))

    print(f"[OK] Generated: {workdir / 'pflotran.in'}")
    print(f"[OK] Generated: {workdir / 'forcing_daily.csv'}")
    print(f"[OK] Generated: {workdir / 'soilflow_run_summary.txt'}")

    if args.dry_run or not args.run:
        print("[INFO] Dry generation completed. Use --run to launch PFLOTRAN.")
        return 0

    mpi_n = as_int(params.get("mpi_processes"), 1)
    native = find_pflotran_native(params, args.pflotran_exe)
    if native:
        print(f"[INFO] Running native PFLOTRAN: {native}")
        rc = run_native(workdir, native, mpi_n)
        print(f"[INFO] Native PFLOTRAN exit code: {rc}")
        print(f"[INFO] Log: {workdir / 'run_pflotran.log'}")
        return rc

    prefer_wsl = args.prefer_wsl or as_bool(params.get("prefer_wsl"), True)
    if prefer_wsl:
        wsl_exe = find_pflotran_wsl()
        if wsl_exe:
            print(f"[INFO] Running PFLOTRAN via WSL: {wsl_exe}")
            rc = run_wsl(workdir, wsl_exe, mpi_n)
            print(f"[INFO] WSL PFLOTRAN exit code: {rc}")
            print(f"[INFO] Log: {workdir / 'run_pflotran_wsl.log'}")
            return rc

    print(
        f"""
[WARN] PFLOTRAN executable was not found.

Generated input files are ready in:
  {workdir}

From Linux/WSL:
  cd {workdir}
  mpirun -n 1 pflotran -pflotranin pflotran.in
"""
    )
    return 0




def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate and optionally run PFLOTRAN Richards inputs from JSON.")
    parser.add_argument("--input-json", type=Path, required=True, help="Path to JSON input snapshot.")
    parser.add_argument("--workdir", type=Path, default=None, help="Run directory.")
    parser.add_argument("--output-dir", type=Path, default=None, help="Output root for test-suite runs.")
    parser.add_argument("--mode", choices=["demo", "_test", "test"], default="demo", help="Run mode: demo or _test.")
    parser.add_argument(
        "--test",
        default="all",
        choices=list(TEST_REGISTRY) + ["all"],
        help="Какой аналитический verification-test запустить.",
    )
    parser.add_argument("--run", action="store_true", help="Run PFLOTRAN if executable is found.")
    parser.add_argument("--dry-run", action="store_true", help="Generate files only.")
    parser.add_argument("--pflotran-exe", default=None, help="Native Linux/Windows PFLOTRAN executable.")
    parser.add_argument("--prefer-wsl", action="store_true", help="Prefer WSL PFLOTRAN when native executable is absent.")
    args = parser.parse_args(argv)

    if args.mode == "test":
        args.mode = "_test"
    if args.workdir is None:
        args.workdir = None if args.mode == "_test" else Path("runs/demo_richards")

    if args.mode == "_test":
        return run_test_mode(args)
    return run_demo_mode(args)


if __name__ == "__main__":
    raise SystemExit(main())
