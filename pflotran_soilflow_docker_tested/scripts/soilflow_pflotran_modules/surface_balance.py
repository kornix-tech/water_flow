from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from soilflow_pflotran_modules.input_contract import as_float
from soilflow_pflotran_modules.physical_models import normalize_model_token, validate_soil_model_pair


@dataclass
class Derived:
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


class SimpleSurfaceFluxModel:
    """Текущая минимальная модель: P + irrigation - Epot без root uptake."""

    def normalize_row(self, row: dict[str, Any]) -> dict[str, Any] | None:
        return normalize_weather_row(row)

    def mean_top_flux_m_s(self, params: dict[str, Any], weather: list[dict[str, Any]]) -> float:
        return compute_mean_top_flux_m_s(params, weather)


def normalize_weather_row(row: dict[str, Any]) -> dict[str, Any] | None:
    date_text = str(row.get("date") or "")
    if not date_text:
        return None
    precipitation_mm_day = as_float(row.get("precipitation_mm_day"), 0.0)
    irrigation_mm_day = as_float(row.get("irrigation_mm_day"), 0.0)
    potential_soil_evaporation_mm_day = as_float(row.get("epot_mm_day"), 0.0)
    potential_transpiration_mm_day = as_float(row.get("tpot_mm_day"), 0.0)
    groundwater_depth_m = as_float(row.get("groundwater_depth_m"), math.nan)

    # Текущая постановка передает в PFLOTRAN только поверхностный поток:
    # осадки + полив - потенциальное испарение почвы. Транспирация хранится
    # отдельно как контракт будущего sink/root uptake модуля.
    net_surface_input_mm_day = precipitation_mm_day + irrigation_mm_day - potential_soil_evaporation_mm_day
    return {
        "date": date_text,
        "precipitation_mm_day": precipitation_mm_day,
        "irrigation_mm_day": irrigation_mm_day,
        "epot_mm_day": potential_soil_evaporation_mm_day,
        "tpot_mm_day": potential_transpiration_mm_day,
        "groundwater_depth_m": groundwater_depth_m,
        "net_surface_input_mm_day": net_surface_input_mm_day,
    }


def compute_mean_top_flux_m_s(params: dict[str, Any], weather: list[dict[str, Any]]) -> float:
    top_flux_override = params.get("top_flux_override_m_s")
    if top_flux_override not in (None, ""):
        return as_float(top_flux_override)
    mean_net_mm_day = sum(row["net_surface_input_mm_day"] for row in weather) / len(weather)
    return mean_net_mm_day / 1000.0 / 86400.0


def compute_derived(params: dict[str, Any], weather: list[dict[str, Any]]) -> Derived:
    theta_s = as_float(params.get("theta_s"))
    theta_r = as_float(params.get("theta_r"))
    retention_model = normalize_model_token(params.get("retention_model"), "van_genuchten")
    conductivity_model = normalize_model_token(params.get("conductivity_model"), "mualem")
    vg_alpha_1_m = as_float(params.get("vg_alpha_1_m"))
    vg_n = as_float(params.get("vg_n"))
    bc_lambda = as_float(params.get("bc_lambda"), 2.0)
    ksat_m_s = as_float(params.get("ksat_m_s"))
    rho = as_float(params.get("rho_water_kg_m3"), 997.0)
    mu = as_float(params.get("mu_water_pa_s"), 0.00089)
    gravity = as_float(params.get("gravity_m_s2"), 9.80665)
    anisotropy_x = as_float(params.get("anisotropy_x"), 1.0)
    anisotropy_y = as_float(params.get("anisotropy_y"), 1.0)
    anisotropy_z = as_float(params.get("anisotropy_z"), 1.0)

    if not (0.0 < theta_r < theta_s < 0.9):
        raise ValueError("Ожидается 0 < theta_r < theta_s < 0.9")
    validate_soil_model_pair(retention_model, conductivity_model)
    if vg_n <= 1.0:
        raise ValueError("Для van Genuchten должно быть n > 1")
    if bc_lambda <= 0.0:
        raise ValueError("Для Brooks-Corey должно быть bc_lambda > 0")
    if ksat_m_s <= 0:
        raise ValueError("ksat_m_s должен быть > 0")

    residual_saturation = theta_r / theta_s
    vg_m = 1.0 - 1.0 / vg_n
    alpha_pa_inv = vg_alpha_1_m / (rho * gravity)
    intrinsic_perm = ksat_m_s * mu / (rho * gravity)

    return Derived(
        residual_saturation=residual_saturation,
        retention_model=retention_model,
        conductivity_model=conductivity_model,
        vg_m=vg_m,
        alpha_pa_inv=alpha_pa_inv,
        bc_lambda=bc_lambda,
        intrinsic_perm_x_m2=intrinsic_perm * anisotropy_x,
        intrinsic_perm_y_m2=intrinsic_perm * anisotropy_y,
        intrinsic_perm_z_m2=intrinsic_perm * anisotropy_z,
        mean_top_flux_m_s=compute_mean_top_flux_m_s(params, weather),
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
    with path.open("w", newline="", encoding="utf-8") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=fields)
        writer.writeheader()
        for row in weather:
            writer.writerow(row)
