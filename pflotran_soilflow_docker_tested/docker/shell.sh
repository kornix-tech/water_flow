#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME="${IMAGE_NAME:-soilflow-pflotran}"
IMAGE_TAG="${IMAGE_TAG:-local}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT_DIR="${OUTPUT_DIR:-${ROOT_DIR}/output}"
mkdir -p "${OUTPUT_DIR}"

exec docker run --rm -it \
  -v "${OUTPUT_DIR}:/workspace/output" \
  "${IMAGE_NAME}:${IMAGE_TAG}" shell
