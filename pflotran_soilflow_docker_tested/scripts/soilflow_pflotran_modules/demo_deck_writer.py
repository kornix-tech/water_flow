from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from soilflow_pflotran_modules.input_contract import as_float, as_int, optional_float, pf_float
from soilflow_pflotran_modules.physical_models import normalize_grid_dimension, validate_soil_model_pair


DIMENSION_LABELS = {
    "1d_z": "1D вертикальная колонка Z",
    "2d_xz": "2D вертикальный разрез XZ",
    "2d_xy": "2D плановая сетка XY",
    "3d_xyz": "3D блок XYZ",
}


@dataclass(frozen=True)
class DemoGrid:
    dimension: str
    length_x_m: float
    length_y_m: float
    depth_z_m: float
    nx: int
    ny: int
    nz: int
    dx_m: float
    dy_m: float
    dz_m: float


class DemoDerivedValues(Protocol):
    residual_saturation: float
    retention_model: str
    conductivity_model: str
    vg_m: float
    alpha_pa_inv: float
    bc_lambda: float
    intrinsic_perm_x_m2: float
    intrinsic_perm_y_m2: float
    intrinsic_perm_z_m2: float
    mean_top_flux_m_s: float


def build_demo_grid(params: dict[str, Any]) -> DemoGrid:
    dimension = normalize_grid_dimension(params.get("dimension"), params.get("grid_plane"))
    length_x = as_float(params.get("length_x_m"), 1.0)
    length_y = as_float(params.get("length_y_m"), 1.0)
    depth_z = as_float(params.get("depth_z_m"), 2.0)
    nx = as_int(params.get("nx"), 1)
    ny = as_int(params.get("ny"), 1)
    nz = as_int(params.get("nz"), 80)

    if length_x <= 0 or length_y <= 0 or depth_z <= 0:
        raise ValueError("length_x_m, length_y_m, depth_z_m должны быть > 0")
    if nx < 1 or ny < 1 or nz < 1:
        raise ValueError("nx, ny, nz должны быть >= 1")

    if dimension == "1d_z":
        nx, ny = 1, 1
        if nz < 2:
            raise ValueError("Для 1D_Z ожидается nz >= 2")
    elif dimension == "2d_xz":
        ny = 1
        if nx < 2 or nz < 2:
            raise ValueError("Для 2D_XZ ожидается nx >= 2 и nz >= 2")
    elif dimension == "2d_xy":
        nz = 1
        if nx < 2 or ny < 2:
            raise ValueError("Для 2D_XY ожидается nx >= 2 и ny >= 2")
    elif dimension == "3d_xyz":
        if nx < 2 or ny < 2 or nz < 2:
            raise ValueError("Для 3D_XYZ ожидается nx >= 2, ny >= 2 и nz >= 2")

    return DemoGrid(
        dimension=dimension,
        length_x_m=length_x,
        length_y_m=length_y,
        depth_z_m=depth_z,
        nx=nx,
        ny=ny,
        nz=nz,
        dx_m=length_x / nx,
        dy_m=length_y / ny,
        dz_m=depth_z / nz,
    )


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


def characteristic_curves_lines(
    *,
    name: str,
    residual_saturation: float,
    retention_model: str,
    conductivity_model: str,
    alpha_pa_inv: float,
    vg_m: float,
    bc_lambda: float,
    permeability_function_lines: list[str] | None = None,
) -> list[str]:
    validate_soil_model_pair(retention_model, conductivity_model)
    lines = [f"CHARACTERISTIC_CURVES {name}"]
    if retention_model == "brooks_corey":
        lines += [
            "  SATURATION_FUNCTION BROOKS_COREY",
            f"    LIQUID_RESIDUAL_SATURATION {pf_float(residual_saturation)}",
            f"    LAMBDA {pf_float(bc_lambda)}",
            f"    ALPHA {pf_float(alpha_pa_inv)}",
            "  /",
        ]
    else:
        lines += [
            "  SATURATION_FUNCTION VAN_GENUCHTEN",
            f"    LIQUID_RESIDUAL_SATURATION {pf_float(residual_saturation)}",
            f"    M {pf_float(vg_m)}",
            f"    ALPHA {pf_float(alpha_pa_inv)}",
            "  /",
        ]

    if permeability_function_lines is not None:
        lines += [*permeability_function_lines, "/"]
        return lines

    if retention_model == "brooks_corey":
        permeability_function = "BURDINE_BC_LIQ" if conductivity_model == "burdine" else "MUALEM_BC_LIQ"
        parameter_lines = [f"    LAMBDA {pf_float(bc_lambda)}"]
    else:
        permeability_function = "BURDINE_VG_LIQ" if conductivity_model == "burdine" else "MUALEM_VG_LIQ"
        parameter_lines = [f"    M {pf_float(vg_m)}"]
    lines += [
        f"  PERMEABILITY_FUNCTION {permeability_function}",
        f"    LIQUID_RESIDUAL_SATURATION {pf_float(residual_saturation)}",
        *parameter_lines,
        "  /",
        "/",
    ]
    return lines


def generate_standard_pflotran_input(
    params: dict[str, Any],
    derived: DemoDerivedValues,
    characteristic_curve_lines: list[str] | None = None,
    permeability_function_lines: list[str] | None = None,
) -> str:
    grid = build_demo_grid(params)
    theta_s = as_float(params.get("theta_s"))
    tortuosity = as_float(params.get("tortuosity"), 0.5)
    final_time_days = as_float(params.get("final_time_days"), 7.0)
    max_dt_days = as_float(params.get("maximum_timestep_days"), 0.02)
    initial_pressure = as_float(params.get("initial_liquid_pressure_pa"), 101325.0)
    bottom_pressure = as_float(params.get("bottom_liquid_pressure_pa"), initial_pressure)
    bottom_bc_type = str(params.get("bottom_bc_type", "HYDROSTATIC")).strip().upper()
    lateral_boundaries = [
        ("west", "WEST", "xy_west_liquid_pressure_pa", optional_float(params.get("xy_west_liquid_pressure_pa"))),
        ("east", "EAST", "xy_east_liquid_pressure_pa", optional_float(params.get("xy_east_liquid_pressure_pa"))),
        ("south", "SOUTH", "xy_south_liquid_pressure_pa", optional_float(params.get("xy_south_liquid_pressure_pa"))),
        ("north", "NORTH", "xy_north_liquid_pressure_pa", optional_float(params.get("xy_north_liquid_pressure_pa"))),
    ]

    lines: list[str] = []
    lines += [
        "# Generated by soilflow_pflotran.py",
        "# Demonstration: structured-grid RICHARDS problem for soil-water flow.",
        f"# Grid mode: {DIMENSION_LABELS[grid.dimension]}.",
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
        f"  NXYZ {grid.nx} {grid.ny} {grid.nz}",
        "  DXYZ",
        f"    {pf_float(grid.dx_m)}",
        f"    {pf_float(grid.dy_m)}",
        f"    {pf_float(grid.dz_m)}",
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
        *(
            characteristic_curve_lines
            if characteristic_curve_lines is not None
            else characteristic_curves_lines(
                name="cc_soil",
                residual_saturation=derived.residual_saturation,
                retention_model=derived.retention_model,
                conductivity_model=derived.conductivity_model,
                alpha_pa_inv=derived.alpha_pa_inv,
                vg_m=derived.vg_m,
                bc_lambda=derived.bc_lambda,
                permeability_function_lines=permeability_function_lines,
            )
        ),
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
        f"    {pf_float(grid.length_x_m)} {pf_float(grid.length_y_m)} {pf_float(grid.depth_z_m)}",
        "  /",
        "END",
        "",
        "REGION top",
        "  COORDINATES",
        f"    0.d0 0.d0 {pf_float(grid.depth_z_m)}",
        f"    {pf_float(grid.length_x_m)} {pf_float(grid.length_y_m)} {pf_float(grid.depth_z_m)}",
        "  /",
        "  FACE TOP",
        "END",
        "",
        "REGION bottom",
        "  COORDINATES",
        "    0.d0 0.d0 0.d0",
        f"    {pf_float(grid.length_x_m)} {pf_float(grid.length_y_m)} 0.d0",
        "  /",
        "  FACE BOTTOM",
        "END",
        "",
    ]
    if grid.dimension in {"2d_xy", "3d_xyz"}:
        lines += [
            "REGION west",
            "  COORDINATES",
            "    0.d0 0.d0 0.d0",
            f"    0.d0 {pf_float(grid.length_y_m)} {pf_float(grid.depth_z_m)}",
            "  /",
            "  FACE WEST",
            "END",
            "",
            "REGION east",
            "  COORDINATES",
            f"    {pf_float(grid.length_x_m)} 0.d0 0.d0",
            f"    {pf_float(grid.length_x_m)} {pf_float(grid.length_y_m)} {pf_float(grid.depth_z_m)}",
            "  /",
            "  FACE EAST",
            "END",
            "",
            "REGION south",
            "  COORDINATES",
            "    0.d0 0.d0 0.d0",
            f"    {pf_float(grid.length_x_m)} 0.d0 {pf_float(grid.depth_z_m)}",
            "  /",
            "  FACE SOUTH",
            "END",
            "",
            "REGION north",
            "  COORDINATES",
            f"    0.d0 {pf_float(grid.length_y_m)} 0.d0",
            f"    {pf_float(grid.length_x_m)} {pf_float(grid.length_y_m)} {pf_float(grid.depth_z_m)}",
            "  /",
            "  FACE NORTH",
            "END",
            "",
        ]

    lines += [
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

    for region_name, _face_name, _param_key, pressure_pa in lateral_boundaries:
        if pressure_pa is None:
            continue
        lines += [
            f"FLOW_CONDITION {region_name}_pressure",
            "  TYPE",
            "    LIQUID_PRESSURE DIRICHLET",
            "  /",
            f"  LIQUID_PRESSURE {pf_float(pressure_pa)}",
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

    if grid.dimension in {"2d_xy", "3d_xyz"}:
        for region_name, _face_name, param_key, pressure_pa in lateral_boundaries:
            if pressure_pa is None:
                lines += [f"# {region_name.upper()} boundary: NO_FLOW. Set {param_key} to enable lateral Dirichlet pressure.", ""]
                continue
            lines += [
                f"BOUNDARY_CONDITION {region_name}_pressure_bc",
                f"  FLOW_CONDITION {region_name}_pressure",
                f"  REGION {region_name}",
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
