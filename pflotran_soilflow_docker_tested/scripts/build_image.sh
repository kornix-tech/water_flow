#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

IMAGE_NAME="${IMAGE_NAME:-soilflow-pflotran:local}"
PETSC_VERSION="${PETSC_VERSION:-v3.24.5}"
PETSC_ARCH="${PETSC_ARCH:-linux-gnu-c-opt}"
PFLOTRAN_GIT_REF="${PFLOTRAN_GIT_REF:-master}"
BUILD_JOBS="${BUILD_JOBS:-$(nproc)}"
UBUNTU_VERSION="${UBUNTU_VERSION:-24.04}"

cat <<INFO
[INFO] Building Docker image
  image              = ${IMAGE_NAME}
  ubuntu             = ${UBUNTU_VERSION}
  PETSc version      = ${PETSC_VERSION}
  PETSc arch         = ${PETSC_ARCH}
  PFLOTRAN git ref   = ${PFLOTRAN_GIT_REF}
  build jobs         = ${BUILD_JOBS}
INFO

docker build \
  --progress=plain \
  --build-arg UBUNTU_VERSION="${UBUNTU_VERSION}" \
  --build-arg PETSC_VERSION="${PETSC_VERSION}" \
  --build-arg PETSC_ARCH="${PETSC_ARCH}" \
  --build-arg PFLOTRAN_GIT_REF="${PFLOTRAN_GIT_REF}" \
  --build-arg BUILD_JOBS="${BUILD_JOBS}" \
  -t "${IMAGE_NAME}" \
  .

cat <<INFO
[OK] Image built: ${IMAGE_NAME}

Run analytical _test:
  ./scripts/run_test_docker.sh

Run demo:
  ./scripts/run_demo_docker.sh

Check image:
  docker run --rm ${IMAGE_NAME} check
INFO
