# NOTEBOOK-SURFACE: Notebooks as editing surface (OFF MVP TRACK)

*Status: Backlog · Depends: WORKERS · Size: L · Roadmap: orch-build-mvp*

## Why

Beyond a terminal, notebooks are a *document* surface: prose +
executable cells + inline plots + widgets — a design lab notebook
that fits the gdsfactory ecosystem's grain (training, cspdk
examples, KLive all live there). Bigger win than the REPL, bigger
bill (server machinery, format decisions, auth implications), so
it waits behind the minimal console. Tracked here so the idea
survives with its design notes attached.

## What (when scheduled)

- Jupyter machinery RocketIDE-side; engine owns kernel lifecycle
  via console ops (open/execute/reset ≈ kernel manager).
- Format decision: `.ipynb` as native artifact indexed by YAML
  (recommended) vs YAML transcript; kernel tier-split proposal
  (shared analysis kernel + fresh effectful workers) vs
  strict restart-per-cell — needs PRD call (I23).

## Acceptance

- Reference notebook runs end-to-end against the engine;
  restart-per-cell (or approved tier-split) proven by tests;
  format decision recorded in ADR.
