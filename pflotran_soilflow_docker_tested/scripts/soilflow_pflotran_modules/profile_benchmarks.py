from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Protocol

from soilflow_pflotran_modules.extended_analytical import generate_normalized_profile_rows, green_ampt_cumulative_infiltration
from soilflow_pflotran_modules.physical_models import (
    saturation_from_effective_saturation,
    vg_effective_saturation_from_pressure_head,
)
from soilflow_pflotran_modules.result_diagnostics import (
    find_final_tec_file,
    load_tecpotran_records,
    records_to_z_pressure_saturation,
    write_unified_status,
)
from soilflow_pflotran_modules.test_artifacts import analytical_profile_overlay_diagnostics, write_rows_csv
from soilflow_pflotran_modules.test_registry import verification_level_for_test


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
    status_fields.update(analytical_profile_overlay_diagnostics(workdir))
    return status_fields


def evaluate_profile_test_after_run(test_name: str, workdir: Path, result_factory: ProfileTestResultFactory) -> Any:
    status_path = workdir / "TEST_STATUS.txt"
    status_fields = profile_status_fields_after_run(test_name, workdir)
    write_unified_status(status_path, status_fields)
    return result_factory(f"_test_{test_name}", "PASS_WITH_WARNINGS", workdir, status_fields)
