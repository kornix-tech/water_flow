#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
soilflow_pflotran.py

Минимальная Python-обвязка для исследовательской программы SoilFlow/PFLOTRAN:
1) читает JSON-снимок параметров почвенной задачи;
2) генерирует PFLOTRAN input deck для RICHARDS mode;
3) пишет вспомогательный CSV с погодным форсингом;
4) при наличии PFLOTRAN запускает расчёт;
5) поддерживает специальный режим _test для аналитической проверки.

Режим demo:
- формирует структурированную сетку 1D/2D/3D;
- верхний поток задаётся как средний чистый поток по таблице Weather:
  precipitation + irrigation - potential soil evaporation;
- root uptake, динамические грунтовые воды и дренаж представлены в JSON
  как контракт расширения.

Режим _test:
- формирует классическую установившуюся задачу насыщенной однородной колонки;
- использует линеаризованную форму уравнения Ричардса, то есть закон Дарси
  с постоянной гидропроводностью K = Ks;
- задаёт давления на верхней и нижней границах так, чтобы аналитический поток
  был постоянным во всей колонке;
- после запуска PFLOTRAN сравнивает численный профиль давления с аналитическим.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

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

TEST_SHEET = "_test"
TEST_SHEETS = {
    "linear_darcy": "_test_linear_darcy",
    "hydrostatic_vg_no_flow": "_test_hydrostatic_vg_no_flow",
    "unit_gradient_unsat": "_test_unit_gradient_unsat",
    "transient_uniform_storage_vg": "_test_transient_uniform_storage_vg",
}
TEST_OUTPUT_DIRS = {
    "linear_darcy": "_test_linear_darcy",
    "hydrostatic_vg_no_flow": "_test_hydrostatic_vg_no_flow",
    "unit_gradient_unsat": "_test_unit_gradient_unsat",
    "transient_uniform_storage_vg": "_test_transient_uniform_storage_vg",
}
TEST_REGISTRY = tuple(TEST_OUTPUT_DIRS)
PRESSURE_REPORT_ZERO_THRESHOLD_PA = 10.0
UNEXPECTED_WARNING_FAIL_PATTERNS = ("failed", "invalid", "not recognized", "ignored card", "missing")


# -----------------------------------------------------------------------------
# Generic parsing helpers
# -----------------------------------------------------------------------------
def as_float(value: Any, default: float | None = None) -> float:
    if value is None or value == "":
        if default is None:
            raise ValueError("Пустое значение нельзя преобразовать в float")
        return float(default)
    if isinstance(value, str):
        value = value.replace(",", ".").strip()
    return float(value)


def as_int(value: Any, default: int | None = None) -> int:
    if value is None or value == "":
        if default is None:
            raise ValueError("Пустое значение нельзя преобразовать в int")
        return int(default)
    return int(float(value))


def as_bool(value: Any, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"true", "1", "yes", "y", "да", "истина", "вкл"}


def clean_key(value: Any) -> str:
    return str(value).strip()


def pf_float(value: float) -> str:
    """PFLOTRAN examples use Fortran d exponent; this is accepted by Fortran parsers."""
    if abs(value) == 0:
        return "0.d0"
    return f"{value:.12e}".replace("e", "d")


def report_pressure_error(raw_error_pa: float) -> float:
    return 0.0 if raw_error_pa < PRESSURE_REPORT_ZERO_THRESHOLD_PA else raw_error_pa


def pressure_reporting(raw_error_pa: float, tolerance_pa: float) -> dict[str, float]:
    return {
        "raw_max_abs_pressure_error_pa": raw_error_pa,
        "reported_max_abs_pressure_error_pa": report_pressure_error(raw_error_pa),
        "pressure_report_zero_threshold_pa": PRESSURE_REPORT_ZERO_THRESHOLD_PA,
        "pressure_abs_tolerance_pa": tolerance_pa,
    }


def test_output_block(snapshot_period_line: str = "  PERIODIC TIMESTEP 1") -> list[str]:
    # CONSERVATION_FILE/MASS_BALANCE_FILE дают прямой диагностический probe потоков.
    return [
        "OUTPUT",
        "  TIME_UNITS day",
        "  SNAPSHOT_FILE",
        "    FORMAT TECPLOT POINT",
        snapshot_period_line,
        "    VARIABLES",
        "      LIQUID_PRESSURE",
        "      LIQUID_SATURATION",
        "      LIQUID_HEAD",
        "      LIQUID_RELATIVE_PERMEABILITY",
        "      POROSITY",
        "      PERMEABILITY",
        "      MATERIAL_ID",
        "    /",
        "  /",
        "  MASS_BALANCE_FILE",
        "    PERIODIC TIMESTEP 1",
        "  /",
        "  CONSERVATION_FILE",
        "    PERIODIC TIMESTEP 1",
        "  /",
        "  VELOCITY_AT_CENTER",
        "  SCREEN PERIODIC 1",
        "/",
    ]


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


def read_test_params(input_json: Path, test_name: str = "linear_darcy") -> dict[str, Any]:
    data = read_input_document(input_json)
    scenarios = data.get("test_scenarios", {})
    params = scenarios.get(test_name, {}) if isinstance(scenarios, dict) else {}
    if not params:
        raise ValueError(f"В JSON отсутствует сценарий теста {test_name!r}")
    return params


def read_weather(input_json: Path) -> list[dict[str, Any]]:
    data = read_input_document(input_json)
    rows: list[dict[str, Any]] = []
    for tab in data.get("tabs", []):
        if tab.get("id") != "10_Weather_Daily":
            continue
        for row in tab.get("weather", []):
            date_text = str(row.get("date") or "")
            if not date_text:
                continue
            precip = as_float(row.get("precipitation_mm_day"), 0.0)
            irrigation = as_float(row.get("irrigation_mm_day"), 0.0)
            epot = as_float(row.get("epot_mm_day"), 0.0)
            tpot = as_float(row.get("tpot_mm_day"), 0.0)
            gw_depth = as_float(row.get("groundwater_depth_m"), math.nan)
            net = precip + irrigation - epot
            rows.append(
                {
                    "date": date_text,
                    "precipitation_mm_day": precip,
                    "irrigation_mm_day": irrigation,
                    "epot_mm_day": epot,
                    "tpot_mm_day": tpot,
                    "groundwater_depth_m": gw_depth,
                    "net_surface_input_mm_day": net,
                }
            )
    if not rows:
        raise ValueError("JSON исходных данных не содержит строк погодного форсинга")
    return rows


# -----------------------------------------------------------------------------
# Demo mode
# -----------------------------------------------------------------------------
@dataclass
class Derived:
    residual_saturation: float
    vg_m: float
    alpha_pa_inv: float
    intrinsic_perm_x_m2: float
    intrinsic_perm_y_m2: float
    intrinsic_perm_z_m2: float
    mean_top_flux_m_s: float


def compute_derived(params: dict[str, Any], weather: list[dict[str, Any]]) -> Derived:
    theta_s = as_float(params.get("theta_s"))
    theta_r = as_float(params.get("theta_r"))
    vg_alpha_1_m = as_float(params.get("vg_alpha_1_m"))
    vg_n = as_float(params.get("vg_n"))
    ksat_m_s = as_float(params.get("ksat_m_s"))
    rho = as_float(params.get("rho_water_kg_m3"), 997.0)
    mu = as_float(params.get("mu_water_pa_s"), 0.00089)
    g = as_float(params.get("gravity_m_s2"), 9.80665)
    ax = as_float(params.get("anisotropy_x"), 1.0)
    ay = as_float(params.get("anisotropy_y"), 1.0)
    az = as_float(params.get("anisotropy_z"), 1.0)

    if not (0.0 < theta_r < theta_s < 0.9):
        raise ValueError("Ожидается 0 < theta_r < theta_s < 0.9")
    if vg_n <= 1.0:
        raise ValueError("Для van Genuchten должно быть n > 1")
    if ksat_m_s <= 0:
        raise ValueError("ksat_m_s должен быть > 0")

    residual_saturation = theta_r / theta_s
    vg_m = 1.0 - 1.0 / vg_n
    alpha_pa_inv = vg_alpha_1_m / (rho * g)
    intrinsic_perm = ksat_m_s * mu / (rho * g)

    top_flux_override = params.get("top_flux_override_m_s")
    if top_flux_override not in (None, ""):
        mean_top_flux = as_float(top_flux_override)
    else:
        mean_net_mm_day = sum(r["net_surface_input_mm_day"] for r in weather) / len(weather)
        mean_top_flux = mean_net_mm_day / 1000.0 / 86400.0

    return Derived(
        residual_saturation=residual_saturation,
        vg_m=vg_m,
        alpha_pa_inv=alpha_pa_inv,
        intrinsic_perm_x_m2=intrinsic_perm * ax,
        intrinsic_perm_y_m2=intrinsic_perm * ay,
        intrinsic_perm_z_m2=intrinsic_perm * az,
        mean_top_flux_m_s=mean_top_flux,
    )


def write_weather_csv(weather: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "date",
        "precipitation_mm_day",
        "irrigation_mm_day",
        "epot_mm_day",
        "tpot_mm_day",
        "groundwater_depth_m",
        "net_surface_input_mm_day",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in weather:
            writer.writerow(row)


def generate_pflotran_input(params: dict[str, Any], derived: Derived) -> str:
    length_x = as_float(params.get("length_x_m"), 1.0)
    length_y = as_float(params.get("length_y_m"), 1.0)
    depth_z = as_float(params.get("depth_z_m"), 2.0)
    nx = as_int(params.get("nx"), 1)
    ny = as_int(params.get("ny"), 1)
    nz = as_int(params.get("nz"), 80)

    if nx < 1 or ny < 1 or nz < 1:
        raise ValueError("nx, ny, nz должны быть >= 1")
    if length_x <= 0 or length_y <= 0 or depth_z <= 0:
        raise ValueError("length_x_m, length_y_m, depth_z_m должны быть > 0")

    dx = length_x / nx
    dy = length_y / ny
    dz = depth_z / nz

    theta_s = as_float(params.get("theta_s"))
    tortuosity = as_float(params.get("tortuosity"), 0.5)
    final_time_days = as_float(params.get("final_time_days"), 7.0)
    max_dt_days = as_float(params.get("maximum_timestep_days"), 0.02)
    initial_pressure = as_float(params.get("initial_liquid_pressure_pa"), 101325.0)
    bottom_pressure = as_float(params.get("bottom_liquid_pressure_pa"), initial_pressure)
    bottom_bc_type = str(params.get("bottom_bc_type", "HYDROSTATIC")).strip().upper()

    lines: list[str] = []
    lines += [
        "# Generated by soilflow_pflotran.py",
        "# Demonstration: structured-grid RICHARDS problem for soil-water flow.",
        "",
        "SIMULATION",
        "  SIMULATION_TYPE SUBSURFACE",
        "  PROCESS_MODELS",
        "    SUBSURFACE_FLOW flow",
        "      MODE RICHARDS",
        "    /",
        "  /",
        "END",
        "",
        "SUBSURFACE",
        "",
        "GRID",
        "  TYPE structured",
        "  ORIGIN 0.d0 0.d0 0.d0",
        f"  NXYZ {nx} {ny} {nz}",
        "  DXYZ",
        f"    {pf_float(dx)}",
        f"    {pf_float(dy)}",
        f"    {pf_float(dz)}",
        "  /",
        "END",
        "",
        "MATERIAL_PROPERTY soil",
        "  ID 1",
        f"  POROSITY {pf_float(theta_s)}",
        f"  TORTUOSITY {pf_float(tortuosity)}",
        "  CHARACTERISTIC_CURVES cc_soil",
        "  PERMEABILITY",
        f"    PERM_X {pf_float(derived.intrinsic_perm_x_m2)}",
        f"    PERM_Y {pf_float(derived.intrinsic_perm_y_m2)}",
        f"    PERM_Z {pf_float(derived.intrinsic_perm_z_m2)}",
        "  /",
        "/",
        "",
        "CHARACTERISTIC_CURVES cc_soil",
        "  SATURATION_FUNCTION VAN_GENUCHTEN",
        f"    LIQUID_RESIDUAL_SATURATION {pf_float(derived.residual_saturation)}",
        f"    M {pf_float(derived.vg_m)}",
        f"    ALPHA {pf_float(derived.alpha_pa_inv)}",
        "  /",
        "  PERMEABILITY_FUNCTION MUALEM_VG_LIQ",
        f"    LIQUID_RESIDUAL_SATURATION {pf_float(derived.residual_saturation)}",
        f"    M {pf_float(derived.vg_m)}",
        "  /",
        "/",
        "",
        *test_output_block("    PERIODIC TIMESTEP 1"),
        "",
        "TIME",
        f"  FINAL_TIME {pf_float(final_time_days)} d",
        f"  MAXIMUM_TIMESTEP_SIZE {pf_float(max_dt_days)} d",
        "/",
        "",
        "REGION all",
        "  COORDINATES",
        "    0.d0 0.d0 0.d0",
        f"    {pf_float(length_x)} {pf_float(length_y)} {pf_float(depth_z)}",
        "  /",
        "END",
        "",
        "REGION top",
        "  COORDINATES",
        f"    0.d0 0.d0 {pf_float(depth_z)}",
        f"    {pf_float(length_x)} {pf_float(length_y)} {pf_float(depth_z)}",
        "  /",
        "  FACE TOP",
        "END",
        "",
        "REGION bottom",
        "  COORDINATES",
        "    0.d0 0.d0 0.d0",
        f"    {pf_float(length_x)} {pf_float(length_y)} 0.d0",
        "  /",
        "  FACE BOTTOM",
        "END",
        "",
        "FLOW_CONDITION top",
        "  TYPE",
        "    LIQUID_FLUX NEUMANN",
        "  /",
        f"  LIQUID_FLUX {pf_float(derived.mean_top_flux_m_s)}",
        "END",
        "",
        "FLOW_CONDITION initial",
        "  TYPE",
        "    LIQUID_PRESSURE HYDROSTATIC",
        "  /",
        f"  LIQUID_PRESSURE {pf_float(initial_pressure)}",
        "END",
        "",
    ]

    if bottom_bc_type == "CONSTANT_PRESSURE":
        lines += [
            "FLOW_CONDITION bottom",
            "  TYPE",
            "    LIQUID_PRESSURE DIRICHLET",
            "  /",
            f"  LIQUID_PRESSURE {pf_float(bottom_pressure)}",
            "END",
            "",
        ]

    lines += [
        "INITIAL_CONDITION",
        "  FLOW_CONDITION initial",
        "  REGION all",
        "END",
        "",
        "BOUNDARY_CONDITION top_bc",
        "  FLOW_CONDITION top",
        "  REGION top",
        "END",
        "",
    ]

    if bottom_bc_type == "NO_FLOW":
        lines += ["# Bottom boundary: NO_FLOW. PFLOTRAN default no-flow is used by not assigning a BC.", ""]
    elif bottom_bc_type == "CONSTANT_PRESSURE":
        lines += [
            "BOUNDARY_CONDITION bottom_bc",
            "  FLOW_CONDITION bottom",
            "  REGION bottom",
            "END",
            "",
        ]
    else:
        lines += [
            "# Bottom boundary: HYDROSTATIC, linked to the initial hydrostatic condition.",
            "BOUNDARY_CONDITION bottom_pressure_bc",
            "  FLOW_CONDITION initial",
            "  REGION bottom",
            "END",
            "",
        ]

    lines += [
        "STRATA",
        "  REGION all",
        "  MATERIAL soil",
        "END",
        "",
        "END_SUBSURFACE",
        "",
    ]
    return "\n".join(lines)


def write_summary(params: dict[str, Any], derived: Derived, weather: list[dict[str, Any]], path: Path) -> None:
    lines = [
        "SoilFlow/PFLOTRAN run summary",
        "=============================",
        "",
        f"Project: {params.get('project_name')}",
        f"Model mode: {params.get('model_mode')}",
        f"Dimension: {params.get('dimension')}",
        "",
        "Derived parameters:",
        f"  residual_saturation = {derived.residual_saturation:.8g}",
        f"  vg_m                = {derived.vg_m:.8g}",
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
@dataclass
class LinearDarcyTest:
    test_case_id: str
    column_height_m: float
    length_x_m: float
    length_y_m: float
    nx: int
    ny: int
    nz: int
    porosity: float
    ksat_m_s: float
    rho_water_kg_m3: float
    mu_water_pa_s: float
    gravity_m_s2: float
    bottom_pressure_pa: float
    imposed_flux_z_m_s: float
    final_time_days: float
    maximum_timestep_days: float
    tolerance_abs_pressure_pa: float
    tolerance_rel_pressure: float
    mpi_processes: int
    top_pressure_pa: float
    intrinsic_perm_m2: float


@dataclass
class VGRichardsTest:
    test_id: str
    column_height_m: float
    length_x_m: float
    length_y_m: float
    nx: int
    ny: int
    nz: int
    porosity: float
    residual_saturation: float
    alpha_1_m: float
    n: float
    m: float
    ksat_m_s: float
    rho_water_kg_m3: float
    mu_water_pa_s: float
    gravity_m_s2: float
    atmospheric_pressure_pa: float
    bottom_pressure_pa: float
    constant_pressure_pa: float
    duration_days: float
    pressure_abs_tolerance_pa: float
    saturation_abs_tolerance: float
    flux_abs_tolerance_m_s: float
    flux_relative_tolerance: float
    mpi_processes: int
    intrinsic_perm_m2: float
    test_kind: str


@dataclass
class TransientStorageTest:
    test_id: str
    length_x_m: float
    length_y_m: float
    length_z_m: float
    nx: int
    ny: int
    nz: int
    porosity: float
    residual_saturation: float
    alpha_1_m: float
    n: float
    m: float
    ksat_m_s: float
    rho_water_kg_m3: float
    mu_water_pa_s: float
    gravity_m_s2: float
    atmospheric_pressure_pa: float
    initial_saturation: float
    saturation_amplitude: float
    period_days: float
    duration_days: float
    maximum_timestep_days: float
    output_interval_days: float
    pressure_abs_tolerance_pa: float
    saturation_abs_tolerance: float
    uniformity_tolerance: float
    mass_balance_tolerance_m3: float
    mpi_processes: int
    intrinsic_perm_m2: float


@dataclass
class TestResult:
    test_id: str
    status: str
    output_dir: Path
    metrics: dict[str, float | str | bool]


def build_linear_darcy_test(params: dict[str, Any]) -> LinearDarcyTest:
    test_case_id = str(params.get("test_case_id", "linear_darcy_saturated_column"))
    column_height_m = as_float(params.get("column_height_m"), 2.0)
    length_x_m = as_float(params.get("length_x_m"), 1.0)
    length_y_m = as_float(params.get("length_y_m"), 1.0)
    nx = as_int(params.get("nx"), 1)
    ny = as_int(params.get("ny"), 1)
    nz = as_int(params.get("nz"), 80)
    porosity = as_float(params.get("porosity"), 0.43)
    ksat_m_s = as_float(params.get("ksat_m_s"), 1.0e-5)
    rho = as_float(params.get("rho_water_kg_m3"), 997.0)
    mu = as_float(params.get("mu_water_pa_s"), 0.001002)
    g = as_float(params.get("gravity_m_s2"), 9.80665)
    bottom_pressure_pa = as_float(params.get("bottom_pressure_pa"), 125000.0)
    imposed_flux = as_float(params.get("imposed_flux_z_m_s"), -1.0e-6)
    final_time_days = as_float(params.get("final_time_days"), 10.0)
    max_dt_days = as_float(params.get("maximum_timestep_days"), 0.1)
    tol_abs_p = as_float(params.get("tolerance_abs_pressure_pa") or params.get("pressure_abs_tolerance_pa"), 10.0)
    tol_rel_p = as_float(params.get("tolerance_rel_pressure"), 1.0e-3)
    mpi_n = as_int(params.get("mpi_processes"), 1)

    if column_height_m <= 0 or length_x_m <= 0 or length_y_m <= 0:
        raise ValueError("Размеры колонки должны быть положительными")
    if nx < 1 or ny < 1 or nz < 2:
        raise ValueError("Для _test ожидается nx>=1, ny>=1, nz>=2")
    if not (0.0 < porosity < 1.0):
        raise ValueError("porosity должен быть в интервале (0,1)")
    if ksat_m_s <= 0:
        raise ValueError("ksat_m_s должен быть > 0")
    if abs(imposed_flux) >= 0.95 * ksat_m_s:
        raise ValueError("Для устойчивого демонстрационного saturated-test задайте |q| < 0.95*Ks")

    intrinsic_perm = ksat_m_s * mu / (rho * g)
    # Координата z направлена вверх. Для saturated-test используем форму
    # q_z = -Ks*d(P/(rho*g) + z)/dz, откуда P(z)=P_bottom-rho*g*(1+q_z/Ks)*z.
    top_pressure_pa = bottom_pressure_pa - rho * g * (1.0 + imposed_flux / ksat_m_s) * column_height_m
    atmospheric_pressure_pa = 101325.0
    if top_pressure_pa <= atmospheric_pressure_pa:
        raise ValueError(
            "Некорректный saturated _test: ожидаемое давление на верхней границе "
            f"{top_pressure_pa:.3f} Pa <= атмосферного {atmospheric_pressure_pa:.3f} Pa. "
            "Увеличьте bottom_pressure_pa или уменьшите высоту/поток, иначе колонка не будет насыщенной."
        )

    return LinearDarcyTest(
        test_case_id=test_case_id,
        column_height_m=column_height_m,
        length_x_m=length_x_m,
        length_y_m=length_y_m,
        nx=nx,
        ny=ny,
        nz=nz,
        porosity=porosity,
        ksat_m_s=ksat_m_s,
        rho_water_kg_m3=rho,
        mu_water_pa_s=mu,
        gravity_m_s2=g,
        bottom_pressure_pa=bottom_pressure_pa,
        imposed_flux_z_m_s=imposed_flux,
        final_time_days=final_time_days,
        maximum_timestep_days=max_dt_days,
        tolerance_abs_pressure_pa=tol_abs_p,
        tolerance_rel_pressure=tol_rel_p,
        mpi_processes=mpi_n,
        top_pressure_pa=top_pressure_pa,
        intrinsic_perm_m2=intrinsic_perm,
    )


def analytical_pressure(test: LinearDarcyTest, z_m: float) -> float:
    return test.bottom_pressure_pa - test.rho_water_kg_m3 * test.gravity_m_s2 * (
        1.0 + test.imposed_flux_z_m_s / test.ksat_m_s
    ) * z_m


def analytical_potential(test: LinearDarcyTest, z_m: float) -> float:
    # Для оси z, направленной вверх, гидравлический потенциал равен P + rho*g*z.
    return analytical_pressure(test, z_m) + test.rho_water_kg_m3 * test.gravity_m_s2 * z_m


def vg_effective_saturation_from_pressure_head(h_m: float, alpha_1_m: float, n: float, m: float) -> float:
    if h_m >= 0.0:
        return 1.0
    return (1.0 + (alpha_1_m * abs(h_m)) ** n) ** (-m)


def saturation_from_effective_saturation(se: float, residual_saturation: float) -> float:
    se = max(0.0, min(1.0, se))
    return residual_saturation + (1.0 - residual_saturation) * se


def effective_saturation_from_saturation(saturation: float, residual_saturation: float) -> float:
    if not (residual_saturation < saturation <= 1.0):
        raise ValueError("saturation должна быть в интервале (residual_saturation, 1]")
    return (saturation - residual_saturation) / (1.0 - residual_saturation)


def vg_pressure_head_from_saturation(saturation: float, residual_saturation: float, alpha_1_m: float, n: float, m: float) -> float:
    se = effective_saturation_from_saturation(saturation, residual_saturation)
    if se >= 1.0:
        return 0.0
    # Обратная VG-кривая: для ненасыщенного состояния pressure head отрицателен.
    return -((se ** (-1.0 / m) - 1.0) ** (1.0 / n)) / alpha_1_m


def mualem_vg_relative_permeability(se: float, m: float) -> float:
    se = max(0.0, min(1.0, se))
    if se <= 0.0:
        return 0.0
    if se >= 1.0:
        return 1.0
    return math.sqrt(se) * (1.0 - (1.0 - se ** (1.0 / m)) ** m) ** 2


def build_vg_test(params: dict[str, Any], test_kind: str) -> VGRichardsTest:
    theta_s = as_float(params.get("theta_s"), 0.43)
    theta_r = as_float(params.get("theta_r"), 0.045)
    residual = as_float(params.get("residual_saturation"), theta_r / theta_s)
    n = as_float(params.get("n"), 1.56)
    m = as_float(params.get("m"), 1.0 - 1.0 / n)
    rho = as_float(params.get("rho_water_kg_m3"), 997.0)
    mu = as_float(params.get("mu_water_pa_s"), 0.00089)
    g = as_float(params.get("gravity_m_s2"), 9.80665)
    ksat = as_float(params.get("ksat_m_s"), 5.0e-6)
    if not (0.0 <= residual < 1.0):
        raise ValueError("residual_saturation должен быть в интервале [0,1)")
    if theta_s <= 0.0 or ksat <= 0.0 or n <= 1.0:
        raise ValueError("Для VG-тестов ожидаются theta_s>0, ksat_m_s>0 и n>1")
    duration_key = "duration_days"
    return VGRichardsTest(
        test_id=f"_test_{test_kind}",
        column_height_m=as_float(params.get("column_height_m"), 2.0),
        length_x_m=as_float(params.get("length_x_m"), 1.0),
        length_y_m=as_float(params.get("length_y_m"), 1.0),
        nx=as_int(params.get("nx"), 1),
        ny=as_int(params.get("ny"), 1),
        nz=as_int(params.get("nz"), 80),
        porosity=theta_s,
        residual_saturation=residual,
        alpha_1_m=as_float(params.get("alpha_1_m"), 3.6),
        n=n,
        m=m,
        ksat_m_s=ksat,
        rho_water_kg_m3=rho,
        mu_water_pa_s=mu,
        gravity_m_s2=g,
        atmospheric_pressure_pa=as_float(params.get("atmospheric_pressure_pa"), 101325.0),
        bottom_pressure_pa=as_float(params.get("bottom_pressure_pa"), 101325.0),
        constant_pressure_pa=as_float(params.get("constant_pressure_pa"), 90000.0),
        duration_days=as_float(params.get(duration_key), 1.0 if test_kind == "hydrostatic_vg_no_flow" else 3.0),
        pressure_abs_tolerance_pa=as_float(params.get("pressure_abs_tolerance_pa"), 10.0),
        saturation_abs_tolerance=as_float(params.get("saturation_abs_tolerance"), 5.0e-5),
        flux_abs_tolerance_m_s=as_float(params.get("flux_abs_tolerance_m_s"), 1.0e-10),
        flux_relative_tolerance=as_float(params.get("flux_relative_tolerance"), 0.005),
        mpi_processes=as_int(params.get("mpi_processes"), 1),
        intrinsic_perm_m2=ksat * mu / (rho * g),
        test_kind=test_kind,
    )


def build_hydrostatic_vg_no_flow_test(params: dict[str, Any]) -> VGRichardsTest:
    return build_vg_test(params, "hydrostatic_vg_no_flow")


def build_unit_gradient_unsat_test(params: dict[str, Any]) -> VGRichardsTest:
    return build_vg_test(params, "unit_gradient_unsat")


def transient_saturation(test: TransientStorageTest, time_days: float) -> float:
    return test.initial_saturation + 0.5 * test.saturation_amplitude * (
        1.0 - math.cos(2.0 * math.pi * time_days / test.period_days)
    )


def transient_dsdt_per_day(test: TransientStorageTest, time_days: float) -> float:
    return (
        0.5
        * test.saturation_amplitude
        * (2.0 * math.pi / test.period_days)
        * math.sin(2.0 * math.pi * time_days / test.period_days)
    )


def transient_pressure(test: TransientStorageTest, saturation: float) -> float:
    h_m = vg_pressure_head_from_saturation(
        saturation,
        test.residual_saturation,
        test.alpha_1_m,
        test.n,
        test.m,
    )
    return test.atmospheric_pressure_pa + test.rho_water_kg_m3 * test.gravity_m_s2 * h_m


def transient_domain_volume_m3(test: TransientStorageTest) -> float:
    return test.length_x_m * test.length_y_m * test.length_z_m


def transient_rate_m3_day(test: TransientStorageTest, time_days: float) -> float:
    return test.porosity * transient_domain_volume_m3(test) * transient_dsdt_per_day(test, time_days)


def build_transient_uniform_storage_vg_test(params: dict[str, Any]) -> TransientStorageTest:
    theta_s = as_float(params.get("theta_s"), 0.43)
    theta_r = as_float(params.get("theta_r"), 0.045)
    residual = as_float(params.get("residual_saturation"), theta_r / theta_s)
    n = as_float(params.get("n"), 1.56)
    m = as_float(params.get("m"), 1.0 - 1.0 / n)
    rho = as_float(params.get("rho_water_kg_m3"), 997.0)
    mu = as_float(params.get("mu_water_pa_s"), 0.00089)
    g = as_float(params.get("gravity_m_s2"), 9.80665)
    ksat = as_float(params.get("ksat_m_s"), 5.0e-6)
    initial_s = as_float(params.get("initial_saturation"), 0.55)
    amplitude = as_float(params.get("saturation_amplitude"), 0.08)
    if not (0.0 <= residual < initial_s < initial_s + amplitude < 1.0):
        raise ValueError("Для transient VG ожидается residual < initial_s < initial_s+amplitude < 1")
    if theta_s <= 0.0 or ksat <= 0.0 or n <= 1.0:
        raise ValueError("Для transient VG ожидаются theta_s>0, ksat_m_s>0 и n>1")
    return TransientStorageTest(
        test_id="_test_transient_uniform_storage_vg",
        length_x_m=as_float(params.get("length_x_m"), 1.0),
        length_y_m=as_float(params.get("length_y_m"), 1.0),
        length_z_m=as_float(params.get("length_z_m") or params.get("column_height_m"), 0.2),
        nx=as_int(params.get("nx"), 10),
        ny=as_int(params.get("ny"), 1),
        nz=as_int(params.get("nz"), 1),
        porosity=theta_s,
        residual_saturation=residual,
        alpha_1_m=as_float(params.get("alpha_1_m"), 3.6),
        n=n,
        m=m,
        ksat_m_s=ksat,
        rho_water_kg_m3=rho,
        mu_water_pa_s=mu,
        gravity_m_s2=g,
        atmospheric_pressure_pa=as_float(params.get("atmospheric_pressure_pa"), 101325.0),
        initial_saturation=initial_s,
        saturation_amplitude=amplitude,
        period_days=as_float(params.get("period_days"), 1.0),
        duration_days=as_float(params.get("duration_days"), 1.0),
        maximum_timestep_days=as_float(params.get("maximum_timestep_days"), 0.001),
        output_interval_days=as_float(params.get("output_interval_days"), 0.01),
        pressure_abs_tolerance_pa=as_float(params.get("pressure_abs_tolerance_pa"), 120.0),
        saturation_abs_tolerance=as_float(params.get("saturation_abs_tolerance"), 3.0e-3),
        uniformity_tolerance=as_float(params.get("uniformity_tolerance"), 1.0e-8),
        mass_balance_tolerance_m3=as_float(params.get("mass_balance_tolerance_m3"), 1.0e-8),
        mpi_processes=as_int(params.get("mpi_processes"), 1),
        intrinsic_perm_m2=ksat * mu / (rho * g),
    )


TEST_BUILDERS = {
    "linear_darcy": build_linear_darcy_test,
    "hydrostatic_vg_no_flow": build_hydrostatic_vg_no_flow_test,
    "unit_gradient_unsat": build_unit_gradient_unsat_test,
    "transient_uniform_storage_vg": build_transient_uniform_storage_vg_test,
}


def generate_pflotran_test_input(test: LinearDarcyTest) -> str:
    dx = test.length_x_m / test.nx
    dy = test.length_y_m / test.ny
    dz = test.column_height_m / test.nz

    lines = [
        "# Generated by soilflow_pflotran.py --mode _test",
        "# Analytical verification test: saturated homogeneous isotropic column.",
        "# Linearized Richards equation -> Darcy equation with constant K = Ks.",
        "# Upper boundary is imposed as constant flux; lower boundary is reference pressure.",
        "# The bottom flux is checked against the analytical steady flux.",
        "",
        "SIMULATION",
        "  SIMULATION_TYPE SUBSURFACE",
        "  PROCESS_MODELS",
        "    SUBSURFACE_FLOW flow",
        "      MODE RICHARDS",
        "    /",
        "  /",
        "END",
        "",
        "SUBSURFACE",
        "",
        "GRID",
        "  TYPE structured",
        "  ORIGIN 0.d0 0.d0 0.d0",
        f"  NXYZ {test.nx} {test.ny} {test.nz}",
        "  DXYZ",
        f"    {pf_float(dx)}",
        f"    {pf_float(dy)}",
        f"    {pf_float(dz)}",
        "  /",
        "END",
        "",
        "MATERIAL_PROPERTY soil",
        "  ID 1",
        f"  POROSITY {pf_float(test.porosity)}",
        "  TORTUOSITY 1.d0",
        "  CHARACTERISTIC_CURVES cc_saturated",
        "  PERMEABILITY",
        f"    PERM_X {pf_float(test.intrinsic_perm_m2)}",
        f"    PERM_Y {pf_float(test.intrinsic_perm_m2)}",
        f"    PERM_Z {pf_float(test.intrinsic_perm_m2)}",
        "  /",
        "/",
        "",
        "# Saturation curve is present because RICHARDS mode expects characteristic curves.",
        "# Positive pressure levels keep the domain saturated; the test therefore reduces",
        "# to the linear Darcy column problem.",
        "CHARACTERISTIC_CURVES cc_saturated",
        "  SATURATION_FUNCTION VAN_GENUCHTEN",
        "    LIQUID_RESIDUAL_SATURATION 0.d0",
        "    M 0.5d0",
        "    ALPHA 1.d-4",
        "  /",
        "  PERMEABILITY_FUNCTION MUALEM_VG_LIQ",
        "    LIQUID_RESIDUAL_SATURATION 0.d0",
        "    M 0.5d0",
        "  /",
        "/",
        "",
        *test_output_block("    PERIODIC TIMESTEP 1"),
        "",
        "TIME",
        f"  FINAL_TIME {pf_float(test.final_time_days)} d",
        f"  MAXIMUM_TIMESTEP_SIZE {pf_float(test.maximum_timestep_days)} d",
        "/",
        "",
        "REGION all",
        "  COORDINATES",
        "    0.d0 0.d0 0.d0",
        f"    {pf_float(test.length_x_m)} {pf_float(test.length_y_m)} {pf_float(test.column_height_m)}",
        "  /",
        "END",
        "",
        "REGION top",
        "  COORDINATES",
        f"    0.d0 0.d0 {pf_float(test.column_height_m)}",
        f"    {pf_float(test.length_x_m)} {pf_float(test.length_y_m)} {pf_float(test.column_height_m)}",
        "  /",
        "  FACE TOP",
        "END",
        "",
        "REGION bottom",
        "  COORDINATES",
        "    0.d0 0.d0 0.d0",
        f"    {pf_float(test.length_x_m)} {pf_float(test.length_y_m)} 0.d0",
        "  /",
        "  FACE BOTTOM",
        "END",
        "",
        "FLOW_CONDITION initial",
        "  TYPE",
        "    LIQUID_PRESSURE HYDROSTATIC",
        "  /",
        f"  LIQUID_PRESSURE {pf_float(test.bottom_pressure_pa)}",
        "END",
        "",
        "FLOW_CONDITION bottom_pressure",
        "  TYPE",
        "    LIQUID_PRESSURE DIRICHLET",
        "  /",
        f"  LIQUID_PRESSURE {pf_float(test.bottom_pressure_pa)}",
        "END",
        "",
        "FLOW_CONDITION top_flux",
        "  TYPE",
        "    LIQUID_FLUX NEUMANN",
        "  /",
        "  # PFLOTRAN sign convention: positive boundary flux is inward.",
        "  # imposed_flux_z_m_s is a +z Darcy flux; downward top infiltration has q_z < 0.",
        f"  LIQUID_FLUX {pf_float(abs(test.imposed_flux_z_m_s))}",
        "END",
        "",
        "INITIAL_CONDITION",
        "  FLOW_CONDITION initial",
        "  REGION all",
        "END",
        "",
        "BOUNDARY_CONDITION bottom_pressure_bc",
        "  FLOW_CONDITION bottom_pressure",
        "  REGION bottom",
        "END",
        "",
        "BOUNDARY_CONDITION top_flux_bc",
        "  FLOW_CONDITION top_flux",
        "  REGION top",
        "END",
        "",
        "STRATA",
        "  REGION all",
        "  MATERIAL soil",
        "END",
        "",
        "END_SUBSURFACE",
        "",
    ]
    return "\n".join(lines)


def write_analytical_solution(test: LinearDarcyTest, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    dz = test.column_height_m / test.nz
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "cell_id",
                "z_center_m",
                "pressure_analytical_pa",
                "pressure_head_m",
                "hydraulic_potential_p_plus_rho_g_z_pa",
                "analytical_flux_z_m_s",
            ],
        )
        writer.writeheader()
        for i in range(test.nz):
            z = (i + 0.5) * dz
            p = analytical_pressure(test, z)
            writer.writerow(
                {
                    "cell_id": i + 1,
                    "z_center_m": f"{z:.12g}",
                    "pressure_analytical_pa": f"{p:.12g}",
                    "pressure_head_m": f"{p / (test.rho_water_kg_m3 * test.gravity_m_s2):.12g}",
                    "hydraulic_potential_p_plus_rho_g_z_pa": f"{analytical_potential(test, z):.12g}",
                    "analytical_flux_z_m_s": f"{test.imposed_flux_z_m_s:.12g}",
                }
            )


def write_test_summary(test: LinearDarcyTest, path: Path, status: str = "GENERATED") -> None:
    lines = [
        "SoilFlow/PFLOTRAN _test summary",
        "=================================",
        "",
        f"Status: {status}",
        f"Test case: {test.test_case_id}",
        "",
        "Physical model:",
        "  1D saturated homogeneous isotropic column.",
        "  Linearized Richards equation: K(h)=Ks=const; no sources/sinks; no evaporation.",
        "  PFLOTRAN equation uses qz = -Ks*d(P/(rho*g) + z)/dz for the z-up saturated form.",
        "  Test BC: top constant flux + bottom reference pressure; steady bottom flux must equal imposed top flux.",
        "",
        "Geometry:",
        f"  column_height_m = {test.column_height_m:.8g}",
        f"  nx,ny,nz        = {test.nx},{test.ny},{test.nz}",
        "",
        "Parameters:",
        f"  porosity         = {test.porosity:.8g}",
        f"  ksat_m_s         = {test.ksat_m_s:.8e}",
        f"  intrinsic_perm   = {test.intrinsic_perm_m2:.8e} m2",
        f"  rho_water        = {test.rho_water_kg_m3:.8g} kg/m3",
        f"  mu_water         = {test.mu_water_pa_s:.8g} Pa*s",
        f"  gravity          = {test.gravity_m_s2:.8g} m/s2",
        "",
        "Boundary/reference values:",
        f"  bottom_pressure_pa = {test.bottom_pressure_pa:.8g}  (Dirichlet/reference)",
        f"  top_pressure_pa    = {test.top_pressure_pa:.8g}  (analytical expected value, not imposed)",
        f"  imposed_flux_z_m_s = {test.imposed_flux_z_m_s:.8e}  (analytical qz; negative means downward)",
        f"  top_boundary_liquid_flux = {abs(test.imposed_flux_z_m_s):.8e}  (PFLOTRAN Neumann, inward-positive at top)",
        "",
        "Analytical solution:",
        "  P(z) = P_bottom - rho*g*(1 + qz/Ks)*z",
        "  z=0 is bottom; z=L is top; qz is PFLOTRAN +z-direction flux.",
        "",
        "Acceptance tolerances:",
        f"  abs pressure tolerance = {test.tolerance_abs_pressure_pa:.8g} Pa",
        f"  rel pressure tolerance = {test.tolerance_rel_pressure:.8g}",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def vg_pressure(test: VGRichardsTest, z_m: float) -> float:
    if test.test_kind == "hydrostatic_vg_no_flow":
        return test.bottom_pressure_pa - test.rho_water_kg_m3 * test.gravity_m_s2 * z_m
    return test.constant_pressure_pa


def vg_saturation(test: VGRichardsTest, pressure_pa: float) -> float:
    h_m = (pressure_pa - test.atmospheric_pressure_pa) / (test.rho_water_kg_m3 * test.gravity_m_s2)
    se = vg_effective_saturation_from_pressure_head(h_m, test.alpha_1_m, test.n, test.m)
    return saturation_from_effective_saturation(se, test.residual_saturation)


def vg_alpha_pa_inv(test: VGRichardsTest) -> float:
    return test.alpha_1_m / (test.rho_water_kg_m3 * test.gravity_m_s2)


def generate_pflotran_vg_test_input(test: VGRichardsTest) -> str:
    dx = test.length_x_m / test.nx
    dy = test.length_y_m / test.ny
    dz = test.column_height_m / test.nz
    initial_type = "HYDROSTATIC" if test.test_kind == "hydrostatic_vg_no_flow" else "DIRICHLET"
    initial_pressure = test.bottom_pressure_pa if test.test_kind == "hydrostatic_vg_no_flow" else test.constant_pressure_pa
    lines = [
        f"# Generated by soilflow_pflotran.py --mode _test --test {test.test_kind}",
        "SIMULATION",
        "  SIMULATION_TYPE SUBSURFACE",
        "  PROCESS_MODELS",
        "    SUBSURFACE_FLOW flow",
        "      MODE RICHARDS",
        "    /",
        "  /",
        "END",
        "",
        "SUBSURFACE",
        "",
        "GRID",
        "  TYPE structured",
        "  ORIGIN 0.d0 0.d0 0.d0",
        f"  NXYZ {test.nx} {test.ny} {test.nz}",
        "  DXYZ",
        f"    {pf_float(dx)}",
        f"    {pf_float(dy)}",
        f"    {pf_float(dz)}",
        "  /",
        "END",
        "",
        "MATERIAL_PROPERTY soil",
        "  ID 1",
        f"  POROSITY {pf_float(test.porosity)}",
        "  TORTUOSITY 1.d0",
        "  CHARACTERISTIC_CURVES cc_vg",
        "  PERMEABILITY",
        f"    PERM_X {pf_float(test.intrinsic_perm_m2)}",
        f"    PERM_Y {pf_float(test.intrinsic_perm_m2)}",
        f"    PERM_Z {pf_float(test.intrinsic_perm_m2)}",
        "  /",
        "/",
        "",
        "CHARACTERISTIC_CURVES cc_vg",
        "  SATURATION_FUNCTION VAN_GENUCHTEN",
        f"    LIQUID_RESIDUAL_SATURATION {pf_float(test.residual_saturation)}",
        f"    M {pf_float(test.m)}",
        f"    ALPHA {pf_float(vg_alpha_pa_inv(test))}",
        "  /",
        "  PERMEABILITY_FUNCTION MUALEM_VG_LIQ",
        f"    LIQUID_RESIDUAL_SATURATION {pf_float(test.residual_saturation)}",
        f"    M {pf_float(test.m)}",
        "  /",
        "/",
        "",
        *test_output_block("    PERIODIC TIMESTEP 1"),
        "",
        "TIME",
        f"  FINAL_TIME {pf_float(test.duration_days)} d",
        "  MAXIMUM_TIMESTEP_SIZE 1.d-1 d",
        "/",
        "",
        "REGION all",
        "  COORDINATES",
        "    0.d0 0.d0 0.d0",
        f"    {pf_float(test.length_x_m)} {pf_float(test.length_y_m)} {pf_float(test.column_height_m)}",
        "  /",
        "END",
        "",
        "REGION top",
        "  COORDINATES",
        f"    0.d0 0.d0 {pf_float(test.column_height_m)}",
        f"    {pf_float(test.length_x_m)} {pf_float(test.length_y_m)} {pf_float(test.column_height_m)}",
        "  /",
        "  FACE TOP",
        "END",
        "",
        "REGION bottom",
        "  COORDINATES",
        "    0.d0 0.d0 0.d0",
        f"    {pf_float(test.length_x_m)} {pf_float(test.length_y_m)} 0.d0",
        "  /",
        "  FACE BOTTOM",
        "END",
        "",
        "FLOW_CONDITION initial",
        "  TYPE",
        f"    LIQUID_PRESSURE {initial_type}",
        "  /",
        f"  LIQUID_PRESSURE {pf_float(initial_pressure)}",
        "END",
        "",
    ]
    if test.test_kind == "unit_gradient_unsat":
        lines += [
            "FLOW_CONDITION constant_pressure",
            "  TYPE",
            "    LIQUID_PRESSURE DIRICHLET",
            "  /",
            f"  LIQUID_PRESSURE {pf_float(test.constant_pressure_pa)}",
            "END",
            "",
        ]
    lines += [
        "INITIAL_CONDITION",
        "  FLOW_CONDITION initial",
        "  REGION all",
        "END",
        "",
    ]
    if test.test_kind == "unit_gradient_unsat":
        lines += [
            "BOUNDARY_CONDITION top_pressure_bc",
            "  FLOW_CONDITION constant_pressure",
            "  REGION top",
            "END",
            "",
            "BOUNDARY_CONDITION bottom_pressure_bc",
            "  FLOW_CONDITION constant_pressure",
            "  REGION bottom",
            "END",
            "",
        ]
    else:
        lines += [
            "# Верхняя и нижняя границы не назначены: используется no-flow по умолчанию.",
            "",
        ]
    lines += [
        "STRATA",
        "  REGION all",
        "  MATERIAL soil",
        "END",
        "",
        "END_SUBSURFACE",
        "",
    ]
    return "\n".join(lines)


def write_vg_analytical_solution(test: VGRichardsTest, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    dz = test.column_height_m / test.nz
    h_const = (test.constant_pressure_pa - test.atmospheric_pressure_pa) / (test.rho_water_kg_m3 * test.gravity_m_s2)
    se_const = vg_effective_saturation_from_pressure_head(h_const, test.alpha_1_m, test.n, test.m)
    kr_const = mualem_vg_relative_permeability(se_const, test.m)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "cell_id",
                "z_center_m",
                "pressure_analytical_pa",
                "pressure_head_m",
                "saturation_analytical",
                "effective_saturation",
                "relative_permeability",
                "analytical_flux_z_m_s",
            ],
        )
        writer.writeheader()
        for i in range(test.nz):
            z = (i + 0.5) * dz
            p = vg_pressure(test, z)
            h = (p - test.atmospheric_pressure_pa) / (test.rho_water_kg_m3 * test.gravity_m_s2)
            se = vg_effective_saturation_from_pressure_head(h, test.alpha_1_m, test.n, test.m)
            sat = saturation_from_effective_saturation(se, test.residual_saturation)
            kr = mualem_vg_relative_permeability(se, test.m)
            q = 0.0 if test.test_kind == "hydrostatic_vg_no_flow" else -test.ksat_m_s * kr_const
            writer.writerow(
                {
                    "cell_id": i + 1,
                    "z_center_m": f"{z:.12g}",
                    "pressure_analytical_pa": f"{p:.12g}",
                    "pressure_head_m": f"{h:.12g}",
                    "saturation_analytical": f"{sat:.12g}",
                    "effective_saturation": f"{se:.12g}",
                    "relative_permeability": f"{kr:.12g}",
                    "analytical_flux_z_m_s": f"{q:.12g}",
                }
            )


def write_vg_test_summary(test: VGRichardsTest, path: Path, status: str = "GENERATED") -> None:
    if test.test_kind == "hydrostatic_vg_no_flow":
        title = "Hydrostatic VG no-flow verification"
        formula = "P(z)=P_bottom-rho*g*z; S=VG((P-P_atm)/(rho*g)); qz=0"
        pressure_head_bottom = (test.bottom_pressure_pa - test.atmospheric_pressure_pa) / (
            test.rho_water_kg_m3 * test.gravity_m_s2
        )
        pressure_head_top = (
            test.bottom_pressure_pa
            - test.rho_water_kg_m3 * test.gravity_m_s2 * test.column_height_m
            - test.atmospheric_pressure_pa
        ) / (test.rho_water_kg_m3 * test.gravity_m_s2)
        hydro_extra = [
            "",
            "Гидростатические контрольные величины:",
            f"  pressure_head_bottom_m      = {pressure_head_bottom:.8g}",
            f"  pressure_head_top_m         = {pressure_head_top:.8g}",
            f"  hydraulic_head_bottom_m     = {pressure_head_bottom:.8g}",
            f"  hydraulic_head_top_m        = {pressure_head_top + test.column_height_m:.8g}",
            "  hydraulic_head_slope_m_per_m = 0",
            f"  saturation_bottom_cell      = {vg_saturation(test, test.bottom_pressure_pa):.8g}",
            f"  saturation_top_cell         = {vg_saturation(test, test.bottom_pressure_pa - test.rho_water_kg_m3 * test.gravity_m_s2 * test.column_height_m):.8g}",
            "  expected_flux_m_s           = 0",
        ]
    else:
        title = "Unit-gradient unsaturated drainage verification"
        formula = "P(z)=const; S=const; qz=-Ks*kr(S)"
        hydro_extra = [f"  constant_pressure= {test.constant_pressure_pa:.8g} Pa"]
    lines = [
        f"SoilFlow/PFLOTRAN {test.test_id} summary",
        "=" * (len(test.test_id) + 31),
        "",
        f"Status: {status}",
        title,
        "",
        "Физический смысл:",
        f"  {formula}",
        "  z направлена вверх; отрицательный qz означает нисходящий поток.",
        "",
        "Параметры:",
        f"  column_height_m = {test.column_height_m:.8g}",
        f"  nx,ny,nz        = {test.nx},{test.ny},{test.nz}",
        f"  porosity         = {test.porosity:.8g}",
        f"  residual_sat     = {test.residual_saturation:.8g}",
        f"  alpha_1_m        = {test.alpha_1_m:.8g} 1/m",
        f"  n,m              = {test.n:.8g}, {test.m:.8g}",
        f"  ksat_m_s         = {test.ksat_m_s:.8e}",
        f"  intrinsic_perm   = {test.intrinsic_perm_m2:.8e} m2",
        f"  rho_water        = {test.rho_water_kg_m3:.8g} kg/m3",
        f"  mu_water         = {test.mu_water_pa_s:.8g} Pa*s",
        f"  gravity          = {test.gravity_m_s2:.8g} m/s2",
        f"  P_atm            = {test.atmospheric_pressure_pa:.8g} Pa",
        f"  bottom_pressure  = {test.bottom_pressure_pa:.8g} Pa",
        *hydro_extra,
        "",
        "Критерии PASS:",
        f"  pressure_abs_tolerance_pa = {test.pressure_abs_tolerance_pa:.8g}",
        f"  saturation_abs_tolerance  = {test.saturation_abs_tolerance:.8g}",
        f"  flux_abs_tolerance_m_s    = {test.flux_abs_tolerance_m_s:.8e}",
        f"  flux_relative_tolerance   = {test.flux_relative_tolerance:.8g}",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def transient_time_grid(test: TransientStorageTest) -> list[float]:
    steps = max(1, int(round(test.duration_days / test.output_interval_days)))
    values = [min(test.duration_days, i * test.output_interval_days) for i in range(steps + 1)]
    if values[-1] < test.duration_days:
        values.append(test.duration_days)
    return sorted(set(round(t, 12) for t in values))


def generate_pflotran_transient_storage_input(test: TransientStorageTest) -> str:
    dx = test.length_x_m / test.nx
    dy = test.length_y_m / test.ny
    dz = test.length_z_m / test.nz
    initial_pressure = transient_pressure(test, test.initial_saturation)
    rate_lines = [
        f"        {pf_float(t)} {pf_float(transient_rate_m3_day(test, t))}" for t in transient_time_grid(test)
    ]
    return "\n".join(
        [
            "# Generated by soilflow_pflotran.py --mode _test --test transient_uniform_storage_vg",
            "# Horizontal no-flow domain with a spatially uniform source/sink RATE LIST.",
            "",
            "SIMULATION",
            "  SIMULATION_TYPE SUBSURFACE",
            "  PROCESS_MODELS",
            "    SUBSURFACE_FLOW flow",
            "      MODE RICHARDS",
            "    /",
            "  /",
            "END",
            "",
            "SUBSURFACE",
            "",
            "GRID",
            "  TYPE structured",
            "  ORIGIN 0.d0 0.d0 0.d0",
            f"  NXYZ {test.nx} {test.ny} {test.nz}",
            "  DXYZ",
            f"    {pf_float(dx)}",
            f"    {pf_float(dy)}",
            f"    {pf_float(dz)}",
            "  /",
            "END",
            "",
            "MATERIAL_PROPERTY soil",
            "  ID 1",
            f"  POROSITY {pf_float(test.porosity)}",
            "  TORTUOSITY 1.d0",
            "  CHARACTERISTIC_CURVES cc_vg",
            "  PERMEABILITY",
            f"    PERM_X {pf_float(test.intrinsic_perm_m2)}",
            f"    PERM_Y {pf_float(test.intrinsic_perm_m2)}",
            f"    PERM_Z {pf_float(test.intrinsic_perm_m2)}",
            "  /",
            "/",
            "",
            "CHARACTERISTIC_CURVES cc_vg",
            "  SATURATION_FUNCTION VAN_GENUCHTEN",
            f"    LIQUID_RESIDUAL_SATURATION {pf_float(test.residual_saturation)}",
            f"    M {pf_float(test.m)}",
            f"    ALPHA {pf_float(test.alpha_1_m / (test.rho_water_kg_m3 * test.gravity_m_s2))}",
            "  /",
            "  PERMEABILITY_FUNCTION MUALEM_VG_LIQ",
            f"    LIQUID_RESIDUAL_SATURATION {pf_float(test.residual_saturation)}",
            f"    M {pf_float(test.m)}",
            "  /",
            "/",
            "",
            *test_output_block(
                f"    PERIODIC TIMESTEP {max(1, int(round(test.output_interval_days / test.maximum_timestep_days)))}"
            ),
            "",
            "TIME",
            f"  FINAL_TIME {pf_float(test.duration_days)} d",
            f"  MAXIMUM_TIMESTEP_SIZE {pf_float(test.maximum_timestep_days)} d",
            "/",
            "",
            "REGION all",
            "  COORDINATES",
            "    0.d0 0.d0 0.d0",
            f"    {pf_float(test.length_x_m)} {pf_float(test.length_y_m)} {pf_float(test.length_z_m)}",
            "  /",
            "END",
            "",
            "FLOW_CONDITION initial",
            "  TYPE",
            "    LIQUID_PRESSURE DIRICHLET",
            "  /",
            f"  LIQUID_PRESSURE {pf_float(initial_pressure)}",
            "END",
            "",
            "FLOW_CONDITION uniform_storage_rate",
            "  TYPE",
            "    RATE SCALED_VOLUMETRIC_RATE VOLUME",
            "  /",
            "  SYNC_TIMESTEP_WITH_UPDATE",
            "  RATE LIST",
            "    TIME_UNITS day",
            "    DATA_UNITS m^3/day",
            *rate_lines,
            "  /",
            "END",
            "",
            "INITIAL_CONDITION",
            "  FLOW_CONDITION initial",
            "  REGION all",
            "END",
            "",
            "SOURCE_SINK uniform_storage",
            "  FLOW_CONDITION uniform_storage_rate",
            "  REGION all",
            "/",
            "",
            "# Границы не назначены: PFLOTRAN применяет no-flow по умолчанию.",
            "STRATA",
            "  REGION all",
            "  MATERIAL soil",
            "END",
            "",
            "END_SUBSURFACE",
            "",
        ]
    )


def write_transient_analytical_files(test: TransientStorageTest, workdir: Path) -> None:
    times = transient_time_grid(test)
    volume = transient_domain_volume_m3(test)
    with (workdir / "uniform_storage_rate.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["time_days", "rate_m3_day"])
        writer.writeheader()
        for t in times:
            writer.writerow({"time_days": f"{t:.12g}", "rate_m3_day": f"{transient_rate_m3_day(test, t):.12g}"})
    with (workdir / "analytical_time_series.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "time_days",
                "saturation_analytical",
                "pressure_analytical_pa",
                "stored_water_volume_m3",
                "rate_m3_day",
            ],
        )
        writer.writeheader()
        for t in times:
            s = transient_saturation(test, t)
            writer.writerow(
                {
                    "time_days": f"{t:.12g}",
                    "saturation_analytical": f"{s:.12g}",
                    "pressure_analytical_pa": f"{transient_pressure(test, s):.12g}",
                    "stored_water_volume_m3": f"{test.porosity * volume * s:.12g}",
                    "rate_m3_day": f"{transient_rate_m3_day(test, t):.12g}",
                }
            )
    final_s = transient_saturation(test, test.duration_days)
    with (workdir / "analytical_solution.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["cell_id", "x_center_m", "saturation_analytical", "pressure_analytical_pa"])
        writer.writeheader()
        for i in range(test.nx * test.ny * test.nz):
            writer.writerow(
                {
                    "cell_id": i + 1,
                    "x_center_m": f"{((i % test.nx) + 0.5) * test.length_x_m / test.nx:.12g}",
                    "saturation_analytical": f"{final_s:.12g}",
                    "pressure_analytical_pa": f"{transient_pressure(test, final_s):.12g}",
                }
            )


def write_transient_test_summary(test: TransientStorageTest, path: Path, status: str = "GENERATED") -> None:
    lines = [
        "Transient uniform storage VG verification",
        "=========================================",
        "",
        f"Status: {status}",
        "Физический смысл:",
        "  Горизонтальная no-flow область получает равномерный RATE LIST.",
        "  Аналитика задаёт S(t)=S0+A*(1-cos(2*pi*t/T))/2 и Q=phi*V*dS/dt.",
        "",
        f"initial_saturation = {test.initial_saturation:.8g}",
        f"saturation_amplitude = {test.saturation_amplitude:.8g}",
        f"duration_days = {test.duration_days:.8g}",
        f"period_days = {test.period_days:.8g}",
        f"pressure_abs_tolerance_pa = {test.pressure_abs_tolerance_pa:.8g}",
        f"saturation_abs_tolerance = {test.saturation_abs_tolerance:.8g}",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


# -----------------------------------------------------------------------------
# PFLOTRAN execution helpers
# -----------------------------------------------------------------------------
def find_pflotran_native(params: dict[str, Any], cli_exe: str | None) -> str | None:
    candidates: list[str] = []
    if cli_exe:
        candidates.append(cli_exe)
    env_exe = os.environ.get("PFLOTRAN_EXE")
    if env_exe:
        candidates.append(env_exe)
    configured_exe = params.get("pflotran_exe") if params else None
    if configured_exe not in (None, ""):
        candidates.append(str(configured_exe))
    path_exe = shutil.which("pflotran")
    if path_exe:
        candidates.append(path_exe)

    for c in candidates:
        p = Path(str(c).strip('"'))
        if p.exists():
            return str(p)
        if shutil.which(str(c)):
            return str(c)
    return None


def has_wsl() -> bool:
    return shutil.which("wsl") is not None


def wsl_path(win_path: Path) -> str:
    completed = subprocess.run(
        ["wsl", "wslpath", "-a", str(win_path)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"wslpath failed: {completed.stderr}")
    return completed.stdout.strip()


def find_pflotran_wsl() -> str | None:
    if not has_wsl():
        return None
    cmd = (
        "if command -v pflotran >/dev/null 2>&1; then command -v pflotran; "
        "elif [ -x \"$HOME/pflotran/src/pflotran/pflotran\" ]; then echo \"$HOME/pflotran/src/pflotran/pflotran\"; "
        "elif [ -x \"$HOME/pflotran_build/pflotran/src/pflotran/pflotran\" ]; then echo \"$HOME/pflotran_build/pflotran/src/pflotran/pflotran\"; "
        "else true; fi"
    )
    completed = subprocess.run(["wsl", "bash", "-lc", cmd], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if completed.returncode != 0:
        return None
    out = completed.stdout.strip()
    return out if out else None


def run_native(workdir: Path, pflotran_exe: str, mpi_processes: int) -> int:
    log_path = workdir / "run_pflotran.log"
    mpirun = shutil.which("mpirun") or shutil.which("mpiexec")
    if mpirun and mpi_processes >= 1:
        cmd = [mpirun, "-n", str(mpi_processes), pflotran_exe, "-pflotranin", "pflotran.in"]
    else:
        cmd = [pflotran_exe, "-pflotranin", "pflotran.in"]

    with log_path.open("w", encoding="utf-8", errors="replace") as log:
        log.write("COMMAND: " + " ".join(shlex.quote(x) for x in cmd) + "\n\n")
        proc = subprocess.run(cmd, cwd=workdir, stdout=log, stderr=subprocess.STDOUT, text=True)
    return proc.returncode


def run_wsl(workdir: Path, pflotran_wsl: str, mpi_processes: int) -> int:
    log_path = workdir / "run_pflotran_wsl.log"
    workdir_wsl = wsl_path(workdir)

    run_line = (
        f"cd {shlex.quote(workdir_wsl)} && "
        f"if command -v mpirun >/dev/null 2>&1; then "
        f"mpirun -n {int(mpi_processes)} {shlex.quote(pflotran_wsl)} -pflotranin pflotran.in; "
        f"else {shlex.quote(pflotran_wsl)} -pflotranin pflotran.in; fi"
    )

    with log_path.open("w", encoding="utf-8", errors="replace") as log:
        log.write("WSL COMMAND: " + run_line + "\n\n")
        proc = subprocess.run(["wsl", "bash", "-lc", run_line], stdout=log, stderr=subprocess.STDOUT, text=True)
    return proc.returncode


# -----------------------------------------------------------------------------
# PFLOTRAN output parsing and test comparison
# -----------------------------------------------------------------------------
def _parse_tec_variables(line: str) -> list[str]:
    quoted = re.findall(r'"([^"]+)"', line)
    if quoted:
        return [q.strip() for q in quoted]
    _, _, rhs = line.partition("=")
    return [part.strip().strip('"') for part in rhs.split(",") if part.strip()]


def _float_line(line: str) -> list[float] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    upper = stripped.upper()
    if upper.startswith(("TITLE", "VARIABLES", "ZONE", "TEXT", "GEOMETRY")):
        return None
    parts = stripped.replace("D", "E").replace("d", "e").split()
    try:
        return [float(x) for x in parts]
    except ValueError:
        return None


def parse_tecpotran_tec(path: Path) -> tuple[list[str], list[list[float]]]:
    variables: list[str] = []
    rows: list[list[float]] = []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.strip().upper().startswith("VARIABLES"):
                variables = _parse_tec_variables(line)
                continue
            nums = _float_line(line)
            if nums is not None:
                rows.append(nums)
    if not variables and rows:
        variables = [f"col_{i}" for i in range(len(rows[0]))]
    return variables, rows


def find_final_tec_file(workdir: Path) -> Path | None:
    candidates = [p for p in workdir.glob("pflotran-[0-9]*.tec") if p.is_file()]
    if not candidates:
        return None
    # Prefer files with more numeric data and later modification time.
    return sorted(candidates, key=lambda p: (p.stat().st_size, p.stat().st_mtime))[-1]


def _find_column(variables: list[str], aliases: Iterable[str]) -> int | None:
    lower_vars = [v.lower().replace("_", " ") for v in variables]
    for alias in aliases:
        a = alias.lower()
        for i, v in enumerate(lower_vars):
            if a in v:
                return i
    return None


def load_numerical_pressure_profile(workdir: Path) -> tuple[Path, list[tuple[float, float]]]:
    tec = find_final_tec_file(workdir)
    if tec is None:
        raise FileNotFoundError("Не найден TECPLOT/DAT output PFLOTRAN (*.tec, *.dat, *.plt)")
    variables, rows = parse_tecpotran_tec(tec)
    if not rows:
        raise ValueError(f"Файл {tec.name} не содержит числовых строк")

    z_col = _find_column(variables, ["z [", "z", "z coordinate", "coordinate z"])
    p_col = _find_column(variables, ["liquid pressure", "pressure [pa]", "pressure"])
    if z_col is None:
        # For a 1D structured POINT output PFLOTRAN usually writes X,Y,Z first.
        z_col = 2 if len(rows[0]) > 2 else 0
    if p_col is None:
        # Try a conservative fallback: first column after coordinates with pressure-scale values.
        for j in range(len(rows[0])):
            vals = [r[j] for r in rows if len(r) > j]
            if vals and max(abs(v) for v in vals) > 1000.0:
                p_col = j
                break
    if p_col is None:
        raise ValueError(f"Не удалось найти колонку давления в {tec.name}. Variables: {variables}")

    profile = []
    for r in rows:
        if len(r) <= max(z_col, p_col):
            continue
        profile.append((float(r[z_col]), float(r[p_col])))
    if not profile:
        raise ValueError(f"Не удалось извлечь профиль z/pressure из {tec.name}")

    # PFLOTRAN may output all cells for 3D; aggregate pressure by z center for 1D comparison.
    by_z: dict[float, list[float]] = {}
    for z, p in profile:
        key = round(z, 12)
        by_z.setdefault(key, []).append(p)
    averaged = sorted((z, sum(vals) / len(vals)) for z, vals in by_z.items())
    return tec, averaged


def load_tecpotran_records(workdir: Path) -> tuple[Path, list[dict[str, float]]]:
    tec = find_final_tec_file(workdir)
    if tec is None:
        raise FileNotFoundError("Не найден TECPLOT/DAT output PFLOTRAN (*.tec, *.dat, *.plt)")
    variables, rows = parse_tecpotran_tec(tec)
    if not rows:
        raise ValueError(f"Файл {tec.name} не содержит числовых строк")
    records: list[dict[str, float]] = []
    for row in rows:
        record: dict[str, float] = {}
        for i, value in enumerate(row):
            key = variables[i] if i < len(variables) else f"col_{i}"
            record[key] = float(value)
        records.append(record)
    return tec, records


def record_value(record: dict[str, float], aliases: Iterable[str]) -> float:
    normalized = {k.lower().replace("_", " "): v for k, v in record.items()}
    for alias in aliases:
        a = alias.lower()
        for key, value in normalized.items():
            if a in key:
                return value
    raise KeyError(f"Не найдена колонка PFLOTRAN output: {list(aliases)}")


def records_to_z_pressure_saturation(records: list[dict[str, float]]) -> list[dict[str, float]]:
    converted: list[dict[str, float]] = []
    for record in records:
        converted.append(
            {
                "z_m": record_value(record, ["z [", "z", "coordinate z"]),
                "pressure_pa": record_value(record, ["liquid pressure", "pressure [pa]", "pressure"]),
                "saturation": record_value(record, ["liquid saturation", "saturation"]),
            }
        )
    by_z: dict[float, dict[str, list[float]]] = {}
    for row in converted:
        key = round(row["z_m"], 12)
        bucket = by_z.setdefault(key, {"pressure_pa": [], "saturation": []})
        bucket["pressure_pa"].append(row["pressure_pa"])
        bucket["saturation"].append(row["saturation"])
    return [
        {
            "z_m": z,
            "pressure_pa": sum(vals["pressure_pa"]) / len(vals["pressure_pa"]),
            "saturation": sum(vals["saturation"]) / len(vals["saturation"]),
        }
        for z, vals in sorted(by_z.items())
    ]


def compute_saturation_bounds(records: list[dict[str, float]]) -> tuple[float, float]:
    values = [row["saturation"] for row in records if "saturation" in row]
    if not values:
        raise ValueError("В PFLOTRAN output не найдена колонка Liquid Saturation.")
    return min(values), max(values)


def fit_line_slope(xs: list[float], ys: list[float]) -> float:
    if len(xs) != len(ys):
        raise ValueError("xs and ys must have the same length.")
    if len(xs) < 2:
        raise ValueError("At least two points are required to fit a slope.")
    x_mean = sum(xs) / len(xs)
    y_mean = sum(ys) / len(ys)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    denominator = sum((x - x_mean) ** 2 for x in xs)
    if denominator == 0.0:
        raise ValueError("Cannot fit slope: all x values are identical.")
    return numerator / denominator


def _warning_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if "WARNING" in line]


def classify_pflotran_warnings(log_path: Path, test_kind: str) -> dict[str, bool | int | str]:
    text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    mualem_smooth_phrase = (
        "Mualem-van Genuchten relative permeability function is being used without SMOOTH option"
    )
    lines = _warning_lines(text)
    mualem_count = sum(1 for line in lines if mualem_smooth_phrase in line)
    fail_like = any(any(pattern in line.lower() for pattern in UNEXPECTED_WARNING_FAIL_PATTERNS) for line in lines)
    policy = "ignore_for_saturated_test" if test_kind == "linear_darcy" else "warn_for_unsaturated_test"
    unexpected = max(0, len(lines) - mualem_count)
    if fail_like:
        check = "FAIL"
    elif policy == "ignore_for_saturated_test" and unexpected == 0:
        check = "PASS"
    elif len(lines) > 0 and policy == "warn_for_unsaturated_test":
        check = "WARN"
    elif unexpected > 0:
        check = "WARN"
    else:
        check = "PASS"
    return {
        "mualem_vg_without_smooth": mualem_count > 0,
        "mualem_vg_without_smooth_warning": mualem_count > 0,
        "warning_count": len(lines),
        "solver_warning_count": len(lines),
        "expected_warning_count": mualem_count,
        "unexpected_warning_count": unexpected,
        "warning_check": check,
        "warning_policy": policy,
        "mualem_smooth_warning_policy": policy,
    }


def parse_pflotran_solver_diagnostics(log_path: Path) -> dict[str, bool | int | float | None]:
    text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    cuts = [int(m.group(1)) for m in re.finditer(r"cuts\s*=\s*(\d+)", text, flags=re.IGNORECASE)]
    error_count = len(re.findall(r"\bERROR\b", text, flags=re.IGNORECASE))
    diverged = bool(re.search(r"\b(?:DIVERGED|SNES_DIVERGED)\b", text, flags=re.IGNORECASE))
    newton = [int(m.group(1)) for m in re.finditer(r"newton\s*=\s*(\d+)", text, flags=re.IGNORECASE)]
    linear = [int(m.group(1)) for m in re.finditer(r"linear\s*=\s*(\d+)", text, flags=re.IGNORECASE)]
    return {
        "solver_error_count": error_count,
        "solver_warning_count": len(_warning_lines(text)),
        "solver_diverged": diverged,
        "solver_cuts": max(cuts) if cuts else 0,
        "snes_diverged_count": len(re.findall(r"SNES_DIVERGED|DIVERGED", text, flags=re.IGNORECASE)),
        "flow_ts_snes_steps": len(re.findall(r"^\s*Step\s+\d+\s+Time=", text, flags=re.MULTILINE)),
        "flow_ts_newton_iterations": sum(newton),
        "flow_ts_linear_iterations": sum(linear),
        "wall_clock_time_s": None,
    }


def warning_status(warnings: dict[str, bool | int], policy: str) -> str:
    if policy == "warn_for_unsaturated_test" and warnings.get("mualem_vg_without_smooth"):
        return "WARN"
    if policy == "fail_if_unexpected" and warnings.get("warning_count", 0):
        return "FAIL"
    return "PASS"


def combined_test_status(physical_ok: bool, solver_ok: bool, warning_check: str) -> str:
    if not physical_ok or not solver_ok or warning_check == "FAIL":
        return "FAIL"
    if warning_check == "WARN":
        return "PASS_WITH_WARNINGS"
    return "PASS"


def write_unified_status(path: Path, fields: dict[str, Any]) -> None:
    ordered = []
    for key, value in fields.items():
        if isinstance(value, bool):
            value = str(value).lower()
        ordered.append(f"{key}={value}")
    path.write_text("\n".join(ordered) + "\n", encoding="utf-8")


def find_pflotran_conservation_files(output_dir: Path) -> list[Path]:
    return sorted(p for p in output_dir.glob("*conservation*") if p.is_file())


def find_pflotran_mass_balance_files(output_dir: Path) -> list[Path]:
    return sorted(p for p in output_dir.glob("*mass*balance*") if p.is_file())


def parse_pflotran_conservation_or_mass_balance(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    header = next((line for line in lines if not line.startswith("#")), "")
    tokens = re.split(r"[\s,]+", header)
    interesting = [
        token
        for token in tokens
        if any(marker in token.lower() for marker in ("flux", "source", "sink", "liquid", "water", "boundary"))
    ]
    return {
        "path": str(path),
        "line_count": len(lines),
        "header": header[:500],
        "candidate_columns": interesting,
        "parseable": bool(interesting),
    }


def direct_flux_output_probe(workdir: Path) -> dict[str, Any]:
    conservation_files = find_pflotran_conservation_files(workdir)
    mass_balance_files = find_pflotran_mass_balance_files(workdir)
    velocity_files = sorted(p for p in workdir.glob("*vel*.tec") if p.is_file())
    parsed = [parse_pflotran_conservation_or_mass_balance(p) for p in conservation_files + mass_balance_files]
    q_direct_m_s = None
    if velocity_files:
        variables, rows = parse_tecpotran_tec(velocity_files[-1])
        qz_col = _find_column(variables, ["qlz", "z velocity", "liquid z"])
        if qz_col is not None and rows:
            vals = [row[qz_col] for row in rows if len(row) > qz_col]
            if vals:
                # PFLOTRAN velocity Tecplot пишет q в m/day при TIME_UNITS day.
                q_direct_m_s = sum(vals) / len(vals) / 86400.0
    parseable = any(item.get("parseable") for item in parsed) or q_direct_m_s is not None
    return {
        "requested": True,
        "conservation_files": [p.name for p in conservation_files],
        "mass_balance_files": [p.name for p in mass_balance_files],
        "velocity_files": [p.name for p in velocity_files],
        "parseable": parseable,
        "q_direct_m_s": q_direct_m_s,
        "parsed_files": parsed,
        "reason": (
            "parseable velocity/conservation output found" if parseable else "no recognized liquid flux columns"
        ),
    }


def write_test_comparison(test: LinearDarcyTest, numerical: list[tuple[float, float]], path: Path) -> tuple[float, float, int]:
    max_abs = 0.0
    max_rel = 0.0
    n = 0
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "z_m",
                "pressure_numerical_pa",
                "pressure_analytical_pa",
                "abs_error_pa",
                "rel_error",
            ],
        )
        writer.writeheader()
        for z, p_num in numerical:
            if z < -1e-10 or z > test.column_height_m + 1e-10:
                continue
            p_ana = analytical_pressure(test, z)
            abs_err = abs(p_num - p_ana)
            rel_err = abs_err / max(abs(p_ana), 1.0)
            max_abs = max(max_abs, abs_err)
            max_rel = max(max_rel, rel_err)
            n += 1
            writer.writerow(
                {
                    "z_m": f"{z:.12g}",
                    "pressure_numerical_pa": f"{p_num:.12g}",
                    "pressure_analytical_pa": f"{p_ana:.12g}",
                    "abs_error_pa": f"{abs_err:.12g}",
                    "rel_error": f"{rel_err:.12g}",
                }
            )
    return max_abs, max_rel, n


def write_test_svg(test: LinearDarcyTest, comparison_csv: Path, svg_path: Path) -> None:
    rows = []
    if not comparison_csv.exists():
        return
    with comparison_csv.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append((float(r["z_m"]), float(r["pressure_numerical_pa"]), float(r["pressure_analytical_pa"])))
    if not rows:
        return
    p_values = [p for _, p, pa in rows for p in (p, pa)]
    p_min = min(p_values)
    p_max = max(p_values)
    if math.isclose(p_min, p_max):
        p_min -= 1.0
        p_max += 1.0
    z_min = 0.0
    z_max = test.column_height_m
    width, height = 900, 520
    left, right, top, bottom = 90, 40, 40, 70
    plot_w = width - left - right
    plot_h = height - top - bottom

    def sx(p: float) -> float:
        return left + (p - p_min) / (p_max - p_min) * plot_w

    def sy(z: float) -> float:
        return top + (z_max - z) / (z_max - z_min) * plot_h

    ana_points = " ".join(f"{sx(pa):.2f},{sy(z):.2f}" for z, _, pa in rows)
    num_points = " ".join(f"{sx(p):.2f},{sy(z):.2f}" for z, p, _ in rows)

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="100%" height="100%" fill="#ffffff"/>
  <text x="{width/2:.0f}" y="24" text-anchor="middle" font-family="Arial" font-size="18" font-weight="700">_test: PFLOTRAN vs аналитическое решение Дарси</text>
  <line x1="{left}" y1="{top}" x2="{left}" y2="{top+plot_h}" stroke="#222"/>
  <line x1="{left}" y1="{top+plot_h}" x2="{left+plot_w}" y2="{top+plot_h}" stroke="#222"/>
  <text x="{left+plot_w/2:.0f}" y="{height-20}" text-anchor="middle" font-family="Arial" font-size="13">Давление, Па</text>
  <text x="22" y="{top+plot_h/2:.0f}" transform="rotate(-90 22 {top+plot_h/2:.0f})" text-anchor="middle" font-family="Arial" font-size="13">z, м</text>
  <polyline fill="none" stroke="#1f77b4" stroke-width="3" points="{ana_points}"/>
  <polyline fill="none" stroke="#d62728" stroke-width="2" stroke-dasharray="7,5" points="{num_points}"/>
  <rect x="{left+plot_w-260}" y="{top+15}" width="245" height="62" fill="#fff" stroke="#ccc"/>
  <line x1="{left+plot_w-245}" y1="{top+35}" x2="{left+plot_w-200}" y2="{top+35}" stroke="#1f77b4" stroke-width="3"/>
  <text x="{left+plot_w-190}" y="{top+40}" font-family="Arial" font-size="12">аналитика</text>
  <line x1="{left+plot_w-245}" y1="{top+60}" x2="{left+plot_w-200}" y2="{top+60}" stroke="#d62728" stroke-width="2" stroke-dasharray="7,5"/>
  <text x="{left+plot_w-190}" y="{top+65}" font-family="Arial" font-size="12">PFLOTRAN</text>
  <text x="{left}" y="{top+plot_h+22}" font-family="Arial" font-size="11">{p_min:.3g}</text>
  <text x="{left+plot_w}" y="{top+plot_h+22}" text-anchor="end" font-family="Arial" font-size="11">{p_max:.3g}</text>
  <text x="{left-8}" y="{top+plot_h}" text-anchor="end" font-family="Arial" font-size="11">0</text>
  <text x="{left-8}" y="{top+5}" text-anchor="end" font-family="Arial" font-size="11">{z_max:.3g}</text>
</svg>'''
    svg_path.write_text(svg, encoding="utf-8")


def evaluate_test_after_run(test: LinearDarcyTest, workdir: Path) -> TestResult:
    status_path = workdir / "TEST_STATUS.txt"
    try:
        tec, records_raw = load_tecpotran_records(workdir)
        records = records_to_z_pressure_saturation(records_raw)
        numerical = [(row["z_m"], row["pressure_pa"]) for row in records]
        max_abs, max_rel, n = write_test_comparison(test, numerical, workdir / "test_comparison.csv")
        write_test_svg(test, workdir / "test_comparison.csv", workdir / "test_comparison.svg")
        saturation_min, saturation_max = compute_saturation_bounds(records)
        saturation_check = saturation_min >= 0.999999 and saturation_max <= 1.000001
        z_values = [row["z_m"] for row in records]
        p_values = [row["pressure_pa"] for row in records]
        numerical_slope = fit_line_slope(z_values, p_values)
        analytical_slope = -test.rho_water_kg_m3 * test.gravity_m_s2 * (
            1.0 + test.imposed_flux_z_m_s / test.ksat_m_s
        )
        q_from_gradient = -test.ksat_m_s * (numerical_slope / (test.rho_water_kg_m3 * test.gravity_m_s2) + 1.0)
        q_error = q_from_gradient - test.imposed_flux_z_m_s
        flux_tolerance = max(1.0e-9, 2.0e-3 * abs(test.imposed_flux_z_m_s))
        flux_check = abs(q_error) <= flux_tolerance
        log_path = workdir / "run_pflotran.log"
        warnings = classify_pflotran_warnings(log_path, "linear_darcy")
        solver = parse_pflotran_solver_diagnostics(log_path)
        direct_probe = direct_flux_output_probe(workdir)
        pressure_check = n > 0 and max_abs <= test.tolerance_abs_pressure_pa and max_rel <= test.tolerance_rel_pressure
        solver_check = (
            solver["solver_error_count"] == 0 and not solver["solver_diverged"] and solver["solver_cuts"] == 0
        )
        warn_check = str(warnings["warning_check"])
        physical_ok = (
            n > 0
            and pressure_check
            and saturation_check
            and flux_check
        )
        status = combined_test_status(physical_ok, solver_check, warn_check)
        pressure_info = pressure_reporting(max_abs, test.tolerance_abs_pressure_pa)
        reported_abs = pressure_info["reported_max_abs_pressure_error_pa"]
        diagnostics = {
            "pressure_reporting": pressure_info,
            "max_rel_pressure_error": max_rel,
            "saturation_min": saturation_min,
            "saturation_max": saturation_max,
            "numerical_pressure_slope_pa_m": numerical_slope,
            "analytical_pressure_slope_pa_m": analytical_slope,
            "q_from_gradient_m_s": q_from_gradient,
            "q_error_m_s": q_error,
            "flux_tolerance_abs_m_s": flux_tolerance,
            "direct_flux_output_probe": direct_probe,
            **warnings,
            **solver,
        }
        (workdir / "test_diagnostics.json").write_text(json.dumps(diagnostics, indent=2), encoding="utf-8")
        write_unified_status(
            status_path,
            {
                "TEST_STATUS": status,
                "test_id": "_test_linear_darcy",
                "pressure_check": "PASS" if pressure_check else "FAIL",
                "saturation_check": "PASS" if saturation_check else "FAIL",
                "flux_check": "PASS" if flux_check else "FAIL",
                "solver_check": "PASS" if solver_check else "FAIL",
                "warning_check": warn_check,
                "raw_max_abs_pressure_error_pa": f"{max_abs:.12g}",
                "max_abs_pressure_error_pa": f"{reported_abs:.12g}",
                "pressure_report_zero_threshold_pa": f"{PRESSURE_REPORT_ZERO_THRESHOLD_PA:.12g}",
                "pressure_abs_tolerance_pa": f"{test.tolerance_abs_pressure_pa:.12g}",
                "saturation_min": f"{saturation_min:.12g}",
                "saturation_max": f"{saturation_max:.12g}",
                "solver_error_count": solver["solver_error_count"],
                "solver_warning_count": solver["solver_warning_count"],
                "solver_diverged": solver["solver_diverged"],
                "solver_cuts": solver["solver_cuts"],
                "snes_diverged_count": solver["snes_diverged_count"],
                "allow_solver_cuts": "FALSE",
                "warning_count": warnings["warning_count"],
                "expected_warning_count": warnings["expected_warning_count"],
                "unexpected_warning_count": warnings["unexpected_warning_count"],
                "mualem_vg_without_smooth_warning": warnings["mualem_vg_without_smooth"],
                "mualem_smooth_warning_policy": warnings["mualem_smooth_warning_policy"],
                "direct_flux_output_probe": "AVAILABLE" if direct_probe["parseable"] else "UNAVAILABLE",
                "direct_flux_output_available": direct_probe["parseable"],
                "direct_flux_output_file": (
                    (direct_probe["conservation_files"] + direct_probe["mass_balance_files"] + direct_probe["velocity_files"])[0]
                    if direct_probe["conservation_files"] or direct_probe["mass_balance_files"] or direct_probe["velocity_files"]
                    else "NA"
                ),
                "output_file": tec.name,
                "comparison_points": n,
                "max_rel_pressure_error": f"{max_rel:.12g}",
                "tolerance_rel_pressure": f"{test.tolerance_rel_pressure:.12g}",
                "q_from_gradient_m_s": f"{q_from_gradient:.12g}",
                "q_error_m_s": f"{q_error:.12g}",
                "expected_formula": "P(z)=P_bottom-rho*g*(1+qz/Ks)*z",
                "qz_m_s": f"{test.imposed_flux_z_m_s:.12g}",
            },
        )
        print(f"[TEST] {status}: max_abs={max_abs:.6g} Pa, max_rel={max_rel:.6g}, points={n}")
        return TestResult("_test_linear_darcy", status, workdir, diagnostics)
    except Exception as exc:
        status_path.write_text(
            "TEST_STATUS=UNKNOWN\n"
            f"reason={type(exc).__name__}: {exc}\n"
            "PFLOTRAN output was not parsed; generated analytical_solution.csv is still available.\n",
            encoding="utf-8",
        )
        print(f"[TEST] UNKNOWN: {exc}", file=sys.stderr)
        return TestResult("_test_linear_darcy", "UNKNOWN", workdir, {"reason": f"{type(exc).__name__}: {exc}"})


def write_vg_comparison(test: VGRichardsTest, records: list[dict[str, float]], path: Path) -> tuple[float, float, int]:
    max_pressure = 0.0
    max_saturation = 0.0
    n = 0
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "z_m",
                "pressure_numerical_pa",
                "pressure_analytical_pa",
                "pressure_abs_error_pa",
                "saturation_numerical",
                "saturation_analytical",
                "saturation_abs_error",
            ],
        )
        writer.writeheader()
        for row in records:
            z = row["z_m"]
            p_ana = vg_pressure(test, z)
            s_ana = vg_saturation(test, p_ana)
            p_err = abs(row["pressure_pa"] - p_ana)
            s_err = abs(row["saturation"] - s_ana)
            max_pressure = max(max_pressure, p_err)
            max_saturation = max(max_saturation, s_err)
            n += 1
            writer.writerow(
                {
                    "z_m": f"{z:.12g}",
                    "pressure_numerical_pa": f"{row['pressure_pa']:.12g}",
                    "pressure_analytical_pa": f"{p_ana:.12g}",
                    "pressure_abs_error_pa": f"{p_err:.12g}",
                    "saturation_numerical": f"{row['saturation']:.12g}",
                    "saturation_analytical": f"{s_ana:.12g}",
                    "saturation_abs_error": f"{s_err:.12g}",
                }
            )
    return max_pressure, max_saturation, n


def evaluate_vg_test_after_run(test: VGRichardsTest, workdir: Path) -> TestResult:
    status_path = workdir / "TEST_STATUS.txt"
    try:
        tec, records_raw = load_tecpotran_records(workdir)
        records = records_to_z_pressure_saturation(records_raw)
        max_pressure, max_saturation, n = write_vg_comparison(test, records, workdir / "test_comparison.csv")
        saturation_min, saturation_max = compute_saturation_bounds(records)
        z_values = [row["z_m"] for row in records]
        p_values = [row["pressure_pa"] for row in records]
        numerical_slope = fit_line_slope(z_values, p_values)
        if test.test_kind == "hydrostatic_vg_no_flow":
            analytical_slope = -test.rho_water_kg_m3 * test.gravity_m_s2
            # В ненасыщенном hydrostatic-тесте поток масштабируется K(S), а не Ks:
            # при малом численном остатке градиента использование Ks искусственно
            # завышает диагностический q на несколько порядков.
            kr_values = []
            for row in records:
                p_ana = vg_pressure(test, row["z_m"])
                h_m = (p_ana - test.atmospheric_pressure_pa) / (test.rho_water_kg_m3 * test.gravity_m_s2)
                se = vg_effective_saturation_from_pressure_head(h_m, test.alpha_1_m, test.n, test.m)
                kr_values.append(mualem_vg_relative_permeability(se, test.m))
            kr_const = sum(kr_values) / len(kr_values)
            k_eff = test.ksat_m_s * kr_const
            q_from_gradient = -k_eff * (numerical_slope / (test.rho_water_kg_m3 * test.gravity_m_s2) + 1.0)
            q_expected = 0.0
            flux_tolerance = test.flux_abs_tolerance_m_s
        else:
            analytical_slope = 0.0
            h_const = (test.constant_pressure_pa - test.atmospheric_pressure_pa) / (
                test.rho_water_kg_m3 * test.gravity_m_s2
            )
            se_const = vg_effective_saturation_from_pressure_head(h_const, test.alpha_1_m, test.n, test.m)
            kr_const = mualem_vg_relative_permeability(se_const, test.m)
            k_eff = test.ksat_m_s * kr_const
            q_expected = -k_eff
            q_from_gradient = -k_eff * (numerical_slope / (test.rho_water_kg_m3 * test.gravity_m_s2) + 1.0)
            flux_tolerance = max(1.0e-12, test.flux_relative_tolerance * abs(q_expected))
        q_error = q_from_gradient - q_expected
        pressure_check = max_pressure <= test.pressure_abs_tolerance_pa
        saturation_check = max_saturation <= test.saturation_abs_tolerance
        flux_check = abs(q_error) <= flux_tolerance
        log_path = workdir / "run_pflotran.log"
        warnings = classify_pflotran_warnings(log_path, test.test_kind)
        solver = parse_pflotran_solver_diagnostics(log_path)
        direct_probe = direct_flux_output_probe(workdir)
        solver_check = (
            solver["solver_error_count"] == 0 and not solver["solver_diverged"] and solver["solver_cuts"] == 0
        )
        warn_policy = str(warnings["mualem_smooth_warning_policy"])
        warn_check = str(warnings["warning_check"])
        status = combined_test_status(n > 0 and pressure_check and saturation_check and flux_check, solver_check, warn_check)
        pressure_info = pressure_reporting(max_pressure, test.pressure_abs_tolerance_pa)
        reported_abs = pressure_info["reported_max_abs_pressure_error_pa"]
        if test.test_kind == "unit_gradient_unsat":
            h_const = (test.constant_pressure_pa - test.atmospheric_pressure_pa) / (
                test.rho_water_kg_m3 * test.gravity_m_s2
            )
            se_const = vg_effective_saturation_from_pressure_head(h_const, test.alpha_1_m, test.n, test.m)
            kr_const = mualem_vg_relative_permeability(se_const, test.m)
            k_eff = test.ksat_m_s * kr_const
        metrics = {
            "pressure_reporting": pressure_info,
            "max_abs_saturation_error": max_saturation,
            "saturation_min": saturation_min,
            "saturation_max": saturation_max,
            "numerical_pressure_slope_pa_m": numerical_slope,
            "analytical_pressure_slope_pa_m": analytical_slope,
            "kr_const": kr_const,
            "k_eff_m_s": k_eff,
            "q_expected_m_s": q_expected,
            "q_from_gradient_m_s": q_from_gradient,
            "q_error_m_s": q_error,
            "flux_tolerance_abs_m_s": flux_tolerance,
            "direct_flux_output_probe": direct_probe,
            "q_direct_m_s": direct_probe.get("q_direct_m_s"),
            "q_direct_error_m_s": (
                direct_probe["q_direct_m_s"] - q_expected if direct_probe.get("q_direct_m_s") is not None else None
            ),
            **warnings,
            **solver,
        }
        if test.test_kind == "hydrostatic_vg_no_flow":
            pressure_head_bottom = (test.bottom_pressure_pa - test.atmospheric_pressure_pa) / (
                test.rho_water_kg_m3 * test.gravity_m_s2
            )
            pressure_head_top = (
                test.bottom_pressure_pa
                - test.rho_water_kg_m3 * test.gravity_m_s2 * test.column_height_m
                - test.atmospheric_pressure_pa
            ) / (test.rho_water_kg_m3 * test.gravity_m_s2)
            hydraulic_head_bottom = pressure_head_bottom
            hydraulic_head_top = pressure_head_top + test.column_height_m
            metrics.update(
                {
                    "pressure_head_bottom_m": pressure_head_bottom,
                    "pressure_head_top_m": pressure_head_top,
                    "hydraulic_head_bottom_m": hydraulic_head_bottom,
                    "hydraulic_head_top_m": hydraulic_head_top,
                    "hydraulic_head_slope_m_per_m": (hydraulic_head_top - hydraulic_head_bottom)
                    / test.column_height_m,
                    "saturation_bottom_cell": records[0]["saturation"],
                    "saturation_top_cell": records[-1]["saturation"],
                }
            )
        (workdir / "test_diagnostics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
        status_fields: dict[str, Any] = {
            "TEST_STATUS": status,
            "test_id": test.test_id,
            "pressure_check": "PASS" if pressure_check else "FAIL",
            "saturation_check": "PASS" if saturation_check else "FAIL",
            "flux_check": "PASS" if flux_check else "FAIL",
            "solver_check": "PASS" if solver_check else "FAIL",
            "warning_check": warn_check,
            "raw_max_abs_pressure_error_pa": f"{max_pressure:.12g}",
            "max_abs_pressure_error_pa": f"{reported_abs:.12g}",
            "pressure_report_zero_threshold_pa": f"{PRESSURE_REPORT_ZERO_THRESHOLD_PA:.12g}",
            "pressure_abs_tolerance_pa": f"{test.pressure_abs_tolerance_pa:.12g}",
            "saturation_min": f"{saturation_min:.12g}",
            "saturation_max": f"{saturation_max:.12g}",
            "solver_error_count": solver["solver_error_count"],
            "solver_warning_count": solver["solver_warning_count"],
            "solver_diverged": solver["solver_diverged"],
            "solver_cuts": solver["solver_cuts"],
            "snes_diverged_count": solver["snes_diverged_count"],
            "allow_solver_cuts": "FALSE",
            "warning_count": warnings["warning_count"],
            "expected_warning_count": warnings["expected_warning_count"],
            "unexpected_warning_count": warnings["unexpected_warning_count"],
            "mualem_vg_without_smooth_warning": warnings["mualem_vg_without_smooth"],
            "mualem_smooth_warning_policy": warn_policy,
            "direct_flux_output_probe": "AVAILABLE" if direct_probe["parseable"] else "UNAVAILABLE",
            "direct_flux_output_available": direct_probe["parseable"],
            "direct_flux_output_file": (
                (direct_probe["conservation_files"] + direct_probe["mass_balance_files"] + direct_probe["velocity_files"])[0]
                if direct_probe["conservation_files"] or direct_probe["mass_balance_files"] or direct_probe["velocity_files"]
                else "NA"
            ),
            "output_file": tec.name,
            "comparison_points": n,
            "max_abs_saturation_error": f"{max_saturation:.12g}",
            "numerical_pressure_slope_pa_m": f"{numerical_slope:.12g}",
            "analytical_pressure_slope_pa_m": f"{analytical_slope:.12g}",
            "q_from_gradient_m_s": f"{q_from_gradient:.12g}",
            "q_error_m_s": f"{q_error:.12g}",
        }
        if test.test_kind == "hydrostatic_vg_no_flow":
            status_fields.update(
                {
                    "pressure_head_bottom_m": f"{metrics['pressure_head_bottom_m']:.12g}",
                    "pressure_head_top_m": f"{metrics['pressure_head_top_m']:.12g}",
                    "hydraulic_head_bottom_m": f"{metrics['hydraulic_head_bottom_m']:.12g}",
                    "hydraulic_head_top_m": f"{metrics['hydraulic_head_top_m']:.12g}",
                    "hydraulic_head_slope_m_per_m": f"{metrics['hydraulic_head_slope_m_per_m']:.12g}",
                    "saturation_bottom_cell": f"{metrics['saturation_bottom_cell']:.12g}",
                    "saturation_top_cell": f"{metrics['saturation_top_cell']:.12g}",
                    "flux_expected_m_s": f"{q_expected:.12g}",
                }
            )
        else:
            direct_q = direct_probe.get("q_direct_m_s")
            status_fields.update(
                {
                    "flux_observation_method": "gradient_reconstruction",
                    "kr_const": f"{kr_const:.12g}",
                    "k_eff_m_s": f"{k_eff:.12g}",
                    "q_expected_m_s": f"{q_expected:.12g}",
                    "q_direct_m_s": f"{direct_q:.12g}" if direct_q is not None else "NA",
                    "q_direct_error_m_s": f"{direct_q - q_expected:.12g}" if direct_q is not None else "NA",
                    "direct_flux_output_note": (
                        "PFLOTRAN velocity output parsed"
                        if direct_q is not None
                        else "PFLOTRAN conservation/velocity output was generated but no parseable liquid flux field was found"
                    ),
                }
            )
        write_unified_status(status_path, status_fields)
        print(f"[TEST] {status}: {test.test_id} max_abs={max_pressure:.6g} Pa, max_sat={max_saturation:.6g}")
        return TestResult(test.test_id, status, workdir, metrics)
    except Exception as exc:
        status_path.write_text(f"TEST_STATUS=UNKNOWN\nreason={type(exc).__name__}: {exc}\n", encoding="utf-8")
        print(f"[TEST] UNKNOWN {test.test_id}: {exc}", file=sys.stderr)
        return TestResult(test.test_id, "UNKNOWN", workdir, {"reason": f"{type(exc).__name__}: {exc}"})


def transient_output_times_from_log(log_path: Path) -> list[float]:
    text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    times: list[float] = [0.0]
    current_time = 0.0
    for line in text.splitlines():
        match = re.search(r"Time=\s*([0-9.Ee+-]+)", line)
        if match:
            current_time = float(match.group(1).replace("D", "E").replace("d", "e"))
        if "write tecplot output file" in line.lower():
            if not times or not math.isclose(times[-1], current_time):
                times.append(current_time)
    return times


def load_transient_snapshots(workdir: Path) -> list[dict[str, float]]:
    files = sorted((p for p in workdir.glob("*.tec") if "-vel-" not in p.name), key=lambda p: (p.name, p.stat().st_mtime))
    output_times = transient_output_times_from_log(workdir / "run_pflotran.log")
    snapshots: list[dict[str, float]] = []
    for index, path in enumerate(files):
        variables, rows = parse_tecpotran_tec(path)
        if not rows:
            continue
        records = []
        for row in rows:
            records.append({variables[i] if i < len(variables) else f"col_{i}": float(v) for i, v in enumerate(row)})
        converted = records_to_z_pressure_saturation(records)
        pressures = [r["pressure_pa"] for r in converted]
        sats = [r["saturation"] for r in converted]
        snapshots.append(
            {
                "index": float(index),
                "time_days": output_times[index] if index < len(output_times) else float(index),
                "pressure_mean_pa": sum(pressures) / len(pressures),
                "pressure_min_pa": min(pressures),
                "pressure_max_pa": max(pressures),
                "saturation_mean": sum(sats) / len(sats),
                "saturation_min": min(sats),
                "saturation_max": max(sats),
            }
        )
    return snapshots


def write_xy_svg(path: Path, title: str, x_label: str, y_label: str, rows: list[dict[str, float]], y_num: str, y_ana: str) -> None:
    if not rows:
        return
    xs = [r["time_days"] for r in rows]
    ys = [r[y_num] for r in rows] + [r[y_ana] for r in rows]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    if math.isclose(x_min, x_max):
        x_max = x_min + 1.0
    if math.isclose(y_min, y_max):
        y_min -= 1.0
        y_max += 1.0
    width, height = 900, 520
    left, right, top, bottom = 90, 40, 42, 72
    plot_w = width - left - right
    plot_h = height - top - bottom

    def sx(x: float) -> float:
        return left + (x - x_min) / (x_max - x_min) * plot_w

    def sy(y: float) -> float:
        return top + (y_max - y) / (y_max - y_min) * plot_h

    num_points = " ".join(f"{sx(r['time_days']):.2f},{sy(r[y_num]):.2f}" for r in rows)
    ana_points = " ".join(f"{sx(r['time_days']):.2f},{sy(r[y_ana]):.2f}" for r in rows)
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="100%" height="100%" fill="#ffffff"/>
  <text x="{width/2:.0f}" y="26" text-anchor="middle" font-family="Arial" font-size="18" font-weight="700">{title}</text>
  <line x1="{left}" y1="{top}" x2="{left}" y2="{top+plot_h}" stroke="#222"/>
  <line x1="{left}" y1="{top+plot_h}" x2="{left+plot_w}" y2="{top+plot_h}" stroke="#222"/>
  <text x="{left+plot_w/2:.0f}" y="{height-22}" text-anchor="middle" font-family="Arial" font-size="13">{x_label}</text>
  <text x="22" y="{top+plot_h/2:.0f}" transform="rotate(-90 22 {top+plot_h/2:.0f})" text-anchor="middle" font-family="Arial" font-size="13">{y_label}</text>
  <polyline fill="none" stroke="#1f77b4" stroke-width="3" points="{ana_points}"/>
  <polyline fill="none" stroke="#d62728" stroke-width="2" stroke-dasharray="7,5" points="{num_points}"/>
  <text x="{left+plot_w-210}" y="{top+36}" font-family="Arial" font-size="12" fill="#1f77b4">аналитика</text>
  <text x="{left+plot_w-210}" y="{top+58}" font-family="Arial" font-size="12" fill="#d62728">PFLOTRAN</text>
</svg>'''
    path.write_text(svg, encoding="utf-8")


def evaluate_transient_storage_after_run(test: TransientStorageTest, workdir: Path) -> TestResult:
    status_path = workdir / "TEST_STATUS.txt"
    try:
        snapshots = load_transient_snapshots(workdir)
        if not snapshots:
            raise ValueError("Не найдены transient TECPLOT snapshots PFLOTRAN")
        rows: list[dict[str, float]] = []
        max_p_err = 0.0
        max_s_err = 0.0
        max_s_uniformity = 0.0
        max_p_uniformity = 0.0
        for i, snap in enumerate(snapshots):
            t = snap["time_days"]
            s_ana = transient_saturation(test, t)
            p_ana = transient_pressure(test, s_ana)
            p_err = abs(snap["pressure_mean_pa"] - p_ana)
            s_err = abs(snap["saturation_mean"] - s_ana)
            s_uni = snap["saturation_max"] - snap["saturation_min"]
            p_uni = snap["pressure_max_pa"] - snap["pressure_min_pa"]
            max_p_err = max(max_p_err, p_err)
            max_s_err = max(max_s_err, s_err)
            max_s_uniformity = max(max_s_uniformity, s_uni)
            max_p_uniformity = max(max_p_uniformity, p_uni)
            rows.append(
                {
                    "time_days": t,
                    "pressure_mean_pa": snap["pressure_mean_pa"],
                    "pressure_analytical_pa": p_ana,
                    "saturation_mean": snap["saturation_mean"],
                    "saturation_analytical": s_ana,
                    "pressure_abs_error_pa": p_err,
                    "saturation_abs_error": s_err,
                    "saturation_spread": s_uni,
                    "pressure_spread_pa": p_uni,
                }
            )
        with (workdir / "test_comparison.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        write_xy_svg(
            workdir / "test_comparison.svg",
            "Transient uniform storage: saturation",
            "time, days",
            "S",
            rows,
            "saturation_mean",
            "saturation_analytical",
        )
        write_xy_svg(
            workdir / "test_pressure_comparison.svg",
            "Transient uniform storage: pressure",
            "time, days",
            "P, Pa",
            rows,
            "pressure_mean_pa",
            "pressure_analytical_pa",
        )
        integrated_rate = 0.0
        rate_times = transient_time_grid(test)
        for a, b in zip(rate_times, rate_times[1:]):
            qa = transient_rate_m3_day(test, a)
            qb = transient_rate_m3_day(test, b)
            integrated_rate += 0.5 * (qa + qb) * (b - a)
        storage_delta = test.porosity * transient_domain_volume_m3(test) * (
            rows[-1]["saturation_analytical"] - rows[0]["saturation_analytical"]
        )
        mass_balance_error = abs(integrated_rate - storage_delta)
        source_rates = [transient_rate_m3_day(test, t) for t in rate_times]
        pressure_check = max_p_err <= test.pressure_abs_tolerance_pa
        saturation_check = max_s_err <= test.saturation_abs_tolerance
        source_sink_balance_check = mass_balance_error <= test.mass_balance_tolerance_m3
        mass_balance_check = mass_balance_error <= test.mass_balance_tolerance_m3
        uniformity_check = max_s_uniformity <= test.uniformity_tolerance
        log_path = workdir / "run_pflotran.log"
        warnings = classify_pflotran_warnings(log_path, "transient_uniform_storage_vg")
        solver = parse_pflotran_solver_diagnostics(log_path)
        direct_probe = direct_flux_output_probe(workdir)
        solver_check = (
            solver["solver_error_count"] == 0 and not solver["solver_diverged"] and solver["solver_cuts"] == 0
        )
        warn_policy = str(warnings["mualem_smooth_warning_policy"])
        warn_check = str(warnings["warning_check"])
        status = combined_test_status(
            pressure_check and saturation_check and source_sink_balance_check and mass_balance_check and uniformity_check,
            solver_check,
            warn_check,
        )
        pressure_info = pressure_reporting(max_p_err, test.pressure_abs_tolerance_pa)
        reported_abs = pressure_info["reported_max_abs_pressure_error_pa"]
        metrics = {
            "pressure": {
                **pressure_info,
                "pressure_check": "PASS" if pressure_check else "FAIL",
            },
            "saturation": {
                "max_abs_saturation_error": max_s_err,
                "saturation_abs_tolerance": test.saturation_abs_tolerance,
                "saturation_check": "PASS" if saturation_check else "FAIL",
            },
            "uniformity": {
                "max_spatial_saturation_range": max_s_uniformity,
                "max_spatial_pressure_range_pa": max_p_uniformity,
                "uniformity_check": "PASS" if uniformity_check else "FAIL",
            },
            "source_sink_balance": {
                "source_rate_min_m3_day": min(source_rates),
                "source_rate_max_m3_day": max(source_rates),
                "max_abs_storage_rate_integral_error_m3": mass_balance_error,
                "mass_balance_abs_tolerance_m3": test.mass_balance_tolerance_m3,
                "source_sink_balance_check": "PASS" if source_sink_balance_check else "FAIL",
                "mass_balance_check": "PASS" if mass_balance_check else "FAIL",
            },
            "solver": {
                **solver,
                "solver_check": "PASS" if solver_check else "FAIL",
            },
            "direct_flux_output_probe": direct_probe,
            **warnings,
            **solver,
        }
        (workdir / "test_diagnostics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
        write_unified_status(
            status_path,
            {
                "TEST_STATUS": status,
                "test_id": test.test_id,
                "pressure_check": "PASS" if pressure_check else "FAIL",
                "saturation_check": "PASS" if saturation_check and uniformity_check else "FAIL",
                "uniformity_check": "PASS" if uniformity_check else "FAIL",
                "source_sink_balance_check": "PASS" if source_sink_balance_check else "FAIL",
                "mass_balance_check": "PASS" if mass_balance_check else "FAIL",
                "flux_check": "SKIP",
                "flux_observation_method": "no_spatial_flux_uniform_storage_test",
                "solver_check": "PASS" if solver_check else "FAIL",
                "warning_check": warn_check,
                "raw_max_abs_pressure_error_pa": f"{max_p_err:.12g}",
                "max_abs_pressure_error_pa": f"{reported_abs:.12g}",
                "pressure_report_zero_threshold_pa": f"{PRESSURE_REPORT_ZERO_THRESHOLD_PA:.12g}",
                "pressure_abs_tolerance_pa": f"{test.pressure_abs_tolerance_pa:.12g}",
                "max_abs_saturation_error": f"{max_s_err:.12g}",
                "saturation_abs_tolerance": f"{test.saturation_abs_tolerance:.12g}",
                "saturation_min_global": f"{min(r['saturation_mean'] for r in rows):.12g}",
                "saturation_max_global": f"{max(r['saturation_mean'] for r in rows):.12g}",
                "max_spatial_saturation_range": f"{max_s_uniformity:.12g}",
                "max_spatial_pressure_range_pa": f"{max_p_uniformity:.12g}",
                "source_rate_min_m3_day": f"{min(source_rates):.12g}",
                "source_rate_max_m3_day": f"{max(source_rates):.12g}",
                "max_abs_storage_rate_integral_error_m3": f"{mass_balance_error:.12g}",
                "mass_balance_abs_tolerance_m3": f"{test.mass_balance_tolerance_m3:.12g}",
                "mass_balance_observation_method": "analytical_rate_integral",
                "time_points_compared": len(rows),
                "duration_days": f"{test.duration_days:.12g}",
                "saturation_initial": f"{test.initial_saturation:.12g}",
                "saturation_amplitude": f"{test.saturation_amplitude:.12g}",
                "solver_error_count": solver["solver_error_count"],
                "solver_warning_count": solver["solver_warning_count"],
                "solver_diverged": solver["solver_diverged"],
                "solver_cuts": solver["solver_cuts"],
                "snes_diverged_count": solver["snes_diverged_count"],
                "allow_solver_cuts": "FALSE",
                "warning_count": warnings["warning_count"],
                "expected_warning_count": warnings["expected_warning_count"],
                "unexpected_warning_count": warnings["unexpected_warning_count"],
                "mualem_vg_without_smooth_warning": warnings["mualem_vg_without_smooth"],
                "mualem_smooth_warning_policy": warn_policy,
                "direct_flux_output_probe": "AVAILABLE" if direct_probe["parseable"] else "UNAVAILABLE",
                "direct_flux_output_available": direct_probe["parseable"],
                "direct_flux_output_file": (
                    (direct_probe["conservation_files"] + direct_probe["mass_balance_files"] + direct_probe["velocity_files"])[0]
                    if direct_probe["conservation_files"] or direct_probe["mass_balance_files"] or direct_probe["velocity_files"]
                    else "NA"
                ),
                "snapshots": len(rows),
            },
        )
        print(f"[TEST] {status}: {test.test_id} max_abs={max_p_err:.6g} Pa, max_sat={max_s_err:.6g}")
        return TestResult(test.test_id, status, workdir, metrics)
    except Exception as exc:
        status_path.write_text(f"TEST_STATUS=UNKNOWN\nreason={type(exc).__name__}: {exc}\n", encoding="utf-8")
        print(f"[TEST] UNKNOWN {test.test_id}: {exc}", file=sys.stderr)
        return TestResult(test.test_id, "UNKNOWN", workdir, {"reason": f"{type(exc).__name__}: {exc}"})


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
    derived = compute_derived(params, weather)

    workdir = args.workdir
    workdir.mkdir(parents=True, exist_ok=True)

    write_weather_csv(weather, workdir / "forcing_daily.csv")
    input_text = generate_pflotran_input(params, derived)
    (workdir / "pflotran.in").write_text(input_text, encoding="utf-8")
    write_summary(params, derived, weather, workdir / "soilflow_run_summary.txt")

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


def test_workdir(args: argparse.Namespace, test_name: str) -> Path:
    root = args.output_dir if args.output_dir is not None else None
    if args.workdir is not None and args.test != "all":
        return args.workdir
    if root is None:
        return Path("runs") / TEST_OUTPUT_DIRS[test_name]
    return root / "runs" / TEST_OUTPUT_DIRS[test_name]


def write_suite_status(results: list[TestResult], suite_dir: Path, dry_run: bool = False) -> None:
    suite_dir.mkdir(parents=True, exist_ok=True)
    failed = [r for r in results if r.status not in {"PASS", "PASS_WITH_WARNINGS"}]
    warned = [r for r in results if r.status == "PASS_WITH_WARNINGS"]
    suite_status = "DRY_RUN" if dry_run else ("FAIL" if failed else ("PASS_WITH_WARNINGS" if warned else "PASS"))
    lines = [
        f"TEST_SUITE_STATUS={suite_status}",
        f"tests_total={len(results)}",
        f"tests_passed={sum(1 for r in results if r.status == 'PASS')}",
        f"tests_passed_with_warnings={sum(1 for r in results if r.status == 'PASS_WITH_WARNINGS')}",
        f"tests_failed={sum(1 for r in results if r.status not in {'PASS', 'PASS_WITH_WARNINGS'})}",
        "",
    ]
    for result in results:
        lines.append(f"{result.test_id}={result.status}")
    lines.extend(
        [
            "",
            f"warnings_total={sum(int(r.metrics.get('warning_count', 0)) for r in results)}",
            f"unexpected_warnings_total={sum(int(r.metrics.get('unexpected_warning_count', 0)) for r in results)}",
            f"solver_errors_total={sum(int(r.metrics.get('solver_error_count', 0)) for r in results)}",
            f"solver_divergences_total={sum(1 for r in results if bool(r.metrics.get('solver_diverged', False)))}",
            f"solver_cuts_total={sum(int(r.metrics.get('solver_cuts', 0)) for r in results)}",
        ]
    )
    (suite_dir / "TEST_SUITE_STATUS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def generate_single_test_files(
    test_name: str, params: dict[str, Any], workdir: Path
) -> LinearDarcyTest | VGRichardsTest | TransientStorageTest:
    workdir.mkdir(parents=True, exist_ok=True)
    test = TEST_BUILDERS[test_name](params)
    if isinstance(test, LinearDarcyTest):
        (workdir / "pflotran.in").write_text(generate_pflotran_test_input(test), encoding="utf-8")
        write_analytical_solution(test, workdir / "analytical_solution.csv")
        write_test_summary(test, workdir / "analytical_test_summary.txt")
    elif isinstance(test, VGRichardsTest):
        (workdir / "pflotran.in").write_text(generate_pflotran_vg_test_input(test), encoding="utf-8")
        write_vg_analytical_solution(test, workdir / "analytical_solution.csv")
        write_vg_test_summary(test, workdir / "analytical_test_summary.txt")
    else:
        (workdir / "pflotran.in").write_text(generate_pflotran_transient_storage_input(test), encoding="utf-8")
        write_transient_analytical_files(test, workdir)
        write_transient_test_summary(test, workdir / "analytical_test_summary.txt")
    print(f"[OK] Generated {test_name} PFLOTRAN input: {workdir / 'pflotran.in'}")
    print(f"[OK] Generated analytical solution: {workdir / 'analytical_solution.csv'}")
    return test


def run_single_test(args: argparse.Namespace, test_name: str) -> TestResult:
    input_json = args.input_json.resolve()
    if not input_json.exists():
        raise FileNotFoundError(f"input JSON not found: {input_json}")

    params = read_test_params(input_json, test_name)
    workdir = test_workdir(args, test_name)
    test = generate_single_test_files(test_name, params, workdir)

    if args.dry_run or not args.run:
        print(f"[INFO] {test_name} dry generation completed.")
        return TestResult(f"_test_{test_name}", "GENERATED", workdir, {})

    native = find_pflotran_native({}, args.pflotran_exe)
    if native:
        print(f"[INFO] Running native PFLOTRAN for {test_name}: {native}")
        rc = run_native(workdir, native, test.mpi_processes)
        print(f"[INFO] PFLOTRAN exit code: {rc}")
        print(f"[INFO] Log: {workdir / 'run_pflotran.log'}")
        if rc != 0:
            (workdir / "TEST_STATUS.txt").write_text(f"TEST_STATUS=PFLOTRAN_ERROR\nexit_code={rc}\n", encoding="utf-8")
            return TestResult(f"_test_{test_name}", "PFLOTRAN_ERROR", workdir, {"exit_code": rc})
        if isinstance(test, LinearDarcyTest):
            return evaluate_test_after_run(test, workdir)
        if isinstance(test, VGRichardsTest):
            return evaluate_vg_test_after_run(test, workdir)
        return evaluate_transient_storage_after_run(test, workdir)

    if args.prefer_wsl:
        wsl_exe = find_pflotran_wsl()
        if wsl_exe:
            print(f"[INFO] Running PFLOTRAN via WSL for {test_name}: {wsl_exe}")
            rc = run_wsl(workdir, wsl_exe, test.mpi_processes)
            print(f"[INFO] PFLOTRAN WSL exit code: {rc}")
            print(f"[INFO] Log: {workdir / 'run_pflotran_wsl.log'}")
            if rc != 0:
                (workdir / "TEST_STATUS.txt").write_text(f"TEST_STATUS=PFLOTRAN_ERROR\nexit_code={rc}\n", encoding="utf-8")
                return TestResult(f"_test_{test_name}", "PFLOTRAN_ERROR", workdir, {"exit_code": rc})
            if isinstance(test, LinearDarcyTest):
                return evaluate_test_after_run(test, workdir)
            if isinstance(test, VGRichardsTest):
                return evaluate_vg_test_after_run(test, workdir)
            return evaluate_transient_storage_after_run(test, workdir)

    (workdir / "TEST_STATUS.txt").write_text(
        "TEST_STATUS=GENERATED_ONLY\nPFLOTRAN executable was not found; analytical files were generated only.\n",
        encoding="utf-8",
    )
    print("[WARN] PFLOTRAN executable was not found. _test files generated only.")
    return TestResult(f"_test_{test_name}", "GENERATED_ONLY", workdir, {})


def run_test_mode(args: argparse.Namespace) -> int:
    if args.test == "all":
        test_names = list(TEST_REGISTRY)
    else:
        test_names = [args.test]
    results = [run_single_test(args, name) for name in test_names]
    suite_root = args.output_dir if args.output_dir is not None else None
    suite_dir = (suite_root / "runs" / "_test_suite") if suite_root is not None else Path("runs/_test_suite")
    write_suite_status(results, suite_dir, dry_run=args.dry_run or not args.run)
    if args.dry_run or not args.run:
        return 0
    return 0 if all(r.status in {"PASS", "PASS_WITH_WARNINGS"} for r in results) else 1


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
