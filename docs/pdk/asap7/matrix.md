# ASAP7 capability-matrix rows (proposed, PDK-ASAP7, predictive-only)

Proposed rows for the ENGINE-SETUP capability matrix / catalogue
(the integrator places them; this lane only proposes). Proofs are
the lane column in `tests/pdk_asap7/` (19 pass). EVERY row is
labeled predictive-only: ASAP7 is a predictive PDK, never
manufacturable, and must never look better-proven than measured
silicon.

| Capability | Status | Proved by |
|---|---|---|
| inventory (predictive-only cell census) | ✓ predictive-only | lane `test_cells_inventory.py`: 812 Verilog modules (42/37/34/33/56/1 × 4 VTs), 213 LEF macros × 4, RVT Verilog⊆LEF + 10 named physical-only, 24 techlef layers, 73 NLDM + 218 CCS archives, TBUF extract → 1 cell @0.7 V |
| layout-view (predictive-only GDS read) | ✓ predictive-only | lane `test_gds_proof.py`: KLayout 0.28.16 batch; 213 GDS cells == LEF macros all 4 VTs; INVx1_R bbox (0,-88;824,1168) dbu, 51 shapes, 16 layers; fixture agrees |
| digital-flow (openroad synthesis/P&R) | claimed-upstream, NOT-RUN (predictive-only) | ORFS `flow/platforms/asap7` exists upstream (HTTP 200, drc/gds/KLayout collateral); openroad+yosys absent here so nothing ran; library LEF/LIB/techlef/Verilog inventoried above are the flow inputs |
| drc | n/a (predictive-only, missing-open-source) | No open-source deck exists: r1p7 has Calibre placeholder READMEs only; real SVRF decks are a manual asap.asu.edu download needing commercial Calibre |
| lvs | n/a (predictive-only, missing-open-source) | Same as DRC: no open-source LVS deck in-repo or verified upstream |
| analog-sim (ngspice BSIMCMG-OSDI) | n/a (predictive-only, blocked-openvaf-missing) | ngspice-42 + OSDI symbols verified + RC smoke green, but OpenVAF is absent and the PDK ships HSPICE-only level=72 cards (no Verilog-A), so no FinFET model can compile |
| schematic (xschem) | n/a (predictive-only, no PDK collateral) | xschem 3.4.8RC runs text-mode, but r1p7 ships no xschem symbols/testbenches (Cadence-only) |

Caveats (honest n/a + limits, keep with the rows):

- P0 (predictive ceiling): every ✓ above proves file-census and
  geometry-read agreement on a PREDICTIVE kit. No timing, power,
  DRC-cleanliness, silicon correlation, or tapeout-readiness is
  claimed. These rows must render below any measured-silicon row.
- D1: the submodule-init step was verified equivalently (shallow
  probe clone @58d72c9 into /tmp, pre-cloned wrapper untouched),
  not by mutating the shared wrapper.
- D2: the Calibre-deck download (asap.asu.edu, manual) and the
  Cadence `setup_asap7.csh` flow were NOT run (commercial).
- D3: GDS/LEF name equality is exact for all 4 VTs, but the
  IO_cell antenna collateral is inventoried, not proven.
- D4: LIB proof extracts only the tiny TBUF NLDM (1 cell) plus
  single-entry listing of one more archive; the other 289
  archives are proven by filename census + format regex, not by
  full extraction (5.7 GB tree).
