from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from soilflow_pflotran_modules.demo_deck_writer import characteristic_curves_lines, test_output_block
from soilflow_pflotran_modules.input_contract import as_float, as_int, pf_float
from soilflow_pflotran_modules.physical_models import (
    model_pair_label,
    normalize_model_token,
    saturation_from_effective_saturation,
    validate_soil_model_pair,
    vg_effective_saturation_from_pressure_head,
    vg_mualem_relative_permeability,
)

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
    retention_model: str
    conductivity_model: str
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
    bc_lambda: float
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


def brooks_corey_effective_saturation_from_pressure_head(h_m: float, alpha_1_m: float, bc_lambda: float) -> float:
    if h_m >= 0.0:
        return 1.0
    capillary_factor = alpha_1_m * abs(h_m)
    if capillary_factor <= 1.0:
        return 1.0
    return capillary_factor ** (-bc_lambda)


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


def brooks_corey_pressure_head_from_saturation(saturation: float, residual_saturation: float, alpha_1_m: float, bc_lambda: float) -> float:
    se = effective_saturation_from_saturation(saturation, residual_saturation)
    if se >= 1.0:
        return 0.0
    return -(se ** (-1.0 / bc_lambda)) / alpha_1_m


def burdine_vg_relative_permeability(se: float, m: float) -> float:
    se = max(0.0, min(1.0, se))
    if se <= 0.0:
        return 0.0
    if se >= 1.0:
        return 1.0
    return se**2 * (1.0 - (1.0 - se ** (1.0 / m)) ** m)


def brooks_corey_relative_permeability(se: float, bc_lambda: float, conductivity_model: str) -> float:
    se = max(0.0, min(1.0, se))
    if se <= 0.0:
        return 0.0
    if se >= 1.0:
        return 1.0
    if conductivity_model == "burdine":
        return se ** (3.0 + 2.0 / bc_lambda)
    return se ** (2.5 + 2.0 / bc_lambda)


def richards_effective_saturation_from_pressure_head(test: VGRichardsTest, h_m: float) -> float:
    if test.retention_model == "brooks_corey":
        return brooks_corey_effective_saturation_from_pressure_head(h_m, test.alpha_1_m, test.bc_lambda)
    return vg_effective_saturation_from_pressure_head(h_m, test.alpha_1_m, test.n, test.m)


def richards_pressure_head_from_saturation(test: VGRichardsTest | TransientStorageTest, saturation: float) -> float:
    if isinstance(test, VGRichardsTest) and test.retention_model == "brooks_corey":
        return brooks_corey_pressure_head_from_saturation(saturation, test.residual_saturation, test.alpha_1_m, test.bc_lambda)
    return vg_pressure_head_from_saturation(saturation, test.residual_saturation, test.alpha_1_m, test.n, test.m)


def richards_relative_permeability(test: VGRichardsTest, se: float) -> float:
    if test.retention_model == "brooks_corey":
        return brooks_corey_relative_permeability(se, test.bc_lambda, test.conductivity_model)
    if test.conductivity_model == "burdine":
        return burdine_vg_relative_permeability(se, test.m)
    return vg_mualem_relative_permeability(se, test.m)


def build_vg_test(params: dict[str, Any], test_kind: str) -> VGRichardsTest:
    theta_s = as_float(params.get("theta_s"), 0.43)
    theta_r = as_float(params.get("theta_r"), 0.045)
    residual = as_float(params.get("residual_saturation"), theta_r / theta_s)
    default_retention = "brooks_corey" if test_kind == "brooks_corey_burdine" else "van_genuchten"
    default_conductivity = "burdine" if test_kind == "brooks_corey_burdine" else "mualem"
    retention_model = normalize_model_token(params.get("retention_model"), default_retention)
    conductivity_model = normalize_model_token(params.get("conductivity_model"), default_conductivity)
    n = as_float(params.get("n"), 1.56)
    m = as_float(params.get("m"), 1.0 - 1.0 / n)
    bc_lambda = as_float(params.get("bc_lambda"), 2.0)
    rho = as_float(params.get("rho_water_kg_m3"), 997.0)
    mu = as_float(params.get("mu_water_pa_s"), 0.00089)
    g = as_float(params.get("gravity_m_s2"), 9.80665)
    ksat = as_float(params.get("ksat_m_s"), 5.0e-6)
    if not (0.0 <= residual < 1.0):
        raise ValueError("residual_saturation должен быть в интервале [0,1)")
    validate_soil_model_pair(retention_model, conductivity_model)
    if theta_s <= 0.0 or ksat <= 0.0 or n <= 1.0:
        raise ValueError("Для VG-тестов ожидаются theta_s>0, ksat_m_s>0 и n>1")
    if bc_lambda <= 0.0:
        raise ValueError("Для Brooks-Corey должно быть bc_lambda > 0")
    duration_key = "duration_days"
    return VGRichardsTest(
        test_id=f"_test_{test_kind}",
        retention_model=retention_model,
        conductivity_model=conductivity_model,
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
        bc_lambda=bc_lambda,
        ksat_m_s=ksat,
        rho_water_kg_m3=rho,
        mu_water_pa_s=mu,
        gravity_m_s2=g,
        atmospheric_pressure_pa=as_float(params.get("atmospheric_pressure_pa"), 101325.0),
        bottom_pressure_pa=as_float(params.get("bottom_pressure_pa"), 101325.0),
        constant_pressure_pa=as_float(params.get("constant_pressure_pa"), 90000.0),
        duration_days=as_float(params.get(duration_key), 1.0 if test_kind in {"hydrostatic_vg_no_flow", "brooks_corey_burdine"} else 3.0),
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


def build_brooks_corey_burdine_test(params: dict[str, Any]) -> VGRichardsTest:
    return build_vg_test(params, "brooks_corey_burdine")


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
    "brooks_corey_burdine": build_brooks_corey_burdine_test,
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
    if test.test_kind in {"hydrostatic_vg_no_flow", "brooks_corey_burdine"}:
        return test.bottom_pressure_pa - test.rho_water_kg_m3 * test.gravity_m_s2 * z_m
    return test.constant_pressure_pa


def vg_saturation(test: VGRichardsTest, pressure_pa: float) -> float:
    h_m = (pressure_pa - test.atmospheric_pressure_pa) / (test.rho_water_kg_m3 * test.gravity_m_s2)
    se = richards_effective_saturation_from_pressure_head(test, h_m)
    return saturation_from_effective_saturation(se, test.residual_saturation)


def vg_alpha_pa_inv(test: VGRichardsTest) -> float:
    return test.alpha_1_m / (test.rho_water_kg_m3 * test.gravity_m_s2)


def generate_pflotran_vg_test_input(test: VGRichardsTest) -> str:
    dx = test.length_x_m / test.nx
    dy = test.length_y_m / test.ny
    dz = test.column_height_m / test.nz
    is_hydrostatic = test.test_kind in {"hydrostatic_vg_no_flow", "brooks_corey_burdine"}
    initial_type = "HYDROSTATIC" if is_hydrostatic else "DIRICHLET"
    initial_pressure = test.bottom_pressure_pa if is_hydrostatic else test.constant_pressure_pa
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
        *characteristic_curves_lines(
            name="cc_vg",
            residual_saturation=test.residual_saturation,
            retention_model=test.retention_model,
            conductivity_model=test.conductivity_model,
            alpha_pa_inv=vg_alpha_pa_inv(test),
            vg_m=test.m,
            bc_lambda=test.bc_lambda,
        ),
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
    se_const = richards_effective_saturation_from_pressure_head(test, h_const)
    kr_const = richards_relative_permeability(test, se_const)
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
            se = richards_effective_saturation_from_pressure_head(test, h)
            sat = saturation_from_effective_saturation(se, test.residual_saturation)
            kr = richards_relative_permeability(test, se)
            q = 0.0 if test.test_kind in {"hydrostatic_vg_no_flow", "brooks_corey_burdine"} else -test.ksat_m_s * kr_const
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
    if test.test_kind in {"hydrostatic_vg_no_flow", "brooks_corey_burdine"}:
        title = "Hydrostatic retention/conductivity no-flow verification"
        formula = f"P(z)=P_bottom-rho*g*z; S={model_pair_label(test.retention_model, test.conductivity_model)}; qz=0"
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
        f"  soil_model_pair  = {model_pair_label(test.retention_model, test.conductivity_model)}",
        f"  column_height_m = {test.column_height_m:.8g}",
        f"  nx,ny,nz        = {test.nx},{test.ny},{test.nz}",
        f"  porosity         = {test.porosity:.8g}",
        f"  residual_sat     = {test.residual_saturation:.8g}",
        f"  alpha_1_m        = {test.alpha_1_m:.8g} 1/m",
        f"  n,m              = {test.n:.8g}, {test.m:.8g}",
        f"  bc_lambda        = {test.bc_lambda:.8g}",
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
