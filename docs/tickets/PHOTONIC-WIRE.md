# PHOTONIC-WIRE: Wire proven photonic solvers to engine ops

*Status: Done · Depends: none · Size: M ·
Roadmap: to-GDS lane (MVP track, serves P06/P09)*

## Why

Circulax and Meow are proven in tests but unreachable:
`run_optical` only accepts deck.tool `sax`, and `run_em`
has no adapter at all — so P06 (device mode/field
solving) and P09 (dynamic/active circuit behavior) have
no button despite GREEN proofs. Wiring proven solvers
is pure seam work, no new science, and it turns two
dark PRD stages green.

## What

- RED-first: `circulax` as a second deck.tool behind
  `run_optical` (time-domain transient/DC/AC per the
  Circulax proof); `run_em` ToolAdapter via `meow`
  (EME mode/field solving with convergence evidence).
- FDTD/FEM (Palace/Meep sidecars) stay proposed per the
  PRD solvers table — this ticket wires what's proven,
  not what's hoped.
- Existing proofs become op-level fixtures: same
  MZI/coupler cases, now dispatched as engine runs with
  run_ids and ledger evidence.

## Acceptance

- P06 + P09 dispatchable as engine ops with structured
  results; sax path untouched and green.
- Contract + api_spec regen; full suite + gate green.

*Audit 2026-11-02 (T-26): flipped to Done on landing-commit + code evidence per RULING-06 (was Ready/Backlog in-file, Done on board).*

*RULING-03 (T-22): meow ON-TRACK — MVP-track wiring stands; dump-first proofs proceed under ADAPT-GROUPC. simulate.em task binding stays post_mvp per RULING-02 until ruled otherwise (proofs are not bindings).*
