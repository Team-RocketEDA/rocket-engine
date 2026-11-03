#!/usr/bin/env bash
# DEMO-PATH: one-command Nov 4 demo — provision, prove, report.
#
# Stages:
#   install    scripts/install.sh --install (venv + locked sync + engine
#              + PDK register + tool probe)
#   fetch      fixture license gate (all vendored trees present + accepted)
#   scenarios  scripts/scenarios.py over scenarios/ (all MVP flows)
#   gate       scripts/correctness.py (correctness report, PASS/FAIL)
#
# Never aborts early: every stage runs, each failure names its cause +
# next step, and the exit code is 0 iff all four stages pass. Expected
# output for the demo machine is recorded in docs/demo-runbook.md.
#
# Usage:
#   scripts/demo.sh [--help]
#
# Environment: PATH must include the batch toolchain
# ($HOME/tools/oss-cad-suite/bin); ROCKETEDA_HOME and PDK_* pass
# through to install.sh (see its header for defaults).

set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
    sed -n '2,/^$/p' "$0" | sed 's/^# \?//'
    exit 0
fi
if [ $# -ne 0 ]; then
    echo "usage: scripts/demo.sh [--help]" >&2
    exit 2
fi

STAGES_OK=0
STAGES_FAIL=0

run_stage() {  # name, next-step, cmd...
    local name="$1" next="$2"; shift 2
    echo "================================================================"
    echo "demo stage: $name"
    echo "================================================================"
    "$@" && {
        echo "demo stage $name: PASS"
        STAGES_OK=$((STAGES_OK + 1))
    } || {
        echo "demo stage $name: FAIL"
        echo "next: $next"
        STAGES_FAIL=$((STAGES_FAIL + 1))
    }
}

PY=".venv/bin/python"
if [ ! -x "$PY" ]; then
    echo "demo: no engine interpreter at $PY (install stage will bootstrap it)"
fi

run_stage "install" \
    "read the failing install.sh step above and retry that mode (see docs/demo-runbook.md)" \
    bash scripts/install.sh --install

if [ -x "$PY" ]; then
    run_stage "fetch" \
        "run $PY scripts/fetch_fixtures.py to vendor the missing tree (needs network)" \
        "$PY" scripts/fetch_fixtures.py --check
    run_stage "scenarios" \
        "each FAIL line above names its cause; env-blocked items cite their ticket" \
        "$PY" scripts/scenarios.py scenarios/
    run_stage "gate" \
        "open tmp/correctness/report.md: quarantines cite refs, failures link artifacts" \
        "$PY" scripts/correctness.py
else
    echo "demo stage fetch: SKIP (no $PY; install failed)"
    echo "demo stage scenarios: SKIP (no $PY; install failed)"
    echo "demo stage gate: SKIP (no $PY; install failed)"
    STAGES_FAIL=$((STAGES_FAIL + 3))
fi

echo "================================================================"
echo "demo: $STAGES_OK passed, $STAGES_FAIL failed (install/fetch/scenarios/gate)"
if [ "$STAGES_FAIL" -ne 0 ]; then
    echo "demo: FAIL — see docs/demo-runbook.md for the expected transcript"
    exit 1
fi
echo "demo: PASS"
exit 0
