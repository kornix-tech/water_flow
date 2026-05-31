#!/usr/bin/env bash
set -euo pipefail

export PETSC_DIR="${PETSC_DIR:-/opt/petsc}"
export PETSC_ARCH="${PETSC_ARCH:-linux-gnu-c-opt}"
export PFLOTRAN_DIR="${PFLOTRAN_DIR:-/opt/pflotran}"
export PFLOTRAN_EXE="${PFLOTRAN_EXE:-${PFLOTRAN_DIR}/src/pflotran/pflotran}"
export SOILFLOW_HOME="${SOILFLOW_HOME:-/opt/soilflow}"
export PATH="${PFLOTRAN_DIR}/src/pflotran:${PETSC_DIR}/${PETSC_ARCH}/bin:${PATH}"
export LD_LIBRARY_PATH="${PETSC_DIR}/${PETSC_ARCH}/lib:${LD_LIBRARY_PATH:-}"

cmd="${1:-demo}"
case "${cmd}" in
  web|serve)
    shift || true
    exec "${SOILFLOW_HOME}/docker/run_web.sh" "$@"
    ;;
  demo)
    mkdir -p /workspace/output/demo_richards
    exec python3 "${SOILFLOW_HOME}/scripts/soilflow_pflotran.py" \
      --mode demo \
      --input-json "${SOILFLOW_HOME}/input/soilflow_pflotran_demo.json" \
      --workdir /workspace/output/demo_richards \
      --run \
      --pflotran-exe "${PFLOTRAN_EXE}"
    ;;
  test|_test)
    shift || true
    mkdir -p /work/runs
    exec python3 "${SOILFLOW_HOME}/scripts/soilflow_pflotran.py" \
      --mode _test \
      --input-json "${SOILFLOW_HOME}/input/soilflow_pflotran_demo.json" \
      --output-dir /work \
      --run \
      --pflotran-exe "${PFLOTRAN_EXE}" \
      "$@"
    ;;
  run-demo)
    shift
    input_json="${1:-${SOILFLOW_HOME}/input/soilflow_pflotran_demo.json}"
    workdir="${2:-/work/runs/demo_richards}"
    mkdir -p "${workdir}"
    exec python3 "${SOILFLOW_HOME}/scripts/soilflow_pflotran.py" \
      --mode demo \
      --input-json "${input_json}" \
      --workdir "${workdir}" \
      --run \
      --pflotran-exe "${PFLOTRAN_EXE}"
    ;;
  run-test|run-_test)
    shift
    input_json="${1:-${SOILFLOW_HOME}/input/soilflow_pflotran_demo.json}"
    workdir="${2:-/work/runs/_test_linear_darcy}"
    test_name="${3:-linear_darcy}"
    mkdir -p "${workdir}"
    exec python3 "${SOILFLOW_HOME}/scripts/soilflow_pflotran.py" \
      --mode _test \
      --test "${test_name}" \
      --input-json "${input_json}" \
      --workdir "${workdir}" \
      --run \
      --pflotran-exe "${PFLOTRAN_EXE}"
    ;;
	  generate)
	    shift
	    exec python3 "${SOILFLOW_HOME}/scripts/soilflow_pflotran.py" "$@"
	    ;;
	  visualize|viz|plot)
	    shift || true
	    exec python3 "${SOILFLOW_HOME}/scripts/soilflow_visualize.py" "$@"
	    ;;
	  check)
    exec /usr/local/bin/soilflow-check
    ;;
  pflotran)
    shift
    exec "${PFLOTRAN_EXE}" "$@"
    ;;
  mpirun)
    shift
    exec mpirun "$@"
    ;;
  bash|shell)
    exec /bin/bash
    ;;
  *)
    exec "$@"
    ;;
esac
