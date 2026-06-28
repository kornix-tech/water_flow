from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any, Protocol

from soilflow_pflotran_modules.extended_analytical import generate_normalized_profile_rows, green_ampt_cumulative_infiltration
from soilflow_pflotran_modules.physical_models import (
    saturation_from_effective_saturation,
    vg_effective_saturation_from_pressure_head,
)
from soilflow_pflotran_modules.profile_benchmark_evaluators import (
    evaluate_profile_strict_candidate,
    evaluate_reference_overlay_quality,
    profile_evaluator_metadata,
)
from soilflow_pflotran_modules.result_diagnostics import (
    find_final_tec_file,
    load_tecpotran_records,
    records_to_z_pressure_saturation,
    write_unified_status,
)
from soilflow_pflotran_modules.richards_mms_case import validate_richards_mms_adapter_artifacts
from soilflow_pflotran_modules.test_artifacts import analytical_profile_overlay_diagnostics, write_rows_csv
from soilflow_pflotran_modules.test_registry import verification_level_for_test

PROFILE_POROSITY = 0.43
PROFILE_RHO_WATER_KG_M3 = 997.0
PROFILE_GRAVITY_M_S2 = 9.80665
PROFILE_ATMOSPHERIC_PRESSURE_PA = 101325.0


class ProfileTestResultFactory(Protocol):
    def __call__(self, test_id: str, status: str, workdir: Path, metrics: dict[str, object]) -> Any:
        ...


def write_richards_profile_analytical_profiles(test_name: str, workdir: Path) -> None:
    length_m = 1.2
    nz = 96
    dz = length_m / nz
    porosity = 0.43
    residual_saturation = 0.10465116279069768
    alpha_1_m = 3.6
    n = 1.56
    m = 1.0 - 1.0 / n
    output_interval_days = 0.025
    if test_name not in {"green_ampt_infiltration", "philip_infiltration", "richards_mms"}:
        write_rows_csv(workdir / "analytical_profiles.csv", generate_normalized_profile_rows(test_name, length_m))
        return

    if test_name == "green_ampt_infiltration":
        final_time_days = 0.5
        initial_head_m = -1.4
        ksat_m_s = 1.0e-6
        suction_m = 0.25
        delta_theta = 0.25
    elif test_name == "philip_infiltration":
        final_time_days = 0.25
        initial_head_m = -1.0
        sorptivity = 0.012
        a_coeff = 2.0e-6
    else:
        final_time_days = 0.5
        initial_head_m = -1.0
        amplitude = 0.2
        tau_days = 1.0

    initial_se = vg_effective_saturation_from_pressure_head(initial_head_m, alpha_1_m, n, m)
    initial_saturation = saturation_from_effective_saturation(initial_se, residual_saturation)
    initial_theta = porosity * initial_saturation
    frame_count = int(round(final_time_days / output_interval_days)) + 2
    rows: list[dict[str, float]] = []
    for frame_index in range(frame_count):
        time_days = min(final_time_days, frame_index * output_interval_days)
        time_s = time_days * 86400.0
        if test_name == "green_ampt_infiltration":
            cumulative_m = green_ampt_cumulative_infiltration(time_s, ksat_m_s, suction_m, delta_theta)
            wetting_depth_m = min(length_m, cumulative_m / max(1.0e-12, porosity - initial_theta))
        elif test_name == "philip_infiltration":
            cumulative_m = sorptivity * math.sqrt(max(0.0, time_s)) + a_coeff * time_s
            wetting_depth_m = min(length_m, cumulative_m / max(1.0e-12, porosity - initial_theta))
        else:
            wetting_depth_m = 0.0

        for cell_id in range(1, nz + 1):
            z_center_m = (cell_id - 0.5) * dz
            depth_m = length_m - z_center_m
            if test_name == "richards_mms":
                pressure_head_m = initial_head_m + amplitude * math.sin(math.pi * z_center_m / length_m) * math.exp(
                    -time_days / tau_days
                )
                se = vg_effective_saturation_from_pressure_head(pressure_head_m, alpha_1_m, n, m)
                theta = porosity * saturation_from_effective_saturation(se, residual_saturation)
            else:
                # Инфильтрационные эталоны пока задают интегральное продвижение фронта.
                # Поэтому overlay строится как инженерный wetting-front профиль, а не
                # как строгая numerical-vs-analytical метрика.
                if depth_m <= wetting_depth_m:
                    theta = porosity
                    pressure_head_m = -0.02
                else:
                    theta = initial_theta
                    pressure_head_m = initial_head_m
            rows.append(
                {
                    "frame_index": frame_index,
                    "time_days": time_days,
                    "cell_id": cell_id,
                    "depth_m": depth_m,
                    "theta_m3_m3": theta,
                    "pressure_head_m": pressure_head_m,
                }
            )
    write_rows_csv(workdir / "analytical_profiles.csv", rows)


def _read_analytical_profile_rows(path: Path) -> list[dict[str, float]]:
    with path.open("r", newline="", encoding="utf-8") as file_obj:
        reader = csv.DictReader(file_obj)
        if reader.fieldnames is None:
            return []
        rows: list[dict[str, float]] = []
        for raw_row in reader:
            try:
                rows.append({key: float(value) for key, value in raw_row.items() if value not in (None, "")})
            except ValueError:
                continue
    if not rows:
        return []
    if "frame_index" in rows[0]:
        final_frame = max(row["frame_index"] for row in rows if "frame_index" in row)
        return [row for row in rows if row.get("frame_index") == final_frame]
    if "time_days" in rows[0] and len({row.get("time_days") for row in rows}) > 1:
        final_time = max(row["time_days"] for row in rows if "time_days" in row)
        return [row for row in rows if row.get("time_days") == final_time]
    return rows


def _interpolate_by_depth(rows: list[dict[str, float]], depth_m: float, value_key: str) -> float:
    points = sorted((row["depth_m"], row[value_key]) for row in rows if "depth_m" in row and value_key in row)
    if not points:
        raise ValueError(f"В аналитическом профиле нет колонки {value_key}")
    if depth_m <= points[0][0]:
        return points[0][1]
    if depth_m >= points[-1][0]:
        return points[-1][1]
    for left, right in zip(points, points[1:]):
        z0, y0 = left
        z1, y1 = right
        if z0 <= depth_m <= z1:
            if math.isclose(z0, z1):
                return 0.5 * (y0 + y1)
            ratio = (depth_m - z0) / (z1 - z0)
            return y0 + ratio * (y1 - y0)
    return points[-1][1]


def profile_overlay_comparison_rows(
    numerical_rows: list[dict[str, float]],
    analytical_rows: list[dict[str, float]],
) -> list[dict[str, float]]:
    if not numerical_rows or not analytical_rows:
        return []

    max_z_m = max(row["z_m"] for row in numerical_rows)
    comparison_rows: list[dict[str, float]] = []
    for row in numerical_rows:
        depth_m = max_z_m - row["z_m"]
        theta_numerical = PROFILE_POROSITY * row["saturation"]
        pressure_head_numerical = (
            row["pressure_pa"] - PROFILE_ATMOSPHERIC_PRESSURE_PA
        ) / (PROFILE_RHO_WATER_KG_M3 * PROFILE_GRAVITY_M_S2)
        theta_analytical = _interpolate_by_depth(analytical_rows, depth_m, "theta_m3_m3")
        pressure_head_analytical = _interpolate_by_depth(analytical_rows, depth_m, "pressure_head_m")
        comparison_rows.append(
            {
                "depth_m": depth_m,
                "z_m": row["z_m"],
                "theta_numerical_m3_m3": theta_numerical,
                "theta_analytical_m3_m3": theta_analytical,
                "theta_error_m3_m3": theta_numerical - theta_analytical,
                "pressure_head_numerical_m": pressure_head_numerical,
                "pressure_head_analytical_m": pressure_head_analytical,
                "pressure_head_error_m": pressure_head_numerical - pressure_head_analytical,
            }
        )
    return sorted(comparison_rows, key=lambda item: item["depth_m"])


def profile_overlay_error_metrics(
    numerical_rows: list[dict[str, float]],
    analytical_rows: list[dict[str, float]],
) -> dict[str, object]:
    comparison_rows = profile_overlay_comparison_rows(numerical_rows, analytical_rows)
    if not comparison_rows:
        return {"profile_overlay_comparison": "SKIP", "profile_overlay_points": 0}

    theta_errors = [row["theta_error_m3_m3"] for row in comparison_rows]
    pressure_head_errors = [row["pressure_head_error_m"] for row in comparison_rows]

    def rmse(values: list[float]) -> float:
        return math.sqrt(sum(value * value for value in values) / len(values))

    return {
        "profile_overlay_comparison": "REFERENCE_OVERLAY",
        "profile_overlay_points": len(comparison_rows),
        "theta_overlay_rmse_m3_m3": f"{rmse(theta_errors):.12g}",
        "theta_overlay_max_abs_m3_m3": f"{max(abs(value) for value in theta_errors):.12g}",
        "pressure_head_overlay_rmse_m": f"{rmse(pressure_head_errors):.12g}",
        "pressure_head_overlay_max_abs_m": f"{max(abs(value) for value in pressure_head_errors):.12g}",
        "profile_overlay_note": "Reference overlay metric only; profile_smoke не является строгой физической верификацией.",
    }


def write_profile_overlay_comparison(
    workdir: Path,
    numerical_rows: list[dict[str, float]],
    analytical_rows: list[dict[str, float]],
) -> dict[str, object]:
    comparison_rows = profile_overlay_comparison_rows(numerical_rows, analytical_rows)
    if not comparison_rows:
        return {"profile_overlay_comparison": "SKIP", "profile_overlay_points": 0}
    output_path = workdir / "profile_overlay_comparison.csv"
    write_rows_csv(output_path, comparison_rows)
    metrics = profile_overlay_error_metrics(numerical_rows, analytical_rows)
    return {**metrics, "profile_overlay_source": output_path.name}


def profile_status_fields_after_run(test_name: str, workdir: Path) -> dict[str, object]:
    tec_files = sorted(p for p in workdir.glob("pflotran-[0-9]*.tec") if p.is_file() and "-vel-" not in p.name)
    if not tec_files:
        raise FileNotFoundError("PFLOTRAN не записал TECPLOT snapshot-файлы")
    _, records = load_tecpotran_records(workdir)
    converted = records_to_z_pressure_saturation(records)
    pressure_values = [row["pressure_pa"] for row in converted]
    saturation_values = [row["saturation"] for row in converted]
    final_tec_file = find_final_tec_file(workdir)
    status_fields: dict[str, object] = {
        "TEST_STATUS": "PASS_WITH_WARNINGS",
        "test_id": f"_test_{test_name}",
        "verification_level": verification_level_for_test(test_name),
        "verification_note": (
            "Profile smoke: PFLOTRAN строит расчетный Richards-профиль, но строгая физическая постановка "
            "и аналитическая метрика для этого benchmark еще не подключены."
        ),
        "numerical_comparison": "PFLOTRAN_PROFILE_ONLY",
        "profile_status": "TECPLOT_READY",
        "tecplot_snapshot_count": len(tec_files),
        "final_tecplot_file": final_tec_file.name if final_tec_file else "NA",
        "profile_points": len(converted),
        "pressure_min_pa": f"{min(pressure_values):.12g}",
        "pressure_max_pa": f"{max(pressure_values):.12g}",
        "saturation_min": f"{min(saturation_values):.12g}",
        "saturation_max": f"{max(saturation_values):.12g}",
        "note": "PFLOTRAN расчетные профили построены; строгая аналитическая метрика для этого benchmark будет подключена отдельной задачей.",
    }
    status_fields.update(profile_evaluator_metadata(test_name))
    status_fields.update(analytical_profile_overlay_diagnostics(workdir))
    status_fields.update(
        write_profile_overlay_comparison(
            workdir,
            converted,
            _read_analytical_profile_rows(workdir / "analytical_profiles.csv"),
        )
    )
    status_fields.update(evaluate_reference_overlay_quality(status_fields))
    if test_name == "richards_mms":
        status_fields.update(validate_richards_mms_adapter_artifacts(workdir))
    status_fields.update(evaluate_profile_strict_candidate(test_name, status_fields))
    return status_fields


def evaluate_profile_test_after_run(test_name: str, workdir: Path, result_factory: ProfileTestResultFactory) -> Any:
    status_path = workdir / "TEST_STATUS.txt"
    status_fields = profile_status_fields_after_run(test_name, workdir)
    write_unified_status(status_path, status_fields)
    return result_factory(f"_test_{test_name}", "PASS_WITH_WARNINGS", workdir, status_fields)
