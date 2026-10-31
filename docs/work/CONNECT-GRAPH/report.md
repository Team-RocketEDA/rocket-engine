# CONNECT-GRAPH lane report — shared connectivity extraction + raw-IR emitters

Outcome: implemented and green. New modules extract one shared
connectivity graph (`prepare_netlist_structs`), resolve one raw IR,
and print SPICE/Verilog/VHDL from it with identical net identity;
`Connectivity.net_name` is the single naming authority read by all
printers plus ERC. Wiring into existing files is delivered below as
an exact patch the integrator applies and verifies.

## Files added (new files only; no existing file touched)

| File | Contents |
|---|---|
| `src/workflows/connectgraph.py` | Extraction: spatial-hash coalescing, label propagation, stable `netN`/`X<n>` naming, `lvs_ignore`, explicit-run cache, `net_name()` authority, `erc_findings` |
| `src/workflows/connectgraph_emit.py` | Raw IR (`to_raw_ir`), 4-level `resolve_format`, `emit_spice`/`emit_verilog`/`emit_vhdl` + `emit_netlists`, one bus-expansion and one line-joinery helper |
| `src/adapters/connectivity/__init__.py` | Pure-Python `ConnectivityAdapter` (ToolAdapter) serving `run_connectivity` + `run_erc` with deck tool `connectgraph` |
| `tests/workflows/test_connect_graph_extract.py` | 12 extraction tests |
| `tests/workflows/test_connect_graph_emit.py` | 11 emitter tests incl. 3 goldens + cross-language identity |
| `tests/workflows/test_connect_graph_adapter.py` | 8 adapter tests |
| `tests/workflows/test_connect_graph_wired.py` | 4 integration tests — run AFTER the wiring patch (see below) |
| `tests/workflows/fixtures/connect_graph_demo.json` | Shared demo schematic (single source for goldens + identity) |
| `tests/workflows/fixtures/connect_graph_demo.{spice,verilog,vhdl}.golden` | Byte-exact golden netlists |
| `docs/work/CONNECT-GRAPH/report.md` | This report |

## Contract decisions (locked by the tests above)

- Schematic record: `{cell?, wires, pins, labels, instances, symbols,
  ports?}` with integer `[x, y]` points (module docstring documents
  every field). Two wires connect when an endpoint of one lies on the
  other (shared endpoints + T-junctions); crossing interiors do not.
- Names: labels propagate (sorted-first wins on conflict, recorded as
  a `connectivity.short`); unlabeled nets are `net1..netN` in net
  order skipping label names; unnamed instances take the smallest
  free `X<n>`; generics resolve as symbol-defaults overridden by
  instance values.
- `lvs_ignore` (instance `attrs`): pins leave the graph, the instance
  leaves the netlist; recorded on `NetlistStructs.ignored`.
- Unknown symbol / duplicate instance / dangling pin / dangling port /
  bad port direction raise `ConnectGraphError` (loud). A *known*
  symbol with no template at any format level skips silently (recorded
  on raw IR `skipped`); a present-but-broken template raises loudly.
- Format chain per language: instance `custom` -> symbol `custom` ->
  instance `format` -> symbol `format`. Custom lines emit verbatim;
  format lines run the language post-pass (SPICE `+` wrap over 80
  cols). Templates: `{name} {symbol} {cell} {pins[PIN]} {pin_nets}
  {generics[KEY]}`.
- ERC rules (`connectivity.short/unconnected_pin/dangling_net/
  orphan_label`) are shared; policy differs: run_connectivity fails
  only on shorts, run_erc also fails on unconnected pins. Both read
  names through `net_name()` — asserted by test.
- Net names pass through verbatim in all three languages (no escaping;
  follow-up if PDK flows need it). Bus bits `base[i]` fold into one
  vector declaration in Verilog/VHDL and stay flat in SPICE.
- Cache: `run_key=None` never caches; a reused key serves the cached
  object only when the schematic digest matches, else rebuilds.
- No vocabulary change: `run_connectivity`/`run_erc` are already
  cataloged. Netlist export rides the verdict `measurements.netlists`.

## RED -> GREEN evidence

Shard note: `.venv` holds a stale non-editable `rocket_engine`
snapshot, so all runs map `rocket_engine -> src` via
`PYTHONPATH=/tmp/cgshim` (`/tmp/cgshim/rocket_engine` symlinks
`src`). The integrator reinstalls (see below); until then every
command below needs that prefix.

RED (35 failed — modules absent, ops unwired):

    PYTHONPATH=/tmp/cgshim .venv/bin/python -m pytest \
      tests/workflows/test_connect_graph_extract.py \
      tests/workflows/test_connect_graph_emit.py \
      tests/workflows/test_connect_graph_adapter.py \
      tests/workflows/test_connect_graph_wired.py -q
    # 35 failed in 0.20s
    # extract/emit/adapter: ImportError: cannot import name
    #   'connectgraph' from 'rocket_engine.workflows'
    # wired: KeyError: 'run_connectivity'

GREEN (standalone deliverable + neighbors, 38 passed):

    PYTHONPATH=/tmp/cgshim .venv/bin/python -m pytest \
      tests/workflows/test_connect_graph_extract.py \
      tests/workflows/test_connect_graph_emit.py \
      tests/workflows/test_connect_graph_adapter.py \
      tests/test_docstrings.py tests/workflows/test_process_data.py -q
    # 31 passed (new) + 7 passed (neighbors) = 38 passed
    .venv/bin/python scripts/check_docstrings.py \
      src/workflows/connectgraph.py src/workflows/connectgraph_emit.py \
      src/adapters/connectivity/__init__.py
    # clean (no output)

Goldens were generated from reviewed output (inspected for correct
pin nets, headers, and identical net identity across languages) and
are pinned byte-exact, trailing newline included.

Wired rehearsal (pristine `git archive HEAD` tree in /tmp + new files
+ patch below + `api_spec.py --write` + `contract.py --write`):
`tests/workflows tests/test_api_spec.py tests/test_contract.py
tests/test_check_contract.py tests/test_docstrings.py
tests/test_engine_run.py` -> **82 passed, 3 skipped** (skips are
pre-existing tool-absence skips). The 4 `test_connect_graph_wired`
tests pass only in this patched tree and fail on the shared tree
until the integrator applies the patch.

## Integrator steps

1. Apply the patch below with `patch -p1` (verified fuzz-free on
   `20239f3`; the three files are byte-identical through HEAD
   `9d78ce2` — intervening commits are docs-only).
2. Regenerate: `.venv/bin/python scripts/api_spec.py --write` and
   `.venv/bin/python scripts/contract.py --write`.
3. Reinstall so the venv stops serving the stale snapshot (I never
   touched `.venv`: `uv sync` or equivalent is yours).
4. Run: `PYTHONPATH`-free `.venv/bin/python -m pytest
   tests/workflows/test_connect_graph_wired.py
   tests/workflows/test_connect_graph_extract.py
   tests/workflows/test_connect_graph_emit.py
   tests/workflows/test_connect_graph_adapter.py
   tests/test_api_spec.py tests/test_contract.py tests/test_docstrings.py
   -q` (expect all pass), then the full gate per the ticket.

## Wiring patch (exact; 3 existing files)

```diff
diff --git a/src/composition.py b/src/composition.py
--- a/src/composition.py
+++ b/src/composition.py
@@ -23,7 +23,8 @@
 maps to named solvers; `deck.tool` selects one, defaulting to the
 first registered (run_drc: magic, then klayout; run_optical: sax;
 run_extraction: magic; run_lvs: netgen; run_spice: ngspice;
-run_syntax: slang; run_hdl_test: icarus).
+run_syntax: slang; run_hdl_test: icarus; run_connectivity:
+connectgraph; run_erc: connectgraph).
 Unregistered operations and unknown deck tools raise instead of
 faking a verdict.
 """
@@ -33,6 +34,7 @@

 from ruamel.yaml import YAML

+from .adapters.connectivity import ConnectivityAdapter
 from .adapters.drc import MagicDrcAdapter
 from .adapters.drc_kl import KlayoutDrcAdapter
 from .adapters.errors import AdapterError
@@ -160,6 +162,8 @@
             "run_lvs": {"netgen": NetgenLvsAdapter()},
             "run_spice": {"ngspice": NgspiceAdapter()},
             "run_syntax": {"slang": SyntaxAdapter()},
+            "run_connectivity": {"connectgraph": ConnectivityAdapter()},
+            "run_erc": {"connectgraph": ConnectivityAdapter()},
         }
         self._yaml = YAML(typ="safe")
         self._constraints = dict(constraints) if constraints is not None else None
diff --git a/src/workflows/__init__.py b/src/workflows/__init__.py
--- a/src/workflows/__init__.py
+++ b/src/workflows/__init__.py
@@ -1,5 +1,48 @@
 """D/A/P/M step order and check plans as data. Never calls solvers directly."""

+from .connectgraph import (
+    RULE_DANGLING_NET,
+    RULE_ORPHAN_LABEL,
+    RULE_SHORT,
+    RULE_UNCONNECTED_PIN,
+    Connectivity,
+    ConnectGraphError,
+    Net,
+    NetlistStructs,
+    ResolvedInstance,
+    erc_findings,
+    prepare_netlist_structs,
+)
+from .connectgraph_emit import (
+    LANGUAGES,
+    emit_netlists,
+    emit_spice,
+    emit_verilog,
+    emit_vhdl,
+    resolve_format,
+    to_raw_ir,
+)
 from .stages import STAGES, applicable_stages

-__all__ = ["STAGES", "applicable_stages"]
+__all__ = [
+    "STAGES",
+    "applicable_stages",
+    "Connectivity",
+    "ConnectGraphError",
+    "Net",
+    "NetlistStructs",
+    "ResolvedInstance",
+    "erc_findings",
+    "prepare_netlist_structs",
+    "RULE_SHORT",
+    "RULE_UNCONNECTED_PIN",
+    "RULE_DANGLING_NET",
+    "RULE_ORPHAN_LABEL",
+    "LANGUAGES",
+    "emit_netlists",
+    "emit_spice",
+    "emit_verilog",
+    "emit_vhdl",
+    "resolve_format",
+    "to_raw_ir",
+]
diff --git a/src/interfaces/setup.py b/src/interfaces/setup.py
--- a/src/interfaces/setup.py
+++ b/src/interfaces/setup.py
@@ -48,7 +48,8 @@
 # `shutil.which`s (or `_resolve`s), the banner probe for netgen
 # (`adapters.lvs_netgen.resolve_netgen`), the import probe for sax.
 # A registered solver with no row fails loudly (unknown_solver),
-# so a new solver cannot slip into the menu undetected.
+# so a new solver cannot slip into the menu undetected. Pure-Python
+# solvers take an empty spec: always available, nothing to detect.
 SOLVER_DEPS = {
     ("run_drc", "magic"): {"binaries": ["magic"]},
     ("run_drc", "klayout"): {"binaries": ["klayout"]},
@@ -58,6 +59,8 @@
     ("run_lvs", "netgen"): {"binaries": ["netgen"], "banner": "lvs"},
     ("run_spice", "ngspice"): {"binaries": ["ngspice"]},
     ("run_syntax", "slang"): {"binaries": ["slang"]},
+    ("run_connectivity", "connectgraph"): {},
+    ("run_erc", "connectgraph"): {},
 }
```

Notes: the `setup.py` hunk is required — without a SOLVER_DEPS row,
`get_capabilities` raises `unknown_solver` (found by rehearsal). The
empty spec marks the in-process solver always available. No
`setup_catalogue.yaml` entry: nothing is provisionable. No
`server.py`/vocabulary/contract-source edits: both operations are
already cataloged; generated docs come from step 2.

## Refused / not done (with reasons)

- No existing file edited (ownership rule): composition/setup/
  `__init__` wiring ships as the patch above; `api_spec`/`contract`
  regens and reinstall are integrator steps.
- Never ran the full suite (shared-tree rule): ran only the new tests
  plus named neighbors (`test_docstrings`, `test_process_data`) on the
  shared tree; the wider rehearsal ran in a private /tmp copy.
- Never touched `tests/pdk_*/`, `docs/pdk/*/`, `.venv`, `uv sync`,
  or git state (no commit, no push); /tmp scratch only.
- Net-name escaping per language left verbatim (documented above);
  multi-cell hierarchy left out (single-cell extraction is the ticket
  scope).
