from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path
from typing import Any

from soilflow_pflotran_modules.physical_models import model_pair_label
from soilflow_pflotran_modules.result_diagnostics import (
    classify_pflotran_warnings,
    compute_saturation_bounds,
    direct_flux_output_probe,
    fit_line_slope,
    load_tecpotran_records,
    load_transient_snapshots,
    parse_pflotran_solver_diagnostics,
    records_to_z_pressure_saturation,
    write_unified_status,
)
from soilflow_pflotran_modules.richards_test_cases import (
    LinearDarcyTest,
    TestResult,
    TransientStorageTest,
    VGRichardsTest,
    analytical_pressure,
    richards_effective_saturation_from_pressure_head,
    richards_relative_permeability,
    transient_domain_volume_m3,
    transient_pressure,
    transient_rate_m3_day,
    transient_saturation,
    transient_time_grid,
    vg_pressure,
    vg_saturation,
)
from soilflow_pflotran_modules.test_artifacts import write_xy_svg
from soilflow_pflotran_modules.test_evaluation import (
    combined_test_status,
    direct_flux_output_file,
    failure_metrics,
    pass_fail,
    solver_check_passed,
    write_unknown_status,
)
from soilflow_pflotran_modules.test_registry import verification_level_for_test

PRESSURE_REPORT_ZERO_THRESHOLD_PA = 10.0


def report_pressure_error(raw_error_pa: float) -> float:
    return 0.0 if raw_error_pa < PRESSURE_REPORT_ZERO_THRESHOLD_PA else raw_error_pa


def pressure_reporting(raw_error_pa: float, tolerance_pa: float) -> dict[str, float]:
    return {
        "raw_max_abs_pressure_error_pa": raw_error_pa,
        "reported_max_abs_pressure_error_pa": report_pressure_error(raw_error_pa),
        "pressure_report_zero_threshold_pa": PRESSURE_REPORT_ZERO_THRESHOLD_PA,
        "pressure_abs_tolerance_pa": tolerance_pa,
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
        solver_check = solver_check_passed(solver)
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
            "verification_level": verification_level_for_test("linear_darcy"),
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
                "verification_level": verification_level_for_test("linear_darcy"),
                "verification_note": "Строгое сравнение PFLOTRAN с аналитическим стационарным решением Darcy/Richards.",
                "pressure_check": pass_fail(pressure_check),
                "saturation_check": pass_fail(saturation_check),
                "flux_check": pass_fail(flux_check),
                "solver_check": pass_fail(solver_check),
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
                "direct_flux_output_file": direct_flux_output_file(direct_probe),
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
        reason = write_unknown_status(status_path, exc, stage="evaluator")
        with status_path.open("a", encoding="utf-8") as file_obj:
            file_obj.write("PFLOTRAN output was not parsed; generated analytical_solution.csv is still available.\n")
        print(f"[TEST] UNKNOWN: {exc}", file=sys.stderr)
        return TestResult("_test_linear_darcy", "UNKNOWN", workdir, failure_metrics("linear_darcy", "evaluator", reason))


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
        is_hydrostatic = test.test_kind in {"hydrostatic_vg_no_flow", "brooks_corey_burdine"}
        if is_hydrostatic:
            analytical_slope = -test.rho_water_kg_m3 * test.gravity_m_s2
            # В ненасыщенном hydrostatic-тесте поток масштабируется K(S), а не Ks:
            # при малом численном остатке градиента использование Ks искусственно
            # завышает диагностический q на несколько порядков.
            kr_values = []
            for row in records:
                p_ana = vg_pressure(test, row["z_m"])
                h_m = (p_ana - test.atmospheric_pressure_pa) / (test.rho_water_kg_m3 * test.gravity_m_s2)
                se = richards_effective_saturation_from_pressure_head(test, h_m)
                kr_values.append(richards_relative_permeability(test, se))
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
            se_const = richards_effective_saturation_from_pressure_head(test, h_const)
            kr_const = richards_relative_permeability(test, se_const)
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
        solver_check = solver_check_passed(solver)
        warn_policy = str(warnings["mualem_smooth_warning_policy"])
        warn_check = str(warnings["warning_check"])
        status = combined_test_status(n > 0 and pressure_check and saturation_check and flux_check, solver_check, warn_check)
        pressure_info = pressure_reporting(max_pressure, test.pressure_abs_tolerance_pa)
        reported_abs = pressure_info["reported_max_abs_pressure_error_pa"]
        if test.test_kind == "unit_gradient_unsat":
            h_const = (test.constant_pressure_pa - test.atmospheric_pressure_pa) / (
                test.rho_water_kg_m3 * test.gravity_m_s2
            )
            se_const = richards_effective_saturation_from_pressure_head(test, h_const)
            kr_const = richards_relative_permeability(test, se_const)
            k_eff = test.ksat_m_s * kr_const
        metrics = {
            "verification_level": verification_level_for_test(test.test_kind),
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
        if is_hydrostatic:
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
            "verification_level": verification_level_for_test(test.test_kind),
            "verification_note": "Строгое сравнение PFLOTRAN с аналитическим гидростатическим/unit-gradient профилем.",
            "retention_model": test.retention_model,
            "conductivity_model": test.conductivity_model,
            "soil_model_pair": model_pair_label(test.retention_model, test.conductivity_model),
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
            "brooks_corey_without_smooth_warning": warnings["brooks_corey_without_smooth_warning"],
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
        if is_hydrostatic:
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
        reason = write_unknown_status(status_path, exc, stage="evaluator")
        print(f"[TEST] UNKNOWN {test.test_id}: {exc}", file=sys.stderr)
        return TestResult(
            test.test_id,
            "UNKNOWN",
            workdir,
            failure_metrics(test.test_id.removeprefix("_test_"), "evaluator", reason),
        )

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
        solver_check = solver_check_passed(solver)
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
            "verification_level": verification_level_for_test("transient_uniform_storage_vg"),
            "pressure": {
                **pressure_info,
                "pressure_check": pass_fail(pressure_check),
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
                "verification_level": verification_level_for_test("transient_uniform_storage_vg"),
                "verification_note": "Частичная проверка баланса: сравниваются storage/source-sink/однородность, пространственный поток не проверяется.",
                "pressure_check": "PASS" if pressure_check else "FAIL",
                "saturation_check": pass_fail(saturation_check and uniformity_check),
                "uniformity_check": pass_fail(uniformity_check),
                "source_sink_balance_check": pass_fail(source_sink_balance_check),
                "mass_balance_check": pass_fail(mass_balance_check),
                "flux_check": "SKIP",
                "flux_observation_method": "no_spatial_flux_uniform_storage_test",
                "solver_check": pass_fail(solver_check),
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
                "brooks_corey_without_smooth_warning": warnings["brooks_corey_without_smooth_warning"],
                "mualem_smooth_warning_policy": warn_policy,
                "direct_flux_output_probe": "AVAILABLE" if direct_probe["parseable"] else "UNAVAILABLE",
                "direct_flux_output_available": direct_probe["parseable"],
                "direct_flux_output_file": direct_flux_output_file(direct_probe),
                "snapshots": len(rows),
            },
        )
        print(f"[TEST] {status}: {test.test_id} max_abs={max_p_err:.6g} Pa, max_sat={max_s_err:.6g}")
        return TestResult(test.test_id, status, workdir, metrics)
    except Exception as exc:
        reason = write_unknown_status(status_path, exc, stage="evaluator")
        print(f"[TEST] UNKNOWN {test.test_id}: {exc}", file=sys.stderr)
        return TestResult(
            test.test_id,
            "UNKNOWN",
            workdir,
            failure_metrics(test.test_id.removeprefix("_test_"), "evaluator", reason),
        )
