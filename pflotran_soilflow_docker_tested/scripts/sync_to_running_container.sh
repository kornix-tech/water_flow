#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTAINER_NAME="${SOILFLOW_CONTAINER_NAME:-pflotran_soilflow_docker_tested-soilflow-web-1}"
FRONTEND_NODE_IMAGE="${FRONTEND_NODE_IMAGE:-node:20}"

cd "$ROOT_DIR"

if ! docker ps --format "{{.Names}}" | grep -Fxq "$CONTAINER_NAME"; then
  echo "Контейнер $CONTAINER_NAME не запущен" >&2
  exit 1
fi

echo "[1/4] Build frontend dist"
docker run --rm \
  -v "$ROOT_DIR:/app" \
  -w /app/web/frontend \
  "$FRONTEND_NODE_IMAGE" \
  npm run build

echo "[2/4] Copy backend, scripts, input and frontend dist"
docker cp web/backend/app "$CONTAINER_NAME:/opt/soilflow/web/backend/"
docker cp scripts/soilflow_pflotran.py "$CONTAINER_NAME:/opt/soilflow/scripts/soilflow_pflotran.py"
docker cp scripts/soilflow_visualize.py "$CONTAINER_NAME:/opt/soilflow/scripts/soilflow_visualize.py"
docker cp input/soilflow_pflotran_demo.json "$CONTAINER_NAME:/opt/soilflow/input/soilflow_pflotran_demo.json"
docker cp web/frontend/dist "$CONTAINER_NAME:/opt/soilflow/web/frontend/"

echo "[3/4] Cleanup local generated frontend dist"
docker run --rm \
  -v "$ROOT_DIR:/app" \
  alpine:latest \
  sh -lc "rm -rf /app/web/frontend/dist /app/web/frontend/node_modules/.vite-temp"

echo "[4/4] Restart container"
docker restart "$CONTAINER_NAME" >/dev/null

echo "OK: $CONTAINER_NAME synced and restarted"
