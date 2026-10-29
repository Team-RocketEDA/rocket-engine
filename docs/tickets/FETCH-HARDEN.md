# FETCH-HARDEN: Harden fixture fetch pins + license gate

*Status: Backlog · Depends: FIXTURE-FETCH · Size: S · Roadmap: orch-build-mvp*

## Why

Wave-1 review found two soft spots in `scripts/fetch_fixtures.py`
that are fine for MVP but will bite over time: pins can orphan if
an upstream force-pushes (shallow fetch by SHA serves only
reachable commits), and the license gate's README fallback can
false-positive on a README that merely *mentions* a license (e.g.
a dependency note). Both fail in the wrong direction — the first
breaks a fresh setup loudly but confusingly, the second could
admit a tree the gate should reject.

## What

- Pin re-verification: `fetch_fixtures.py --verify-pins` (or a
  scheduled check) re-resolves each pin with `git ls-remote` and
  reports drift/orphans before they break a fetch.
- License precedence: LICENSE*/COPYING* files decide; README
  matches count only as a fallback signal with a loud warning,
  never a silent pass.

## Acceptance

- RED-first: orphaned-pin check reports the dead pin; README-only
  license mention warns instead of passing; LICENSE-file match
  still passes quietly.
- Full suite green both PATH configs.
