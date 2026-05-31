#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
IMAGE_NAME="${IMAGE_NAME:-soilflow-pflotran:local}"
LOCAL_INPUT_JSON="${1:-input/soilflow_pflotran_demo.json}"
CONTAINER_WORKDIR="${2:-/work/runs/demo_richards_dryrun}"
mkdir -p output
DOCKER_TTY_ARGS=()
if [[ -t 0 && -t 1 ]]; then
  # Dry-run не требует сети, но TTY включаем только для ручного терминала.
  DOCKER_TTY_ARGS=(-it)
fi
docker run --rm "${DOCKER_TTY_ARGS[@]}" --network none \
  -v "${ROOT_DIR}:/case:ro" \
  -v "${ROOT_DIR}/output:/work" \
  "${IMAGE_NAME}" \
  generate --mode demo --input-json "/case/${LOCAL_INPUT_JSON}" --workdir "${CONTAINER_WORKDIR}" --dry-run
echo "[OK] Generated files under ${ROOT_DIR}/output${CONTAINER_WORKDIR#/work}"
