#!/usr/bin/env bash
# DEMO-PATH slice: provision the engine's locked Python env + register the
# demo PDK + probe batch-tool capabilities.
#
# STATUS (2026-10-30): venv bootstrap, locked sync, sealed package
# install, engine import check, PDK register, and the tool-capability
# probe below are real and runnable (proven on the demo machine; see
# docs/demo-runbook.md). Pinned tool
# installs (oss-cad-suite tarball, apt pins, source builds) are NOT here
# yet: they stay B10-owned, with `tests/installed/` asserting pins.
#
# Usage:
#   scripts/install.sh --check-only   # probe only: versions + matrix, no writes
#   scripts/install.sh --pdk-only     # register the PDK into ROCKETEDA_HOME only
#   scripts/install.sh [--install]    # venv + locked sync + engine + PDK + probe
#
# PDK register honors:
#   PDK_SOURCE    PDK tree to adopt (default: ~/.local/share/pdk/sky130A)
#   PDK_ID        store id (default: sky130A; slug sky130a on disk)
#   PDK_REVISION  store revision (default: open_pdks commit in nodeinfo.json)
#   ROCKETEDA_HOME  engine store (default: ~/.local/share/rocketeda)
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

probe() {  # name, version-argv...
    local name="$1"; shift
    local bin
    bin="$(command -v "$name" || true)"
    if [ -z "$bin" ]; then
        printf '%-10s %-9s %s\n' "$name" "absent" "-"
        return 0
    fi
    local ver
    ver="$("$@" </dev/null 2>&1 | head -n 1 | cut -c1-72 || true)"
    printf '%-10s %-9s %s [%s]\n' "$name" "present" "$ver" "$bin"
}

pdk_only() {
    local source="${PDK_SOURCE:-$HOME/.local/share/pdk/sky130A}"
    local id="${PDK_ID:-sky130A}"
    local revision="${PDK_REVISION:-5f09001e4b975ba35d27d99a10ecdf45054a9bd5}"
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
    echo "==> venv + locked sync (deps only: the editable project install is broken for the src-as-root layout)"
    (cd "$ROOT" && uv venv --clear --python 3.12 && uv sync --locked --group dev --no-install-project) || exit 1
    echo "==> engine package install (sealed copy)"
    (cd "$ROOT" && uv pip install --python .venv/bin/python --no-deps .) || exit 1
    echo "==> engine import check"
    (cd "$ROOT" && .venv/bin/python -c "import rocket_engine; print('ok')") || exit 1
    echo "==> PDK register"
    bash "$0" --pdk-only || exit 1
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
probe netgen netgen -batch
echo "pins: B10-owned (tests/installed asserts them when B10 lands)."
