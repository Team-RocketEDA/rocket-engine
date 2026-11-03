# API-V1-ADAPTERS: Migrate every solver adapter to emit v1 ResultBundles

*Status: Ready · Design: ADR-014, contracts/v1 (arrays/datasets/views/results/stages) · Created: 2026-11-01 · Re-scoped 2026-11-01 per docs/tool-bindings-audit.md (dump-first MVP; strict normalization post-MVP)*

Depends: API-V1-RESULTS (checker lock on task io/presentation/delivery),
API-V1-TOOLS (task binding). Blocks API-V1-CONFORMANCE provider proof.
Provider gaps (catalog tools with no adapter at all) are explicitly OUT
of scope here; tool provisioning (opensta/xyce/openems) stays PARKED
pending provision per RULING-03 (PROV-UPSTREAM-RECIPE unparks)
per directive — this ticket migrates adapter code shape, not tools.

Uranium-grade rule: no adapter ships on unpinned text scraping. MVP
reads come from bindings/structured escapes first, the four pinned
determinism cases second (magic, netgen, ngspice raw ASCII, xschem —
see audit), and nothing else. STA-text grammar is recorded residue for
when opensta lands; it staffs no adapter today.

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

MVP bar (dump-first): each adapter emits a coherent deterministic DUMP
of its native result — bindings/structured reads preferred (per audit),
golden good+bad fixtures recorded, shape documented in the adapter
README. `parse()` keeps its v0 shape during migration (Engine stays
green throughout); dumps are pure functions of recorded native outputs
so conformance fixtures can feed them without solvers installed.

Post-MVP (under API-V1-CONFORMANCE): strict normalization. Each adapter
gains a PURE normalization function (`results.py` next to the adapter,
Google docstrings, no I/O) mapping its dump to a v1 `ResultBundle`:
`datasets[]` + `views[]` + `findings[]` + `measurements[]` + `logs`
refs + I28 provenance. The Engine v1 boundary calls the normalizer and
validates the bundle against the canonical schema.

Bundle rules (ADR-015, apply at normalization time): data plus at most
short diagnostics, never long prose (help owns explanations); large
traces/tables use chunked buffers with shape/dtype/hash, not giant
inline arrays; axes carry units and stable signal identities; sample
quality explicit (valid/missing/invalid/not-converged); measurements
keep (value, target, margin, status) on PASS too; every view binds only
to datasets in the same bundle (checker-enforced).

## Per-adapter scope (presentation kinds from tasks.json)

Wave 1 — checks (table+markers). Dumps carry violations as finding
rows (rule/severity/message + cell/layer/bbox geometry):
drc, drc_kl (also check.layout_xor), lvs_netgen, syntax, connectivity
(connectivity/erc/netlist), view_sync, formal_sby (+traces:
counterexample waveform as transitions).

Wave 2 — simulation (traces/digital + table). Dumps carry sweeps as
series (explicit axes/units); HDL vectors as transitions (not sample
dumps); scalar corners as tables:
ngspice (spice + characterize.circuit), hdl_sim, sax, circulax, cosim
(traces+digital+table), postlayout.

Wave 3 — implementation (table+tree). Stage tables become dump rows
(one row per gate: id/label/status/stage/evidence) and the step
hierarchy a dumped tree; GDS/netlist/SPEF/DRC-total/LVS-match become
measurements + file refs:
digital_flow (workflow.asic + implement.asic), synth_yosys (table),
extract_magic (table), gdsfactory (views/export, table). timing_sta is
OUT (opensta PARKED pending provision per RULING-03; STA-text
grammar is residue only).

Wave 4 — parked kinds (do NOT staff until unblocked): timing_sta
(with the opensta tool, when PROV-UPSTREAM-RECIPE lands). meow
removed from this wave 2026-11-02 (ON-TRACK via ADAPT-GROUPC per
RULING-03; simulate.em binding stays post_mvp per RULING-02 until
ruled otherwise).

## Acceptance

Per adapter (MVP dump bar): RED (new
`tests/adapters/test_<name>_results.py` feeding at least one recorded
good + one recorded bad native output, asserting the dump is
deterministic, carries the task's classified kinds, and matches the
documented shape) then GREEN; no `parse()` behavior change (existing
adapter tests untouched and green); reads via audit-blessed
bindings/structured escapes or the four pinned determinism cases only;
no prose blobs in dumps (length-capped diagnostics test); chunked
buffers for any trace over the inline cap. Full gate:
`check_v1_contract.py` valid, `api_spec.py --check` clean, docstrings
clean, no module over the size limit. Final proof (post-MVP):
API-V1-CONFORMANCE runs every normalizer against recorded fixtures for
all MVP tasks and every bundle validates.

## Provider gaps (not this ticket, listed so nobody assumes coverage)

Catalog providers with NO adapter today (18, rewritten 2026-11-02
per frontends review + RULING-07): eqy, mcy, verilator, ghdl, cocotb,
nextpnr, amaranth, xyce, xschem, cace, openvaf, meep, openems, palace,
femwell, elmer_fem, devsim, vlsirtools. Dropped from the old list:
vlsir (schema), yosys_slang (plugin), openroad (LibreLane-internal —
standalone ruled out, closure only), openrcx (dead), kfactory +
gmsh (internal per RULING-07). These need adapter-build tickets
(with tools) before any v1 migration applies to them.

## Verdict (Wave-2, 2026-11-03) — Ready, 7 normalizers done

7 v1 normalizers landed for the stdio-owned adapters
(ngspice/postlayout/hdl_sim/cosim/synth_yosys/syntax/formal_sby):
pure normalize() to schema-validated ResultBundles, v0 parse()
unchanged, 25 RED->GREEN tests. Remaining waves 1-3 normalizers
(drc, drc_kl, lvs_netgen, connectivity, view_sync, sax, circulax,
meow, gdsfactory, digital_flow, extract_magic) carry to the
Wave-3 surface lane as parallel slices.
