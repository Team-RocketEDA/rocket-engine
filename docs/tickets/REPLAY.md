# REPLAY: First-class run replay affordance

*Status: Backlog · Depends: PDK-STORE · Size: S · Roadmap: orch-build-mvp*

## Why

I28 promises regenerability, but today replay means hand-resubmitting
an envelope with a fresh id — workable, frictionful, and easy to
get subtly wrong (stale revision, wrong PDK). A one-command replay
from a stored run record closes the loop: the recipe proves itself
by re-executing. Parked because the recipe format must stabilize
(PDK-STORE) before replay automates it.

## What (when scheduled)

- `replay(run_id)` → re-issues the recorded envelope against the
  pinned revision + PDK; reports verdict-vs-recorded comparison.

## Acceptance

- Replay of a golden run reproduces its verdict; drift in inputs
  fails loudly naming the drifted field.
