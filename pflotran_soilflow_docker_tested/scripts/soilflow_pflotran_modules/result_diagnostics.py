from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any, Iterable


UNEXPECTED_WARNING_FAIL_PATTERNS = ("failed", "invalid", "not recognized", "ignored card", "missing")


class ResultParserError(ValueError):
    """Ошибка разбора расчетных artifacts, отделенная от evaluator-логики."""


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
    with path.open("r", encoding="utf-8", errors="replace") as file_obj:
        for line in file_obj:
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
    candidates = [path for path in workdir.glob("pflotran-[0-9]*.tec") if path.is_file()]
    if not candidates:
        return None
    # Более полный и поздний snapshot надежнее отражает финальное состояние.
    return sorted(candidates, key=lambda path: (path.stat().st_size, path.stat().st_mtime))[-1]


def _find_column(variables: list[str], aliases: Iterable[str]) -> int | None:
    lower_vars = [variable.lower().replace("_", " ") for variable in variables]
    for alias in aliases:
        lowered_alias = alias.lower()
        for index, variable in enumerate(lower_vars):
            if lowered_alias in variable:
                return index
    return None


def load_numerical_pressure_profile(workdir: Path) -> tuple[Path, list[tuple[float, float]]]:
    tec = find_final_tec_file(workdir)
    if tec is None:
        raise ResultParserError("Не найден TECPLOT/DAT output PFLOTRAN (*.tec, *.dat, *.plt)")
    variables, rows = parse_tecpotran_tec(tec)
    if not rows:
        raise ResultParserError(f"Файл {tec.name} не содержит числовых строк")

    z_col = _find_column(variables, ["z [", "z", "z coordinate", "coordinate z"])
    p_col = _find_column(variables, ["liquid pressure", "pressure [pa]", "pressure"])
    if z_col is None:
        # Для 1D structured POINT output PFLOTRAN обычно пишет X,Y,Z первыми.
        z_col = 2 if len(rows[0]) > 2 else 0
    if p_col is None:
        # Консервативный fallback: первая колонка после координат с масштабом давления.
        for column_index in range(len(rows[0])):
            vals = [row[column_index] for row in rows if len(row) > column_index]
            if vals and max(abs(value) for value in vals) > 1000.0:
                p_col = column_index
                break
    if p_col is None:
        raise ResultParserError(f"Не удалось найти колонку давления в {tec.name}. Variables: {variables}")

    profile = []
    for row in rows:
        if len(row) <= max(z_col, p_col):
            continue
        profile.append((float(row[z_col]), float(row[p_col])))
    if not profile:
        raise ResultParserError(f"Не удалось извлечь профиль z/pressure из {tec.name}")

    by_z: dict[float, list[float]] = {}
    for z_m, pressure_pa in profile:
        key = round(z_m, 12)
        by_z.setdefault(key, []).append(pressure_pa)
    averaged = sorted((z_m, sum(vals) / len(vals)) for z_m, vals in by_z.items())
    return tec, averaged


def load_tecpotran_records(workdir: Path) -> tuple[Path, list[dict[str, float]]]:
    tec = find_final_tec_file(workdir)
    if tec is None:
        raise ResultParserError("Не найден TECPLOT/DAT output PFLOTRAN (*.tec, *.dat, *.plt)")
    variables, rows = parse_tecpotran_tec(tec)
    if not rows:
        raise ResultParserError(f"Файл {tec.name} не содержит числовых строк")
    records: list[dict[str, float]] = []
    for row in rows:
        record: dict[str, float] = {}
        for index, value in enumerate(row):
            key = variables[index] if index < len(variables) else f"col_{index}"
            record[key] = float(value)
        records.append(record)
    return tec, records


def record_value(record: dict[str, float], aliases: Iterable[str]) -> float:
    normalized = {key.lower().replace("_", " "): value for key, value in record.items()}
    for alias in aliases:
        lowered_alias = alias.lower()
        for key, value in normalized.items():
            if lowered_alias in key:
                return value
    raise ResultParserError(f"Не найдена колонка PFLOTRAN output: {list(aliases)}")


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
            "z_m": z_m,
            "pressure_pa": sum(vals["pressure_pa"]) / len(vals["pressure_pa"]),
            "saturation": sum(vals["saturation"]) / len(vals["saturation"]),
        }
        for z_m, vals in sorted(by_z.items())
    ]


def compute_saturation_bounds(records: list[dict[str, float]]) -> tuple[float, float]:
    values = [row["saturation"] for row in records if "saturation" in row]
    if not values:
        raise ResultParserError("В PFLOTRAN output не найдена колонка Liquid Saturation.")
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
    brooks_corey_smooth_phrase = "Brooks-Corey saturation function is being used without SMOOTH option"
    lines = _warning_lines(text)
    mualem_count = sum(1 for line in lines if mualem_smooth_phrase in line)
    brooks_corey_count = sum(1 for line in lines if brooks_corey_smooth_phrase in line)
    expected_count = mualem_count + brooks_corey_count
    fail_like = any(any(pattern in line.lower() for pattern in UNEXPECTED_WARNING_FAIL_PATTERNS) for line in lines)
    policy = "ignore_for_saturated_test" if test_kind == "linear_darcy" else "warn_for_unsaturated_test"
    unexpected = max(0, len(lines) - expected_count)
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
        "brooks_corey_without_smooth_warning": brooks_corey_count > 0,
        "warning_count": len(lines),
        "solver_warning_count": len(lines),
        "expected_warning_count": expected_count,
        "unexpected_warning_count": unexpected,
        "warning_check": check,
        "warning_policy": policy,
        "mualem_smooth_warning_policy": policy,
    }


def parse_pflotran_solver_diagnostics(log_path: Path) -> dict[str, bool | int | float | None]:
    text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    cuts = [int(match.group(1)) for match in re.finditer(r"cuts\s*=\s*(\d+)", text, flags=re.IGNORECASE)]
    error_count = len(re.findall(r"\bERROR\b", text, flags=re.IGNORECASE))
    diverged = bool(re.search(r"\b(?:DIVERGED|SNES_DIVERGED)\b", text, flags=re.IGNORECASE))
    newton = [int(match.group(1)) for match in re.finditer(r"newton\s*=\s*(\d+)", text, flags=re.IGNORECASE)]
    linear = [int(match.group(1)) for match in re.finditer(r"linear\s*=\s*(\d+)", text, flags=re.IGNORECASE)]
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


def write_unified_status(path: Path, fields: dict[str, Any]) -> None:
    ordered = []
    for key, value in fields.items():
        if isinstance(value, bool):
            value = str(value).lower()
        ordered.append(f"{key}={value}")
    path.write_text("\n".join(ordered) + "\n", encoding="utf-8")


def find_pflotran_conservation_files(output_dir: Path) -> list[Path]:
    return sorted(path for path in output_dir.glob("*conservation*") if path.is_file())


def find_pflotran_mass_balance_files(output_dir: Path) -> list[Path]:
    return sorted(path for path in output_dir.glob("*mass*balance*") if path.is_file())


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
    velocity_files = sorted(path for path in workdir.glob("*vel*.tec") if path.is_file())
    parsed = [parse_pflotran_conservation_or_mass_balance(path) for path in conservation_files + mass_balance_files]
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
        "conservation_files": [path.name for path in conservation_files],
        "mass_balance_files": [path.name for path in mass_balance_files],
        "velocity_files": [path.name for path in velocity_files],
        "parseable": parseable,
        "q_direct_m_s": q_direct_m_s,
        "parsed_files": parsed,
        "reason": (
            "parseable velocity/conservation output found" if parseable else "no recognized liquid flux columns"
        ),
    }


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
    files = sorted((path for path in workdir.glob("*.tec") if "-vel-" not in path.name), key=lambda path: (path.name, path.stat().st_mtime))
    output_times = transient_output_times_from_log(workdir / "run_pflotran.log")
    snapshots: list[dict[str, float]] = []
    for index, path in enumerate(files):
        variables, rows = parse_tecpotran_tec(path)
        if not rows:
            continue
        records = []
        for row in rows:
            records.append({variables[i] if i < len(variables) else f"col_{i}": float(value) for i, value in enumerate(row)})
        converted = records_to_z_pressure_saturation(records)
        pressures = [row["pressure_pa"] for row in converted]
        saturations = [row["saturation"] for row in converted]
        snapshots.append(
            {
                "index": float(index),
                "time_days": output_times[index] if index < len(output_times) else float(index),
                "pressure_mean_pa": sum(pressures) / len(pressures),
                "pressure_min_pa": min(pressures),
                "pressure_max_pa": max(pressures),
                "saturation_mean": sum(saturations) / len(saturations),
                "saturation_min": min(saturations),
                "saturation_max": max(saturations),
            }
        )
    return snapshots
