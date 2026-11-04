# REVIEW-PROOF-RUN: Execute the suite live to confirm review verdicts

*Status: Backlog · Filed: 2026-11-04 · Source: multi-agent review 2026-11-04*

The 2026-11-04 end-to-end review (3 primaries + critic + synthesis)
was read-only by design: every "GREEN / N passed" count is ticket-verdict
text corroborated by file/test-path existence, never an observed run.
Close-out (Step 20) cannot rest on unexecuted evidence.

## Goal

One observed full-suite run converting the review's status claims into
executed evidence.

## Scope

- Run the full pytest suite on the user host (or the reference host per
  Step 1 sandbox-vs-host split) and record: totals, failures, skips,
  wall time, host + commit.
- Run `provision_toolchain.sh --check-only` and record the lane
  verdicts (phase 1 / phase 2 / deferred).
- File discrepancies as new findings against the claiming ticket
  (Done tickets with red evidence get follow-ups, never silent edits).

## Acceptance

- Run output recorded (this file or `docs/tool-outputs/`); every
  review GREEN claim either confirmed or filed as a regression ticket.
