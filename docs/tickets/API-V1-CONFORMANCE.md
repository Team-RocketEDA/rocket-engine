# API-V1-CONFORMANCE: Prove v1 consumers/providers and installed workflows before deployment

*Status: Ready · Design: ADR-014 · Created: 2026-11-01*

Depends: API-V1-CORE, API-V1-EDITORS, TESTBENCH-COMPONENT, API-V1-TOOLS, API-V1-CLIENTS, CANVAS-CST. Design fixtures currently prove contract shape only, never provider/tool behavior.

Gate: types/help regenerate unchanged; every real serialized response/result/error/event validates canonical schema; all fixtures/unknown/null/empty/unsupported cases pass. Meet execution C01-C17 matrix, editor/testbench scoped scenarios, source save and working/pinned ref behavior, cross-transport one-runtime identity, atomic CAS/rollback, admission saturation and retry, shared coalescing, independent concurrency/gated workflows, cancel completion race, disconnect/restart survivors/no auto-run, ordered event cursor expiry/resync and complete I28 drift probes. Run installed representative digital/analog/photonic/mixed fixtures with native tools and known-good/known-bad mutations. Verify current migration passes both consumer and provider conformance against SAME artifact.

Check canonical canvas.toml file/migration/default templates/inline knobs/authored HDL isolation; generated downstream HDL and imported hard macro models correctly distinguished. Verify every package/tool marked ready really passes its qualified inputs and all required deployment profiles. No full readiness claim on Python import, process exit0, GDS existence, fixture-only wiring or schema-only checks. Preserve <=3000-line source-module boundary and current one-runtime policy. Document remaining blocked capabilities with precise remedy and scope.

## Verdict — conformance gate GREEN (CLIENTS wave, 2026-11-03)

`scripts/conformance_v1.py` exits 0: the canonical contract
gate plus all owned v1 suites pass against the working tree
(temporary package shim; no installs, no site-packages sync).

- `tests/test_v1_clients_runtime.py` (7),
  `tests/test_v1_tools_binding.py` (6), and
  `contracts/conformance/test_v1_conformance.py` (6) — 19
  passed, no skips, no xfails, no fake success data.
- Genuine installed-solver proof through the deferred
  runtime: `run_view_sync` over the committed MZI fixture
  judges FAIL with `finding_counts == {error: 5}`, and the
  clean pair judges PASS with its coverage statement.
  Readiness is evidence-backed throughout (ready means
  installed; blocked/unsupported means reason plus remedy).
- Carry V1C-1 (core/composition lane): `engine.findings()`
  resolves ledger run ids only, while deferred completions
  carry the runtime run id — the full finding list is not
  yet reachable through a deferred receipt.
- Out of scope, untouched: `contracts/conformance/deferred/`
  stays RED by design (it pins the missing v1-envelope
  boundary, a core-lane item); `tests/test_contract.py` (2
  failures) reports stale generated artifacts from sibling
  vocabulary/service deltas (annotate/attach_component/
  connect_endpoint) — regen belongs to the core lane.
- Owned-file docstring scan is clean; repo-wide
  pre-existing docstring violations were left alone.

## Follow-ups (recorded 2026-11-03, conformance stays green)

- V1C-1: deferred completions carry the runtime run id while
  `engine.findings()` resolves ledger ids only (`src/ops/deferred.py`
  mints the ledger ack inside the runner; the runtime tracks its
  own id). Deferred findings need an id alias map or a unified id.
- V1C-2: no public Engine runtime accessor; push bindings (HTTP
  /events, MCP subscribe_runtime, IPC EventStream) take
  `runtime=` explicitly instead of defaulting to the integrated
  runtime. A read-only `Engine.runtime` property closes it.
