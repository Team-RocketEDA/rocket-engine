#!/usr/bin/env bash
# DEMO-PATH slice: provision the engine's locked Python env + register the
# demo PDK + probe batch-tool capabilities.
#
# STATUS (2026-10-31): venv bootstrap, locked sync, sealed package
# install, engine import check, PDK register, the tool-capability
# probe, and the PROV phase-1 toolchain provisioner below are real
# and runnable (see docs/demo-runbook.md and docs/work/PROV/report.md).
# The phase-1 slice (oss-cad-suite pin assert, LibreLane supported
# distribution, OpenSTA build) lives in scripts/provision_toolchain.sh
# with `tests/installed/` asserting pins; the rest of the matrix is
# PROV phase 2 (out of scope here).
#
# Usage:
#   scripts/install.sh --check-only   # probe only: versions + matrix, no writes
#   scripts/install.sh --pdk-only     # register the PDK into ROCKETEDA_HOME only
#   scripts/install.sh [--install]    # venv + locked sync + engine + PDK + probe
#
# PDK register honors:
#   PDK_SOURCE    PDK tree to adopt (default: ~/.local/share/pdk/sky130A)
#   PDK_ID        store id (default: sky130A; slug sky130a on disk;
#                 sky130gf takes the pip branch: no tree needed)
#   PDK_REVISION  store revision (default: open_pdks commit in nodeinfo.json)
#   ROCKETEDA_HOME  engine store (default: $ROOT/.stores/rocketeda;
#                 BUILD-LOCAL stage 2 — explicit env still wins)
# PDK-GF180 register (generic --pdk-only honors the knobs above, no new
# mode): PDK_ID=gf180mcu PDK_SOURCE=<gf180mcu tree>
# PDK_REVISION=d422b869efa544597d3a1256eec7441f8cc89980
# scripts/install.sh --pdk-only, then `python install_tech.py` from the
# tree for the KLayout tech (docs/pdk/gf180/recipe.md §2).
#
# Engine/display split (see docs/provision-plan.md): only batch-capable
# tools are engine deps. X-needing tools (xschem/KLayout/GTKWave GUIs,
# Surfer) are RocketIDE-side and never gate engine tests.

set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODE="${1:---install}"

# BUILD-LOCAL stage 2: the engine store defaults into the repo
# ($ROOT/.stores/rocketeda) so a fresh clone writes nothing
# outside it. Explicit env still wins: existing
# ~/.local/share/rocketeda users keep working via
# ROCKETEDA_HOME=~/.local/share/rocketeda.
ROCKETEDA_HOME="${ROCKETEDA_HOME:-$ROOT/.stores/rocketeda}"
export ROCKETEDA_HOME

# Flair: colors on interactive terminals only; piped output
# (tests, logs) stays byte-identical plain. NO_COLOR=1 wins.
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    C_OK=$'\033[32m'
    C_WARN=$'\033[33m'
    C_ERR=$'\033[31m'
    C_HEAD=$'\033[1;36m'
    C_DIM=$'\033[2m'
    C_OFF=$'\033[0m'
else
    C_OK=''
    C_WARN=''
    C_ERR=''
    C_HEAD=''
    C_DIM=''
    C_OFF=''
fi
step() { printf '%s\n' "${C_HEAD}==> $1${C_OFF}"; }

probe() {  # name, version-argv...
    local name="$1"; shift
    local bin
    bin="$(command -v "$name" || true)"
    if [ -z "$bin" ]; then
        printf "%-10s ${C_ERR}%-9s${C_OFF} %s\n" "$name" "absent" "-"
        return 0
    fi
    local ver
    ver="$("$@" </dev/null 2>&1 | head -n 1 | cut -c1-72 || true)"
    printf "%-10s ${C_OK}%-9s${C_OFF} %s [${C_DIM}%s${C_OFF}]\n" \
        "$name" "present" "$ver" "$bin"
}

pdk_pip_sky130gf() {
    # PDK-SKY130GF: pip distribution (sky130==1.0.0) — layout cells +
    # KLayout tech only; DRC/LVS/extract/sim stay on the pdk-sky130A
    # tree entry (docs/pdk/sky130gf/profile.yaml decision.*).
    # --no-deps protects the repo gdsfactory 9.51.0: a plain install
    # resolves gdsfactory~=9.40.1 and downgrades to 9.40.2 (verified).
    local py="$ROOT/.venv/bin/python"
    if [ ! -x "$py" ]; then
        echo "install.sh: no engine interpreter at $py" >&2
        echo "next: run scripts/install.sh --install to bootstrap the venv" >&2
        return 1
    fi
    command -v uv >/dev/null 2>&1 || { echo "install.sh: uv not on PATH" >&2; echo "next: install uv (https://docs.astral.sh/uv/), then retry" >&2; return 1; }
    uv pip install --python "$py" --no-deps "sky130==1.0.0" || return 1
    local sky130
    sky130="$("$py" -c "import sky130, os; print(os.path.dirname(sky130.__file__))")" || return 1
    mkdir -p "$HOME/.klayout/tech"
    ln -sfn "$sky130/klayout" "$HOME/.klayout/tech/sky130gf"
    echo "pdk sky130gf@1.0.0: pip installed + KLayout tech linked"
    echo "next: run the recipe verify probe (docs/pdk/sky130gf/recipe.md §3)"
}

pdk_only() {
    local source="${PDK_SOURCE:-$HOME/.local/share/pdk/sky130A}"
    local id="${PDK_ID:-sky130A}"
    local revision="${PDK_REVISION:-5f09001e4b975ba35d27d99a10ecdf45054a9bd5}"
    if [ "$id" = "sky130gf" ]; then
        pdk_pip_sky130gf || exit 1
        exit 0
    fi
    if [ ! -d "$source" ]; then
        echo "install.sh: PDK source is not a directory: $source" >&2
        echo "next: set PDK_SOURCE to the sky130A tree, then retry" >&2
        return 1
    fi
    local py="$ROOT/.venv/bin/python"
    if [ ! -x "$py" ]; then
        echo "install.sh: no engine interpreter at $py" >&2
        echo "next: run scripts/install.sh --install to bootstrap the venv" >&2
        return 1
    fi
    PDK_SOURCE="$source" PDK_ID="$id" PDK_REVISION="$revision" "$py" - <<'EOF'
import os
from rocket_engine.interfaces.pdks import register_pdk

try:
    entry = register_pdk(os.environ["PDK_SOURCE"], os.environ["PDK_ID"],
                         os.environ["PDK_REVISION"])
except Exception as exc:
    print(f"install.sh: PDK register failed: {exc}")
    print("next: check PDK_SOURCE/PDK_ID/PDK_REVISION and that "
          "ROCKETEDA_HOME is writable, then retry")
    raise SystemExit(1)
state = "already registered, reverified" if entry["reverified"] else "registered"
print(f"pdk {entry['id']}@{entry['revision']}: {state} "
      f"({entry['file_count']} files, {entry['path']})")
EOF
}

if [ "$MODE" != "--check-only" ] && [ "$MODE" != "--install" ] \
    && [ "$MODE" != "--pdk-only" ]; then
    echo "usage: scripts/install.sh [--check-only|--install|--pdk-only]" >&2
    exit 2
fi

if [ "$MODE" = "--pdk-only" ]; then
    pdk_only || exit 1
    exit 0
fi

if [ "$MODE" = "--install" ]; then
    command -v uv >/dev/null 2>&1 || { echo "install.sh: uv not on PATH" >&2; echo "next: install uv (https://docs.astral.sh/uv/), then retry" >&2; exit 1; }
    step "venv + locked sync (core library ships all solvers: plain uv sync installs everything)"
    (cd "$ROOT" && uv venv --clear --python 3.12 && uv sync --locked --no-install-project) || exit 1
    step "engine package install (sealed copy)"
    (cd "$ROOT" && uv pip install --python .venv/bin/python --no-deps .) || exit 1
    step "engine import check"
    (cd "$ROOT" && .venv/bin/python -c "import rocket_engine; print('ok')") || exit 1
    step "PDK register"
    bash "$0" --pdk-only || exit 1
fi

step "tool capability probe (engine = batch-capable only)"
printf '%-10s %-9s %s\n' "TOOL" "STATE" "VERSION"
probe bwrap bwrap --version
probe magic magic --version
probe klayout klayout -v
probe iverilog iverilog -V
probe vvp vvp -V
probe verilator verilator --version
probe slang slang --version
probe yosys yosys -V
probe ghdl ghdl --version
probe sby sby --version
probe librelane librelane --version
probe sta sta -version
probe ngspice ngspice --version
probe netgen netgen -batch
printf '%s\n' "${C_DIM}pins: PROV phases 1+2 (scripts/provision_toolchain.sh + tests/installed).${C_OFF}"
step "toolchain provision (PROV phases 1+2; loud verdict, never blocks venv/PDK)"
if [ "$MODE" = "--check-only" ]; then
    bash "$ROOT/scripts/provision_toolchain.sh" --check-only || true
else
    bash "$ROOT/scripts/provision_toolchain.sh" --install || {
        echo "next: toolchain degraded (see REMEDY lines above); venv + PDK still usable"
    }
fi
