#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME="${IMAGE_NAME:-soilflow-pflotran}"
IMAGE_TAG="${IMAGE_TAG:-local}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXPORT_DIR="${EXPORT_DIR:-${ROOT_DIR}/portable_image}"
mkdir -p "${EXPORT_DIR}"
ARCHIVE="${EXPORT_DIR}/${IMAGE_NAME}_${IMAGE_TAG}.tar.gz"

docker image inspect "${IMAGE_NAME}:${IMAGE_TAG}" >/dev/null

echo "Сохраняю Docker image в ${ARCHIVE}"
docker save "${IMAGE_NAME}:${IMAGE_TAG}" | gzip -c > "${ARCHIVE}"
sha256sum "${ARCHIVE}" > "${ARCHIVE}.sha256"
echo "Готово: ${ARCHIVE}"
echo "Контрольная сумма: ${ARCHIVE}.sha256"
