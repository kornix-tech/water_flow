#!/usr/bin/env bash
set -euo pipefail

export SOILFLOW_HOME="${SOILFLOW_HOME:-/opt/soilflow}"
export SOILFLOW_WORKSPACE="${SOILFLOW_WORKSPACE:-/workspace}"
export PFLOTRAN_EXE="${PFLOTRAN_EXE:-/opt/pflotran/src/pflotran/pflotran}"

mkdir -p \
  "${SOILFLOW_WORKSPACE}/input" \
  "${SOILFLOW_WORKSPACE}/output/runs" \
  "${SOILFLOW_WORKSPACE}/uploads" \
  "${SOILFLOW_WORKSPACE}/jobs" \
  "${SOILFLOW_WORKSPACE}/archives" \
  "${SOILFLOW_WORKSPACE}/tmp"

if [ ! -f "${SOILFLOW_WORKSPACE}/input/soilflow_pflotran_demo.json" ]; then
  cp "${SOILFLOW_HOME}/input/soilflow_pflotran_demo.json" \
     "${SOILFLOW_WORKSPACE}/input/soilflow_pflotran_demo.json"
fi

exec uvicorn web.backend.app.main:app \
  --app-dir "${SOILFLOW_HOME}" \
  --host 0.0.0.0 \
  --port "${PORT:-8080}"
