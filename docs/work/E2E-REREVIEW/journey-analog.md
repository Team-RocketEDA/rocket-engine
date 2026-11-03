# Journey-analog: bandgap end-to-end re-review

Lane: analog (A-flow) on the sky130-bandgap fixture. Review only: no
src/tests/scripts/tracked edits; this file is the lane's only artifact.
Branch GREEN-the-tests @ a8aaa09. Env: project .venv (no reinstall
needed), PATH with oss-cad-suite + ~/tools/bin, ROCKETEDA_HOME=/tmp/rocketeda-live.
Tools: ngspice-42, klayout (system), magic (system), netgen 1.5.326,
sky130a store rev 5f09001e.

## Verdict table

| # | Step | How | Result |
|---|------|-----|--------|
| 1 | scenarios.py bandgap pass (run_spice good) | run_scenario ngspice_bandgap_pass.yaml, live | PASS |
| 2 | scenarios.py bandgap fail (sizing mutant s0) | run_scenario ngspice_bandgap_fail.yaml, live | PASS (FAIL as expected) |
| 3 | correctness.py --flow analog (good + 5 mutants) | gate, live, report tmp/correctness-e2e-rereview-analog | GATE PASS 6/6, 0 quarantine |
| 4 | run_spice sizing x3 / open-net x2 | gate cases bandgap_sizing_out_of_spec-0..2, bandgap_open_net-0..1 | all FAIL with rule=measurement only |
| 5 | run_post_layout synthetic loss | pytest test_postlayout_bandgap_live_delta_is_green_and_nonzero | PASS, delta nonzero |
| 6 | run_post_layout REAL routed PEX | Engine, pex sha c331442e5b28bd74 + minimal TB + provenance | FAIL sim_fail, ngspice "can't find model 'nfet'" (2x identical) -> F1 |
| 7 | run_drc sky130 foundry deck on bandgap_core_routed.gds | Engine, deck sky130A.lydrc from store | FAIL 740x li.5, fixture klt DRC clean/0 (2x identical) -> F2 |
| 8 | run_extraction on bandgap GDS | preflight probe | BLOCKED: adapter is .mag-only, layout is GDS-only -> F4 |
| 9 | run_lvs netgen on klt pair (extract.spice vs reference.spice) | Engine, sky130A_setup.tcl | FAIL 185 net mismatches, fixture klt LVS match/0 (2x identical) -> F3 |
| 10 | I27 falsification (missing stages block completion) | probes: plan_checks, run_thermal, applicable_stages, check_results | STANDS (vacuous: no claim surface) -> F5 |
| 11 | I09 falsification (exit-zero-is-not-PASS) | probes: evaluate() matrix + live mutant exit 0 -> FAIL | STANDS -> F6 (minor doc gap) |

Repeats: sizing-v0 FAIL 3x (scenario + gate + probe, vref 1.165872 live);
DRC-740 2x; LVS-185 2x; PL sim_fail 2x. No flakes observed, nothing quarantined.

## Findings

### F1 (high) run_post_layout cannot sim the real extracted PEX
The engine sims `extracted_netlist` as-is; `klt extract` writes generic
LVS device-class placeholders (`nfet`, `pfet`, `pnp`, `res_high_po`) that
ngspice's sky130 lib does not define. Native log: `warning, can't find
model 'nfet'` -> exit 1 -> sim_fail. The fixture's own flow translates
classes to vendor models externally (post_layout_common.py); the engine
has no such step, so A19/M12 on a real layout ends here. The committed
live test proves deltas only on a synthetic Rpar mutant, not the real PEX.
Evidence: `src/adapters/postlayout/adapter.py:533-534` (as-is body),
fixture translator `fixtures/upstream/sky130-bandgap/sim/bin/post_layout_common.py:22-64`,
synthetic-only proof `tests/adapters/test_postlayout.py:795-850`.
Proposed ticket: POSTLAYOUT-REAL: translate klt generic device classes to vendor models.

### F2 (high) Foundry-deck DRC floods where fixture klt DRC is clean
Engine run_drc (klayout, store sky130A.lydrc) on the routed top GDS:
FAIL, all 740 errors one rule (li.5 licom enclosure). Fixture drc.json
for the same GDS: status clean, 0 violations (klt curated deck). One of
them is wrong for this layout, or the engine needs deck-parity/waiver
handling; no waiver support exists in the DRC path. Deterministic 2x.
Evidence: `src/adapters/drc_kl/__init__.py:164-173` (deck mode, no
waivers), fixture `layout/bandgap-core/reports/20260817-020222-13476b7/drc.json`
(status clean).
Proposed ticket: DRC-BANDGAP-TRIAGE: reconcile foundry-deck li.5 flood vs klt-clean.

### F3 (high) Netgen LVS floods where fixture klt LVS matches
Engine run_lvs (netgen, sky130A_setup.tcl) on extract.spice vs
reference.spice: FAIL, 185 lvs_net_mismatch (VSS, NG, D1, D2, PN, ...).
Fixture lvs.combined.json for the same pair: status match, 0 mismatches
with combine_devices on. Suspect device-combining/setup gap in the
engine path; needs triage before A16 can be claimed on bandgap.
Deterministic 2x.
Evidence: `src/adapters/lvs_netgen/__init__.py:248-256`,
fixture `layout/bandgap-core/reports/20260817-020222-13476b7/lvs.combined.json`
(status match).
Proposed ticket: LVS-BANDGAP-TRIAGE: reconcile netgen mismatch flood vs klt match.

### F4 (med) run_extraction is .mag-only; bandgap layout is GDS-only
The magic script is `load {cell}` + `extract all` (no `gds read`), and
every bandgap layout artifact is GDS. A17 cannot run on this fixture
through the engine, which also starves LVS of an engine-produced
layout.spice (step 9 used the fixture's klt netlist instead).
Evidence: `src/adapters/extract_magic/__init__.py:35-38`.
Proposed ticket: EXTRACT-GDS: support GDS input for run_extraction.

### F5 (med) I27 has no enforcement point
Falsification attempts all refused loudly, so I27 stands — but nothing
computes a "fully verified" claim: `applicable_stages` has no production
consumer (tests only), `plan_checks` is vocabulary but unwired
(`unsupported_operation: Operation not wired yet`), `check_results`
returns latest-per-op with no completeness claim, and `run_thermal`
(A20/P19/M14 entrypoint) has no registered solver so those stages can
never be ready. I27 is currently untestable through any API.
Evidence: `src/workflows/stages.py:121`, `src/composition.py:107-116`
(wired set), `src/interfaces/vocabulary.py:24-39`, probe transcripts below.
Proposed ticket: PLAN-CHECKS: wire plan_checks/applicable_stages to a completion claim.

### F6 (low) evaluate() drops the exit code it claims to record
`ExecutionService.evaluate` docstring says the exit code "is recorded,
never the verdict" — the verdict carries only status + finding_counts;
the code is discarded (verdict keys observed: finding_counts,
measurements, status). I09 itself holds (exit 0 + error -> FAIL,
exit 1 + clean -> PASS, live mutant exit 0 -> FAIL vref 1.165872).
Evidence: `src/execution/service.py:190-224`.
Proposed ticket: VERDICT-EXIT-CODE: record native exit on verdict or fix docstring.

## Falsification transcripts (abridged)

- I09-evaluate: exit0+error -> FAIL; exit1+clean -> PASS.
- I09-live-mutant: native_exit=0 verdict=FAIL vref=1.165872.
- I27-plan_checks: unsupported_operation: Operation not wired yet: plan_checks.
- I27-run_thermal: unsupported_operation: No solver registered: run_thermal.
- I27-plan: analog minus layout backends -> 10 blocked (A04, A13-A17, ...).
- I27-check_results: {checks: {}, current_revision} — no completeness claim.
- DRC-bandgap: FAIL {error: 740}, first page all rule li.5.
- EXT-bandgap: .mag-only script; GDS has no path (tech-name probe also
  shows bare `tech: sky130A` without tech_file refuses missing_dependency).
- PL-real-pex: exit=1 total=1 rules=[sim_fail]; ngspice: can't find model 'nfet'.
- LVS-bandgap: FAIL {error: 185} net mismatches incl. VSS/D1/D2/PN.

Probes: /tmp/e2e_analog_probes.py, /tmp/e2e_analog_probes2.py (outside repo).
Gate report: tmp/correctness-e2e-rereview-analog/report.json (gitignored).
