# sky130gf capability-matrix rows (proposed, PDK-SKY130GF)

Proposed rows for the ENGINE-SETUP capability matrix / catalogue
(B10 places them; this lane only proposes). Per the ticket, every
row names its distribution: `sky130gf` = the pip package
(`sky130==1.0.0`), `sky130A` = the open_pdks tree. Proofs: the
tree column already exists (DRC-SKY130, EXTRACT-SKY130,
SIM-SKY130 slices); the pip column is new in
`tests/pdk_sky130gf/` (16 pass in the pinned env; 6 pass +
10 honest skips where the pip package is absent).

| Capability | Distribution | Status | Proved by |
|---|---|---|---|
| layout (cell build) | sky130gf (pip) | ✓ | lane `test_cell_build.py`: 767 cells registered; nfet_01v8 ports BODY/DRAIN/GATE/SOURCE, 48 polygons, bbox [[-1.0,-1.205],[1.0,1.205]]; inv_2 46 polygons at golden bbox; exact fixture roundtrip (sha256 `0bd23411…54a3e34`) |
| klayout-tech | sky130gf (pip) | ✓ | lane `test_tech.py`: tech link into scratch HOME resolves `sky130` in KLayout 0.28.16 batch |
| drc (klayout) | sky130gf (pip) | n/a → sky130A | No runnable deck ships (0 `.lydrc`; `.lyd25` is a GUI macro, batch run fails — guarded by `test_tech.py`); upstream DRC CI is gdsfactoryplus cloud. DRC stays on the tree `sky130A.lydrc` row |
| lvs | sky130gf (pip) | n/a → sky130A | No LVS deck ships with the pip package; LVS stays on the tree netgen row |
| extract | sky130gf (pip) | n/a → sky130A | No Magic tech ships with the pip package; extraction stays on the tree Magic row |
| sim (spice) | sky130gf (pip) | n/a → sky130A | 146 vendored `.spice` files inventoried but unproven here (PySpice wrappers unexercised); sim stays on the tree `sky130.lib.spice` row |
| routing (doroutes) | sky130gf (pip) | n/a (unproven) | `routing_utils.py` needs doroutes, skipped by the `--no-deps` install; no routing proof in this lane |

Caveats (honest n/a + limits, keep with the rows):

- D1: The pip ✓ covers layout cells + KLayout tech ONLY. Every
  verification capability (drc/lvs/extract/sim) is n/a on the pip
  distribution with an explicit pointer to the sky130A tree row.
  Runs pin the distribution in the ingredient closure; the two
  registrations never overlap, so no run can silently mix them.
- P1: The lane pins `sky130==1.0.0` installed with `--no-deps`
  to protect the repo's gdsfactory 9.51.0 (a plain install
  resolves `gdsfactory~=9.40.1` and downgrades to 9.40.2).
  Forward-compat is verified, not assumed: identical cell
  goldens under 9.40.2 and 9.51.0. Every skipped dep is
  documented in recipe.md §1.
- P2: `pip install sky130` (plain) pulls `gdsfactoryplus`
  (cloud) as a dependency. The lane path never imports it
  (zero `gdsfactoryplus` imports in the package — grep-clean);
  the `--no-deps` recipe skips it entirely. `check_no_cloud`
  must stay green.
- P3: volare was evaluated and rejected as a lane distribution:
  it fetches the same open_pdks tree (not a distinct
  distribution) and needs GitHub network + token at provision
  time. It must not appear as a third sky130 registration.
- P4: Wheel 38 MB / installed 204 MB (vendored SkyWater GDS +
  models). Wrapper is MIT; vendored SkyWater content is
  Apache-2.0.
