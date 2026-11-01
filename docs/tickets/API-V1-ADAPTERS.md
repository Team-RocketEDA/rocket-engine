# API-V1-ADAPTERS: Migrate every solver adapter to emit v1 ResultBundles

*Status: Ready · Design: ADR-014, contracts/v1 (arrays/datasets/views/results/stages) · Created: 2026-11-01*

Depends: API-V1-RESULTS (checker lock on task io/presentation/delivery),
API-V1-TOOLS (task binding). Blocks API-V1-CONFORMANCE provider proof.
Provider gaps (catalog tools with no adapter at all) are explicitly OUT
of scope here; tool provisioning (opensta/xyce/openems) stays deferred
per directive — this ticket migrates adapter code shape, not tools.

## Problem

All 19 solver adapters emit v0 dialects (`{total, violations[],
measurements{...}}` plus per-adapter extras) and zero adapters emit v1
types (`ResultBundle`/`Dataset`/`DataView` appear nowhere in `src/`).
The v1 contract is frozen and checker-locked, but no solver speaks it,
so no client can consume typed results. Evidence: `parse()` exists in
19 adapters (ngspice, syntax, circulax, gdsfactory, sax, extract_magic,
drc_kl, connectivity, view_sync, cosim, synth_yosys, digital_flow,
postlayout, drc, meow, hdl_sim, formal_sby, timing_sta, lvs_netgen);
none references any v1 result schema.

## Mechanism (fixed by this ticket)

Each adapter gains a PURE normalization function (`results.py` next to
the adapter, Google docstrings, no I/O) mapping its `parse()` output to
a v1 `ResultBundle`: `datasets[]` + `views[]` + `findings[]` +
`measurements[]` + `logs` refs + I28 provenance. `parse()` keeps its v0
shape during migration (Engine stays green throughout); the Engine v1
boundary calls the normalizer and validates the bundle against the
canonical schema. Normalizers are pure so conformance fixtures can feed
recorded native outputs without solvers installed.

Bundle rules (ADR-015): data plus at most short diagnostics, never long
prose (help owns explanations); large traces/tables use chunked buffers
with shape/dtype/hash, not giant inline arrays; axes carry units and
stable signal identities; sample quality explicit
(valid/missing/invalid/not-converged); measurements keep
(value, target, margin, status) on PASS too; every view binds only to
datasets in the same bundle (checker-enforced).

## Per-adapter scope (presentation kinds from tasks.json)

Wave 1 — checks (table+markers). Violations become `MarkerDataset`
(rule/severity/message + cell/layer/bbox geometry) with a `TableView`
over the finding rows:
drc, drc_kl (also check.layout_xor), lvs_netgen, syntax, connectivity
(connectivity/erc/netlist), view_sync, formal_sby (+traces: counterexample
waveform as `DigitalDataset`).

Wave 2 — simulation (traces/digital + table). Sweeps become
`SeriesDataset` (explicit axes/units); HDL vectors become
`DigitalDataset` (transitions, not sample dumps); scalar corners stay a
`TableDataset`:
ngspice (spice + characterize.circuit), hdl_sim, sax, circulax, cosim
(traces+digital+table), postlayout.

Wave 3 — implementation (table+tree). Stage tables become `TableDataset`
(one row per gate: id/label/status/stage/evidence) and the step
hierarchy becomes `TreeDataset`/`TreeView`; GDS/netlist/SPEF/DRC-total/
LVS-match become measurements + file refs:
digital_flow (workflow.asic + implement.asic), synth_yosys (table),
extract_magic (table), gdsfactory (views/export, table), timing_sta
(table; migrate when the opensta tool lands).

Wave 4 — deferred kinds (do NOT staff until scope opens): meow
(simulate.em field+matrix+traces+table, post_mvp).

## Acceptance

Per adapter: RED (new `tests/adapters/test_<name>_results.py` feeding at
least one recorded good + one recorded bad native output, asserting the
bundle validates canonical schema and carries the task's classified
kinds) then GREEN; no `parse()` behavior change (existing adapter tests
untouched and green); no prose blobs in bundles (length-capped
diagnostics test); chunked buffers for any trace over the inline cap.
Full gate: `check_v1_contract.py` valid, `api_spec.py --check` clean,
docstrings clean, no module over the size limit. Final proof:
API-V1-CONFORMANCE runs every normalizer against recorded fixtures for
all MVP tasks and every bundle validates.

## Provider gaps (not this ticket, listed so nobody assumes coverage)

Catalog providers with NO adapter today: xyce, openroad (standalone),
eqy, mcy, openrcx, cace, meep, openems, palace, femwell, elmer_fem,
devsim, kfactory, xschem, vlsir, amaranth, ghdl, verilator, openvaf,
nextpnr, yosys_slang. These need adapter-build tickets (with tools)
before any v1 migration applies to them.
