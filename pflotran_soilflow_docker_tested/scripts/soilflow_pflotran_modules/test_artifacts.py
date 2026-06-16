from __future__ import annotations

import csv
import math
from pathlib import Path


def write_xy_svg(
    path: Path,
    title: str,
    x_label: str,
    y_label: str,
    rows: list[dict[str, float]],
    y_num: str,
    y_ana: str,
) -> None:
    if not rows:
        return
    xs = [row["time_days"] for row in rows]
    ys = [row[y_num] for row in rows] + [row[y_ana] for row in rows]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    if math.isclose(x_min, x_max):
        x_max = x_min + 1.0
    if math.isclose(y_min, y_max):
        y_min -= 1.0
        y_max += 1.0
    width, height = 900, 520
    left, right, top, bottom = 90, 40, 42, 72
    plot_w = width - left - right
    plot_h = height - top - bottom

    def sx(x: float) -> float:
        return left + (x - x_min) / (x_max - x_min) * plot_w

    def sy(y: float) -> float:
        return top + (y_max - y) / (y_max - y_min) * plot_h

    num_points = " ".join(f"{sx(row['time_days']):.2f},{sy(row[y_num]):.2f}" for row in rows)
    ana_points = " ".join(f"{sx(row['time_days']):.2f},{sy(row[y_ana]):.2f}" for row in rows)
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="100%" height="100%" fill="#ffffff"/>
  <text x="{width/2:.0f}" y="26" text-anchor="middle" font-family="Arial" font-size="18" font-weight="700">{title}</text>
  <line x1="{left}" y1="{top}" x2="{left}" y2="{top+plot_h}" stroke="#222"/>
  <line x1="{left}" y1="{top+plot_h}" x2="{left+plot_w}" y2="{top+plot_h}" stroke="#222"/>
  <text x="{left+plot_w/2:.0f}" y="{height-22}" text-anchor="middle" font-family="Arial" font-size="13">{x_label}</text>
  <text x="22" y="{top+plot_h/2:.0f}" transform="rotate(-90 22 {top+plot_h/2:.0f})" text-anchor="middle" font-family="Arial" font-size="13">{y_label}</text>
  <polyline fill="none" stroke="#1f77b4" stroke-width="3" points="{ana_points}"/>
  <polyline fill="none" stroke="#d62728" stroke-width="2" stroke-dasharray="7,5" points="{num_points}"/>
  <text x="{left+plot_w-210}" y="{top+36}" font-family="Arial" font-size="12" fill="#1f77b4">аналитика</text>
  <text x="{left+plot_w-210}" y="{top+58}" font-family="Arial" font-size="12" fill="#d62728">PFLOTRAN</text>
</svg>'''
    path.write_text(svg, encoding="utf-8")


def write_curve_svg(
    path: Path,
    title: str,
    x_label: str,
    y_label: str,
    rows: list[dict[str, float]],
    x_key: str,
    y_key: str,
) -> None:
    if not rows:
        return
    xs = [float(row[x_key]) for row in rows]
    ys = [float(row[y_key]) for row in rows]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    if math.isclose(x_min, x_max):
        x_max = x_min + 1.0
    if math.isclose(y_min, y_max):
        y_min -= 1.0
        y_max += 1.0
    width, height = 900, 520
    left, right, top, bottom = 90, 40, 42, 72
    plot_w = width - left - right
    plot_h = height - top - bottom

    def sx(x: float) -> float:
        return left + (x - x_min) / (x_max - x_min) * plot_w

    def sy(y: float) -> float:
        return top + (y_max - y) / (y_max - y_min) * plot_h

    points = " ".join(f"{sx(float(row[x_key])):.2f},{sy(float(row[y_key])):.2f}" for row in rows)
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="100%" height="100%" fill="#ffffff"/>
  <text x="{width/2:.0f}" y="26" text-anchor="middle" font-family="Arial" font-size="18" font-weight="700">{title}</text>
  <line x1="{left}" y1="{top}" x2="{left}" y2="{top+plot_h}" stroke="#222"/>
  <line x1="{left}" y1="{top+plot_h}" x2="{left+plot_w}" y2="{top+plot_h}" stroke="#222"/>
  <text x="{left+plot_w/2:.0f}" y="{height-22}" text-anchor="middle" font-family="Arial" font-size="13">{x_label}</text>
  <text x="22" y="{top+plot_h/2:.0f}" transform="rotate(-90 22 {top+plot_h/2:.0f})" text-anchor="middle" font-family="Arial" font-size="13">{y_label}</text>
  <polyline fill="none" stroke="#1f77b4" stroke-width="3" points="{points}"/>
</svg>'''
    path.write_text(svg, encoding="utf-8")


def write_rows_csv(path: Path, rows: list[dict[str, float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def analytical_profile_overlay_diagnostics(workdir: Path) -> dict[str, str | int]:
    path = workdir / "analytical_profiles.csv"
    if not path.exists():
        return {"analytical_overlay_check": "FAIL", "analytical_profile_points": 0, "analytical_profile_source": "missing"}
    with path.open("r", newline="", encoding="utf-8") as file_obj:
        reader = csv.DictReader(file_obj)
        required = {"depth_m", "theta_m3_m3", "pressure_head_m"}
        if reader.fieldnames is None or not required.issubset(set(reader.fieldnames)):
            return {"analytical_overlay_check": "FAIL", "analytical_profile_points": 0, "analytical_profile_source": path.name}
        points = sum(1 for row in reader if any((row.get(key) or "").strip() for key in required))
    return {
        "analytical_overlay_check": "PASS" if points > 0 else "FAIL",
        "analytical_profile_points": points,
        "analytical_profile_source": path.name,
    }
