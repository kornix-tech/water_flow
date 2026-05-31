#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME="${IMAGE_NAME:-soilflow-pflotran}"
IMAGE_TAG="${IMAGE_TAG:-local}"
UBUNTU_VERSION="${UBUNTU_VERSION:-24.04}"
PETSC_VERSION="${PETSC_VERSION:-v3.24.5}"
PETSC_ARCH="${PETSC_ARCH:-linux-opt}"
PFLOTRAN_GIT_REF="${PFLOTRAN_GIT_REF:-master}"
PFLOTRAN_REPO="${PFLOTRAN_REPO:-https://bitbucket.org/pflotran/pflotran}"
PLATFORM_ARG="${PLATFORM_ARG:-}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker не найден в PATH. Установите Docker внутри WSL/Ubuntu." >&2
  exit 1
fi

set -x
docker build ${PLATFORM_ARG} --progress=plain \
  --build-arg UBUNTU_VERSION="${UBUNTU_VERSION}" \
  --build-arg PETSC_VERSION="${PETSC_VERSION}" \
  --build-arg PETSC_ARCH="${PETSC_ARCH}" \
  --build-arg PFLOTRAN_GIT_REF="${PFLOTRAN_GIT_REF}" \
  --build-arg PFLOTRAN_REPO="${PFLOTRAN_REPO}" \
  -t "${IMAGE_NAME}:${IMAGE_TAG}" \
  -f Dockerfile .
set +x

echo ""
echo "Готово: ${IMAGE_NAME}:${IMAGE_TAG}"
echo "Проверка: docker run --rm ${IMAGE_NAME}:${IMAGE_TAG} check"
echo "_test:   docker run --rm ${IMAGE_NAME}:${IMAGE_TAG} _test"
echo "Демо:    docker/run_demo.sh"
