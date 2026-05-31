#!/usr/bin/env bash
set -euo pipefail
IMAGE_NAME="${IMAGE_NAME:-soilflow-pflotran}"
IMAGE_TAG="${IMAGE_TAG:-local}"
docker run --rm "${IMAGE_NAME}:${IMAGE_TAG}" check
