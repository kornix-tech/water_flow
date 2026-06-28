#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WEB_PORT="${WEB_PORT:-18080}"
FRONTEND_NODE_IMAGE="${FRONTEND_NODE_IMAGE:-node:20}"

cd "$ROOT_DIR"

echo "[1/8] Python compile"
python3 -m compileall -q web/backend/app scripts tests

echo "[2/8] Backend unit tests"
python3 -m unittest discover -s web/backend/tests
python3 -m unittest discover -s tests

echo "[3/8] Modular scenario smoke"
./scripts/smoke_modular_scenarios.sh

echo "[4/8] Frontend production build"
docker run --rm \
  -v "$ROOT_DIR:/app" \
  -w /app/web/frontend \
  "$FRONTEND_NODE_IMAGE" \
  npm run build

echo "[5/8] Cleanup generated frontend build"
docker run --rm \
  -v "$ROOT_DIR:/app" \
  alpine:latest \
  sh -lc "rm -rf /app/web/frontend/dist /app/web/frontend/node_modules/.vite-temp"

echo "[6/8] Restart web service"
WEB_PORT="$WEB_PORT" docker compose restart soilflow-web

echo "[7/8] API contract and workflow checks"
for attempt in $(seq 1 30); do
  if curl -fsS "http://localhost:${WEB_PORT}/api/health" >/dev/null 2>&1; then
    break
  fi
  if [[ "$attempt" -eq 30 ]]; then
    echo "API health check failed after ${attempt} attempts" >&2
    exit 1
  fi
  sleep 1
done
curl -fsS "http://localhost:${WEB_PORT}/api/system/info" >/dev/null
WEB_PORT="$WEB_PORT" ./scripts/api_smoke.sh
WEB_PORT="$WEB_PORT" ./scripts/api_tabular_workflow_smoke.sh

echo "[8/8] Frontend route smoke"
WEB_PORT="$WEB_PORT" ./scripts/ui_route_smoke.sh

echo "OK: project checks passed on http://localhost:${WEB_PORT}"
