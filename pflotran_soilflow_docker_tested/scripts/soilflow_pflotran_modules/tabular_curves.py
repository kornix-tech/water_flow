from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from soilflow_pflotran_modules.input_contract import as_float, pf_float


@dataclass(frozen=True)
class TabularCurveAssets:
    characteristic_curve_lines: list[str]
    written_files: list[Path]


@dataclass(frozen=True)
class TabularPermeabilityAssets:
    permeability_function_lines: list[str]
    written_files: list[Path]


def _curve_kind(table: dict[str, Any]) -> str:
    return str(table.get("curve_kind") or "").strip().lower()


def _curve_points(table: dict[str, Any]) -> list[dict[str, Any]]:
    points = table.get("points", [])
    return points if isinstance(points, list) else []


def _point_saturation(point: dict[str, Any], theta_s: float) -> float:
    if point.get("saturation") not in (None, ""):
        return as_float(point["saturation"])
    if point.get("water_content") not in (None, ""):
        return as_float(point["water_content"]) / theta_s
    raise ValueError("Табличная кривая должна содержать saturation или water_content для каждой точки")


def _point_capillary_pressure_pa(point: dict[str, Any], rho: float, gravity: float) -> float:
    if point.get("pressure_pa") not in (None, ""):
        return max(0.0, as_float(point["pressure_pa"]))
    if point.get("pressure_head_m") not in (None, ""):
        # В интерфейсе задается напор давления воды h. Для PFLOTRAN PCHIP нужна
        # капиллярная шкала Pc, поэтому отрицательный h переводится в Pc > 0.
        return max(0.0, -rho * gravity * as_float(point["pressure_head_m"]))
    raise ValueError("Табличная кривая водоудерживания должна содержать pressure_pa или pressure_head_m")


def _point_relative_permeability(point: dict[str, Any], ksat_m_s: float) -> float:
    if point.get("relative_permeability") not in (None, ""):
        return as_float(point["relative_permeability"])
    if point.get("hydraulic_conductivity_m_s") not in (None, ""):
        return as_float(point["hydraulic_conductivity_m_s"]) / ksat_m_s
    raise ValueError("Табличная кривая влагопроводности должна содержать relative_permeability или hydraulic_conductivity_m_s")


def _select_table(tables: list[dict[str, Any]], required_kind: str) -> dict[str, Any]:
    allowed_kinds = {required_kind, "retention_conductivity"}
    matches = [table for table in tables if _curve_kind(table) in allowed_kinds]
    if not matches:
        raise ValueError(f"Для табличной модели не найдена таблица типа {required_kind}")
    return matches[0]


def _ensure_strictly_increasing(values: list[float], label: str) -> None:
    for previous, current in zip(values, values[1:]):
        if current <= previous:
            raise ValueError(f"Значения {label} в табличной кривой должны строго возрастать")


def _ensure_monotonic(values: list[float], label: str) -> None:
    if len(values) < 2:
        return
    nondecreasing = all(current >= previous for previous, current in zip(values, values[1:]))
    nonincreasing = all(current <= previous for previous, current in zip(values, values[1:]))
    if not (nondecreasing or nonincreasing):
        raise ValueError(f"Значения {label} в табличной кривой должны быть монотонными")


def _table_file_name(prefix: str, table: dict[str, Any]) -> str:
    raw_name = str(table.get("curve_name") or prefix).strip().lower()
    safe_name = "".join(character if character.isalnum() or character in {"_", "-"} else "_" for character in raw_name)
    return f"{prefix}_{safe_name or prefix}.dat"


def _write_pairs(path: Path, rows: list[tuple[float, float]]) -> None:
    path.write_text(
        "\n".join(f"{pf_float(saturation)} {pf_float(value)}" for saturation, value in rows) + "\n",
        encoding="utf-8",
    )


def build_tabular_characteristic_curve_assets(
    *,
    tables: list[dict[str, Any]],
    workdir: Path,
    theta_s: float,
    ksat_m_s: float,
    rho: float,
    gravity: float,
    curve_name: str = "cc_soil",
) -> TabularCurveAssets:
    retention_table = _select_table(tables, "retention")
    conductivity_table = _select_table(tables, "conductivity")

    retention_rows = sorted(
        (
            _point_saturation(point, theta_s),
            _point_capillary_pressure_pa(point, rho, gravity),
        )
        for point in _curve_points(retention_table)
    )
    conductivity_rows = sorted(
        (
            _point_saturation(point, theta_s),
            max(0.0, min(1.0, _point_relative_permeability(point, ksat_m_s))),
        )
        for point in _curve_points(conductivity_table)
    )
    if len(retention_rows) < 2 or len(conductivity_rows) < 2:
        raise ValueError("Для табличной модели нужны минимум две точки водоудерживания и две точки влагопроводности")

    _ensure_strictly_increasing([row[0] for row in retention_rows], "saturation")
    _ensure_strictly_increasing([row[0] for row in conductivity_rows], "saturation")
    _ensure_monotonic([row[1] for row in retention_rows], "Pc")
    _ensure_monotonic([row[1] for row in conductivity_rows], "kr")

    retention_path = workdir / _table_file_name("retention", retention_table)
    conductivity_path = workdir / _table_file_name("conductivity", conductivity_table)
    _write_pairs(retention_path, retention_rows)
    _write_pairs(conductivity_path, conductivity_rows)

    lines = [
        f"CHARACTERISTIC_CURVES {curve_name}",
        "  SATURATION_FUNCTION PCHIP",
        f"    FILE {retention_path.name}",
        "    UNSATURATED_EXTENSION NONE",
        "  /",
        "  PERMEABILITY_FUNCTION PCHIP_LIQ",
        f"    FILE {conductivity_path.name}",
        "  /",
        "/",
    ]
    return TabularCurveAssets(characteristic_curve_lines=lines, written_files=[retention_path, conductivity_path])


def build_tabular_permeability_assets(
    *,
    tables: list[dict[str, Any]],
    workdir: Path,
    theta_s: float,
    ksat_m_s: float,
) -> TabularPermeabilityAssets:
    conductivity_table = _select_table(tables, "conductivity")
    conductivity_rows = sorted(
        (
            _point_saturation(point, theta_s),
            max(0.0, min(1.0, _point_relative_permeability(point, ksat_m_s))),
        )
        for point in _curve_points(conductivity_table)
    )
    if len(conductivity_rows) < 2:
        raise ValueError("Для табличной влагопроводности нужны минимум две точки")

    _ensure_strictly_increasing([row[0] for row in conductivity_rows], "saturation")
    _ensure_monotonic([row[1] for row in conductivity_rows], "kr")

    conductivity_path = workdir / _table_file_name("conductivity", conductivity_table)
    _write_pairs(conductivity_path, conductivity_rows)
    lines = [
        "  PERMEABILITY_FUNCTION PCHIP_LIQ",
        f"    FILE {conductivity_path.name}",
        "  /",
    ]
    return TabularPermeabilityAssets(permeability_function_lines=lines, written_files=[conductivity_path])
