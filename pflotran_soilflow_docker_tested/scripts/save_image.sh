#!/usr/bin/env bash
set -euo pipefail
IMAGE_NAME="${IMAGE_NAME:-soilflow-pflotran:local}"
OUT="${1:-soilflow-pflotran-image.tar}"
docker save -o "$OUT" "$IMAGE_NAME"
echo "[OK] Saved Docker image to $OUT"
