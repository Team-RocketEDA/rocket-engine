# E2E journey: mixed-signal (ttsky-sigma-delta) — review lane report

Ticket: `docs/tickets/E2E-REREVIEW.md` · Branch: GREEN-the-tests @ `a8aaa09`
Env: `UV_CACHE_DIR=/tmp/uv-cache UV_LINK_MODE=copy`,
`PATH=$HOME/tools/oss-cad-suite/bin:$HOME/tools/bin:$PATH`,
`ROCKETEDA_HOME=/tmp/rocketeda-live`. Toolchain observed: iverilog/vvp,
ngspice, magic, klayout, netgen, yosys, xschem 3.4.8; **opensta (`sta`)
absent**. Fixture pin `f868b81` (`fixtures/upstream/ttsky-sigma-delta.md`).
Review-only: no src/tests/scripts/tracked-file edits; this file is the
lane's only artifact. Sibling scratch (`/tmp/sigma-lvs`, `/tmp/top-drc*`)
stays in /tmp; the repo tree is untouched except this report.

## Verdict table

| # | Leg | Command / probe | Result |
|---|---|---|---|
| J1 | Scenario gate, mixed | `scripts/scenarios.py` on staged `ngspice_sdtop_{pass,fail}` + `hdl_sdm_{pass,fail}` | **PASS 4/4, exit 0** |
| J2 | Correctness, mixed flow | `scripts/correctness.py --flow mixed` | **GATE PASS 14/14, 0 quarantined**, exit 0; `tmp/correctness/report.json` |
| J3 | Mutants, mixed (5) | `scripts/mutate.py recheck` × `sdm_{truncation,reset_break,unconnected_port}` + `sdtop_{sizing_out_of_spec,open_net}` | **5/5 proven** (`mutated FAIL`, declared rule seen) |
| J4 | `run_cosim` closed loop, tier-1 | `test_cosim_live.py -k "tier1 or wired"` | **17/17 passed (157s)** — joint PASS in 36.4–38.0 dB band, sdm mutants flip with only `assert_fatal`, analog faults with only `measurement`, 3× determinism, I28 artifacts, engine wiring |
| J5 | `run_cosim` closed loop, PEX macro | `test_pex_good_joint_passes_in_extracted_band`, `COSIM_PEX_LIVE=1` | **PASS (363s)** — joint PASS in extracted 38.3–40.7 dB band |
| J6 | `run_post_layout` sd_top | `test_postlayout_sdtop_live_delta_is_green_and_nonzero` | **PASS (34s)** — pre/post delta green and nonzero |
| J7 | Top-level DRC via engine | `Engine.run run_drc` klayout sky130 deck on vendored `tt_um_pthomas_sigma_delta.gds` (`/tmp/top_drc2.py`) | **FAIL, 10× error `m4.5ab`** (3.8s) vs fixture-documented magic-DRC 0 → **F2** |
| J8 | Top-level LVS via engine | schematic = `gen_top_golden.py` (needs `spice/ota_top.spice` via xschem) | **BLOCKED** — xschem hierarchical netlist exits silently with no output (flat tier1 control works) → **F4**; adapter itself green on `lvs_sky130_pass` (inv_2), so the blocker is fixture inputs, not the solver |
| J9 | Mixed determinism + seam | `test_mixed.py -k "determinism or seam or handoff"` | **5/5 passed (593s)** — sdm/sdtop 3× identical, pex_bits handoff drives digital, seam-closure wired |
| J10 | I09 falsification | `/tmp/mixed_probes.py` P1–P4 | **HOLDS** — exit-0+violation → FAIL; corrupt → NOT_RUN; cancel-finished keeps state; console → NOT_RUN only |
| J11 | I27 falsification | `/tmp/mixed_probes.py` Q1–Q4 | **FALSIFIED (live)** — `plan_checks` unwired, M14 blocked invisible, `run_thermal` vocabulary-without-solver → **F1** (confirms invariant-map F1) |

No flaky runs observed; nothing quarantined this lane. All FAIL/BLOCKED
legs above are deterministic (J7 re-ran 2/2 identical; J8 xschem fails
4/4 attempts across two schematics while the flat control passes).

## Failure artifacts captured

- `TOP-DRC` (`/tmp/top_drc2.py` run): verdict
  `{"status": "FAIL", "finding_counts": {"error": 10}}`, all rule
  `m4.5ab` ("min. 3um.m4 spacing m4 : 0.4um"), bboxes inside the
  319.24×225.76 µm macro, e.g. `[188.6, 197.205, 190.0, 197.205]`.
  GDS top cell confirmed single `tt_um_pthomas_sigma_delta`
  (`klayout -b -r /tmp/tops.py`), so the deck checked the right cell.
  Native `drc_report.lyrdb` + 1709-line klayout log under `/tmp/top-drc2/`.
- `TOP-LVS-BLOCKED`: `gen_golden.py` outputs (6 blocks) under
  `/tmp/sigma-lvs/spice/golden/`; `gen_top_golden.py` dies at
  `open("spice/ota_top.spice")` (`tools/gen_top_golden.py:118`);
  xschem `ota_top.sch`/`comp_top.sch` netlist attempts exit 0/1 with
  only the X-banner and no output file; control `tier1_sdm.sch`
  netlists fine (`/tmp/xsch-ctl/spice/tier1_sdm.spice`, 1914 B).
- `I09-P1`: magic native `exit_code=0` + 1 violation →
  engine `{"status": "FAIL", "finding_counts": {"error": 1}}`.
- `I09-P2`: `evaluate("probe-corrupt", 0, "not: [valid yaml{{{")` →
  `{"status": "NOT_RUN", "reason": "unparsable output"}`; empty list → PASS.
- `I27-Q1/Q3`: `submit plan_checks` →
  `ProjectError: Operation not wired yet: plan_checks.`;
  `run run_thermal` → `ProjectError: No solver registered: run_thermal.`
- `I27-Q2`: mixed readiness — M01–M13/M15–M16 ready, **M14 blocked**
  (`run_em, run_thermal, run_spice`); M11 reads ready though `sta`
  is absent (→ F5).
- Gate outputs: J1 stdout (4 passed), J2 `tmp/correctness/report.json`,
  J4/J5/J6/J9 pytest tails, `/tmp/mixed_probes.py` full log.

## Findings

### F1 — I27 unenforced: no completion surface consumes stage readiness (high)

`plan_checks` is declared in `src/interfaces/vocabulary.py:28` but no
implementation exists — `Engine.submit` raises `unsupported_operation`
(`src/composition.py:560`). `applicable_stages`
(`src/workflows/stages.py:121`) computes ready/blocked data that
nothing reads: with all 19 wired operations, mixed M14
(`run_thermal`, and `run_thermal` appears nowhere outside
`vocabulary.py:13` — no adapter, no setup entry) stays blocked with no
signal anywhere, and `check_results`
(`src/composition.py:1686`) reports only ran operations, so
run_spice+run_hdl_test PASSes with M09/M10/M14 never run look identical
to a fully verified design. Live confirmation of invariant-map F1.
Proposed ticket: `E2E-REREVIEW: wire plan_checks/design-completion gate (I27)`
(same ticket; this lane adds the mixed live probes, do not double-file).

### F2 — Engine top-DRC FAILs where the fixture documents DRC 0 (medium)

Klayout sky130A deck via `Engine.run run_drc` reports 10× `m4.5ab`
errors on the vendored macro GDS; the fixture documents "sd_top DRC 0"
(`fixtures/upstream/ttsky-sigma-delta/STATUS.md:38`, via magic DRC).
Either the magic flow misses/waives m4 wide-metal spacing or the
klayout deck over-flags this GDS (which predates the 2026-07-26 frame
fix per STATUS.md). Either way M09 top-DRC cannot be claimed PASS
through the engine today. Needs PDK/deck triage, not a harness tweak.
Proposed ticket: `Mixed M09: triage klayout-deck m4.5ab FAIL vs documented magic-DRC 0 on sd_top GDS`.

### F3 — Klayout deck mode silently ignores the `cell` argument (medium)

Deck mode runs `klayout -b -rd input=… -rd report=… -r <deck>`
(`src/adapters/drc_kl/__init__.py:263`) with no top-cell selection and
`preflight` drops `cell` from the checked mapping
(`src/adapters/drc_kl/__init__.py:205-238`). Benign for this single-top
GDS (verified: one top cell), but a multi-top GDS would check
`layout.top_cell()` while the job claims another cell — a
silent-wrong-target gap on the M09 path.
Proposed ticket: `DRC-KL: honor cell in deck mode or refuse multi-top GDS`.

### F4 — sd_top top-LVS schematic is not reproducible in this env (medium)

`run_lvs` needs a schematic netlist that exists only as generator output
(`tools/gen_top_golden.py:118` reads `spice/ota_top.spice`), and the
xschem step that produces it silent-fails here for hierarchical
schematics (`ota_top`, `comp_top`: banner only, no output, exit 0/1)
while the flat `tier1_sdm.sch` control netlists fine — same binary,
same flags, schematic-dependent. The engine LVS adapter is proven
(`lvs_sky130_pass` green), so M09 top-LVS is blocked on fixture
reproducibility, not solver work. Vendoring `spice/golden/top.spice`
(or pinning the xschem behavior) would unblock it.
Proposed ticket: `Mixed M09: make sd_top top-LVS schematic reproducible (xschem *_top netlist silent-fail)`.

### F5 — Stage planner is wiring-based, tool-blind: M11 ready without `sta` (low)

`applicable_stages` marks M11 (`run_timing`) ready because the operation
is wired, but `run_timing` needs the `opensta` binary
(`src/interfaces/setup.py:73`) and `sta` is absent here — runtime
preflight would fail loudly, but the plan overstates readiness.
Contributes to F1; separable fix.
Proposed ticket: `Workflows: capability-aware readiness (missing tool still reads ready)`.

### F6 — `Engine.run` docstring contradicts I09 (low)

`src/composition.py:2426` says "the verdict is evaluated from the
native exit code" while the code judges parsed violations and records
the exit code only (`src/composition.py:2389`,
`src/execution/service.py:190-224`; J10 probes confirm). Doc-only, but
it misstates the invariant the review exists to protect.
Proposed ticket: `Docs: fix Engine.run verdict docstring (exit-code wording contradicts I09)`.

## Cross-lane notes

- Digital J11 (I27 HOLDS at adapter level: missing tool → NOT_RUN) and
  this lane's J11 (I27 FALSIFIED at stage-completion level) are
  complementary scopes, not in conflict: per-run honesty holds, the
  missing piece is the cross-stage completion claim.
- Invariant-map I09 PROVEN == this lane's J10 (live corroboration, no
  new ticket). Invariant-map F1 == this lane's F1 (live corroboration).
- J7/J8 are mixed-lane only: no sibling lane ran engine DRC/LVS against
  the sigma-delta top.
