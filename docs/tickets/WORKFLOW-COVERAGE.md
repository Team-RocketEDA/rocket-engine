# WORKFLOW-COVERAGE: stage tables as the tool coverage map

*Status: Ready · Depends: none · Size: S ·
Roadmap: planning data (MVP track)*

## Why

The workflow stage tables (D01-D30, A01-A23,
P01-P23, M01-M16) were written to answer "which
provisioned tools cover which steps" — librelane
alone knocks out ~90% of digital in one deck,
other steps need other tools. But the tables do
not say that: entrypoints name ops, decks are not
linked, and uncovered steps are invisible. The
tables must become the coverage map they were
meant to be, so fuel plans ("what can run now?"),
the UI renders progress honestly, and gaps ("no
deck covers M14-thermal") are named, not felt.

## What

- Every stage gains its covering deck(s) via the
  v1 catalog mechanism: task `io` ports +
  `presentation` kinds + `delivery` in
  `contracts/v1/catalog/tasks.json` joined with live
  setup probes — op + deck.tool + provision
  requirement, or an explicit `uncovered` marker
  with the reason (no tool / not provisioned /
  bespoke-script
  escape hatch).
- `plan_from_capabilities` answers per-step
  ready/blocked from live setup state; the
  completion report cites covering decks per
  blocker.
- Bespoke python decks stay the documented escape
  hatch for weird requirements — the map points
  at them, never hides behind them.
- Contract + api_spec regen if surfaces change;
  full suite + gate green.

## Acceptance

- Digital lane renders: which steps librelane
  covers, which need lint/synth/formal/sta, which
  are uncovered — all from the tables + live
  probes (test pins).
- No stage is silently uncoverable: every entry
  resolves to a deck, a probe-gated deck, or a
  named gap.
