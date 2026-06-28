#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WEB_PORT="${WEB_PORT:-18080}"
FRONTEND_NODE_IMAGE="${FRONTEND_NODE_IMAGE:-node:20}"
CHECK_PROFILE="${CHECK_PROFILE:-full}"

cd "$ROOT_DIR"

wait_for_api() {
  for attempt in $(seq 1 30); do
    if curl -fsS "http://localhost:${WEB_PORT}/api/health" >/dev/null 2>&1; then
      return 0
    fi
    if [[ "$attempt" -eq 30 ]]; then
      echo "API health check failed after ${attempt} attempts" >&2
      return 1
    fi
    sleep 1
  done
}

if [[ "$CHECK_PROFILE" == "fast" ]]; then
  echo "[fast 1/6] Python compile"
  python3 -m compileall -q web/backend/app scripts tests

  echo "[fast 2/6] Unit tests"
  python3 -m unittest discover -s web/backend/tests
  python3 -m unittest discover -s tests

  echo "[fast 3/6] Modular scenario smoke"
  ./scripts/smoke_modular_scenarios.sh

  echo "[fast 4/6] Restart web service"
  WEB_PORT="$WEB_PORT" docker compose restart soilflow-web
  wait_for_api

  echo "[fast 5/6] API smoke"
  WEB_PORT="$WEB_PORT" ./scripts/api_smoke.sh

  echo "[fast 6/6] Frontend route smoke"
  WEB_PORT="$WEB_PORT" ./scripts/ui_route_smoke.sh

  echo "OK: fast project checks passed on http://localhost:${WEB_PORT}"
  exit 0
fi

if [[ "$CHECK_PROFILE" != "full" ]]; then
  echo "Unknown CHECK_PROFILE=${CHECK_PROFILE}; supported: fast, full" >&2
  exit 2
fi

echo "[1/10] Python compile"
python3 -m compileall -q web/backend/app scripts tests

echo "[2/10] Backend unit tests"
python3 -m unittest discover -s web/backend/tests
python3 -m unittest discover -s tests

echo "[3/10] Modular scenario smoke"
./scripts/smoke_modular_scenarios.sh

echo "[4/10] Frontend production build"
docker run --rm \
  -v "$ROOT_DIR:/app" \
  -w /app/web/frontend \
  "$FRONTEND_NODE_IMAGE" \
  npm run build

echo "[5/10] Cleanup generated frontend build"
docker run --rm \
  -v "$ROOT_DIR:/app" \
  alpine:latest \
  sh -lc "rm -rf /app/web/frontend/dist /app/web/frontend/node_modules/.vite-temp"

echo "[6/10] Restart web service"
WEB_PORT="$WEB_PORT" docker compose restart soilflow-web

echo "[7/10] API contract and workflow checks"
wait_for_api
curl -fsS "http://localhost:${WEB_PORT}/api/system/info" >/dev/null
WEB_PORT="$WEB_PORT" ./scripts/api_smoke.sh
WEB_PORT="$WEB_PORT" ./scripts/api_tabular_workflow_smoke.sh

echo "[8/10] Results performance smoke"
WEB_PORT="$WEB_PORT" ./scripts/api_results_performance_smoke.sh

echo "[9/10] Restart resilience smoke"
WEB_PORT="$WEB_PORT" ./scripts/api_restart_resilience_smoke.sh

echo "[10/10] Frontend route smoke"
WEB_PORT="$WEB_PORT" ./scripts/ui_route_smoke.sh

echo "OK: project checks passed on http://localhost:${WEB_PORT}"
