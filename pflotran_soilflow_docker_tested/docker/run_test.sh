#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME="${IMAGE_NAME:-soilflow-pflotran}"
IMAGE_TAG="${IMAGE_TAG:-local}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT_DIR="${OUTPUT_DIR:-${ROOT_DIR}/output}"
TEST_NAME="${1:-all}"
DRY_FLAG="${2:-}"
mkdir -p "${OUTPUT_DIR}"

MODE_ARGS=()
if [ "${DRY_FLAG}" = "--dry-run" ]; then
  MODE_ARGS+=(--dry-run)
fi

exec docker run --rm \
  -v "${OUTPUT_DIR}:/work" \
  "${IMAGE_NAME}:${IMAGE_TAG}" \
  _test --test "${TEST_NAME}" "${MODE_ARGS[@]}"
