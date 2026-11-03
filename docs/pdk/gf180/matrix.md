# PDK-GF180 capability matrix rows (proposed)

Lane: `gf180` (GlobalFoundries 180nm MCU, gdsfactory wrapper
`gf180mcu==1.0.0`). Verdicts below are lane-observed on
2026-10-31 (KLayout 0.28.16, ngspice-42, gdsfactory 9.51.0 on
the source tree / 9.40.2 on the release).

| Capability | Verdict | Evidence / note |
|---|---|---|
| Layout build (gdsfactory) | PASS | `gf180_inv_pair` builds both paths; goldens in `profile.yaml` proofs.layout; `test_inv_build.py` |
| KLayout tech install | PASS | `install_tech.py` → tech `gf180mcu` visible in batch; recipe §2 |
| DRC, PDK deck | N/A | No deck ships in the wrapper; upstream DRC needs `GFP_API_KEY` cloud; signoff decks user-supplied (fd_pr/volare) |
| DRC, engine stand-in | PASS w/ caveat | Metal1 0.23/0.23 batch rules: width 0, lane-routing space 0; 16 PDK-interior corner hits pinned (not waived); `test_drc.py` incl. dirty tripwires |
| LVS (netgen) | N/A | No device/extraction setup ships in the wrapper; no LVS deck to run |
| Extraction (Magic) | N/A | No gf180 Magic tech file in the wrapper; ambient magic has no gf180 setup |
| ngspice sim, typical | PASS | Inverter DC sweep, rail-to-rail + switching window goldens; `test_ngspice_sim.py`; identical both paths |
| ngspice sim, corners (ff/ss/fs/sf) | N/A | Wrappers define them; only typical proven here |
| Xyce models | N/A | Ship in-package but unproven (upstream flags passive translations broken) |
| Stdcell 7T/9T libs | N/A | Submodules uninitialized (249 cells each, incl. inverters); needs network fetch + separate proof |
| Fixed cells (BJT/efuse GDS) | N/A | Ship (`gf180mcu/gds/`), inventoried only, no proof run |
| Xschem symbols / display | N/A | Out of engine scope (RocketIDE concern); no symbols ship in the wrapper |

## Row semantics for the integrator

- PASS rows can gate on `pytest tests/pdk_gf180` (14 tests).
- N/A rows are honest gaps, not failures: each names what would
  promote it (user-supplied deck, submodule fetch, corner proofs).
- The engine-stand-in DRC row must never be relabeled foundry
  DRC: the pinned 16 PDK-interior hits prove the stand-in is not
  signoff.
