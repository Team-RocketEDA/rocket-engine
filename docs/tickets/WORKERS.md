# WORKERS: Isolated worker substrate (I23/I24)

*Status: Backlog · Depends: none · Size: M · Roadmap: orch-build-mvp*

## Why

Every console dream (MATLAB-esque REPL, notebooks, remote exec)
stands on one substrate: workers that spawn sandboxed, run one
approved cell with execution-scoped credentials, then die with
confirmed tree termination and zero state carried forward (I23).
Approval binding already exists in `console.py`; execution does
not. Without this ticket, the console is a ledger that records
cells without running them — everything downstream is blocked on it.

## What

- Worker spawn under BwrapRunner confinement (reuse I16 mechanics:
  no network, scratch-only writes, budgets, kill on timeout).
- Execution-scoped IPC credentials: accepted only while the run
  lives; revoked + tree-kill confirmed before terminal state or
  next cell (I23); delayed/background calls rejected.
- Fresh worker per cell; namespace never crosses cells (I23);
  reusable results persist only as approved artifacts (I24 shape).
- Crash/timeout reconciliation with truthful states (no fake PASS).

## Acceptance

- RED-first: adversarial tests deny host/network/evidence access;
  post-cell threaded callbacks rejected; kill-tree confirmed;
  timeout yields truthful state + retained partials.
- Unavailable isolation disables admission with reason (no host
  fallback). Suite green both configs.
