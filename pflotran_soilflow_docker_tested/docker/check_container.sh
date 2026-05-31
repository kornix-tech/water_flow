#!/usr/bin/env bash
set -euo pipefail

: "${SOILFLOW_HOME:=/opt/soilflow}"
: "${PFLOTRAN_EXE:=/opt/pflotran/src/pflotran/pflotran}"

test -x "${PFLOTRAN_EXE}"
python3 - <<'PY'
import fastapi
import matplotlib
import numpy
import pandas
import plotly
import uvicorn
print("Python modules OK: numpy pandas matplotlib plotly fastapi uvicorn")
PY
if command -v mpirun >/dev/null 2>&1; then
  mpirun --version >/dev/null 2>&1 || true
fi
python3 "${SOILFLOW_HOME}/scripts/soilflow_pflotran.py" \
  --mode demo \
  --input-json "${SOILFLOW_HOME}/input/soilflow_pflotran_demo.json" \
  --workdir /tmp/soilflow_check_demo \
  --dry-run >/dev/null
python3 "${SOILFLOW_HOME}/scripts/soilflow_pflotran.py" \
  --mode _test \
  --input-json "${SOILFLOW_HOME}/input/soilflow_pflotran_demo.json" \
  --workdir /tmp/soilflow_check_test \
  --dry-run >/dev/null
printf 'SoilFlow container check OK\n'
