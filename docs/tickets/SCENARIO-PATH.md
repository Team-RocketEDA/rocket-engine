# SCENARIO-PATH: Pin scenario gate to dev-PATH

*Status: Backlog · Depends: MOCK-HARNESS · Size: S · Roadmap: orch-build-mvp*

## Why

Wave-1 verify showed `scripts/scenarios.py` exits 1 on a default
PATH (2 HDL scenarios report NOT_RUN) and 8/8 green under
dev-PATH with oss-cad-suite on PATH. The failures are
toolchain-PATH-caused, not code defects — but a gate that flips
on ambient PATH is a trap for CI and for anyone running the
harness cold. The gate must declare which toolchain it needs.

## What

- Document the scenario gate's PATH contract (dev-PATH with
  oss-cad-suite) in the scenarios README/runbook.
- Make `scenarios.py` fail loudly at startup when a scenario's
  required tool is missing from PATH (missing_dependency with
  the tool name), instead of NOT_RUN verdicts mid-run.

## Acceptance

- RED-first: harness on bare PATH errors naming the missing
  tool; on dev-PATH the suite is 8/8 green.
- Full suite green both PATH configs.
