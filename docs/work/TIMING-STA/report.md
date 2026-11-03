# TIMING-STA lane report — run_timing via PROV-pinned OpenSTA

Ticket: `docs/tickets/TIMING-STA.md` · Branch: GREEN-the-tests ·
No commits, no pushes (integrator commits).

## Status: BLOCKED on `sta` (honest, not fake-green)

`sta` is not provisioned in this sandbox and cannot be installed
here: `scripts/provision_toolchain.sh --check-only` reports
`PROV-PHASE1: DEGRADED (missing: librelane opensta)`, no ambient
`sta` exists on PATH, and the sandbox proxy refuses github
(`Proxy CONNECT aborted due to timeout` on a bounded probe), so
the OpenSTA CMake source build is infeasible — the same verdict
PROV recorded. Per the ticket, this lane therefore reports
BLOCKED: everything deliverable without the binary is delivered
(adapter, hermetic + live tests, fixtures, wiring patch), the 4
live tests skip loudly with `sta not provisioned`, and the
gate-host live run is the remaining proof. Nothing is faked to
close the gap: stub-sta tests pin the invocation contract, golden
parse tests pin the report grammar, and §"Unverified assumptions"
names every OpenSTA behavior the gate host must confirm.

## Files added (new files only — zero edits to existing files)

- `src/adapters/timing_sta/__init__.py` — `OpenStaTimingAdapter`
  behind the `ToolAdapter` port: operation `run_timing`, deck.tool
  `opensta`. Preflight refuses the wrong operation, bad tops, bad
  timeouts, missing/unsafe inputs, and unresolvable or
  unassertable tools with the PROV remedy; execute runs a
  generated `timing.tcl` under `sta`; parse normalizes margins,
  paths, and findings (details below).
- `src/adapters/timing_sta/README.md` — adapter contract note.
- `tests/adapters/test_timing_sta.py` — 32 tests: port,
  capabilities, preflight refusals, version/env resolution,
  script-content contract, golden-log parse units, failure
  semantics, plus 4 live tests (counter margins, counter
  unconstrained pin, mixed SERV top recheck, SPEF flow-through).
- `tests/adapters/fixtures/timing/counter.v` — micro-RTL.
- `tests/adapters/fixtures/timing/counter_mapped.v` — the counter
  genuinely mapped with ambient Yosys 0.70+219 + sky130 liberty
  (4 DFFs + sky130 comb cells; provenance header in-file).
- `tests/adapters/fixtures/timing/counter.sdc` — 10 ns clock and
  boundary delays; `overflow` deliberately delay-less.
- `tests/adapters/fixtures/timing/top_mixed.v` — M11 wrapper:
  1:1 `serv_top` exposure plus the arc-less `analog_boundary`
  stub. Elaborates clean (`iverilog -Wall`, exit 0) against the
  vendored SERV tree.
- `tests/adapters/fixtures/timing/top_mixed.sdc` — 20 ns clock,
  boundary delays/loads/transitions; deliberate gaps
  (`rdata0_in`, `rdata1_in`, `wdata0_out`, `wdata1_out`, all
  analog pins). Script-verified: braces balanced, all 306 named
  ports exist in the wrapper, gaps exactly as designed.
- `tests/adapters/fixtures/timing/top_mixed.spef` — minimal
  top-level SPEF (clock + analog nets; IEEE 1481 shape).
- `tests/adapters/fixtures/timing/stub.lib` — labeled
  path-existence placeholder for hermetic tests only, never
  timing data (live tests use the ambient sky130 liberty).
- `docs/work/TIMING-STA/wiring.patch` — the integrator patch as a
  file (byte-identical to the embedded diff below).
- `docs/work/TIMING-STA/report.md` — this file.

## Contract implemented (ticket clause → behavior)

- RED-first `run_timing` ToolAdapter (deck.tool `opensta`):
  mapped netlist + libs + SDC → setup/hold, WNS/TNS, critical
  paths, slew/load, unconstrained endpoints — the adapter writes
  `timing.tcl` (`read_liberty` each lib, `read_verilog` each
  netlist file, `link_design` the top, `read_spef` when given,
  `read_sdc`), then marker-delimited sections
  (`report_checks -path_delay min_max` with slew/cap fields,
  `report_wns`/`report_tns -max`/`-min`, bare
  `report_constraint`, bare `check_setup`) closed by `exit`.
  Parse returns the four margins (ns), critical-path records
  (startpoint/endpoint/group/type/slack/violated), violated
  paths as `setup_violation`/`hold_violation` errors,
  `VIOLATED` constraint lines as `constraint_violation` errors,
  and warnings (including `unconstrained_endpoint` findings)
  that never fail alone. Raw `check_setup` text always rides
  along, so missing constraints stay visible however the
  structured parse lands.
- Mixed fixture (digital block + analog boundary + top-level
  SPEF; boundary honored, gaps reported never assumed) — the
  live mixed tests synthesize SERV through the real
  `YosysSynthAdapter`, wrap it in `top_mixed.v`, and run STA
  with and without the SPEF; the SDC constrains the digital
  boundary with documented gaps, and the tests assert the
  gap pins surface in the unconstrained evidence.
- Missing binary → loud `missing_dependency` with the PROV
  remedy — resolution is job `tool_dir`, then
  `$OPENSTA_PREFIX/bin` (the PROV consumer contract), then
  PATH; every failure message names
  `scripts/provision_toolchain.sh --install` and
  `docs/work/PROV/report.md`, and the binary must answer
  `-version` (fallback `--version`) with an `OpenSTA` banner.
- Contract + api_spec regen; full suite + gate green — regen is
  an integrator step (generated docs are tracked files); lane
  suite plus gates green, see below. Full-suite green is
  claimed only for the lane + gates + neighbor lanes run here
  (a whole-tree run is the integrator's, on the gate host).

Generalization law: the adapter consumes project inputs only
(`netlist`, `libs`, `sdc`, `spef`, `top`, `timeout_s`,
`tool_dir`, `workdir`) — no baked-in fixture paths, and the
SDC passes through opaquely (project generated clocks and
boundary constraints flow untouched). The SERV + counter tests
stage vendored upstream trees plus committed fixtures as
qualification probes; nothing in `src/` names a fixture.
Smokes qualify, project inputs flow.

## Unverified assumptions (gate host must confirm)

Best-knowledge OpenSTA behaviors this lane could not execute
against (no `sta` here, no network for the manual): the
`-format full_clock_expanded -fields {slew cap} -group_count 50`
flags on `report_checks`; the `-min`/`-max` flags on
`report_wns`/`report_tns`; bare `report_constraint` /
`check_setup` output shapes (parsed tolerantly, raw text always
kept); `sta -version` printing an `OpenSTA` banner. Every one
fails LOUDLY on mismatch (`sta_error` / `runner_unavailable` /
`missing_dependency` — never a silent wrong verdict), and the 4
live tests are written to catch exactly that drift. If any flag
is rejected, the fix is small and the hermetic suite re-pins it.

## Measured evidence (ambient tools, this machine)

- PROV: `PROV-PHASE1: DEGRADED (missing: librelane opensta)`;
  yosys `Yosys 0.70+219`, sby `SBY v0.70-9-g79fc9ed` asserted.
- Liberty (ambient PDK tree, store-independent):
  `~/.local/share/pdk/sky130A/libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__tt_100C_1v80.lib`
  (override with `TIMING_STA_LIBERTY`; live tests skip, never
  fake-green, when absent).
- `counter_mapped.v`: real Yosys map — 4 `dfxtp_1` + 11
  combinational sky130 cells, top ports preserved.
- `top_mixed.v` + SERV RTL: `iverilog -Wall` elaborates exit 0,
  zero warnings.
- `top_mixed.sdc` ⇄ `top_mixed.v`: 306/306 SDC ports resolve;
  7 ungapped wrapper ports absent by design (submodule internals
  + `clk_in` clock root + the 3 delay-less inputs).
- Stub-contract proof: the hermetic tests execute a stub `sta`
  through the real `execute`/`parse` path (golden log with MET
  setup + VIOLATED hold paths, four margins, a constraint
  violator, two unconstrained warnings, one generic warning).

## RED → GREEN log

1. RED: wrote the 32 tests with no adapter present —
   `ModuleNotFoundError: No module named
   'rocket_engine.adapters.timing_sta'` on 28, 4 live skips.
2. GREEN: added fixtures (counter mapped with real Yosys,
   wrapper elaborated with real iverilog) + `src/adapters/
   timing_sta/`, re-ran the sanctioned `scripts/install.sh
   --install` (sealed copy), 28/28 pass, 4 loud skips.
3. One genuine failure on the way up, fixed in-lane: a
   mid-file SDC edit briefly dropped the `set_input_transition`
   command line (mechanical slip, restored and re-verified by
   the port cross-check — the cross-check exists because of it).

## Suite + gates (this lane)

- Lane: `tests/adapters/test_timing_sta.py` 28 passed, 4
  skipped (`sta not provisioned` × 4 with the live-tools PATH).
- Gates: `tests/test_docstrings.py`, `tests/test_api_spec.py`,
  `tests/test_contract.py`, `tests/test_check_contract.py` —
  29 passed. `scripts/check_docstrings.py` clean on the new
  adapter; 100-col holds on all new Python files.
- Neighbors: `tests/adapters/test_synth_yosys.py` +
  `tests/test_prov_toolchain.py` — 45 passed (no fallout; this
  lane's files are purely additive and imported only by its
  own tests).
- Env note: `install.sh --install` refreshed the venv + sealed
  copy successfully; its PDK-register tail fails in this
  sandbox (`Read-only file system` on `~/.local/share/
  rocketeda`) — pre-existing environmental limit, unrelated to
  this lane, hides nothing (reads of the ambient PDK/liberty
  used above are unaffected).

## Wiring patch (integrator applies — tracked files)

Checked with `git apply --check` at HEAD `23d5fa5`. Four
additive lines across two files (verified in a scratch
worktree: `py_compile` clean, solver/import/deps rows present):

- `src/composition.py`: docstring tool list + import +
  `_solvers` entry `run_timing: {opensta:
  OpenStaTimingAdapter()}` (single solver → also the default
  when `deck.tool` is absent).
- `src/interfaces/setup.py`: SOLVER_DEPS gains `(run_timing,
  opensta) -> binaries [sta]` (detection rides the existing
  `opensta` catalogue entry, which already lists `sta` — no
  catalogue change needed, and `_covering_remedy` joins by
  binary name automatically).

No `vocabulary.py` change: `run_timing` already sits in
OPERATIONS. No `stages.py` change: D22 and M11 already list
`run_timing` entrypoints.

```diff
diff --git a/src/composition.py b/src/composition.py
index e341109..5be1ad4 100644
--- a/src/composition.py
+++ b/src/composition.py
@@ -31,7 +31,7 @@ netgen; run_spice: ngspice;
 run_post_layout: ngspice; run_syntax: slang; run_hdl_test: icarus;
 run_synth: yosys; run_connectivity: connectgraph; run_erc: connectgraph;
 run_formal: sby; run_view_sync: connectgraph;
-generate_views: gdsfactory; run_cosim: cosim).
+generate_views: gdsfactory; run_cosim: cosim; run_timing: opensta).
 Unregistered operations and unknown deck tools raise instead of
 faking a verdict.
 """
@@ -55,6 +55,7 @@ from .adapters.postlayout.adapter import PostLayoutAdapter
 from .adapters.sax import SaxAdapter
 from .adapters.syntax import SyntaxAdapter
 from .adapters.synth_yosys import YosysSynthAdapter
+from .adapters.timing_sta import OpenStaTimingAdapter
 from .adapters.view_sync import ViewSyncAdapter
 from .execution.apig_pool import (
     ApigPool,
@@ -286,6 +287,7 @@ class Engine:
             "run_view_sync": {"connectgraph": ViewSyncAdapter()},
             "generate_views": {"gdsfactory": GdsfactoryViewsAdapter()},
             "run_cosim": {"cosim": CosimAdapter()},
+            "run_timing": {"opensta": OpenStaTimingAdapter()},
         }
         self._constraints = dict(constraints) if constraints is not None else None
         self._logs = {}
diff --git a/src/interfaces/setup.py b/src/interfaces/setup.py
index e3673ed..afb6e93 100644
--- a/src/interfaces/setup.py
+++ b/src/interfaces/setup.py
@@ -69,6 +69,7 @@ SOLVER_DEPS = {
     ("run_view_sync", "connectgraph"): {},
     ("generate_views", "gdsfactory"): {"python": ["gdsfactory"]},
     ("run_cosim", "cosim"): {"binaries": ["ngspice", "iverilog", "vvp"]},
+    ("run_timing", "opensta"): {"binaries": ["sta"]},
 }
 
 
```

## Integrator steps

1. `git apply --check docs/work/TIMING-STA/wiring.patch` (must
   be clean), then `git apply docs/work/TIMING-STA/wiring.patch`
   (touches ONLY `src/composition.py` + `src/interfaces/
   setup.py`). NOTE: the sibling DIGITAL-FLOW lane is in flight
   with its own additive patch — apply both; anchors differ,
   resolve adjacency if git complains.
2. Regen the derived contract surfaces (tracked,
   generator-owned): `.venv/bin/python scripts/api_spec.py
   --write` (rewrites `docs/engine-api.md`,
   `docs/api-schema.json`, `docs/api-help.json`) then
   `.venv/bin/python scripts/contract.py --write` (rewrites
   `docs/contract.json`).
3. Re-provision the sealed env exactly like any other change:
   `export UV_CACHE_DIR=/tmp/uv-cache UV_LINK_MODE=copy` then
   `scripts/install.sh --install` with
   `PATH=$HOME/tools/oss-cad-suite/bin:$HOME/tools/bin:$PATH`.
4. Provision `sta` on a networked host:
   `scripts/provision_toolchain.sh --install`, then source
   `$TOOLS_DIR/prov-phase1.env` so `$OPENSTA_PREFIX` resolves
   (or pass `tool_dir` per job).
5. Verify: `.venv/bin/python -m pytest tests/adapters/
   test_timing_sta.py tests/test_docstrings.py
   tests/test_api_spec.py tests/test_contract.py
   tests/test_check_contract.py -q` — expect 32/32 live-green
   (zero skips) plus gates green, then the full suite. Any
   `sta_error`/`runner_unavailable` there is §"Unverified
   assumptions" settling — fix the flag, re-pin hermetic.
6. Commit the patch + regen + this lane's new files together.

Deliberately NOT in the patch (integrator decisions, not
oversights):

- No `setup_catalogue.yaml` change: the PROV `opensta` entry
  already provisions + detects `sta`, and `_covering_remedy`
  already points missing-sta reports at it.
- No `src/workflows/stages.py` change: D22 (`run_digital_flow`,
  `run_timing`) and M11 (`run_timing`) already expect this
  operation; wiring the solver flips them ready by design.
- No `src/mutate/__init__.py` operators and no SDC mutation
  tests beyond the deliberate-constraint-gap fixtures: the
  gap pins ARE the mutation surface (present-vs-listed), and
  mutate-map entries are that module's own RED lane.
- No generated-clock demo in the fixture SDC: the adapter
  passes SDC through opaquely, so project generated clocks
  already flow; anchoring one to yosys-generated instance
  names would be brittle fixture-wise. A generated-clock live
  assertion is follow-up once the gate host settles §assumptions.
