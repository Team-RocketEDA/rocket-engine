# DOCKER-DEPLOY: one-container judging/deployment recipe (engine side).
#
# Multi-stage: base (pinned interpreter + system deps) -> locked
# engine install -> provisioned batch toolchain -> run (non-root,
# volume PDK, demo gate as the container command).
#
# Base pin: the tag below is fully qualified (never `:latest`).
# The digest pin lands at build time on a networked host:
#   docker build --provenance=true -t rocketeda:local .
#   docker images --digests rocketeda:local   # record the digest
# then repin `BASE_IMAGE` to `...@sha256:<digest>` for the judging
# build. This checkout host has no daemon route and no registry
# route, so the digest transcription is BLOCKED-needs-host
# (recorded, never faked with an unverified digest).
#
# PDK story (never baked into layers): the 12G sky130A tree rides
# a named volume (`edata-pdk` at /pdk) or a first-run fetch into
# the engine store volume (`edata-store` at /stores/rocketeda).
# `scripts/install.sh --pdk-only` adopts it on first run; later
# runs re-verify instead of copying.
#
# Trust boundary: the plain-HTTP adapter stays NO-AUTH for
# local/judging convenience and binds 127.0.0.1 only. The image
# therefore runs with `--network=host` (Linux judging hosts), so
# the container loopback IS the host loopback — never publish
# the port to untrusted networks (auth'd HTTPS is the later path).
#
# Fuel + web app seams: sibling checkouts mount at /fuel and /ui
# (build args below); the engine image serves them once those
# lanes land their own layers (out of scope here).
ARG BASE_IMAGE=docker.io/library/python:3.12-slim-bookworm

# ---- base: interpreter + provisioner system deps ------------------
FROM ${BASE_IMAGE} AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_CACHE_DIR=/tmp/uv-cache
# Provisioner build prerequisites (docs/provision-sources.md):
# git + curl + dpkg-deb for fetching/unpacking, compilers for the
# source builds (opensta, magic, netgen, ngspice, xschem, openems).
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl ca-certificates dpkg-deb \
    make cmake gcc g++ gfortran bison flex swig \
    tcl tcl-dev tk tk-dev libx11-dev \
    bzip2 xz-utils unzip sudo \
    && rm -rf /var/lib/apt/lists/*
RUN useradd --create-home --shell /bin/bash rocketeda
WORKDIR /engine

# ---- engine: locked install (uv, no dev groups) -------------------
FROM base AS engine
COPY pyproject.toml uv.lock .python-version README.md ./
COPY src/ ./src/
COPY scripts/install.sh ./scripts/install.sh
RUN pip install --no-cache-dir uv \
    && uv sync --locked --no-dev --no-install-project \
    && uv pip install --no-deps . \
    && rm -rf /tmp/uv-cache
COPY scripts/ ./scripts/
COPY docs/ ./docs/
COPY contracts/ ./contracts/
COPY scenarios/ ./scenarios/
COPY fixtures/ ./fixtures/

# ---- toolchain: provisioned batch tools (needs network) ----------
FROM engine AS toolchain
ENV TOOLS_DIR=/tools \
    ROCKETEDA_HOME=/stores/rocketeda \
    OSS_CAD_SUITE_DIR=/tools/oss-cad-suite
RUN mkdir -p /tools /stores/rocketeda /pdk \
    && chown -R rocketeda:rocketeda /tools /stores /pdk /engine
USER rocketeda
# Pinned toolchain install (PROV phase 1+2). Off-host this layer
# is loud-skipped: it needs registry + release-tarball routes.
RUN bash scripts/provision_toolchain.sh --install

# ---- run: volumes, loopback serve, demo gate ----------------------
FROM toolchain AS run
USER rocketeda
ENV TOOLS_DIR=/tools \
    ROCKETEDA_HOME=/stores/rocketeda \
    PATH="/tools/oss-cad-suite/bin:/tools/bin:${PATH}"
# PDK + store stay on named volumes, never in layers.
VOLUME ["/pdk", "/stores/rocketeda"]
EXPOSE 8000
# First run adopts the volume PDK into the store; every run after
# re-verifies. Then the four demo stages prove the engine.
CMD ["bash", "-c", "scripts/install.sh --pdk-only && scripts/demo.sh"]
