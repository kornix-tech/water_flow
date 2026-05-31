#!/usr/bin/env bash
set -euo pipefail
IN="${1:-soilflow-pflotran-image.tar}"
docker load -i "$IN"
echo "[OK] Loaded Docker image from $IN"
