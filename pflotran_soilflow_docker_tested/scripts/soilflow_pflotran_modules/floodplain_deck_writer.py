from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from soilflow_pflotran_modules.demo_deck_writer import characteristic_curves_lines, test_output_block
from soilflow_pflotran_modules.input_contract import as_float, as_int, pf_float


ATM_PRESSURE_PA = 101325.0


def head_to_pressure_at_elevation(head_z_m: float, point_z_m: float, rho: float, gravity: float) -> float:
    return ATM_PRESSURE_PA + rho * gravity * (head_z_m - point_z_m)


def controlled_drain_max_mass_rate(params: dict[str, Any], rho: float, gravity: float, river_head_z_m: float) -> float:
    open_fraction = max(0.0, min(1.0, as_float(params.get("drain_gate_open_fraction"), 1.0)))
    if open_fraction <= 0.0:
        return 0.0
    discharge_coefficient = as_float(params.get("drain_orifice_discharge_coefficient"), 0.62)
    pipe_diameter = as_float(params.get("drain_pipe_diameter_m"), 0.05)
    well_head_z = as_float(params.get("drain_control_head_z_m"), river_head_z_m)
    head_drop = max(0.0, well_head_z - river_head_z_m)
    area = math.pi * (pipe_diameter * 0.5) ** 2 * open_fraction
    flow_m3_s = discharge_coefficient * area * math.sqrt(2.0 * gravity * head_drop) if head_drop > 0.0 else 0.0
    return rho * flow_m3_s


def generate_floodplain_drainage_input(params: dict[str, Any]) -> str:
    length_x = as_float(params.get("length_x_m"), as_float(params.get("drain_spacing_m"), 15.0))
    length_y = as_float(params.get("length_y_m"), as_float(params.get("drain_length_m"), 200.0))
    depth_z = as_float(params.get("depth_z_m"), 2.6)
    nx = as_int(params.get("nx"), 60)
    ny = 1
    nz = as_int(params.get("nz"), 52)
    if nx < 2 or nz < 2:
        raise ValueError("Для floodplain_controlled_drainage ожидается nx >= 2 и nz >= 2")

    surface_z = depth_z
    peat_thickness = as_float(params.get("peat_thickness_m"), 0.6)
    sand_thickness = as_float(params.get("sand_thickness_m"), 2.0)
    peat_bottom_z = max(0.0, surface_z - peat_thickness)
    drain_depth = as_float(params.get("drain_axis_depth_m"), 1.0)
    drain_z = surface_z - drain_depth
    drain_x = as_float(params.get("drain_x_m"), 0.5 * length_x)
    river_head_z = surface_z - as_float(params.get("river_stage_below_surface_m"), 1.5)
    control_head_z = as_float(params.get("drain_control_head_z_m"), river_head_z)
    rho = as_float(params.get("rho_water_kg_m3"), 997.0)
    mu = as_float(params.get("mu_water_pa_s"), 0.001002)
    gravity = as_float(params.get("gravity_m_s2"), 9.80665)
    top_flux = as_float(params.get("top_flux_override_m_s"), -1.0e-8)
    final_time_days = as_float(params.get("final_time_days"), 5.0)
    max_dt_days = as_float(params.get("maximum_timestep_days"), 0.05)
    output_interval_days = as_float(params.get("output_interval_days"), max(0.1, final_time_days / 30.0))
    initial_head_z = as_float(params.get("initial_water_table_z_m"), river_head_z + 0.4)
    initial_pressure = head_to_pressure_at_elevation(initial_head_z, 0.0, rho, gravity)
    river_pressure = head_to_pressure_at_elevation(river_head_z, 0.0, rho, gravity)
    drain_threshold_pressure = head_to_pressure_at_elevation(control_head_z, drain_z, rho, gravity)
    threshold_span_pa = as_float(params.get("drain_threshold_span_pa"), rho * gravity * 0.05)
    max_mass_rate = controlled_drain_max_mass_rate(params, rho, gravity, river_head_z)

    peat_porosity = as_float(params.get("peat_theta_s"), 0.82)
    peat_theta_r = as_float(params.get("peat_theta_r"), 0.12)
    peat_ksat = as_float(params.get("peat_ksat_m_s"), 2.0e-6)
    peat_alpha = as_float(params.get("peat_vg_alpha_1_m"), 1.2)
    peat_n = as_float(params.get("peat_vg_n"), 1.35)
    sand_porosity = as_float(params.get("sand_theta_s"), 0.36)
    sand_theta_r = as_float(params.get("sand_theta_r"), 0.03)
    sand_ksat = as_float(params.get("sand_ksat_m_s"), 2.0e-5)
    sand_alpha = as_float(params.get("sand_vg_alpha_1_m"), 4.5)
    sand_n = as_float(params.get("sand_vg_n"), 2.2)
    peat_perm = peat_ksat * mu / (rho * gravity)
    sand_perm = sand_ksat * mu / (rho * gravity)
    peat_residual = peat_theta_r / peat_porosity
    sand_residual = sand_theta_r / sand_porosity
    peat_m = 1.0 - 1.0 / peat_n
    sand_m = 1.0 - 1.0 / sand_n
    peat_alpha_pa = peat_alpha / (rho * gravity)
    sand_alpha_pa = sand_alpha / (rho * gravity)
    tortuosity = as_float(params.get("tortuosity"), 0.5)
    dx = length_x / nx
    dy = length_y / ny
    dz = depth_z / nz

    if not (0.0 < peat_thickness < depth_z and 0.0 < sand_thickness <= depth_z):
        raise ValueError("Некорректные толщины слоев торфа/песка")
    if not (0.0 < drain_x < length_x and 0.0 < drain_z < depth_z):
        raise ValueError("Ось дрены должна попадать внутрь расчетной области")

    source_sink_lines: list[str] = []
    if max_mass_rate > 0.0:
        source_sink_lines = [
            "FLOW_CONDITION controlled_drain",
            "  TYPE",
            "    RATE PRESSURE_REGULATED_MASS_RATE VOLUME",
            "  /",
            f"  THRESHOLD_PRESSURE PREVENT_FLOW_BELOW {pf_float(drain_threshold_pressure)}",
            f"  THRESHOLD_PRESSURE_SPAN {pf_float(threshold_span_pa)}",
            f"  RATE {pf_float(-max_mass_rate)} kg/s",
            "END",
            "",
        ]

    lines = [
        "# Generated by soilflow_pflotran.py",
        "# Scenario: floodplain controlled drainage with two soil layers and regulated drain sink.",
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
        "MATERIAL_PROPERTY peat",
        "  ID 1",
        f"  POROSITY {pf_float(peat_porosity)}",
        f"  TORTUOSITY {pf_float(tortuosity)}",
        "  CHARACTERISTIC_CURVES cc_peat",
        "  PERMEABILITY",
        f"    PERM_X {pf_float(peat_perm)}",
        f"    PERM_Y {pf_float(peat_perm)}",
        f"    PERM_Z {pf_float(peat_perm)}",
        "  /",
        "/",
        "",
        "MATERIAL_PROPERTY sand",
        "  ID 2",
        f"  POROSITY {pf_float(sand_porosity)}",
        f"  TORTUOSITY {pf_float(tortuosity)}",
        "  CHARACTERISTIC_CURVES cc_sand",
        "  PERMEABILITY",
        f"    PERM_X {pf_float(sand_perm)}",
        f"    PERM_Y {pf_float(sand_perm)}",
        f"    PERM_Z {pf_float(sand_perm)}",
        "  /",
        "/",
        "",
        *characteristic_curves_lines(
            name="cc_peat",
            residual_saturation=peat_residual,
            retention_model="van_genuchten",
            conductivity_model="mualem",
            alpha_pa_inv=peat_alpha_pa,
            vg_m=peat_m,
            bc_lambda=2.0,
        ),
        "",
        *characteristic_curves_lines(
            name="cc_sand",
            residual_saturation=sand_residual,
            retention_model="van_genuchten",
            conductivity_model="mualem",
            alpha_pa_inv=sand_alpha_pa,
            vg_m=sand_m,
            bc_lambda=2.0,
        ),
        "",
        *test_output_block(f"    PERIODIC TIME {pf_float(output_interval_days)} d"),
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
        "REGION sand_layer",
        "  COORDINATES",
        "    0.d0 0.d0 0.d0",
        f"    {pf_float(length_x)} {pf_float(length_y)} {pf_float(peat_bottom_z)}",
        "  /",
        "END",
        "",
        "REGION peat_layer",
        "  COORDINATES",
        f"    0.d0 0.d0 {pf_float(peat_bottom_z)}",
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
        "REGION river",
        "  COORDINATES",
        f"    {pf_float(length_x)} 0.d0 0.d0",
        f"    {pf_float(length_x)} {pf_float(length_y)} {pf_float(depth_z)}",
        "  /",
        "  FACE EAST",
        "END",
        "",
        "REGION drain_cell",
        f"  COORDINATE {pf_float(drain_x)} {pf_float(0.5 * length_y)} {pf_float(drain_z)}",
        "END",
        "",
        "FLOW_CONDITION top_recharge",
        "  TYPE",
        "    LIQUID_FLUX NEUMANN",
        "  /",
        f"  LIQUID_FLUX {pf_float(top_flux)}",
        "END",
        "",
        "FLOW_CONDITION initial",
        "  TYPE",
        "    LIQUID_PRESSURE HYDROSTATIC",
        "  /",
        "  DATUM 0.d0 0.d0 0.d0",
        f"  LIQUID_PRESSURE {pf_float(initial_pressure)}",
        "END",
        "",
        "FLOW_CONDITION river_stage",
        "  TYPE",
        "    LIQUID_PRESSURE DIRICHLET",
        "  /",
        f"  LIQUID_PRESSURE {pf_float(river_pressure)}",
        "END",
        "",
        *source_sink_lines,
        "INITIAL_CONDITION",
        "  FLOW_CONDITION initial",
        "  REGION all",
        "END",
        "",
        "BOUNDARY_CONDITION recharge_bc",
        "  FLOW_CONDITION top_recharge",
        "  REGION top",
        "END",
        "",
        "BOUNDARY_CONDITION river_bc",
        "  FLOW_CONDITION river_stage",
        "  REGION river",
        "END",
        "",
        "# Bottom boundary: aquitard/no-flow.",
        "",
    ]
    if max_mass_rate > 0.0:
        lines += [
            "SOURCE_SINK controlled_drain_sink",
            "  FLOW_CONDITION controlled_drain",
            "  REGION drain_cell",
            "END",
            "",
        ]
    else:
        lines += ["# Controlled drain is fully closed: no SOURCE_SINK is assigned.", ""]
    lines += [
        "STRATA",
        "  REGION sand_layer",
        "  MATERIAL sand",
        "END",
        "",
        "STRATA",
        "  REGION peat_layer",
        "  MATERIAL peat",
        "END",
        "",
        "END_SUBSURFACE",
        "",
    ]
    return "\n".join(lines)


def write_floodplain_drainage_summary(params: dict[str, Any], weather: list[dict[str, Any]], path: Path) -> None:
    depth_z = as_float(params.get("depth_z_m"), 2.6)
    rho = as_float(params.get("rho_water_kg_m3"), 997.0)
    gravity = as_float(params.get("gravity_m_s2"), 9.80665)
    river_head_z = depth_z - as_float(params.get("river_stage_below_surface_m"), 1.5)
    control_head_z = as_float(params.get("drain_control_head_z_m"), river_head_z)
    drain_z = depth_z - as_float(params.get("drain_axis_depth_m"), 1.0)
    max_mass_rate = controlled_drain_max_mass_rate(params, rho, gravity, river_head_z)
    lines = [
        "Floodplain controlled drainage run summary",
        "==========================================",
        "",
        f"Project: {params.get('project_name')}",
        "Scenario: floodplain_controlled_drainage",
        "",
        "Schematic:",
        f"  domain_x_spacing_m        = {as_float(params.get('length_x_m'), as_float(params.get('drain_spacing_m'), 15.0)):.8g}",
        f"  drain_length_y_m          = {as_float(params.get('length_y_m'), as_float(params.get('drain_length_m'), 200.0)):.8g}",
        f"  depth_z_m                 = {depth_z:.8g}",
        f"  peat_thickness_m          = {as_float(params.get('peat_thickness_m'), 0.6):.8g}",
        f"  sand_thickness_m          = {as_float(params.get('sand_thickness_m'), 2.0):.8g}",
        f"  drain_axis_depth_m        = {as_float(params.get('drain_axis_depth_m'), 1.0):.8g}",
        f"  drain_axis_z_m            = {drain_z:.8g}",
        f"  river_head_z_m            = {river_head_z:.8g}",
        f"  drain_control_head_z_m    = {control_head_z:.8g}",
        f"  gate_open_fraction        = {as_float(params.get('drain_gate_open_fraction'), 1.0):.8g}",
        f"  max_orifice_mass_rate_kg_s= {max_mass_rate:.8g}",
        f"  max_orifice_flow_m3_s     = {max_mass_rate / rho:.8g}",
        f"  output_interval_days      = {as_float(params.get('output_interval_days'), max(0.1, as_float(params.get('final_time_days'), 5.0) / 30.0)):.8g}",
        "",
        "Boundary/forcing:",
        f"  top_flux_m_s              = {as_float(params.get('top_flux_override_m_s'), -1.0e-8):.8e}",
        f"  weather_days              = {len(weather)}",
        "",
        "Notes:",
        "  The drain is represented as a pressure-regulated internal sink at the pipe axis.",
        "  The outlet gate is represented by a maximum orifice capacity and a control head threshold.",
        "  Fully closed gate is represented by gate_open_fraction=0 and no SOURCE_SINK.",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
