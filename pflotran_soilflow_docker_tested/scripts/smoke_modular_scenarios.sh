#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
WORKDIR="${WORKDIR:-/tmp/soilflow_modular_scenarios_smoke}"

cd "$ROOT_DIR"
rm -rf "$WORKDIR"
mkdir -p "$WORKDIR"

standard_input="$WORKDIR/standard_demo.json"
floodplain_input="$WORKDIR/floodplain_demo.json"

"$PYTHON_BIN" - "$standard_input" "$floodplain_input" <<'PY'
import json
import sys
from pathlib import Path

standard_path = Path(sys.argv[1])
floodplain_path = Path(sys.argv[2])
source = json.loads(Path("input/soilflow_pflotran_demo.json").read_text(encoding="utf-8"))


def update_fields(snapshot: dict, updates: dict[str, object]) -> dict:
    result = json.loads(json.dumps(snapshot))
    applied = set()
    first_fields_tab = None
    for tab in result.get("tabs", []):
        if tab.get("kind") != "fields":
            continue
        if first_fields_tab is None:
            first_fields_tab = tab
        for field in tab.get("fields", []):
            key = field.get("key")
            if key in updates:
                field["value"] = updates[key]
                applied.add(key)
    if first_fields_tab is not None:
        fields = first_fields_tab.setdefault("fields", [])
        for key, value in updates.items():
            if key not in applied:
                fields.append({"key": key, "value": value})
    return result


standard = update_fields(
    source,
    {
        "project_name": "smoke_standard_demo",
        "final_time_days": 0.01,
        "maximum_timestep_days": 0.005,
        "output_interval_days": 0.005,
    },
)
floodplain = update_fields(
    source,
    {
        "project_name": "smoke_floodplain_drainage",
        "scenario_type": "floodplain_controlled_drainage",
        "length_x_m": 15.0,
        "length_y_m": 200.0,
        "depth_z_m": 2.6,
        "nx": 12,
        "nz": 12,
        "final_time_days": 0.02,
        "maximum_timestep_days": 0.01,
        "output_interval_days": 0.01,
        "top_flux_override_m_s": -1.0e-8,
        "drain_gate_open_fraction": 0.5,
        "drain_control_head_z_m": 1.2,
    },
)
standard_path.write_text(json.dumps(standard, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
floodplain_path.write_text(json.dumps(floodplain, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

"$PYTHON_BIN" scripts/soilflow_pflotran.py \
  --input-json "$standard_input" \
  --mode demo \
  --workdir "$WORKDIR/standard_demo" \
  --dry-run
grep -q "MODE RICHARDS" "$WORKDIR/standard_demo/pflotran.in"
grep -q "SoilFlow/PFLOTRAN run summary" "$WORKDIR/standard_demo/soilflow_run_summary.txt"

"$PYTHON_BIN" scripts/soilflow_pflotran.py \
  --input-json input/soilflow_pflotran_demo.json \
  --mode test \
  --test brooks_corey_burdine \
  --workdir "$WORKDIR/brooks_corey_burdine" \
  --dry-run
grep -q "BROOKS_COREY" "$WORKDIR/brooks_corey_burdine/pflotran.in"
grep -q "BURDINE_BC_LIQ" "$WORKDIR/brooks_corey_burdine/pflotran.in"

"$PYTHON_BIN" scripts/soilflow_pflotran.py \
  --input-json "$floodplain_input" \
  --mode demo \
  --workdir "$WORKDIR/floodplain_demo" \
  --dry-run
grep -q "controlled_drain" "$WORKDIR/floodplain_demo/pflotran.in"
grep -q "Floodplain controlled drainage run summary" "$WORKDIR/floodplain_demo/soilflow_run_summary.txt"

echo "OK: modular scenario smoke passed in $WORKDIR"
