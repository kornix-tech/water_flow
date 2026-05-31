# syntax=docker/dockerfile:1
# -----------------------------------------------------------------------------
# SoilFlow/PFLOTRAN portable Docker image
# -----------------------------------------------------------------------------
# Builds PETSc + PFLOTRAN inside the image and ships the Python adapter + JSON
# demo input. Network is required only during docker build. Runtime can be run
# with --network none.
# -----------------------------------------------------------------------------

ARG UBUNTU_VERSION=24.04

FROM ubuntu:${UBUNTU_VERSION} AS pflotran-builder

ARG DEBIAN_FRONTEND=noninteractive
ARG PETSC_VERSION=v3.24.5
ARG PETSC_ARCH=linux-gnu-c-opt
ARG PFLOTRAN_REPO=https://bitbucket.org/pflotran/pflotran
ARG PFLOTRAN_GIT_REF=master
ARG BUILD_JOBS=4

ENV PETSC_DIR=/opt/petsc \
    PETSC_ARCH=${PETSC_ARCH} \
    PFLOTRAN_DIR=/opt/pflotran

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    build-essential \
    ca-certificates \
    cmake \
    curl \
    file \
    g++ \
    gcc \
    gfortran \
    git \
    make \
    perl \
    pkg-config \
    python3 \
    python3-dev \
    tar \
    wget \
    xz-utils \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# PETSc version follows PFLOTRAN v6.0 installation guide current recommendation.
RUN git clone --depth 1 --branch ${PETSC_VERSION} https://gitlab.com/petsc/petsc.git ${PETSC_DIR} \
    || (git clone https://gitlab.com/petsc/petsc.git ${PETSC_DIR} && cd ${PETSC_DIR} && git checkout ${PETSC_VERSION})

WORKDIR ${PETSC_DIR}
RUN ./configure \
      --PETSC_ARCH=${PETSC_ARCH} \
      --COPTFLAGS='-O3' \
      --CXXOPTFLAGS='-O3' \
      --FOPTFLAGS='-O3 -Wno-unused-function' \
      --with-debugging=no \
      --download-mpich=yes \
      --download-hdf5=yes \
      --download-hdf5-fortran-bindings=yes \
      --download-fblaslapack=yes \
      --download-metis=yes \
      --download-parmetis=yes \
    && make PETSC_DIR=${PETSC_DIR} PETSC_ARCH=${PETSC_ARCH} -j${BUILD_JOBS} all

RUN git clone ${PFLOTRAN_REPO} ${PFLOTRAN_DIR} \
    && cd ${PFLOTRAN_DIR} \
    && if [ -n "${PFLOTRAN_GIT_REF}" ]; then git checkout ${PFLOTRAN_GIT_REF}; fi

WORKDIR ${PFLOTRAN_DIR}/src/pflotran
RUN make -j${BUILD_JOBS} pflotran \
    && test -x ${PFLOTRAN_DIR}/src/pflotran/pflotran

# -----------------------------------------------------------------------------
# Frontend image: builds Vite/React into static production assets.
# -----------------------------------------------------------------------------
FROM node:20-bookworm-slim AS frontend-builder

WORKDIR /app
COPY web/frontend/package*.json ./
RUN npm ci
COPY web/frontend ./
RUN npm run build

# -----------------------------------------------------------------------------
# Runtime image: contains built PETSc/PFLOTRAN, Python adapter and demo data.
# -----------------------------------------------------------------------------
FROM ubuntu:${UBUNTU_VERSION} AS runtime

ARG DEBIAN_FRONTEND=noninteractive
ARG PETSC_ARCH=linux-gnu-c-opt

ENV PETSC_DIR=/opt/petsc \
    PETSC_ARCH=${PETSC_ARCH} \
    PFLOTRAN_DIR=/opt/pflotran \
    PFLOTRAN_EXE=/opt/pflotran/src/pflotran/pflotran \
    PYTHONUNBUFFERED=1

ENV PATH="${PFLOTRAN_DIR}/src/pflotran:${PETSC_DIR}/${PETSC_ARCH}/bin:${PATH}" \
    LD_LIBRARY_PATH="${PETSC_DIR}/${PETSC_ARCH}/lib"

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    ca-certificates \
    libgcc-s1 \
    libgfortran5 \
    libgomp1 \
    libquadmath0 \
    libstdc++6 \
	    procps \
	    python3 \
	    python3-pip \
	    zlib1g \
	    && rm -rf /var/lib/apt/lists/*

COPY --from=pflotran-builder /opt/petsc /opt/petsc
COPY --from=pflotran-builder /opt/pflotran /opt/pflotran

WORKDIR /opt/soilflow
COPY requirements.txt /opt/soilflow/requirements.txt
COPY web/backend/requirements-web.txt /opt/soilflow/web/backend/requirements-web.txt

RUN python3 -m pip install --no-cache-dir --break-system-packages --ignore-installed -r /opt/soilflow/requirements.txt \
    && python3 -m pip install --no-cache-dir --break-system-packages -r /opt/soilflow/web/backend/requirements-web.txt

COPY scripts /opt/soilflow/scripts
COPY input /opt/soilflow/input
COPY docs /opt/soilflow/docs
COPY web/backend /opt/soilflow/web/backend
COPY --from=frontend-builder /app/dist /opt/soilflow/web/frontend/dist
COPY docker /opt/soilflow/docker
COPY docker/entrypoint.sh /usr/local/bin/soilflow-entrypoint
COPY docker/check_container.sh /usr/local/bin/soilflow-check

RUN chmod +x /usr/local/bin/soilflow-entrypoint /usr/local/bin/soilflow-check /opt/soilflow/docker/*.sh /opt/soilflow/scripts/*.sh /opt/soilflow/scripts/soilflow_pflotran.py /opt/soilflow/scripts/soilflow_visualize.py \
    && mkdir -p /work/runs \
    && python3 /opt/soilflow/scripts/soilflow_pflotran.py \
        --mode demo \
        --input-json /opt/soilflow/input/soilflow_pflotran_demo.json \
        --workdir /tmp/soilflow_build_check \
        --dry-run \
    && python3 /opt/soilflow/scripts/soilflow_pflotran.py \
        --mode _test \
        --input-json /opt/soilflow/input/soilflow_pflotran_demo.json \
        --workdir /tmp/soilflow_test_check \
        --dry-run \
    && rm -rf /tmp/soilflow_build_check /tmp/soilflow_test_check

WORKDIR /work
EXPOSE 8080
ENTRYPOINT ["soilflow-entrypoint"]
CMD ["/opt/soilflow/docker/run_web.sh"]
