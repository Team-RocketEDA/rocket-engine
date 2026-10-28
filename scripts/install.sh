#!/usr/bin/env bash
# B10 draft: provision the engine's native toolchain + locked Python env.
#
# DRAFT STATUS (2026-10-28): the venv bootstrap and the tool-capability
# probe below are real and runnable. Pinned tool installs (oss-cad-suite
# tarball, apt pins, source builds) and PDK/deck provisioning are NOT
# here yet: they wait on the deck-source decision (vendor sky130A
# snapshot vs user PDK path) and the corpus review. `tests/installed/`
# lands with the B10 final, since it asserts pins this draft cannot.
#
# Usage:
#   scripts/install.sh --check-only   # probe only: versions + matrix, no writes
#   scripts/install.sh                 # bootstrap venv + locked sync, then probe
#
# Engine/display split (see docs/provision-plan.md): only batch-capable
# tools are engine deps. X-needing tools (xschem/KLayout/GTKWave GUIs,
# Surfer) are RocketIDE-side and never gate engine tests.

set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODE="${1:---install}"

probe() {  # name, version-argv...
    local name="$1"; shift
    local bin
    bin="$(command -v "$name" || true)"
    if [ -z "$bin" ]; then
        printf '%-10s %-9s %s\n' "$name" "absent" "-"
        return 0
    fi
    local ver
    ver="$("$@" 2>&1 | head -n 1 | cut -c1-72 || true)"
    printf '%-10s %-9s %s [%s]\n' "$name" "present" "$ver" "$bin"
}

if [ "$MODE" != "--check-only" ] && [ "$MODE" != "--install" ]; then
    echo "usage: scripts/install.sh [--check-only]" >&2
    exit 2
fi

if [ "$MODE" = "--install" ]; then
    command -v uv >/dev/null 2>&1 || { echo "install.sh: uv not on PATH" >&2; exit 1; }
    echo "==> venv + locked sync"
    (cd "$ROOT" && uv venv --python 3.12 && uv sync --locked --group dev) || exit 1
    echo "==> engine import check"
    (cd "$ROOT" && uv run --locked python -c "import rocket_engine; print('ok')") || exit 1
fi

echo "==> tool capability probe (engine = batch-capable only)"
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
probe ngspice ngspice --version
echo "DRAFT: no pins asserted; PDK/decks pending deck-source decision."
