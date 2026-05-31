#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Постпроцессинг PFLOTRAN/Richards: профили влажности и давления по глубине.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


@dataclass
class ProfileFrame:
    time_value: float
    time_unit: str
    frame_index: int
    data: pd.DataFrame


@dataclass
class ProfileSeries:
    frames: list[ProfileFrame]
    profile_axis: str
    depth_column: str
    source_files: list[Path]


def parse_float(text: str) -> float:
    return float(text.replace("D", "E").replace("d", "e"))


def default_input_json_path() -> Path | None:
    candidates = [
        Path("input/soilflow_pflotran_demo.json"),
        Path("/opt/soilflow/input/soilflow_pflotran_demo.json"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def read_input_defaults(path: Path | None) -> dict[str, float]:
    defaults = {
        "porosity": 0.43,
        "rho_water_kg_m3": 997.0,
        "gravity_m_s2": 9.80665,
        "atmospheric_pressure_pa": 101325.0,
    }
    if path is None or not path.exists():
        return defaults
    data = json.loads(path.read_text(encoding="utf-8"))
    for tab in data.get("tabs", []):
        if tab.get("kind") != "fields":
            continue
        for field in tab.get("fields", []):
            key = str(field.get("key") or "").strip()
            if not key:
                continue
            try:
                value = float(str(field.get("value")).replace(",", "."))
            except ValueError:
                continue
            if key in {"theta_s", "porosity"}:
                defaults["porosity"] = value
            elif key in defaults:
                defaults[key] = value
    return defaults


def find_tecplot_files(run_dir: Path) -> list[Path]:
    """
    Найти snapshot TECPLOT-файлы PFLOTRAN, не смешивая их с velocity output.
    """
    files = sorted(run_dir.glob("pflotran-[0-9]*.tec"))
    return [p for p in files if p.is_file() and "-vel-" not in p.name]


def parse_tecplot_variables(header_text: str) -> list[str]:
    quoted = re.findall(r'"([^"]+)"', header_text)
    if quoted:
        return [q.strip() for q in quoted]
    _, _, rhs = header_text.partition("=")
    return [part.strip().strip('"') for part in rhs.split(",") if part.strip()]


def _parse_time_from_text(text: str, fallback: float) -> tuple[float, str]:
    title = re.search(r'TITLE\s*=\s*"([^"]+)"', text, flags=re.IGNORECASE)
    if title:
        match = re.search(r"([+-]?\d+(?:\.\d*)?(?:[EeDd][+-]?\d+)?)\s*\[([^\]]+)\]", title.group(1))
        if match:
            return parse_float(match.group(1)), match.group(2).strip()
    solution = re.search(r"SOLUTIONTIME\s*=\s*([+-]?\d+(?:\.\d*)?(?:[EeDd][+-]?\d+)?)", text, flags=re.IGNORECASE)
    if solution:
        return parse_float(solution.group(1)), "d"
    return fallback, "frame"


def _numeric_row(line: str) -> list[float] | None:
    stripped = line.strip()
    if not stripped:
        return None
    if stripped.upper().startswith(("TITLE", "VARIABLES", "ZONE", "TEXT", "GEOMETRY")):
        return None
    parts = stripped.replace(",", " ").split()
    try:
        return [parse_float(part) for part in parts]
    except ValueError:
        return None


def parse_tecplot_zones(path: Path, frame_start: int = 0) -> list[ProfileFrame]:
    text = path.read_text(encoding="utf-8", errors="replace")
    variables: list[str] = []
    zone_lines: list[str] = []
    zones: list[list[str]] = []
    zone_headers: list[str] = []
    current_header = ""
    for line in text.splitlines():
        if line.strip().upper().startswith("VARIABLES"):
            variables = parse_tecplot_variables(line)
            continue
        if line.strip().upper().startswith("ZONE"):
            if zone_lines:
                zones.append(zone_lines)
                zone_headers.append(current_header)
            current_header = line
            zone_lines = []
            continue
        zone_lines.append(line)
    if zone_lines:
        zones.append(zone_lines)
        zone_headers.append(current_header)
    if not zones:
        zones = [text.splitlines()]
        zone_headers = [""]
    frames: list[ProfileFrame] = []
    for local_index, lines in enumerate(zones):
        rows = [row for row in (_numeric_row(line) for line in lines) if row is not None]
        if not rows:
            continue
        names = variables or [f"col_{i}" for i in range(len(rows[0]))]
        records = []
        for row in rows:
            records.append({names[i] if i < len(names) else f"col_{i}": row[i] for i in range(len(row))})
        time_value, time_unit = _parse_time_from_text("\n".join([zone_headers[local_index], text[:300]]), frame_start + local_index)
        frames.append(
            ProfileFrame(
                time_value=time_value,
                time_unit=time_unit,
                frame_index=frame_start + local_index,
                data=pd.DataFrame.from_records(records),
            )
        )
    return frames


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    aliases = {
        "coord_x_m": ("x [m]", "x", "coordinate x", "col_0"),
        "coord_y_m": ("y [m]", "y", "coordinate y", "col_1"),
        "coord_z_m": ("z [m]", "z", "coordinate z", "col_2"),
        "liquid_pressure_pa": ("liquid pressure", "pressure [pa]"),
        "liquid_saturation": ("liquid saturation", "saturation"),
        "porosity": ("porosity",),
        "material_id": ("material id", "material_id"),
    }
    lower = {str(c).lower().replace("_", " "): c for c in df.columns}
    out = pd.DataFrame(index=df.index)
    for target, choices in aliases.items():
        found = None
        for choice in choices:
            for normalized, original in lower.items():
                if choice in normalized:
                    found = original
                    break
            if found is not None:
                break
        if found is not None:
            out[target] = pd.to_numeric(df[found], errors="coerce")
    missing_required = [c for c in ("coord_x_m", "coord_y_m", "coord_z_m", "liquid_pressure_pa", "liquid_saturation") if c not in out]
    if missing_required:
        raise ValueError(f"Не найдены обязательные колонки PFLOTRAN output: {', '.join(missing_required)}")
    return out


def choose_profile_axis(df: pd.DataFrame, requested: str) -> str:
    if requested != "auto":
        return requested
    ranges = {
        "x": float(df["coord_x_m"].max() - df["coord_x_m"].min()),
        "y": float(df["coord_y_m"].max() - df["coord_y_m"].min()),
        "z": float(df["coord_z_m"].max() - df["coord_z_m"].min()),
    }
    return max(ranges, key=ranges.get)


def enrich_profile_dataframe(
    df: pd.DataFrame,
    *,
    porosity_default: float,
    rho_water_kg_m3: float,
    gravity_m_s2: float,
    atmospheric_pressure_pa: float,
    profile_axis: str,
    depth_origin: str,
) -> pd.DataFrame:
    data = normalize_columns(df)
    if "porosity" not in data:
        data["porosity"] = porosity_default
    if "material_id" not in data:
        data["material_id"] = 1
    coord = data[f"coord_{profile_axis}_m"]
    if depth_origin == "top":
        data["depth_m"] = float(coord.max()) - coord
    else:
        data["depth_m"] = coord - float(coord.min())
    data["liquid_pressure_kpa"] = data["liquid_pressure_pa"] / 1000.0
    data["pressure_head_m"] = (data["liquid_pressure_pa"] - atmospheric_pressure_pa) / (
        rho_water_kg_m3 * gravity_m_s2
    )
    data["theta_m3_m3"] = data["porosity"] * data["liquid_saturation"]
    return data.sort_values("depth_m").reset_index(drop=True)


def reduce_to_depth_profile(
    df: pd.DataFrame,
    *,
    mode: str,
    depth_round_digits: int = 6,
    x_slice: Optional[float] = None,
    y_slice: Optional[float] = None,
) -> pd.DataFrame:
    if mode == "nearest_column":
        if x_slice is None or y_slice is None:
            raise NotImplementedError("nearest_column требует --x-slice и --y-slice")
        distance = (df["coord_x_m"] - x_slice).abs() + (df["coord_y_m"] - y_slice).abs()
        nearest = df.loc[distance == distance.min()].copy()
        return nearest.sort_values("depth_m").reset_index(drop=True)
    if mode == "raw_1d":
        return df.sort_values("depth_m").reset_index(drop=True)
    if mode != "mean_by_depth":
        raise ValueError(f"Неизвестный profile-mode: {mode}")
    data = df.copy()
    data["depth_key"] = data["depth_m"].round(depth_round_digits)
    agg = data.groupby("depth_key", as_index=False).agg(
        depth_m=("depth_m", "mean"),
        theta_m3_m3=("theta_m3_m3", "mean"),
        theta_min=("theta_m3_m3", "min"),
        theta_max=("theta_m3_m3", "max"),
        pressure_head_m=("pressure_head_m", "mean"),
        pressure_head_min=("pressure_head_m", "min"),
        pressure_head_max=("pressure_head_m", "max"),
        liquid_pressure_pa=("liquid_pressure_pa", "mean"),
        liquid_pressure_kpa=("liquid_pressure_kpa", "mean"),
        liquid_saturation=("liquid_saturation", "mean"),
        saturation_min=("liquid_saturation", "min"),
        saturation_max=("liquid_saturation", "max"),
        porosity=("porosity", "mean"),
        material_id=("material_id", "first"),
    )
    return agg.sort_values("depth_m").reset_index(drop=True)


def collect_profile_frames(
    run_dir: Path,
    *,
    profile_axis: str,
    depth_origin: str,
    profile_mode: str,
    input_defaults: dict[str, float],
    x_slice: Optional[float] = None,
    y_slice: Optional[float] = None,
) -> ProfileSeries:
    files = find_tecplot_files(run_dir)
    if not files:
        raise FileNotFoundError(f"В {run_dir} не найдены snapshot TECPLOT-файлы вида pflotran-NNN.tec")
    raw_frames: list[ProfileFrame] = []
    for path in files:
        raw_frames.extend(parse_tecplot_zones(path, len(raw_frames)))
    if not raw_frames:
        raise ValueError("TECPLOT-файлы найдены, но числовые кадры не прочитаны")
    axis = choose_profile_axis(normalize_columns(raw_frames[0].data), profile_axis)
    frames: list[ProfileFrame] = []
    for index, frame in enumerate(sorted(raw_frames, key=lambda f: (f.time_value, f.frame_index))):
        enriched = enrich_profile_dataframe(
            frame.data,
            porosity_default=input_defaults["porosity"],
            rho_water_kg_m3=input_defaults["rho_water_kg_m3"],
            gravity_m_s2=input_defaults["gravity_m_s2"],
            atmospheric_pressure_pa=input_defaults["atmospheric_pressure_pa"],
            profile_axis=axis,
            depth_origin=depth_origin,
        )
        reduced = reduce_to_depth_profile(enriched, mode=profile_mode, x_slice=x_slice, y_slice=y_slice)
        frames.append(ProfileFrame(frame.time_value, frame.time_unit, index, reduced))
    return ProfileSeries(frames=frames, profile_axis=axis, depth_column="depth_m", source_files=files)


def series_to_long_dataframe(profile_series: ProfileSeries) -> pd.DataFrame:
    rows = []
    for frame in profile_series.frames:
        data = frame.data.copy()
        data.insert(0, "time_unit", frame.time_unit)
        data.insert(0, "time_value", frame.time_value)
        data.insert(0, "frame_index", frame.frame_index)
        rows.append(data)
    return pd.concat(rows, ignore_index=True)


def write_profile_csvs(profile_series: ProfileSeries, output_dir: Path) -> tuple[Path, Path]:
    long_df = series_to_long_dataframe(profile_series)
    long_fields = [
        "frame_index",
        "time_value",
        "time_unit",
        "depth_m",
        "theta_m3_m3",
        "pressure_head_m",
        "liquid_pressure_pa",
        "liquid_pressure_kpa",
        "liquid_saturation",
        "porosity",
        "material_id",
    ]
    long_path = output_dir / "profile_frames_long.csv"
    long_df[[c for c in long_fields if c in long_df.columns]].to_csv(long_path, index=False)
    summary = long_df.groupby(["frame_index", "time_value", "time_unit"], as_index=False).agg(
        depth_min_m=("depth_m", "min"),
        depth_max_m=("depth_m", "max"),
        theta_min=("theta_m3_m3", "min"),
        theta_max=("theta_m3_m3", "max"),
        theta_mean=("theta_m3_m3", "mean"),
        pressure_head_min_m=("pressure_head_m", "min"),
        pressure_head_max_m=("pressure_head_m", "max"),
        pressure_head_mean_m=("pressure_head_m", "mean"),
        saturation_min=("liquid_saturation", "min"),
        saturation_max=("liquid_saturation", "max"),
        saturation_mean=("liquid_saturation", "mean"),
        pressure_min_pa=("liquid_pressure_pa", "min"),
        pressure_max_pa=("liquid_pressure_pa", "max"),
    )
    summary_path = output_dir / "profile_summary.csv"
    summary.to_csv(summary_path, index=False)
    return long_path, summary_path


def _frame_title(frame: ProfileFrame) -> str:
    return f"t = {frame.time_value:.6g} {frame.time_unit}, кадр {frame.frame_index}"


def write_interactive_profile_html(
    profile_series: ProfileSeries,
    output_html: Path,
    *,
    speed_ms: int,
    title: str,
) -> None:
    first = profile_series.frames[0]
    fig = make_subplots(rows=1, cols=2, subplot_titles=("Объёмная влажность θ", "Напор давления h"))
    line_style = {"width": 3}
    marker_style = {"size": 6}
    fig.add_trace(
        go.Scatter(
            x=first.data["theta_m3_m3"],
            y=first.data["depth_m"],
            mode="lines+markers",
            name="θ",
            line={**line_style, "color": "#2563eb"},
            marker={**marker_style, "color": "#2563eb"},
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=first.data["pressure_head_m"],
            y=first.data["depth_m"],
            mode="lines+markers",
            name="h",
            line={**line_style, "color": "#dc2626"},
            marker={**marker_style, "color": "#dc2626"},
        ),
        row=1,
        col=2,
    )
    frames = []
    for frame in profile_series.frames:
        frames.append(
            go.Frame(
                name=str(frame.frame_index),
                data=[
                    go.Scatter(
                        x=frame.data["theta_m3_m3"],
                        y=frame.data["depth_m"],
                        mode="lines+markers",
                        line={**line_style, "color": "#2563eb"},
                        marker={**marker_style, "color": "#2563eb"},
                    ),
                    go.Scatter(
                        x=frame.data["pressure_head_m"],
                        y=frame.data["depth_m"],
                        mode="lines+markers",
                        line={**line_style, "color": "#dc2626"},
                        marker={**marker_style, "color": "#dc2626"},
                    ),
                ],
                layout=go.Layout(title_text=f"{title}<br><sup>{_frame_title(frame)}</sup>"),
            )
        )
    max_depth = max(float(frame.data["depth_m"].max()) for frame in profile_series.frames)
    max_theta = max(float(frame.data["theta_m3_m3"].max()) for frame in profile_series.frames)
    theta_upper = max(0.05, max_theta * 1.05)
    sliders = [
        {
            "active": 0,
            "x": 0.0,
            "y": -0.10,
            "len": 0.88,
            "pad": {"t": 36, "b": 8},
            "currentvalue": {"prefix": "Кадр: ", "font": {"size": 13}},
            "steps": [
                {
                    "label": str(frame.frame_index),
                    "method": "animate",
                    "args": [
                        [str(frame.frame_index)],
                        {"mode": "immediate", "frame": {"duration": 0, "redraw": True}, "transition": {"duration": 0}},
                    ],
                }
                for frame in profile_series.frames
            ],
        }
    ]
    frame_names = [str(frame.frame_index) for frame in profile_series.frames]
    frame_names_json = json.dumps(frame_names, ensure_ascii=False)
    fig.frames = frames
    fig.update_layout(
        title={
            "text": f"{title}<br><sup>{_frame_title(first)}</sup>",
            "x": 0.0,
            "xanchor": "left",
            "y": 0.98,
            "yanchor": "top",
        },
        sliders=sliders,
        height=720,
        autosize=True,
        margin={"l": 70, "r": 28, "t": 104, "b": 150},
        font={"family": "DejaVu Sans, Arial, sans-serif", "size": 13, "color": "#1f2937"},
        legend={"orientation": "h", "x": 0.0, "y": -0.13, "xanchor": "left", "yanchor": "top"},
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
    )
    axis_style = {
        "showline": True,
        "linecolor": "#111827",
        "linewidth": 2,
        "mirror": False,
        "ticks": "outside",
        "tickcolor": "#111827",
        "tickwidth": 2,
        "gridcolor": "#e5e7eb",
        "gridwidth": 1,
        "zeroline": True,
        "zerolinecolor": "#111827",
        "zerolinewidth": 2,
        "title_standoff": 10,
    }
    fig.update_xaxes(title_text="Объёмная влажность θ, м³/м³", range=[0, theta_upper], **axis_style, row=1, col=1)
    fig.update_xaxes(title_text="Напор давления h, м", **axis_style, row=1, col=2)
    fig.update_yaxes(title_text="Глубина, м", autorange="reversed", range=[max_depth, 0], **axis_style, row=1, col=1)
    fig.update_yaxes(title_text="", autorange="reversed", range=[max_depth, 0], **axis_style, row=1, col=2)
    fig.update_annotations(font={"family": "DejaVu Sans, Arial, sans-serif", "size": 14, "color": "#1f2937"})
    controls_script = f"""
(function() {{
  const gd = document.getElementById('{{plot_id}}');
  const frameNames = {frame_names_json};
  const baseSpeedMs = {max(1, int(speed_ms))};
  const minSpeedLog = -1;
  const maxSpeedLog = 3;
  const speedStepLog = 0.1;
  let frameIndex = 0;
  let speedMs = baseSpeedMs;
  let timer = null;
  let playing = false;
  gd.dataset.soilflowSpeedMs = String(speedMs);
  gd.dataset.soilflowPlaying = String(playing);

  const style = document.createElement('style');
  style.textContent = `
    .soilflow-plot-controls {{
      display: flex;
      align-items: center;
      gap: 6px;
      flex-wrap: wrap;
      margin: 0 0 8px 0;
      font-family: DejaVu Sans, Arial, sans-serif;
    }}
    .soilflow-plot-controls button {{
      min-height: 28px;
      border: 1px solid #cbd4df;
      border-radius: 4px;
      background: #ffffff;
      color: #1f2937;
      cursor: pointer;
      padding: 0 9px;
      font: 12px DejaVu Sans, Arial, sans-serif;
    }}
    .soilflow-plot-controls button:hover {{
      border-color: #7b8794;
    }}
    .soilflow-speed-control {{
      display: grid;
      grid-template-columns: auto minmax(220px, 360px) minmax(52px, auto);
      align-items: center;
      gap: 8px;
      color: #1f2937;
      font: 12px DejaVu Sans, Arial, sans-serif;
    }}
    .soilflow-speed-control input[type="range"] {{
      width: 100%;
      accent-color: #1f6feb;
      cursor: pointer;
    }}
    .soilflow-speed-value {{
      min-width: 52px;
      font-weight: 700;
    }}
    .soilflow-speed-marks {{
      grid-column: 2 / 3;
      display: flex;
      justify-content: space-between;
      margin-top: -4px;
      color: #6b7280;
      font-size: 11px;
    }}
  `;
  document.head.appendChild(style);

  const controls = document.createElement('div');
  controls.className = 'soilflow-plot-controls';
  gd.parentNode.insertBefore(controls, gd);

  function currentSliderIndex() {{
    const active = gd.layout && gd.layout.sliders && gd.layout.sliders[0] ? gd.layout.sliders[0].active : 0;
    return Number.isFinite(active) ? Math.max(0, Math.min(frameNames.length - 1, active)) : frameIndex;
  }}

  function animateTo(index) {{
    frameIndex = ((index % frameNames.length) + frameNames.length) % frameNames.length;
    return Plotly.animate(gd, [frameNames[frameIndex]], {{
      mode: 'immediate',
      frame: {{ duration: 0, redraw: true }},
      transition: {{ duration: 0 }}
    }});
  }}

  function stop() {{
    playing = false;
    gd.dataset.soilflowPlaying = String(playing);
    if (timer !== null) {{
      window.clearTimeout(timer);
      timer = null;
    }}
    Plotly.animate(gd, [null], {{
      mode: 'immediate',
      frame: {{ duration: 0, redraw: false }},
      transition: {{ duration: 0 }}
    }});
  }}

  function scheduleNext() {{
    if (!playing) {{
      return;
    }}
    timer = window.setTimeout(async () => {{
      await animateTo(frameIndex + 1);
      scheduleNext();
    }}, speedMs);
  }}

  function formatSpeed(multiplier) {{
    if (multiplier < 1) {{
      return `${{multiplier.toFixed(1).replace(/\\.0$/, '')}}x`;
    }}
    if (multiplier < 10) {{
      return `${{multiplier.toFixed(1).replace(/\\.0$/, '')}}x`;
    }}
    return `${{Math.round(multiplier)}}x`;
  }}

  function speedMsFromLog(logValue) {{
    const multiplier = Math.pow(10, logValue);
    return Math.max(1, Math.round(baseSpeedMs / multiplier));
  }}

  async function play() {{
    stop();
    playing = true;
    gd.dataset.soilflowPlaying = String(playing);
    frameIndex = currentSliderIndex();
    await animateTo(frameIndex);
    scheduleNext();
  }}

  function setSpeedFromLog(logValue) {{
    speedMs = speedMsFromLog(logValue);
    gd.dataset.soilflowSpeedMs = String(speedMs);
    const multiplier = Math.pow(10, logValue);
    const label = controls.querySelector('.soilflow-speed-value');
    if (label) {{
      label.textContent = formatSpeed(multiplier);
    }}
    if (playing) {{
      if (timer !== null) {{
        window.clearTimeout(timer);
        timer = null;
      }}
      scheduleNext();
    }}
  }}

  function addButton(label, onClick) {{
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = label;
    button.addEventListener('click', onClick);
    controls.appendChild(button);
    return button;
  }}

  function addSpeedSlider() {{
    const wrapper = document.createElement('label');
    wrapper.className = 'soilflow-speed-control';

    const title = document.createElement('span');
    title.textContent = 'Скорость';

    const slider = document.createElement('input');
    slider.type = 'range';
    slider.min = String(minSpeedLog);
    slider.max = String(maxSpeedLog);
    slider.step = String(speedStepLog);
    slider.value = '0';
    slider.setAttribute('aria-label', 'Скорость прокрутки графиков');

    const value = document.createElement('span');
    value.className = 'soilflow-speed-value';
    value.textContent = '1x';

    const marks = document.createElement('div');
    marks.className = 'soilflow-speed-marks';
    ['0.1x', '1x', '10x', '100x', '1000x'].forEach((mark) => {{
      const item = document.createElement('span');
      item.textContent = mark;
      marks.appendChild(item);
    }});

    slider.addEventListener('input', () => setSpeedFromLog(Number(slider.value)));
    wrapper.append(title, slider, value, marks);
    controls.appendChild(wrapper);
  }}

  addButton('Пуск', play);
  addButton('Пауза', stop);
  addSpeedSlider();

  gd.on('plotly_sliderchange', (eventData) => {{
    const nextIndex = frameNames.indexOf(String(eventData && eventData.step ? eventData.step.label : ''));
    if (nextIndex >= 0) {{
      frameIndex = nextIndex;
    }}
  }});
}})();
"""
    fig.write_html(
        output_html,
        include_plotlyjs=True,
        config={"responsive": True, "displaylogo": False},
        post_script=controls_script,
    )


def write_static_profile_snapshots(
    profile_series: ProfileSeries,
    output_dir: Path,
    *,
    snapshot_every: int,
    formats: list[str],
) -> int:
    written = 0
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "axes.edgecolor": "#111827",
            "axes.linewidth": 1.6,
            "axes.labelcolor": "#1f2937",
            "xtick.color": "#1f2937",
            "ytick.color": "#1f2937",
        }
    )
    for frame in profile_series.frames[:: max(1, snapshot_every)]:
        fig, axes = plt.subplots(1, 2, figsize=(10, 6), sharey=True)
        axes[0].plot(frame.data["theta_m3_m3"], frame.data["depth_m"], marker="o", color="#2563eb", linewidth=2.0, markersize=4)
        axes[0].set_xlabel("Объёмная влажность θ, м³/м³")
        axes[0].set_ylabel("Глубина, м")
        axes[0].set_xlim(left=0)
        axes[0].grid(True, color="#e5e7eb", linewidth=0.8)
        axes[1].plot(frame.data["pressure_head_m"], frame.data["depth_m"], marker="o", color="#dc2626", linewidth=2.0, markersize=4)
        axes[1].set_xlabel("Напор давления h, м")
        axes[1].grid(True, color="#e5e7eb", linewidth=0.8)
        for axis in axes:
            axis.spines["top"].set_visible(False)
            axis.spines["right"].set_visible(False)
            axis.spines["left"].set_color("#111827")
            axis.spines["bottom"].set_color("#111827")
            axis.spines["left"].set_linewidth(1.6)
            axis.spines["bottom"].set_linewidth(1.6)
            axis.tick_params(width=1.4)
        axes[0].invert_yaxis()
        fig.suptitle(_frame_title(frame))
        fig.tight_layout()
        stem = output_dir / f"profile_theta_h_t{frame.frame_index:04d}"
        for fmt in formats:
            fig.savefig(stem.with_suffix(f".{fmt}"), dpi=150)
            written += 1
        plt.close(fig)
    return written


def write_visualization_status(
    path: Path,
    *,
    status: str,
    run_dir: Path,
    output_dir: Path,
    profile_series: ProfileSeries | None = None,
    profile_mode: str = "",
    snapshots_written: int = 0,
    speed_ms: int = 0,
    error: str | None = None,
) -> None:
    if status == "FAIL":
        path.write_text(f"VISUALIZATION_STATUS=FAIL\nerror={error}\n", encoding="utf-8")
        return
    assert profile_series is not None
    long_df = series_to_long_dataframe(profile_series)
    lines = [
        "VISUALIZATION_STATUS=PASS",
        f"run_dir={run_dir}",
        f"output_dir={output_dir}",
        f"frames_total={len(profile_series.frames)}",
        f"profile_axis={profile_series.profile_axis}",
        f"profile_mode={profile_mode}",
        f"depth_min_m={long_df['depth_m'].min():.12g}",
        f"depth_max_m={long_df['depth_m'].max():.12g}",
        f"theta_min={long_df['theta_m3_m3'].min():.12g}",
        f"theta_max={long_df['theta_m3_m3'].max():.12g}",
        f"pressure_head_min_m={long_df['pressure_head_m'].min():.12g}",
        f"pressure_head_max_m={long_df['pressure_head_m'].max():.12g}",
        f"saturation_min={long_df['liquid_saturation'].min():.12g}",
        f"saturation_max={long_df['liquid_saturation'].max():.12g}",
        "interactive_html=profiles_animation.html",
        "profile_frames_long_csv=profile_frames_long.csv",
        "profile_summary_csv=profile_summary.csv",
        f"snapshots_written={snapshots_written}",
        f"speed_ms={speed_ms}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def make_self_test_series() -> ProfileSeries:
    frames: list[ProfileFrame] = []
    porosity = 0.43
    rho = 997.0
    g = 9.80665
    p_atm = 101325.0
    depths = [2.0 * i / 40 for i in range(41)]
    for t in range(11):
        factor = t / 10.0
        rows = []
        for depth in depths:
            theta = 0.25 + 0.05 * math.sin(math.pi * depth / 2.0) * factor
            pressure_head = -1.0 - depth + 0.2 * factor
            saturation = theta / porosity
            pressure = p_atm + rho * g * pressure_head
            rows.append(
                {
                    "coord_x_m": 0.5,
                    "coord_y_m": 0.5,
                    "coord_z_m": 2.0 - depth,
                    "depth_m": depth,
                    "liquid_pressure_pa": pressure,
                    "liquid_pressure_kpa": pressure / 1000.0,
                    "pressure_head_m": pressure_head,
                    "liquid_saturation": saturation,
                    "porosity": porosity,
                    "theta_m3_m3": theta,
                    "material_id": 1,
                }
            )
        frames.append(ProfileFrame(float(t), "step", t, pd.DataFrame(rows)))
    return ProfileSeries(frames=frames, profile_axis="z", depth_column="depth_m", source_files=[])


def run_visualization(args: argparse.Namespace) -> int:
    output_dir = args.output_dir
    if output_dir is None:
        output_dir = args.run_dir / "plots"
    output_dir.mkdir(parents=True, exist_ok=True)
    status_path = output_dir / "VISUALIZATION_STATUS.txt"
    try:
        if args.self_test:
            profile_series = make_self_test_series()
            run_dir = Path("SELF_TEST")
            profile_mode = "raw_1d"
        else:
            input_json = args.input_json if args.input_json is not None else default_input_json_path()
            defaults = read_input_defaults(input_json)
            profile_series = collect_profile_frames(
                args.run_dir,
                profile_axis=args.profile_axis,
                depth_origin=args.depth_origin,
                profile_mode=args.profile_mode,
                input_defaults=defaults,
                x_slice=args.x_slice,
                y_slice=args.y_slice,
            )
            run_dir = args.run_dir
            profile_mode = args.profile_mode
        write_profile_csvs(profile_series, output_dir)
        snapshots_written = 0
        formats = [part.strip().lower() for part in args.snapshot_format.split(",") if part.strip()]
        if not args.html_only:
            snapshots_written = write_static_profile_snapshots(
                profile_series,
                output_dir,
                snapshot_every=args.snapshot_every,
                formats=formats,
            )
        if not args.static_only:
            write_interactive_profile_html(
                profile_series,
                output_dir / "profiles_animation.html",
                speed_ms=args.speed_ms,
                title="Эпюры влажности и давления SoilFlow/PFLOTRAN",
            )
        write_visualization_status(
            status_path,
            status="PASS",
            run_dir=run_dir,
            output_dir=output_dir,
            profile_series=profile_series,
            profile_mode=profile_mode,
            snapshots_written=snapshots_written,
            speed_ms=args.speed_ms,
        )
        print(f"[OK] Visualization written: {output_dir}")
        return 0
    except Exception as exc:
        write_visualization_status(
            status_path,
            status="FAIL",
            run_dir=args.run_dir if args.run_dir is not None else Path("SELF_TEST"),
            output_dir=output_dir,
            error=f"{type(exc).__name__}: {exc}",
        )
        print(f"[VISUALIZATION] FAIL: {exc}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build SoilFlow/PFLOTRAN profile visualizations.")
    parser.add_argument("--run-dir", type=Path, default=Path("output/runs/demo_richards"))
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--input-json", type=Path, default=None)
    parser.add_argument("--profile-axis", choices=["x", "y", "z", "auto"], default="auto")
    parser.add_argument("--depth-origin", choices=["top", "bottom"], default="top")
    parser.add_argument("--profile-mode", choices=["mean_by_depth", "nearest_column", "raw_1d"], default="mean_by_depth")
    parser.add_argument("--x-slice", type=float, default=None)
    parser.add_argument("--y-slice", type=float, default=None)
    parser.add_argument("--speed-ms", type=int, default=500)
    parser.add_argument("--snapshot-every", type=int, default=1)
    parser.add_argument("--snapshot-format", default="svg")
    parser.add_argument("--html-only", action="store_true")
    parser.add_argument("--static-only", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    return run_visualization(build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
