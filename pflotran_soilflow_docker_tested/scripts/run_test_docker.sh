#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

IMAGE_NAME="${IMAGE_NAME:-soilflow-pflotran:local}"
LOCAL_INPUT_JSON="${1:-input/soilflow_pflotran_demo.json}"
CONTAINER_WORKDIR="${2:-/work/runs/_test_linear_darcy}"
TEST_NAME="${3:-linear_darcy}"

mkdir -p output

DOCKER_TTY_ARGS=()
if [[ -t 0 && -t 1 ]]; then
  # TTY нужен только при ручном запуске из терминала; в автоматическом запуске
  # Docker иначе падает с ошибкой "stdin is not a terminal".
  DOCKER_TTY_ARGS=(-it)
fi

cat <<INFO
[INFO] Running analytical verification _test container
  image       = ${IMAGE_NAME}
  local JSON  = ${LOCAL_INPUT_JSON}
  test        = ${TEST_NAME}
  workdir     = ${CONTAINER_WORKDIR}
  output root = ${ROOT_DIR}/output
INFO

docker run --rm "${DOCKER_TTY_ARGS[@]}" \
  -v "${ROOT_DIR}:/case:ro" \
  -v "${ROOT_DIR}/output:/work" \
  "${IMAGE_NAME}" \
  run-test "/case/${LOCAL_INPUT_JSON}" "${CONTAINER_WORKDIR}" "${TEST_NAME}"

cat <<INFO
[OK] Finished. Test results are under:
  ${ROOT_DIR}/output${CONTAINER_WORKDIR#/work}

Check:
  TEST_STATUS.txt
  test_comparison.csv
  test_comparison.svg
INFO
