# CLOUD-AUTH: Secure field for opt-in cloud account data

*Status: Backlog · Depends: none · Size: S · Roadmap: orch-build-mvp*

## Why

The contract says accounts and auth are opt-in only, never
default. That rule needs a home: today there is nowhere to put a
GDSFactory+ key or a Tidy3D token even if a user wants cloud
features. Without a designed store, keys end up in project files,
shell history, or logs — the exact leak the opt-in rule exists
to prevent. Parked because no selected solver needs cloud; this
unlocks only if a future flow justifies it.

## What (when scheduled)

- A secure credential field/store for cloud account data: OS
  keyring preferred, encrypted file fallback. Never in project
  files, never in logs, never in run records.
- Cloud use requires explicit per-run opt-in plus the standard
  approval binding; the no-cloud-import guard gains an audited
  allowlist for exactly the opt-in call sites, nothing else.
- UI contract: the frontend collects the key into the store
  (it never sees engine internals); readiness reports
  `cloud: opted_in/opted_out` per solver.

## Acceptance

- Keys survive outside the project tree and never appear in any
  engine output, log, or artifact.
- A cloud call without explicit opt-in is refused loudly, naming
  the missing opt-in.
- `scripts/check_no_cloud.py` passes with the allowlist covering
  only the reviewed opt-in sites.
