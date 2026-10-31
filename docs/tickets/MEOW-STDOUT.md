# MEOW-STDOUT: Harden run_em envelope against solver chatter

*Status: Ready · Depends: none · Size: S ·
Roadmap: hardening (E2E-REREVIEW FIND-05, HIGH)*

## Why

run_em is red in the default env: a tidy3d stdout
warning breaks the adapter's strict whole-stdout
json.loads (meow/adapter.py:339-344), failing 4 repo
tests. Workaround verified (clean XDG_CONFIG_HOME →
4/4 pass) but the adapter must not trust solver
stdout — parse the envelope (marker-delimited), never
the stream.

## What

- RED-first: envelope parsing tolerant to stdout
  chatter (markers/framing); warning text preserved
  in logs, never fatal.
- The 4 meow live tests green in the DEFAULT env
  (no XDG workaround needed).

## Acceptance

- 4/4 meow live green default-env; chatter-injection
  regression test pinned.
- Contract + api_spec regen; full suite + gate green.
