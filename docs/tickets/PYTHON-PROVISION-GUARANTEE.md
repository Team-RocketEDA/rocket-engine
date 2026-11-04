# PYTHON-PROVISION-GUARANTEE: Python wheels and libs always provision or fail loudly

*Status: Backlog · Filed: 2026-11-04 · Source: setup-surface review 2026-11-04*

Policy: Python wheels/libs are inexcusable not to provision. Heavy
source builds (Xyce, openEMS) may degrade with reason; `kind: python`
catalogue entries (sax, circulax, meow, gdsfactory, cace, devsim,
pymeep env) must resolve in `--install` or fail loudly — never
silently missing, never quietly skipped.

## Scope

- Every `kind: python` entry in `setup_catalogue.yaml` resolves via
  its recipe (uv group sync, venv pip pin, conda env) under a full
  `--install`; any miss is a hard phase error naming the package.
- `--check-only` reports each python entry installed/missing with
  remedy; no python entry may sit in an unverified state.
- Close the pymeep/deferred ambiguity via DEFERRED-LANE-INTENT first
  if it rules the other way; this ticket then enforces the outcome
  for python-kind entries regardless of lane.

## Acceptance

- Full `--install` on the reference host: all python entries resolve
  or the run fails naming each miss. `--check-only` names every
  python miss with its remedy.
