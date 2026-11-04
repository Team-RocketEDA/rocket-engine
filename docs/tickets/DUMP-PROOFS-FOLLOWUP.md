# DUMP-PROOFS-FOLLOWUP: Close the Step 13 determinism-test gap

*Status: Backlog · Filed: 2026-11-04 · Source: multi-agent review 2026-11-04*

[DUMP-PROOFS-WAVE1](DUMP-PROOFS-WAVE1.md) is Done and the 22
`docs/tool-outputs/<tool>-<version>.md` notes are real, but the review
could not locate the per-tool `test_<name>_results.py` determinism
tests Step 13 requires ("every kept tool has note + tests + README
section"). Either they live under unexpected paths or they were never
written.

## Goal

Step 13 acceptance literally true: every kept tool has note + tests +
README section.

## Scope

- Inventory kept tools vs `test_<name>_results.py` files; list which
  exist and which are missing.
- Write the missing determinism tests (recorded native outputs,
  grammar/shape asserts) or scope out named tools explicitly.

## Acceptance

- Per kept tool: note + determinism test + README section, or an
  explicit scope-out with reason. Suite green.
