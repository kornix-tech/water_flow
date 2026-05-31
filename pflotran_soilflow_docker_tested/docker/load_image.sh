#!/usr/bin/env bash
set -euo pipefail

ARCHIVE="${1:-}"
if [[ -z "${ARCHIVE}" ]]; then
  echo "Использование: docker/load_image.sh portable_image/soilflow-pflotran_local.tar.gz" >&2
  exit 2
fi
if [[ ! -f "${ARCHIVE}" ]]; then
  echo "ERROR: файл не найден: ${ARCHIVE}" >&2
  exit 2
fi

gzip -dc "${ARCHIVE}" | docker load
