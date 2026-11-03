# DIGITAL-FLOW lane report — run_digital_flow via LibreLane Classic

Ticket: `docs/tickets/DIGITAL-FLOW.md` · Branch: GREEN-the-tests ·
No commits, no pushes (integrator commits).

Status: **BLOCKED live**. The pinned LibreLane 3.0.17 supported
distribution is absent in this sandbox (`PROV-PHASE1: DEGRADED
(missing: librelane opensta)`), so the SERV RTL-to-GDS live proof
cannot run here. The adapter plus hermetic qualification are GREEN
(52 passed); the 3 live tests skip loudly with the PROV remedy, never
fake-green. This lane reports `complete: false` with the missing
distribution named in `unresolved`.

## Dependency verification (before starting)

- SYNTH-YOSYS: `75dd122 feat(synth-yosys): close SYNTH-YOSYS lane,
  run_synth via Yosys 27/27 green` — present on GREEN-the-tests.
- PROV: `23d5fa5 feat(prov): land PROV phase-1 toolchain provisioner,
  22 passed + 2 loud skips` — HEAD, present.
- `scripts/provision_toolchain.sh --check-only`: oss-cad-suite
  `20261025` + yosys (`Yosys 0.70+219`) + sby (`SBY v0.70-9-g79fc9ed`)
  asserted; `librelane absent [.../librelane-devshell-x86_64.AppImage]`
  and `opensta absent` with `REMEDY` lines citing the upstream
  install docs; verdict `PROV-PHASE1: DEGRADED`.

## Files added (new files only — zero edits to existing files)

- `src/adapters/digital_flow/__init__.py` — `LibrelaneFlowAdapter`
  behind the `ToolAdapter` port: operation `run_digital_flow`,
  deck.tool `librelane`. Preflight refuses the wrong operation,
  foreign deck tools, bad flow inputs, missing sources, and
  unresolvable or unpinned tools; execute stages the project RTL
  into a LibreLane design dir and runs the Classic flow as a
  subprocess under the job timeout in its own process group
  (timeout SIGKILLs the tree); parse judges the D11–D27 gates from
  the run's step dirs into findings plus per-stage evidence, GDS,
  netlist, SPEF, DRC-total, and LVS-match measurements.
- `src/adapters/digital_flow/README.md` — adapter contract note.
- `tests/adapters/test_digital_flow.py` — 55 tests: port,
  capabilities, 39 preflight refusals/version probes (hermetic stub),
  10 pure parse units (timeout, clean, partial, force-bypass,
  synth-fail, no-run, DRC/LVS/STA failures), 3 stub executes (full
  evidence, synth death, timeout tree-kill), 3 live (counter, broken
  RTL, SERV — all skip without the distribution + PDK root).
- `tests/adapters/fixtures/digital_flow/counter.v`,
  `broken.v` — committed micro-fixtures.
- `docs/work/DIGITAL-FLOW/wiring.patch` — the integrator patch as a
  file (byte-identical to the embedded diff below).
- `docs/work/DIGITAL-FLOW/report.md` — this file.

## Contract implemented (ticket clause → behavior)

- RED-first `run_digital_flow` ToolAdapter driving the pinned
  LibreLane distribution as a subprocess flow; per-stage evidence
  (config, reports, DB checkpoints), stage gates with force-bypass
  per the verdict-gate policy, bounded + cancellable long runs —
  `LibrelaneFlowAdapter` writes `design/src/` + `design/
  digital_flow_config.json` (DESIGN_NAME/VERILOG_FILES/CLOCK_PERIOD/
  CLOCK_PORT/PDK plus job `config` extras) and runs `librelane
  <config> --tag <tag> --pdk <pdk> --overwrite` (`--pdk-root`/`--scl`
  when the job names them) under `timeout_s` (default 3600) in its
  own process group. Parse scans `design/runs/<tag>/` step dirs:
  each D11–D27 gate passes on its step's evidence, fails loudly
  naming the stage plus the report (`digital_flow_gate`), or is
  force-bypassed via the job `force` list (`digital_flow_forced`
  warning, never silent; force on a passing gate is inert). A
  nonzero exit fails the first gate and marks evidence-free
  downstream gates `not_run`; D27 additionally fails as blocked
  while any earlier gate stays failed.
- SERV end-to-end: Verilog → GDS → KLayout DRC + Netgen LVS against
  the schematic, one dispatched flow with inspectable stage
  artifacts — implemented; the live proof is BLOCKED here (no
  distribution, no `~/.ciel` PDK root) and runs on the first
  networked host via the 3 live tests (SERV asserts all 17 gates
  pass plus GDS + DRC 0 + LVS match; broken RTL asserts a D12 death
  with cause).
- deck.tool `librelane`; missing distribution → loud
  `missing_dependency` with the PROV remedy — every resolution or
  version failure names the pinned 3.0.17 distribution plus `run
  scripts/provision_toolchain.sh --install` and the nix-shell
  `--version` assert; the binary must report the pin, and mismatch
  refuses (stub-proved).
- Flow failures name the failing stage + report, never a bare
  traceback — violations carry `Dxx <label> failed: <reason> (see
  <report>)` with the report as `file`; synth ERROR lines surface
  the first line as the D12 cause.
- Contract + api_spec regen; full suite + gate green — regen is an
  integrator step (generated docs are tracked files); lane suite
  plus gates green, see below.

Generalization law: the adapter consumes project inputs only
(`sources`, `top`, `clock_port`, `clock_period`, `pdk`, `pdk_root`,
`scl`, `flow`, `tag`, `force`, `config`, `timeout_s`, `tool_dir`,
`workdir`) — no baked-in fixture paths. The stub binary, fake run
trees, and SERV/counter/broken probes are qualification smokes;
nothing in `src/` names a fixture. Smokes qualify, project inputs
flow.

## Measured evidence (this sandbox)

- Distribution: `librelane` not on PATH;
  `~/tools/librelane-3.0.17/librelane-devshell-x86_64.AppImage`
  absent; `python3 -c "import librelane"` → ModuleNotFoundError
  (correct per the ticket: pip presence would prove nothing about
  the native closure).
- PDK root: `~/.ciel` absent, `DIGITAL_FLOW_PDK_ROOT` unset — the
  engine `~/.local/share/pdk/sky130A` open-PDK tree is not a
  LibreLane volare/ciel root, so the live tests do not accept it.
- Hermetic (52 passed): stub version probe records `LibreLane
  3.0.17`; stub full-run evidence parses to 17/17 pass with GDS +
  `drc_total 0` + `lvs_match True`; partial trees fail D13–D27 by
  name; force lists convert those to warnings; synth-fail trees die
  at D12 with `parse error on line 1 of broken.v`; DRC `total: 5`,
  `Netlists do not match.`, and `Setup VIOLATED` each fail their
  gate; the sleep stub dies by `timeout_s=2` in ~2s with
  `digital_flow_timeout` and no hang.
- Live (3 skipped): counter/broken/SERV each skip naming the missing
  distribution plus the PDK-root remedy — loud skips, never
  fake-green, never skip-gated GREEN.

## RED → GREEN log

1. RED: wrote the 55 tests + 2 fixtures with no adapter present —
   `ModuleNotFoundError: No module named
   'rocket_engine.adapters.digital_flow'` on collection.
2. GREEN: added `src/adapters/digital_flow/`, re-ran the sanctioned
   `scripts/install.sh --install` (sealed copy), 52 passed + 3
   skipped.
3. One genuine failure on the way up, fixed in-lane: the D19 needles
   (`detailrout`) missed the `DetailedRouting` step dir (detail+ed,
   not detail+rout), failing D19 and blocking D27 on the complete
   tree — needles are now (`detailedrout`, `detailroute`, `droute`,
   `antenna`) plus a lowercase-needle audit (the matcher lowercases
   step names, so every needle must be lowercase).

## Suite + gates (this lane)

- Lane: `tests/adapters/test_digital_flow.py` 52 passed + 3 loud
  skips in ~2s.
- Gates: `tests/test_docstrings.py`, `tests/test_api_spec.py`,
  `tests/test_contract.py`, `tests/test_check_contract.py` — 29
  passed; `scripts/check_docstrings.py` clean on the new adapter;
  100-col limit holds on all new Python files; `test_setup.py`
  passes alongside this lane (66 passed + 3 skipped, no
  interference).
- Provision notes: `scripts/install.sh --install` with
  `UV_CACHE_DIR=/tmp/uv-cache UV_LINK_MODE=copy PROV_OFFLINE=1`
  (the documented sandbox fast path) and dev-PATH
  oss-cad-suite. The sealed copy needed one retry (first attempt
  hit a transient hatchling fetch timeout through the sandbox
  proxy; retry resolved from cache). The `--pdk-only` tail fails in
  this sandbox (`ROCKETEDA_HOME` is read-only under the shell
  sandbox) — a pre-existing environment limit, not lane fallout:
  this lane needs no PDK store (the venv + sealed copy provision
  cleanly before that step).
- Full suite: not run to completion in-lane — the tree concurrently
  carries sibling TIMING-STA untracked work-in-flight, so a full
  run would judge two lanes at once. This lane's files are purely
  additive and imported only by its own tests; the full suite runs
  at integration on the networked gate host (step 4 below).

## Upstream-interface assumptions (the live run is the proof)

Derived from the upstream docs (LibreLane readthedocs installation
+ configuration references, the PyPI Classic README) plus observed
community invocations — not from a live binary, which is absent
here:

- CLI: `librelane <config> --tag <tag> --pdk <pdk> --overwrite`
  with `--pdk-root`/`--scl` options; `--version` reports the pin.
- Run layout: `design/runs/<tag>/<Step>/` step dirs holding
  reports, DBs, and state files.
- Config keys: DESIGN_NAME, VERILOG_FILES (absolute staged paths),
  CLOCK_PERIOD, CLOCK_PORT, PDK, plus caller `config` extras.
- Gate matching: step-dir substring table plus report-content rules
  (synth `ERROR:`, DRC totals, LVS match lines, STA `violated`,
  non-empty GDS).

If the live layout differs, gates fail loudly naming the run dir —
never fake-green — and the stage table takes a follow-up against
the real tree.

## Wiring patch (integrator applies — tracked files)

Checked with `git apply --check` at HEAD `23d5fa5`. Two files, all
additive:

- `src/composition.py`: import + `_solvers` entry `run_digital_flow:
  {librelane: LibrelaneFlowAdapter()}` + docstring tool list.
- `src/interfaces/setup.py`: SOLVER_DEPS gains `(run_digital_flow,
  librelane) -> binaries [librelane]` (detection rides the existing
  `librelane` catalogue entry — no catalogue change needed).

```diff
diff --git a/src/composition.py b/src/composition.py
--- a/src/composition.py
+++ b/src/composition.py
@@ -31,7 +31,8 @@
 run_post_layout: ngspice; run_syntax: slang; run_hdl_test: icarus;
 run_synth: yosys; run_connectivity: connectgraph; run_erc: connectgraph;
 run_formal: sby; run_view_sync: connectgraph;
-generate_views: gdsfactory; run_cosim: cosim).
+generate_views: gdsfactory; run_cosim: cosim;
+run_digital_flow: librelane).
 Unregistered operations and unknown deck tools raise instead of
 faking a verdict.
 """
@@ -41,6 +42,7 @@
 from .adapters.circulax.adapter import CirculaxAdapter
 from .adapters.connectivity import ConnectivityAdapter
 from .adapters.cosim import CosimAdapter
+from .adapters.digital_flow import LibrelaneFlowAdapter
 from .adapters.drc import MagicDrcAdapter
 from .adapters.drc_kl import KlayoutDrcAdapter
 from .adapters.errors import AdapterError
@@ -286,6 +288,7 @@
             "run_view_sync": {"connectgraph": ViewSyncAdapter()},
             "generate_views": {"gdsfactory": GdsfactoryViewsAdapter()},
             "run_cosim": {"cosim": CosimAdapter()},
+            "run_digital_flow": {"librelane": LibrelaneFlowAdapter()},
         }
         self._constraints = dict(constraints) if constraints is not None else None
         self._logs = {}
diff --git a/src/interfaces/setup.py b/src/interfaces/setup.py
--- a/src/interfaces/setup.py
+++ b/src/interfaces/setup.py
@@ -69,6 +69,7 @@
     ("run_view_sync", "connectgraph"): {},
     ("generate_views", "gdsfactory"): {"python": ["gdsfactory"]},
     ("run_cosim", "cosim"): {"binaries": ["ngspice", "iverilog", "vvp"]},
+    ("run_digital_flow", "librelane"): {"binaries": ["librelane"]},
 }
 
 
```

## Integrator steps

1. `git apply --check docs/work/DIGITAL-FLOW/wiring.patch` (must
   report clean; checked at `23d5fa5`), then `git apply
   docs/work/DIGITAL-FLOW/wiring.patch` (touches ONLY
   `src/composition.py` + `src/interfaces/setup.py`).
2. Regen the derived contract surfaces (tracked, generator-owned):
   `.venv/bin/python scripts/api_spec.py --write` (rewrites
   `docs/engine-api.md`, `docs/api-schema.json`,
   `docs/api-help.json`) then
   `.venv/bin/python scripts/contract.py --write` (rewrites
   `docs/contract.json`).
3. Provision on a networked Ubuntu 24.04 host exactly like any other
   change: `export UV_CACHE_DIR=/tmp/uv-cache UV_LINK_MODE=copy`
   then `scripts/install.sh --install` with
   `PATH=$HOME/tools/oss-cad-suite/bin:$HOME/tools/bin:$PATH`
   (expect `PROV-PHASE1: OK (4/4 ...)`); populate the LibreLane PDK
   root (`~/.ciel` via volare per the upstream PDK docs) or export
   `DIGITAL_FLOW_PDK_ROOT` at test time.
4. Verify: `.venv/bin/python -m pytest tests/adapters/
   test_digital_flow.py -q` green — expect 55 passed including the
   3 live proofs (SERV full flow carries `timeout_s=3600`; the
   counter live proof 1800) — then the gate files above plus the
   full suite.
5. Commit the patch + regen + this lane's new files together.

Deliberately NOT in the patch (integrator decisions, not
oversights):

- `src/interfaces/vocabulary.py`: `run_digital_flow` already joins
  OPERATIONS — no change needed.
- `src/workflows/stages.py`: D11–D27 already list
  `run_digital_flow` entrypoints — no change needed.
- `src/interfaces/setup_catalogue.yaml`: the `librelane` entry
  already provisions + detects the distribution, and
  `_covering_remedy` already points missing-librelane reports at
  it — no change needed.
- No standalone STA adapter: per the ticket, timing evidence rides
  the flow reports first (D13/D22); TIMING-STA owns any
  flow-external need.
