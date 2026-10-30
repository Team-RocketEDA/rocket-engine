# API-GEN: Docstring-mandated generated API contract

*Status: Done · Size: M · Roadmap: management-plane*

## Why

Three consumers (UIUX frontend, rocket-fuel via MCP help,
generated client types) need one API shape, and today it lives
twice — prose in `docs/engine-api.md`, names in
`vocabulary.py` — with nothing forcing agreement. A third
handwritten copy guarantees drift within a month. ADR-003
makes docstrings the contract source: one text feeds human
docs, machine schemas, and agent help, so drift becomes
structurally impossible. Zero Google-style docstrings exist
today, so this is a genuine migration with a mechanical,
reviewable per-endpoint shape.

## What

- RED-first where code: `AGENTS.md` mandate (Google-style:
  summary, Args, Returns, Raises, `Caution:`) for every
  adapter operation/query handler.
- Guard script in the gate: missing/malformed endpoint
  docstrings fail loudly (same posture as the no-cloud guard).
- Generator deriving from code: human API reference, JSON
  Schema per operation, MCP tool descriptions + help text.
- Migrate `docs/engine-api.md` prose into docstrings per
  endpoint; the file becomes generated output + pointer, never
  hand-edited again.

## Acceptance

- Guard green on the full tree; generated reference covers
  every wired op/query; MCP help serves the same text as the
  docs for a sampled endpoint; a deliberately broken
  docstring fails the gate with the endpoint named.
- Full suite + gate + scenarios green.

## Field notes — slice A (2026-10-30, Doing, NOT closed)

- RED `08b37cc`: `tests/test_docstrings.py` (no-cloud pattern:
  enforced tree scans clean, bad fixture fails naming the
  endpoint, good fixture passes).
- GREEN `f3672dd`: `scripts/check_docstrings.py` with an
  `ENFORCED` manifest (composition, dispatch, mcp/ipc/http
  transports, cli) + Google-style migration of those 7 files.
  `.venv` mirror verified with `diff -rq` (only `__pycache__`
  differs). Gates: test_docstrings + test_no_cloud +
  tests/execution + test_mcp_server + test_transports +
  test_cli → 99 passed, 21 live-skipped.
- Docs: `AGENTS.md` mandate (summary/Args/Returns/Raises +
  `Caution:` where it bites) citing ADR-003, F12/I32 BYOC, ADR-002.
- Remainder for slice B: solver-adapter migration, manifest
  widening, generator (reference + JSON Schema + MCP help),
  `docs/engine-api.md` becomes generated output.

## Field notes — slice B (2026-10-30, Done, closes ticket)

- RED `c2aaa07`: `tests/test_api_spec.py` (reference covers every
  wired op/query via a behavioral Engine.submit probe oracle,
  schemas per wired op, help text == reference section, help
  summaries == live handler docstrings, MCP descriptions == help
  summaries, freshness pins for all three generated files) plus a
  full-tree manifest-coverage test in `tests/test_docstrings.py`.
- GREEN `c1b0aaf`: guard manifest widened to the full `src` tree
  (274 violations → 0 across 33 files); every adapter
  preflight/execute/parse plus transports, execution, interfaces,
  library, mutate, and workflows now carry Google-style
  docstrings. Adapter class docstrings carry the migrated §1
  endpoint prose plus machine-readable `Job keys:` sections.
- Generator `scripts/api_spec.py` (stdlib-only AST, no imports):
  `docs/engine-api.md` (reference tables + per-endpoint sections +
  generator-owned appendix), `docs/api-schema.json` (schema per
  op/query, required-ness from signatures and `(required)`
  markers, `expected_revision` injected from
  `ProjectService.submit`'s own arg text), `docs/api-help.json`
  (identical to the reference section bodies — the double-use).
  `--check` is the freshness gate (default).
- Seams: `composition.QUERY_METHODS` (query → method map),
  `Engine.solvers_for` (introspection for docs/MCP),
  `Engine._run_queued` `Request keys:` (run_job contract).
  `server.describe_tool` reads serving handler docstrings at
  runtime; unwired names honestly say so (same template both
  sides, equality-pinned).
- `.venv` mirror verified with `diff -rq` (only `__pycache__`
  differs). Gates: new tests + docstring guard + mcp neighbors
  (test_mcp_server, test_mcp_live, test_transports) + no-cloud →
  34 passed. Full suite: 808 passed, 33 skipped (live-skips).
- Verify: guard green on full tree; deliberate breakage
  (`SaxAdapter.preflight` Args removed) failed naming the
  endpoint, then reverted clean.
- Residuals (non-blocking): §1 prose controls (`cancel_run`,
  `approve_console`, `submit_revision`) are not in vocabulary and
  have no handler — footnoted as out-of-contract in the appendix
  (follow-up unowned; not in API-GENERALIZE scope). `deck`
  subschemas stay prose (top-level `deck` key only). Cursor
  optionality for `get_events_since` rides a one-line
  `_QUERY_DEFAULTS` citing `Engine._query_events_since`.
  `MagicDrcAdapter` documents `cell` required though preflight
  does not check it (missing check = hardening item, behavior
  untouched). `server.py` reads `Engine._run_queued.__doc__`
  (same-package help introspection, never called).
