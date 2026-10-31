# Capability matrix rows (proposed, PDK-CSPDK)

Proven variant: si340 (cspdk 2.1.0). Evidence: `tests/pdk_cspdk/`
(14 tests green) + `docs/pdk/cspdk/profile.yaml`.

| Capability | cspdk.si340 | Evidence / caveat |
|---|---|---|
| layout | ✓ | si340 MZI builds via gdsfactory 9.51.0: ports [o1,o2,o3], 16 polygons, bbox [[-20.0,-27.8],[181.3,22.8]] (`test_mzi_build.py`) |
| drc | ✓ (klayout, engine rules) | `KlayoutDrcAdapter` batch check, GDS 3/0 350nm/200nm from 49th-call Table 4: ref MZI 0 violations, bad layout 2 at golden bboxes (`test_drc.py`). NOT a foundry deck: si340 ships no local deck; upstream DRC is a gdsfactoryplus cloud workflow the engine must never use. si220/si500/sin300 do ship `.lyd25` decks (inventoried, not proven). |
| optical-sim | ✓ (sax) | `sax.circuit` over the si340 MZI netlist with `PDK.models` (39 models): T cross 0.81408256 / bar 0.05688103 @1550nm (`test_sax_sim.py`) |
| lvs | n/a (photonic) | No electrical netlist to compare; photonics has no LVS step. Documented, not a gap. |
| extraction | n/a (photonic) | No parasitic extraction for photonics. Documented, not a gap. |

Other variants (si220, si500, sin300, sin200, ge_on_si, si_sus,
si220_ebeam_event): inventoried only — tech/deck/model relpaths
verified present in cspdk 2.1.0, behavior not proven. No matrix
claims beyond si340.
