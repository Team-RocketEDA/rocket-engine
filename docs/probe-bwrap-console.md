# Console sandbox study (BWRAP-STUDY input, 2026-11-03)

Question (RULING-04): the console is a plain python console in a
trusted-local, never-cloud deployment with user-side permissions —
so the only question is hygiene vs friction. Standing requirement
(RULING-07): the live env provides every library a client may need
for scripting, with appropriate project contexts — each option is
scored against it below.

## What was compared

1. **bwrap-keep**: every console/python cell runs in a fresh
   BwrapRunner-confined worker (scratch-only writes, execution-scoped
   IPC credentials, confirmed tree-kill before the terminal record).
2. **Raw python exec**: cells run in the engine interpreter (or a
   prepared one) with no namespace confinement.
3. **Prepackaged scripting contexts**: project-aware preludes plus a
   safe stdlib surface, reducing the need for arbitrary exec without
   replacing the substrate.

## Evidence

- `docs/probe-bwrap-isolation.md` (2026-10-28): bwrap 0.11.0 over
  user namespaces confines the filesystem (ro sysdirs, rw work
  bind, invisible home) with identical solver output inside/outside;
  network namespaces and fresh mounts are denied by this kernel, so
  profiles declare required namespaces and preflight REFUSES with
  `runner_unavailable` where they cannot be proven — never silently
  degraded. Net isolation stays UNPROVEN here (re-prove on target
  Ubuntu, B10).
- Current code already implements bwrap-keep: `CellRunner` admits
  approved cells only through `ConsoleSession.admit_cell` and runs
  each in a fresh confined worker (`src/execution/worker.py`, I23
  credentials + I24 artifact harvest with symlink-escape rejection);
  `PythonExecRunner` reuses the same substrate over the prepared
  profile interpreter (`src/execution/pyexec/runner.py`), stamping
  every admission and result with `network_isolated` and refusing
  admission (not degrading) under `require_net=True`.
- Fresh probe on this host (2026-11-03): `/usr/bin/bwrap` preflights
  OK (userns confinement provable); the oss-cad-suite-shadowed
  `bwrap` on PATH refuses loudly with `runner_unavailable` ("No
  permissions to create a new namespace") — the predicted
  adoption-friction case, and it fails closed, never fake-green.
- Middle-path machinery already exists: project-bound preamble
  templates (`PRELUDE_TEMPLATE` in `src/execution/pyexec/support.py`,
  `CELL_PRELUDE_TEMPLATE` in `src/adapters/stdio_console.py`) render
  the project binding before the display cell, and the rendered
  digest pins approvals (a preamble change invalidates outstanding
  approvals instead of running under a new env). Prepared profile
  interpreters carry gdsfactory/numpy where installed, meeting
  RULING-07 without touching the host env.

## Option scoring

| Option | Hygiene | Friction | RULING-07 |
|---|---|---|---|
| bwrap-keep | Writes scoped to scratch; IPC tokens execution-scoped and revoked; runaway trees confirmed-killed; failure mode is loud refusal | Needs a provable bwrap (shadowed/old kernels refuse); net isolation unprovable on some kernels | Met: prepared interpreter + project preamble inside the sandbox |
| Raw python exec | A script typo can destroy the engine root or home dir; no credential scoping; no kill guarantees beyond pgid | Zero: runs everywhere Python runs | Met trivially, at full host exposure |
| Prepackaged contexts | Shrinks what arbitrary code must do (binding + libs prebound) but cannot bound what it does | Lowest for routine tasks; power users still need an escape hatch | Partially met today; grows by adding preludes, not by removing isolation |

## Decision

**Keep bwrap-confined workers as the only cell-execution
substrate; do not add a raw-exec mode.** Rationale: the sandbox is
already built, proven byte-identical on solver output, and its
failure mode is refusal rather than silent escape; raw exec trades
all of that (filesystem scope, credential scope, kill guarantees)
for convenience in a tool whose whole purpose is durable,
attributed mutation of design truth. Friction is real but
addressed the other way: **grow the prepackaged contexts** (more
project-aware preludes, pinned and digest-bound) so routine
scripting never needs the escape hatch that raw exec would be.

## What this feeds (CONSOLE-LIFECYCLE, T-08)

Lifecycle is unchanged: console identity plus generation,
approval binding (code/cursor/env-digest/revision), and reset that
retires the generation and kills outstanding approvals. The
substrate ruling from this study: execution runs only in confined
workers; where bwrap is unprovable the console still records
generations and approvals but admits nothing — refusal is a
lifecycle event, never a silent run.

## Open (B10 / target Ubuntu)

- Re-prove `--unshare-net` where the kernel allows it.
- Decide bwrap provenance (system vs bundled) and PATH order so
  the shadowed-binary refusal stops surprising dev shells.
