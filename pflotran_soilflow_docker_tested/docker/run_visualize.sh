#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME="${IMAGE_NAME:-soilflow-pflotran:local}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT_DIR="${OUTPUT_DIR:-${ROOT_DIR}/output}"

mkdir -p "${OUTPUT_DIR}"

if [ "${1:-}" = "--self-test" ]; then
  docker run --rm \
    -v "${OUTPUT_DIR}:/work" \
    "${IMAGE_NAME}" \
    visualize \
    --self-test \
    --output-dir /work/visualization_selftest
  exit 0
fi

RUN_NAME="${1:-demo_richards}"
SPEED_MS="${SPEED_MS:-400}"
SNAPSHOT_EVERY="${SNAPSHOT_EVERY:-1}"

docker run --rm \
  -v "${OUTPUT_DIR}:/work" \
  "${IMAGE_NAME}" \
  visualize \
  --run-dir "/work/runs/${RUN_NAME}" \
  --output-dir "/work/runs/${RUN_NAME}/plots" \
  --speed-ms "${SPEED_MS}" \
  --snapshot-every "${SNAPSHOT_EVERY}"
