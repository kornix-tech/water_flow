#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
PFLOTRAN_EXE="${PFLOTRAN_EXE:-}"
WORKDIR="${WORKDIR:-/tmp/soilflow_tabular_permeability_smoke}"
INPUT_JSON="${WORKDIR}/tabular_permeability_input.json"
TABULAR_SMOKE_MODE="${TABULAR_SMOKE_MODE:-full}"

cd "$ROOT_DIR"
rm -rf "$WORKDIR"
mkdir -p "$WORKDIR"

"$PYTHON_BIN" - "$INPUT_JSON" "$TABULAR_SMOKE_MODE" <<'PY'
import json
import sys
from pathlib import Path

output_path = Path(sys.argv[1])
mode = sys.argv[2]
source = json.loads(Path("input/soilflow_pflotran_demo.json").read_text(encoding="utf-8"))
for tab in source["tabs"]:
    if tab.get("kind") != "fields":
        continue
    for field in tab.get("fields", []):
        key = field.get("key")
        if key == "retention_model":
            field["value"] = "tabular" if mode == "full" else "van_genuchten"
        elif key == "conductivity_model":
            field["value"] = "tabular"
        elif key == "final_time_days":
            field["value"] = 0.01
        elif key == "maximum_timestep_days":
            field["value"] = 0.005
        elif key == "output_interval_days":
            field["value"] = 0.005

tables = [
    {
        "curve_name": "lab_conductivity",
        "curve_kind": "conductivity",
        "points": [
            {"saturation": 0.2, "relative_permeability": 0.0},
            {"saturation": 0.6, "relative_permeability": 0.25},
            {"saturation": 1.0, "relative_permeability": 1.0},
        ],
    }
]
if mode == "full":
    tables.insert(
        0,
        {
            "curve_name": "lab_retention",
            "curve_kind": "retention",
            "points": [
                {"saturation": 0.2, "pressure_pa": 100000.0},
                {"saturation": 0.6, "pressure_pa": 20000.0},
                {"saturation": 1.0, "pressure_pa": 0.0},
            ],
        },
    )
source["soil_curve_tables"] = tables
output_path.write_text(json.dumps(source, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

if [[ -n "$PFLOTRAN_EXE" && -x "$PFLOTRAN_EXE" ]]; then
  "$PYTHON_BIN" scripts/soilflow_pflotran.py \
    --input-json "$INPUT_JSON" \
    --mode demo \
    --workdir "$WORKDIR" \
    --run \
    --pflotran-exe "$PFLOTRAN_EXE"
else
  "$PYTHON_BIN" scripts/soilflow_pflotran.py \
    --input-json "$INPUT_JSON" \
    --mode demo \
    --workdir "$WORKDIR" \
    --dry-run
fi

grep -q "PERMEABILITY_FUNCTION PCHIP_LIQ" "$WORKDIR/pflotran.in"
grep -q "FILE conductivity_lab_conductivity.dat" "$WORKDIR/pflotran.in"
test -s "$WORKDIR/conductivity_lab_conductivity.dat"
if [[ "$TABULAR_SMOKE_MODE" == "full" ]]; then
  grep -q "SATURATION_FUNCTION LOOKUP_TABLE" "$WORKDIR/pflotran.in"
  grep -q "FILE retention_lab_retention.dat" "$WORKDIR/pflotran.in"
  test -s "$WORKDIR/retention_lab_retention.dat"
  grep -q "soil_curve_tables   = 2" "$WORKDIR/soilflow_run_summary.txt"
else
  grep -q "soil_curve_tables   = 1" "$WORKDIR/soilflow_run_summary.txt"
fi

echo "OK: tabular permeability smoke passed in $WORKDIR"
