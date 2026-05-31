#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
rm -rf "${ROOT_DIR}/output/runs" "${ROOT_DIR}/output/demo_richards" "${ROOT_DIR}/output/_test_linear_darcy"
mkdir -p "${ROOT_DIR}/output"
echo "[OK] Cleaned output directory"
