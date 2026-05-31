#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
IMAGE_NAME="${IMAGE_NAME:-soilflow-pflotran:local}"
mkdir -p output
exec docker run --rm -it \
  -v "${ROOT_DIR}:/case:ro" \
  -v "${ROOT_DIR}/output:/work" \
  "${IMAGE_NAME}" bash
