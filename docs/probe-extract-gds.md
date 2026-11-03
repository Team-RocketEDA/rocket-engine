# Magic GDS extraction + bandgap layout.spice (EXTRACT-GDS, 2026-11-03)

Route: `MagicExtractAdapter` accepts `gds_file` (exactly one of
`cell_file`/`gds_file`); the GDS script is `gds read {path}` before
the proven `load` + `extract all` + `ext2spice lvs` + `ext2spice`
tail. GDS paths are Tcl-safety checked (braces rejected up front).
Tool versions: magic 8.3.685, sky130A tech 1.0.588.

## Proof 1: inv_2 GDS == inv_2 .mag device complement

Recipe: `gds read libs.ref/sky130_fd_sc_hd/gds/sky130_fd_sc_hd.gds`,
`load sky130_fd_sc_hd__inv_2`, extract + ext2spice; PDK store
`sky130a@5f09001e` via resolve_deck (hashes checked).

- GDS-extracted and .mag-extracted netlists agree device-for-device
  (name, nets, class, w/l sorted-equal): 4 FETs, 2x
  `sky130_fd_pr__nfet_01v8` w=0.65 l=0.15, 2x
  `sky130_fd_pr__pfet_01v8_hvt` w=1.0 l=0.15.
- Only difference: `.subckt` port ORDER
  (`A Y VPB VNB VPWR VGND` vs `A VGND VNB VPB VPWR Y`) — flattened
  away downstream, LVS compares top level. Engine surface:
  `run_extraction` with `gds_file` (`src/adapters/extract_magic/`);
  pinned by `tests/adapters/test_extract_gds.py` (7 tests).

## Proof 2: bandgap routed GDS extracts (chain unblocked at extraction)

Recipe through the adapter: cell `bandgap_core_routed`,
`fixtures/upstream/sky130-bandgap/layout/bandgap-core/reports/20260817-020222-13476b7/bandgap_core_routed.gds`,
tech `libs.tech/magic/sky130A.tech`, timeout 1500s.

- Out: `bandgap_core_routed.{ext,spice}` — 18 subckts (full
  hierarchy: top uses inner + guard ring), 109 X-instances.
  `parse` counts the 70 FET-shaped lines (68x
  `sky130_fd_pr__pfet_01v8`, 2x unrecognized `a_...#` artifacts);
  3-terminal PNP lines (`sky130_fd_pr__pnp_05v5_W3p40L3p40`) and
  subcell instances stay in the FILE but outside the FET-shaped
  `device_count` (same FET-centric counting as EXTRACT-SKY130).
- Typing gap (loud, not silent): all 68 FET lines read
  `pfet_01v8` with uniform w=30/l=20, while the klt flow reports 52
  pfet + 16 nfet — and magic's own bulk grouping is exactly 52 on
  one common bulk plus 8 pairs, mirroring the klt split. Wells
  (64/20 nwell et al.) ARE present in the GDS, so the uniform-pfet
  typing is a recognition gap (candidate: select-layer
  construction), not missing layers. Which side is right is NOT
  adjudicated here.
- Hierarchy gap (loud, not silent): ext2spice writes one subckt per
  cell; `flatten_spice` only strips a single wrapper, so this
  layout.spice is hierarchical. Netgen one-shot LVS compares TOP
  circuits — feeding this against the flat `reference.spice` is
  LVS-BANDGAP-TRIAGE's structural question (F3), not this ticket's.

## Verdict

GDS in, extracted netlist out with provenance: EXTRACT-GDS GREEN
at the extraction step. The bandgap LVS feed is LOUDLY BLOCKED on
the two gaps above (typing + hierarchy) — handed to
LVS-BANDGAP-TRIAGE with this evidence, not papered over.
