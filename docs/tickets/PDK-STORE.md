# PDK-STORE: register/verify/list PDK against user tree

*Status: Backlog · Depends: STORAGE-REV, LAYOUT-SCHEMA, PATH-GUARD · Size: M · Roadmap: orch-build-mvp*

## Why

Every real-deck proof (DRC, extraction, sim) is blocked on one
capability: adopting the user's 12G open_pdks tree into a verified,
shared, content-addressed store. Copying per project would waste
disk; trusting unverified paths would break reproducibility. The
manifest (hashes, source, date) is what lets runs record *which*
PDK produced them — the ingredient I28 demands.

## What

- Engine ops: `register_pdk` (adopt local dir → copy + manifest +
  verify), `verify_pdk` (re-hash, fail loudly on drift),
  `list_pdks`; deck resolution by id + revision.
- MVP scope: local-dir adoption only; remote fetch is a later op
  on the same store.

## Acceptance

- RED-first: register user's sky130A green; re-register idempotent
  (verify, no duplicate); tampered deck file fails verify naming
  the file; unknown PDK id/rev raises (never silent substitute).
- Decks resolve to manifest-hashed paths for DRC/EXTRACT/SIM slices.
