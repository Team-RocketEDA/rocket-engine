# LVS bandgap engine-extraction leg (LVS-BANDGAP-TRIAGE, 2026-11-03)

Route: `NetgenLvsAdapter.execute` with `cell` + `bulk_nets`
(`src/adapters/lvs_netgen/`); Wave-1 evidence in
`docs/probe-extract-gds.md`. Tool versions: netgen 1.5.326,
magic 8.3.685 (tech unusable here — no sky130A.tech on host).

## 1. p/n adjudication: the klt 52/16 split is right

Wave-1 bulk grouping (magic's own `.ext` on the routed GDS: 52
devices on one common bulk plus 8 pairs) mirrors the klt
`extract.json` device counts exactly (`nfet 16 / pfet 52`).
Magic's ext2spice typing (68x uniform `pfet_01v8` w=30 l=20) is
the recognition gap (candidate: select-layer construction);
wells ARE in the GDS, so layers are not missing. Verdict: klt
side right, magic typing wrong — adjudicated by bulk nets.

Fix in this wave (`retype_by_bulk`): X-FET lines bulked to the
opposite family re-type with the flavor suffix kept
(`pfet_01v8_hvt` -> `nfet_01v8_hvt`); unknown bulks never
re-type. The inv_2 good path is identity (verified live).

## 2. Hierarchy: slice-then-inline, not slice-only

`flatten_spice(text, cell)` slices the named block but drops the
leaf blocks it instantiates — feeding that to netgen compares
`XAMP ... leaf_amp` instances against flat devices (MISMATCH).
`_prepare_flat` now routes multi-block sides through
`flatten_hierarchy(text, top=cell)`: ports map onto instance
nets, private nets qualify as `INST_net`, devices rename as
`INST_X0`. Single-wrapper/no-block sides behave exactly as
before (pinned by `test_extract_sky130.py` + `test_lvs_escape.py`).

## 3. Inventory now covers M-lines

Both bandgap sides are klt/reference M-format; X-only inventory
saw empty sets there. `inventory_nets` counts M-device nets too
(R/Q cards stay out by design — name evidence comes from
device lines).

## 4. Live proof (synthetic bandgap shape, netgen, no PDK needed)

Recipe: hierarchical uniform-pfet layout + flat re-typed
reference + `permute default` setup through the adapter
(`test_bandgap_engine_leg_matches_live`) → `match True`,
`layout_retyped 1`. Byte-exact transform pinned without netgen
(`test_flatten_then_retype_matches_expected`).

## 5. Still BLOCKED: full bandgap match (setup mapping, needs-host)

The real klt pair (`bandgap_core_routed.extract.spice` vs
`reference.spice`, 229 vs ~28 devices with m-factors/combining)
still FAILs through the adapter with a bare setup — pinned by
`test_bandgap_klt_pair_still_mismatches_without_setup_mapping`.
The fix belongs to the setup/deck surface (device-combining +
M↔X mapping), outside this wave's owned set, and the PDK tech
is absent on this host. Verdict: LVS-BANDGAP-TRIAGE
PARTIAL — adapter leg GREEN and pinned, full-match leg
BLOCKED-needs-host.
