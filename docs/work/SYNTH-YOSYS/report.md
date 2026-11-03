# SYNTH-YOSYS lane report — run_synth via oss-cad-suite Yosys

Ticket: `docs/tickets/SYNTH-YOSYS.md` · Branch: GREEN-the-tests ·
No commits, no pushes (integrator commits).

## Files added (new files only — zero edits to existing files)

- `src/adapters/synth_yosys/__init__.py` — `YosysSynthAdapter`
  behind the `ToolAdapter` port: operation `run_synth`, deck.tool
  `yosys`. Preflight refuses the wrong operation, bad tops, bad
  timeouts/defines, missing sources/liberty, and unresolvable or
  unassertable tools; execute synthesizes with `synth -top` (plus
  `dfflibmap`/`abc -liberty` mapping when a liberty is given) under
  a timeout; parse normalizes `ERROR:`/`Warning:` lines plus the
  stat report into findings, cell counts, the mapped area, and the
  netlist artifact path.
- `src/adapters/synth_yosys/README.md` — adapter contract note.
- `tests/adapters/test_synth_yosys.py` — 27 tests: port,
  capabilities, preflight refusals, pure parse units, counter
  generic + mapped, direct-yosys oracle, latch/undriven findings,
  loud failures, SERV + picorv32 generic + mapped, SERV mutation.
- `tests/adapters/fixtures/synth/counter.v`,
  `latch_undriven.v`, `broken.v` — committed micro-fixtures.
- `docs/work/SYNTH-YOSYS/wiring.patch` — the integrator patch as a
  file (byte-identical to the embedded diff below).
- `docs/work/SYNTH-YOSYS/report.md` — this file.

## Contract implemented (ticket clause → behavior)

- RED-first `run_synth` ToolAdapter driving pinned `yosys`
  (`synth -top`, sky130 cell mapping where the PDK permits) —
  `YosysSynthAdapter` writes a script (`read_verilog` the sources,
  `hierarchy -check -top`, `synth -top`, then `stat` plus
  `write_verilog`) and runs it under the job timeout. With a
  `liberty` input it appends `dfflibmap -liberty` + `abc -liberty`
  + `clean` and stats with `stat -liberty`; without it, generic
  `$_`-cell synth. Evidence = mapped netlist artifact (`netlist`
  path, always written to the workdir), per-family `cells` counts,
  `cell_count`/`wire_count`, the `area` estimate when mapped, and
  warnings as findings (`latch`, `undriven`, `synth_warning`).
- deck.tool `yosys`; missing binary → loud `missing_dependency`
  naming the PROV bundle, never a PATH lottery — every resolution
  failure message names the pinned oss-cad-suite bundle and
  `docs/provision-plan.md`, and the resolved binary must answer
  `yosys -V` with a parseable `Yosys major.minor` banner
  (version-asserted, recorded as `yosys_version` evidence).
- SERV + picorv32 fixtures: synth proves clean with expected cell
  families; mutated RTL (undriven/latch) surfaces as findings —
  SERV stages `rtl/*.v` from the shared `serv_sources.txt`
  manifest (top `serv_top`); picorv32 stages the single
  `picorv32.v` with `defines: ["COMPRESSED_ISA"]` mirroring the
  vendor testbench_ez build (top `picorv32`). Both prove clean
  (zero error findings) with DFF + combinational families;
  `latch_undriven.v` exits 0 carrying `latch` + `undriven`
  findings; corrupted SERV RTL and a missing top fail loudly
  (nonzero exit + `synth_error` naming the cause).
- Click-equivalent API call synthesizes SERV to a mapped netlist
  with evidence; bad RTL fails loudly with cause — the adapter is
  the full solver behind `run_synth`; Engine registration is the
  wiring patch below (integrator applies: new-files-only lane).
- Contract + api_spec regen; full suite + gate green — regen is an
  integrator step (generated docs are tracked files); lane suite
  plus gates green, see below.

Generalization law: the adapter consumes project inputs only
(`sources`, `top`, `defines`, `liberty`, `timeout_s`,
`tool_dir`, `workdir`) — no baked-in fixture paths. The SERV +
picorv32 tests stage vendored upstream trees plus committed
micro-fixtures as qualification probes; nothing in `src/` names a
fixture. Smokes qualify, project inputs flow.

## Measured evidence (ambient tools, this machine)

- `yosys -V`: `Yosys 0.70+219 (git sha1 5053d0e26, Release,
  Clang /usr/bin/clang++ 21.1.8)` from
  `~/tools/oss-cad-suite/bin/yosys`.
- Liberty (ambient PDK tree, store-independent):
  `~/.local/share/pdk/sky130A/libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__tt_100C_1v80.lib`
  (override with `SYNTH_YOSYS_LIBERTY`; mapped tests skip, never
  fake-green, when absent).
- SERV `serv_top` generic: 1196 cells / 1508 wires
  (`$_DFFE_PP_` 232, `$_AND_` 200, `$_MUX_` 180, `$_OR_` 132,
  `$_NAND_` 122), 2 warning findings (1 pre-existing
  `serv_rf_ram.v:41` range warning + ABC-summary-adjacent),
  0 errors. Mapped: 1172 cells / 1446 wires, area
  7393.3408 um^2 (`sky130_fd_sc_hd__edfxtp_1` 296, …_mux2_1 90,
  …_nand2_1 74, …_nor2_1 70), netlist carries 566 sky130 instances.
- picorv32 (`COMPRESSED_ISA`) generic: 9442 cells / 7135 wires,
  0 findings. Mapped: 6044 cells, area 77609.4336 um^2, 0 errors.
- Oracle: adapter `cells` for the counter equal a direct
  `yosys -q -s` stat run cell-for-cell
  (`test_synth_oracle_matches_direct_yosys_stat`).

## RED → GREEN log

1. RED: wrote the 27 tests + 3 fixtures with no adapter present —
   `ModuleNotFoundError: No module named
   'rocket_engine.adapters.synth_yosys'` on collection.
2. GREEN: added `src/adapters/synth_yosys/`, re-ran the sanctioned
   `scripts/install.sh --install` (sealed copy), 27/27 pass.
3. Two genuine failures on the way up, both fixed in-lane: the
   `tool_dir` miss message did not name the oss-cad-suite bundle
   (now it does), and the liberty stat's two-column `N - wires`
   layout undercounted wires (regex now accepts the area/dash
   column; SERV mapped wires 0 → 1446).

## Suite + gates (this lane)

- Full suite (fresh env, `--ignore tests/pdk_ihp/test_drc.py` —
  that module hard-imports `klayout.db` at collection and the
  klayout Python module is absent here): 125 failed, 1769 passed,
  184 skipped, 3 errors in ~7 min. Every failure sits in sibling
  lanes' untracked in-flight work (`test_cosim*.py`,
  `test_view_sync_*.py`, `test_photonic_wire.py`,
  `validate/test_photonic.py`, `pdk_gf180`/`pdk_ubc`/`pdk_cspdk`
  env-dependent tests) — zero failures in `test_synth_yosys.py`,
  `test_docstrings.py`, `test_api_spec.py`, `test_contract.py`,
  or `test_check_contract.py`. Cross-check: `test_cosim.py`
  passes standalone (47/47) and passes alongside this lane
  (92/92 with `test_synth_yosys.py` + `test_view_sync_diff.py`),
  so the full-run failures are sibling cross-test interference,
  not lane fallout. This lane's files are purely additive and
  imported only by its own tests.

- Lane: `tests/adapters/test_synth_yosys.py` 27/27 pass.
- Gates: `tests/test_docstrings.py`, `tests/test_api_spec.py`,
  `tests/test_contract.py`, `tests/test_check_contract.py` all
  pass; `scripts/check_docstrings.py` clean on the new adapter;
  100-col limit holds on all new Python files.

## Wiring patch (integrator applies — tracked files)

Checked with `git apply --check` at HEAD `272c9cf`. Three hunks,
all additive:

- `src/interfaces/vocabulary.py`: `run_synth` joins OPERATIONS.
- `src/composition.py`: import + `_solvers` entry
  `run_synth: {yosys: YosysSynthAdapter()}` + docstring tool list.
- `src/interfaces/setup.py`: SOLVER_DEPS gains
  `(run_synth, yosys) -> binaries [yosys]` (detection rides the
  existing `digital-bundle` catalogue entry, which already lists
  yosys — no catalogue change needed).

```diff
diff --git a/src/interfaces/vocabulary.py b/src/interfaces/vocabulary.py
index c466c7b1ce8755aa8ef981b0e09337426b318aa6..a11f88336cd1dc2786ff37100abf4439fa98a8b5 100644
--- a/src/interfaces/vocabulary.py
+++ b/src/interfaces/vocabulary.py
@@ -7,6 +7,7 @@
 OPERATIONS = frozenset(
     {
         "generate_views", "run_hdl_test", "run_formal", "run_syntax",
+        "run_synth",
         "run_connectivity", "run_drc", "run_lvs", "run_erc", "run_spice",
         "run_optical", "run_digital_flow", "run_timing", "run_extraction",
         "run_post_layout", "run_em", "run_thermal", "python_execute",
diff --git a/src/composition.py b/src/composition.py
index 2bbe32fe9c578d00681582c977c3bb9842b6a9af..5f07fb1ebc78e5e0758e46f026920c25eb833ed5 100644
--- a/src/composition.py
+++ b/src/composition.py
@@ -27,8 +27,8 @@
 maps to named solvers; `deck.tool` selects one, defaulting to the
 first registered (run_drc: magic, then klayout; run_optical: sax;
 run_extraction: magic; run_lvs: netgen; run_spice: ngspice;
-run_syntax: slang; run_hdl_test: icarus; run_connectivity:
-connectgraph; run_erc: connectgraph).
+run_syntax: slang; run_hdl_test: icarus; run_synth: yosys;
+run_connectivity: connectgraph; run_erc: connectgraph).
 Unregistered operations and unknown deck tools raise instead of
 faking a verdict.
 """
@@ -48,6 +48,7 @@
 from .adapters.ngspice import NgspiceAdapter
 from .adapters.sax import SaxAdapter
 from .adapters.syntax import SyntaxAdapter
+from .adapters.synth_yosys import YosysSynthAdapter
 from .execution.apig_pool import (
     ApigPool,
     request_for_run,
@@ -268,6 +269,7 @@
             "run_lvs": {"netgen": NetgenLvsAdapter()},
             "run_spice": {"ngspice": NgspiceAdapter()},
             "run_syntax": {"slang": SyntaxAdapter()},
+            "run_synth": {"yosys": YosysSynthAdapter()},
             "run_connectivity": {"connectgraph": ConnectivityAdapter()},
             "run_erc": {"connectgraph": ConnectivityAdapter()},
         }
diff --git a/src/interfaces/setup.py b/src/interfaces/setup.py
index f662288b5e63aa40a2b74ad5c2e09897aa355ecc..5ad1f94f307eb26dfa6168603123e5b493aaaa81 100644
--- a/src/interfaces/setup.py
+++ b/src/interfaces/setup.py
@@ -59,6 +59,7 @@
     ("run_lvs", "netgen"): {"binaries": ["netgen"], "banner": "lvs"},
     ("run_spice", "ngspice"): {"binaries": ["ngspice"]},
     ("run_syntax", "slang"): {"binaries": ["slang"]},
+    ("run_synth", "yosys"): {"binaries": ["yosys"]},
     ("run_connectivity", "connectgraph"): {},
     ("run_erc", "connectgraph"): {},
 }
```

## Integrator steps

1. `git apply docs/work/SYNTH-YOSYS/wiring.patch` (must report
   clean; the patch is `git apply --check`ed at `272c9cf`).
2. Regen the derived contract surfaces (tracked, generator-owned):
   `.venv/bin/python scripts/api_spec.py --write` (rewrites
   `docs/engine-api.md`, `docs/api-schema.json`,
   `docs/api-help.json`) then
   `.venv/bin/python scripts/contract.py --write` (rewrites
   `docs/contract.json`).
3. Re-provision the sealed env exactly like any other change:
   `export UV_CACHE_DIR=/tmp/uv-cache UV_LINK_MODE=copy` then
   `scripts/install.sh --install` with
   `PATH=$HOME/tools/oss-cad-suite/bin:$HOME/tools/bin:$PATH`.
4. Verify: `.venv/bin/python -m pytest tests/adapters/
   test_synth_yosys.py tests/test_docstrings.py
   tests/test_api_spec.py tests/test_contract.py
   tests/test_check_contract.py -q` green, then the full suite.
5. Commit the patch + regen + this lane's new files together.

Deliberately NOT in the patch (integrator decisions, not
oversights):

- `src/workflows/stages.py` D12 keeps entrypoints
  `[run_digital_flow]`. Adding `run_synth` there would flip D12
  readiness for existing consumers (a stage is ready only when ALL
  entrypoints resolve); the ticket's "stages.py requires it" is
  satisfied by the evidence shape (`Mapped netlist, cell counts,
  area.` — exactly what `parse` returns), and the D12 entrypoint
  extension is a follow-up once planning semantics are agreed.
- `src/mutate/__init__.py` gains no synth operators: the ticket's
  mutation clause is covered by the synth-side tests (corrupted
  SERV RTL fails loudly; latch/undriven surface as findings),
  and mutate-map entries are that module's own RED lane.
- No `setup_catalogue.yaml` change: `digital-bundle` already
  provisions + detects yosys, and `_covering_remedy` already
  points missing-yosys reports at it.
