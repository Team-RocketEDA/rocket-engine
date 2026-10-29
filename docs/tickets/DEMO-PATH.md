# DEMO-PATH: One-command Nov 4 demo

*Status: Backlog · Depends: ENGINE-CORRECTNESS · Size: M · Roadmap: orch-build-mvp*

## Why

A sprint that ends in "works on my machine (mine)" fails the demo.
Nov 4 needs a runbook that provisions, proves, and reports in one
command on the demo machine — install, all validation gates, and
the correctness report, with every failure naming its cause. This
ticket turns the sprint's slices into a deliverable performance.

## What

- `install.sh --install` proven on the demo machine (venv + locked
  sync + engine + tool probe + PDK register).
- Scenario coverage across all MVP flows; `docs/demo-runbook.md`
  with the single command and expected output.

## Acceptance

- Fresh-shell runbook execution passes end-to-end; output recorded.
- Every known-failure mode prints cause + next step (no bare
  tracebacks to the demo audience).
