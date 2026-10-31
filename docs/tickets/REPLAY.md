# REPLAY: First-class run replay affordance

*Status: Closed decided-against (2026-11-01) · Roadmap: orch-build-mvp*

> Closed, not implemented: replay of FINISHED runs was
> decided against — finished runs are never re-executed,
> resubmit-when-wanted covers it (API-GENERALIZE field
> notes, user decision). Survivor resume/discard is
> covered by REPLAY-SAFE (Done). This ticket remains for
> the decision record only.

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
