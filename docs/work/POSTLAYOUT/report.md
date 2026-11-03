# POSTLAYOUT lane report

Base: `272c9cf` (`GREEN-the-tests`). Ownership kept: only new files
created, no tracked file touched (`git status` shows `??` entries only
— this lane plus peers'). The wiring patch was built on scratch copies
under `/tmp` (never in the tree) and verified with `git apply --check
-p1` at this HEAD.

## Outcome

`run_post_layout` is implemented as one new ToolAdapter bound to live
ngspice on extracted netlists, with enforced provenance and a pre/post
delta table against the schematic run. All ticket scope items land as
new files with passing tests, plus an exact, machine-verified wiring
patch:

- One call replays an analog block post-layout: extracted netlist +
  testbench + PDK models through ngspice batch, returning
  measurements, waveforms, provenance, and the pre/post comparison.
- Provenance enforced: a missing extraction record refuses with
  `invalid_command`; bytes that no longer match the record's sha256,
  or a record naming another netlist, refuse with
  `invalid_reference` — before any sim (proven: the runner sees
  nothing). No silent schematic-as-extracted substitution, ever
  (`sources` is refused outright; only `extracted_netlist` sims).
- Pre/post delta vs the schematic run referenced by
  `schematic_run_id` (`run_id` accepted as an alias): pre values
  arrive explicitly (`schematic_measurements`) or through the `runs`
  resolver; unknown runs and schematic gaps refuse loudly. Deltas
  never gate the verdict — bounds do.
- Bandgap + sigma-delta fixtures: post-layout deltas green AND
  nonzero-proven (each live test asserts `delta != 0.0` on its lossy
  extraction; a zero delta fails the test, not the design).

## Files added

- `src/adapters/postlayout/adapter.py` — `PostLayoutAdapter`
  (`OPERATION = "run_post_layout"`, tool `ngspice`) plus
  `build_provenance` (extraction-side record builder),
  `build_deck`, and `delta_table`. Self-contained: reuses only
  public cross-module APIs (`ToolAdapter`, `AdapterError`,
  `tool_roots`, `resolve_deck`). Gate-clean per
  `scripts/check_docstrings.py`, 100-col clean.
- `src/adapters/postlayout/__init__.py` — package re-export (the
  integrator import path).
- `src/adapters/postlayout/README.md` — protocol notes.
- `tests/adapters/test_postlayout.py` (40) — RED-first lane tests,
  all passing (36 unit/canned + 4 live).
- `tests/adapters/fixtures/postlayout/rc_schem.spice`,
  `rc_extracted.spice` — committed model-free pair (5 Ω drawn-vs-
  extracted loss, ~500 µV delta).
- `docs/work/POSTLAYOUT/report.md` (this file).
- `docs/work/POSTLAYOUT/wiring.patch` — same bytes as the inline
  patch below; apply with `git apply -p1` from the repo root.

No committed bandgap/sd_top extracted fixtures: both derive at test
time as staged copies of the vendored trees (never touched in place)
plus one documented parasitic line each (10 MΩ leakage on bandgap
`VREF`; 50 MΩ on sd_top `UA1`), mirroring the sd_top X99-clamp
precedent. Fixture provenance records are synthesized by
`build_provenance` over the staged bytes (extraction runs are not
re-executed; enforcement is on the record).

Forbidden areas untouched: no `tests/pdk_*/` or `docs/pdk/*/`
reads-or-writes beyond listing, no tracked-file edits, no commit.

## Design notes (per scope item)

- **Live ngspice, ngspice protocol.** Deck staging, `.spiceinit`,
  `meas_*` parsing, `sim_fail` synthesis, PDK-via-store
  resolution, and verdicts-from-output mirror the run_spice
  adapter; `.control` adds one `wrdata` line when `waveforms` are
  requested (format verified against live ngspice-42 output:
  no-header, scale-first columns).
- **Generalization law.** Every netlist, testbench, model pin,
  analysis, and waveform expr arrives via the job — the adapter
  hardcodes nothing per design. The RC/bandgap/sd_top cases are
  test fixtures proving the project-input path, not baked-ins.
- **Provenance shape.** `{extraction_run_id, netlist_sha256, cell?,
  tech?, spice_file?, device_count?}`. Freshness = record sha256
  vs current file bytes; `spice_file`, when present, must name the
  same basename (staged copies keep it).
- **Schematic side.** `schematic_run_id` required; explicit
  `schematic_measurements` win over the `runs` resolver; every
  POST measurement name must have a pre value. `rel` is
  `delta/pre`, `None` when `pre == 0` (no div-zero, ever).
- **Verdict routing.** Measurements nest into findings/verdict
  exactly like run_spice. The wiring patch propagates the small,
  reviewable `comparison` + `provenance` onto the verdict; raw
  waveform samples stay adapter-level (available from `parse` and
  the workdir `.dat`) so the ledger — which stores full verdicts —
  never carries bulk vectors.
- **Live-model strategy.** PDK live tests register a minimal
  real-model store (the 3.3 MB `libs.tech/combined/` tree,
  hash-pinned through the real store path) under `tmp_path` — no
  12 GB copy, no default-store writes. Absent ngspice / PDK source
  / fixtures skip loudly, never fake-green.

## Wiring patch (what the integrator applies)

Same bytes as `wiring.patch`. Covers 2 files; `git apply --check
-p1` clean at `272c9cf`:

- `src/composition.py`: import + register `PostLayoutAdapter`
  under `run_post_layout` (tool `ngspice`); propagate
  `comparison` + `provenance` onto the verdict beside
  `measurements`; docstring solver-map line updated.
- `src/interfaces/setup.py`: `("run_post_layout", "ngspice")`
  detection row (without it `get_capabilities` raises
  `unknown_solver`).

Deliberately NOT patched: `vocabulary.py` (`run_post_layout`
already cataloged), `api_spec.py`/`contract.py` (generators read
the `_solvers` map dynamically — the new `Job keys:` flow into
schemas on regen), MCP server (routes through `engine.submit`;
help text refreshes on regen), dispatch/pool/replay (generic
over registered solvers).

```diff
--- rocket-engine.orig/src/composition.py
+++ rocket-engine/src/composition.py
@@ -27,8 +27,8 @@
 maps to named solvers; `deck.tool` selects one, defaulting to the
 first registered (run_drc: magic, then klayout; run_optical: sax;
 run_extraction: magic; run_lvs: netgen; run_spice: ngspice;
-run_syntax: slang; run_hdl_test: icarus; run_connectivity:
-connectgraph; run_erc: connectgraph).
+run_post_layout: ngspice; run_syntax: slang; run_hdl_test: icarus;
+run_connectivity: connectgraph; run_erc: connectgraph).
 Unregistered operations and unknown deck tools raise instead of
 faking a verdict.
 """
@@ -46,6 +46,7 @@
 from .adapters.hdl_sim import HdlSimAdapter
 from .adapters.lvs_netgen import NetgenLvsAdapter
 from .adapters.ngspice import NgspiceAdapter
+from .adapters.postlayout import PostLayoutAdapter
 from .adapters.sax import SaxAdapter
 from .adapters.syntax import SyntaxAdapter
 from .execution.apig_pool import (
@@ -267,6 +268,7 @@
             "run_extraction": {"magic": MagicExtractAdapter()},
             "run_lvs": {"netgen": NetgenLvsAdapter()},
             "run_spice": {"ngspice": NgspiceAdapter()},
+            "run_post_layout": {"ngspice": PostLayoutAdapter()},
             "run_syntax": {"slang": SyntaxAdapter()},
             "run_connectivity": {"connectgraph": ConnectivityAdapter()},
             "run_erc": {"connectgraph": ConnectivityAdapter()},
@@ -2375,6 +2377,16 @@
         if result.get("measurements") is not None:
             verdict = dict(verdict, measurements=result["measurements"])
             self._execution.mark_completed(run_id, verdict)
+        # Post-layout evidence rides the same way: the pre/post delta
+        # table plus the extraction/schematic provenance are small and
+        # reviewable (raw waveform samples stay adapter-level so the
+        # ledger never carries bulk vectors).
+        if result.get("comparison") is not None:
+            verdict = dict(verdict, comparison=result["comparison"])
+            self._execution.mark_completed(run_id, verdict)
+        if result.get("provenance") is not None:
+            verdict = dict(verdict, provenance=result["provenance"])
+            self._execution.mark_completed(run_id, verdict)
         if scope_record is not None:
             verdict = stamp_verdict(verdict, scope_record["provenance"])
             self._execution.mark_completed(run_id, verdict)
--- rocket-engine.orig/src/interfaces/setup.py
+++ rocket-engine/src/interfaces/setup.py
@@ -58,6 +58,7 @@
     ("run_extraction", "magic"): {"binaries": ["magic"]},
     ("run_lvs", "netgen"): {"binaries": ["netgen"], "banner": "lvs"},
     ("run_spice", "ngspice"): {"binaries": ["ngspice"]},
+    ("run_post_layout", "ngspice"): {"binaries": ["ngspice"]},
     ("run_syntax", "slang"): {"binaries": ["slang"]},
     ("run_connectivity", "connectgraph"): {},
     ("run_erc", "connectgraph"): {},
```

## Integrator steps

From the repo root (`rocket-engine/`), with
`PATH=$HOME/tools/oss-cad-suite/bin:$HOME/tools/bin:$PATH`:

1. Apply: `git apply -p1 docs/work/POSTLAYOUT/wiring.patch`
   (re-check first with `git apply --check -p1` if HEAD moved;
   the patch anchors on stable import/map/verdict lines).
2. Refresh the sealed install (new `src` files are invisible
   until then): `export UV_CACHE_DIR=/tmp/uv-cache
   UV_LINK_MODE=copy` first (the default uv cache is read-only
   in sandboxes), then `scripts/install.sh --install`. The PDK
   step may fail where `ROCKETEDA_HOME` is unwritable — that is
   pre-existing and orthogonal; the venv + sealed copy land
   before it.
3. Regen the contract: `python scripts/contract.py --write`
   then `python scripts/api_spec.py --write`. No hand-edits to
   `docs/contract.json`, `docs/engine-api.md`,
   `docs/api-schema.json`, or `docs/api-help.json` — the new
   `Job keys:` flow in automatically.
4. Verify: full suite
   `.venv/bin/python -m pytest tests -q`
   plus gates
   `.venv/bin/python scripts/check_docstrings.py` and
   `.venv/bin/python scripts/check_no_cloud.py`.
5. Post-integration proof (one engine call, delta table on the
   verdict): register nothing by hand — submit `run_post_layout`
   with `deck.tool ngspice` through `Engine.run`/`submit` and
   assert `verdict["comparison"]` carries the pre/post/delta
   rows and `verdict["provenance"]` the extraction +
   schematic run ids. The lane's
   `test_postlayout_dispatches_as_engine_run` covers dispatch
   pre-wiring; post-wiring it can assert the two new verdict
   keys (left for the integrator since it edits a lane test,
   not the engine).

## Verification observed (this lane)

- RED: `tests/adapters/test_postlayout.py` failed on
  `FileNotFoundError: .../src/adapters/postlayout/adapter.py`
  before the adapter existed.
- GREEN: 40/40 lane tests pass (36 unit/canned incl. engine
  dispatch, plus 4 live: RC divider delta, RC tran waveforms,
  bandgap lossy delta, sd_top lossy delta — all green with
  `delta != 0.0`).
- Gates: `check_docstrings.py` (full tree) and
  `check_no_cloud.py` exit 0; new files 100-col clean.
- Neighbors + freshness: `test_api_spec`,
  `test_docstrings`, `test_contract`, `test_check_contract`,
  `test_no_cloud`, `test_ngspice`, `test_extract_sky130`
  — 89 passed, 12 skipped, 0 failed.
- Full suite: not all-green tree-wide, for reasons outside
  this lane — parallel peer lanes are mid-flight (their RED
  tests fail by design, e.g. `test_view_sync_*`), one
  collection module needs the uninstalled `klayout` pip
  package (`tests/pdk_ihp/test_drc.py`, pre-existing), and a
  peer's `install.sh` run mid-session briefly left `.venv`
  without the sealed copy (rebuilt via the sanctioned path;
  PDK-register fails on the sandbox read-only fs as before).
  Zero failures name `postlayout`; `git diff` is empty
  (no tracked file touched).

## Follow-ups (not this lane)

- Auto-build `extraction_provenance` from a `run_extraction`
  completion (record exists as a job input today; the link
  is the `extraction_run_id` string).
- Strict `run_id`-only schematic reference (the
  `schematic_run_id` primary + `run_id` alias stays until a
  caller standardizes).
- Verdict-level waveform summaries if the frontend needs
  sparkline data without calling `parse`.
