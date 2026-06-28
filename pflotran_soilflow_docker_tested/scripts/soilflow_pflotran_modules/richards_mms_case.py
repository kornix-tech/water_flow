from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path

from soilflow_pflotran_modules.input_contract import pf_float
from soilflow_pflotran_modules.physical_models import (
    saturation_from_effective_saturation,
    vg_effective_saturation_from_pressure_head,
)
from soilflow_pflotran_modules.profile_carrier import _test_output_block


@dataclass(frozen=True)
class RichardsMmsCase:
    length_x_m: float = 1.0
    length_y_m: float = 1.0
    length_z_m: float = 1.2
    nx: int = 1
    ny: int = 1
    nz: int = 96
    porosity: float = 0.43
    residual_saturation: float = 0.10465116279069768
    alpha_1_m: float = 3.6
    n: float = 1.56
    rho_water_kg_m3: float = 997.0
    gravity_m_s2: float = 9.80665
    mu_pa_s: float = 0.00089
    ksat_m_s: float = 5.0e-6
    atmospheric_pressure_pa: float = 101325.0
    initial_head_m: float = -1.0
    amplitude_m: float = 0.2
    tau_days: float = 1.0
    final_time_days: float = 0.5
    maximum_timestep_days: float = 0.0025
    output_interval_days: float = 0.025

    @property
    def m(self) -> float:
        return 1.0 - 1.0 / self.n

    @property
    def volume_m3(self) -> float:
        return self.length_x_m * self.length_y_m * self.length_z_m

    @property
    def intrinsic_perm_m2(self) -> float:
        return self.ksat_m_s * self.mu_pa_s / (self.rho_water_kg_m3 * self.gravity_m_s2)


def richards_mms_pressure_head_m(case: RichardsMmsCase, z_m: float, time_days: float) -> float:
    return case.initial_head_m + case.amplitude_m * math.sin(math.pi * z_m / case.length_z_m) * math.exp(
        -time_days / case.tau_days
    )


def richards_mms_theta_m3_m3(case: RichardsMmsCase, z_m: float, time_days: float) -> float:
    head_m = richards_mms_pressure_head_m(case, z_m, time_days)
    effective = vg_effective_saturation_from_pressure_head(head_m, case.alpha_1_m, case.n, case.m)
    return case.porosity * saturation_from_effective_saturation(effective, case.residual_saturation)


def richards_mms_time_grid(case: RichardsMmsCase) -> list[float]:
    steps = max(1, int(round(case.final_time_days / case.output_interval_days)))
    values = [min(case.final_time_days, i * case.output_interval_days) for i in range(steps + 1)]
    if values[-1] < case.final_time_days:
        values.append(case.final_time_days)
    return sorted(set(round(value, 12) for value in values))


def richards_mms_profile_rows(case: RichardsMmsCase, time_days: float) -> list[dict[str, float]]:
    dz = case.length_z_m / case.nz
    rows: list[dict[str, float]] = []
    for cell_id in range(1, case.nz + 1):
        z_center_m = (cell_id - 0.5) * dz
        depth_m = case.length_z_m - z_center_m
        head_m = richards_mms_pressure_head_m(case, z_center_m, time_days)
        rows.append(
            {
                "cell_id": float(cell_id),
                "z_m": z_center_m,
                "depth_m": depth_m,
                "time_days": time_days,
                "pressure_head_m": head_m,
                "pressure_pa": case.atmospheric_pressure_pa + case.rho_water_kg_m3 * case.gravity_m_s2 * head_m,
                "theta_m3_m3": richards_mms_theta_m3_m3(case, z_center_m, time_days),
            }
        )
    return rows


def richards_mms_mean_theta(case: RichardsMmsCase, time_days: float) -> float:
    rows = richards_mms_profile_rows(case, time_days)
    return sum(row["theta_m3_m3"] for row in rows) / len(rows)


def richards_mms_source_rate_m3_day(case: RichardsMmsCase, time_days: float) -> float:
    # PFLOTRAN SOURCE_SINK RATE LIST принимает объемный расход на всю область.
    # Для MMS-кандидата используем производную среднего хранения, пока spatial
    # source-term не вынесен в полноценный физический deck.
    dt = min(1.0e-4, max(1.0e-6, case.maximum_timestep_days * 0.1))
    left = max(0.0, time_days - dt)
    right = min(case.final_time_days, time_days + dt)
    if math.isclose(left, right):
        return 0.0
    derivative = (richards_mms_mean_theta(case, right) - richards_mms_mean_theta(case, left)) / (right - left)
    return case.volume_m3 * derivative


def richards_mms_source_rate_rows(case: RichardsMmsCase) -> list[dict[str, float]]:
    return [
        {
            "time_days": time_days,
            "mean_theta_m3_m3": richards_mms_mean_theta(case, time_days),
            "source_rate_m3_day": richards_mms_source_rate_m3_day(case, time_days),
        }
        for time_days in richards_mms_time_grid(case)
    ]


def write_richards_mms_case_artifacts(case: RichardsMmsCase, workdir: Path) -> None:
    with (workdir / "richards_mms_initial_profile.csv").open("w", newline="", encoding="utf-8") as file_obj:
        writer = csv.DictWriter(
            file_obj,
            fieldnames=["cell_id", "z_m", "depth_m", "time_days", "pressure_head_m", "pressure_pa", "theta_m3_m3"],
        )
        writer.writeheader()
        writer.writerows(richards_mms_profile_rows(case, 0.0))
    with (workdir / "richards_mms_source_rate.csv").open("w", newline="", encoding="utf-8") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=["time_days", "mean_theta_m3_m3", "source_rate_m3_day"])
        writer.writeheader()
        writer.writerows(richards_mms_source_rate_rows(case))


def generate_richards_mms_source_term_input(case: RichardsMmsCase = RichardsMmsCase()) -> str:
    dx = case.length_x_m / case.nx
    dy = case.length_y_m / case.ny
    dz = case.length_z_m / case.nz
    initial_pressure_pa = case.atmospheric_pressure_pa + case.rho_water_kg_m3 * case.gravity_m_s2 * case.initial_head_m
    snapshot_step = max(1, int(round(case.output_interval_days / case.maximum_timestep_days)))
    rate_lines = [
        f"        {pf_float(row['time_days'])} {pf_float(row['source_rate_m3_day'])}"
        for row in richards_mms_source_rate_rows(case)
    ]
    return "\n".join(
        [
            "# Generated by soilflow_pflotran.py --mode _test --test richards_mms",
            "# Richards MMS source-term candidate: uniform storage source from analytical mean theta.",
            "# Spatial MMS source-term and nonuniform initial condition are tracked in profile_case_manifest.json.",
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
            f"  NXYZ {case.nx} {case.ny} {case.nz}",
            "  DXYZ",
            f"    {pf_float(dx)}",
            f"    {pf_float(dy)}",
            f"    {pf_float(dz)}",
            "  /",
            "END",
            "",
            "MATERIAL_PROPERTY soil",
            "  ID 1",
            f"  POROSITY {pf_float(case.porosity)}",
            "  TORTUOSITY 1.d0",
            "  CHARACTERISTIC_CURVES cc_vg",
            "  PERMEABILITY",
            f"    PERM_X {pf_float(case.intrinsic_perm_m2)}",
            f"    PERM_Y {pf_float(case.intrinsic_perm_m2)}",
            f"    PERM_Z {pf_float(case.intrinsic_perm_m2)}",
            "  /",
            "/",
            "",
            "CHARACTERISTIC_CURVES cc_vg",
            "  SATURATION_FUNCTION VAN_GENUCHTEN",
            f"    LIQUID_RESIDUAL_SATURATION {pf_float(case.residual_saturation)}",
            f"    M {pf_float(case.m)}",
            f"    ALPHA {pf_float(case.alpha_1_m / (case.rho_water_kg_m3 * case.gravity_m_s2))}",
            "  /",
            "  PERMEABILITY_FUNCTION MUALEM_VG_LIQ",
            f"    LIQUID_RESIDUAL_SATURATION {pf_float(case.residual_saturation)}",
            f"    M {pf_float(case.m)}",
            "  /",
            "/",
            "",
            *_test_output_block(f"    PERIODIC TIMESTEP {snapshot_step}"),
            "",
            "TIME",
            f"  FINAL_TIME {pf_float(case.final_time_days)} d",
            f"  MAXIMUM_TIMESTEP_SIZE {pf_float(case.maximum_timestep_days)} d",
            "/",
            "",
            "REGION all",
            "  COORDINATES",
            "    0.d0 0.d0 0.d0",
            f"    {pf_float(case.length_x_m)} {pf_float(case.length_y_m)} {pf_float(case.length_z_m)}",
            "  /",
            "END",
            "",
            "FLOW_CONDITION initial",
            "  TYPE",
            "    LIQUID_PRESSURE DIRICHLET",
            "  /",
            f"  LIQUID_PRESSURE {pf_float(initial_pressure_pa)}",
            "END",
            "",
            "FLOW_CONDITION mms_uniform_storage_rate",
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
            "SOURCE_SINK mms_uniform_storage",
            "  FLOW_CONDITION mms_uniform_storage_rate",
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
