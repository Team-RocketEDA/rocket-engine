# ubcpdk capability-matrix rows (proposed, PDK-UBC)

Proposed rows for the ENGINE-SETUP capability matrix / catalogue
(B10 places them; this lane only proposes). Proofs are the lane
column in `tests/pdk_ubc/` (13 pass).

| Capability | Status | Proved by |
|---|---|---|
| layout (ebeam MZI build) | ✓ | lane `test_mzi_build.py`: pdk ubcpdk, ports o1/o2/o3/o4, 34 polygons, bbox [[-10.0,-29.4],[99.1,25.1]], GDS roundtrip preserves name + geometry, fixture agreement |
| drc (klayout, PDK deck) | ✓ with caveat D1 | lane `test_drc.py`: SiEPIC_EBeam_DRC deck (checks verbatim, 2-line batch header) via KlayoutDrcAdapter deck mode; reference MZI total 6 all Boundary, zero physical; bad layout {Boundary:3, Si_space:1, Si_width:1} |
| optical-sim (sax) | ✓ with caveat O1 | lane `test_sax_sim.py`: `sax.circuit(netlist, models=PDK.models)` @1550 nm; dl=10 T(o1>o4)=0.7948270469902452, T(o1>o3)=0.18527868264398265; dl=100 pair pinned; reciprocity + zero reflection/isolation asserted |
| lvs | n/a (photonic) | No transistors to recognize; connectivity compare is kfnetlist's role per docs/gdsfactory-api-map.md, out of this slice |

Caveats (honest n/a + limits, keep with the rows):

- D1: The PDK deck ships GUI-oriented (no batch hooks); the ✓
  runs its verbatim checks through a 2-line batch header (the
  sky130 pattern), generated at test time and asserted verbatim.
  Reference goldens are Boundary-only because a bare cell GDS has
  no layer-99 floorplan — documented deck behavior, not a waived
  failure. The two ELEC463 teaching decks are inventoried, not
  proven.
- O1: Coupler SAX models interpolate the PDK's semi-analytical
  `.nc` tables (documented "use at your own risk", unvalidated by
  the foundry); Y-branch/grating models are documented
  placeholders. Goldens pin model behavior, not foundry data.
- P1: Pip install (`uv pip install "ubcpdk==3.3.5"`) was NOT run
  here — sandbox has no PyPI route. Lane proofs ran against the
  pre-cloned 3.3.5 tree (@598a773) via source-tree resolution;
  the integrator re-runs step 1 on a networked host.
- P2: `pip install ubcpdk` pulls `gdsfactoryplus` (cloud) as a
  dependency. The lane path never imports it (verified absent);
  `check_no_cloud` must stay green.
