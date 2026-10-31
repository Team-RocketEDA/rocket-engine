# lxt capability-matrix rows (proposed, PDK-LXT)

Proposed rows for the ENGINE-SETUP capability matrix / catalogue
(integrator places them; this lane only proposes). Lane column is new
in `tests/pdk_lxt/` (17 pass: 8 profile + 5 live/deck-geometry + 4
user-deck; live proofs need the recipe provision + `LXT_LIVE=1`).

| Capability | Status | Proved by |
|---|---|---|
| layout (ltoi300 straight build) | ✓ | lane `test_proofs.py`: `straight_rwg900_cband(L10)`, ports o1/o2 (w 0.9, (2,10)), full bbox 10.0×12.9 um, ridge bbox 10.0×0.9 um, layers {(2,10),(3,10)}, 26 cells / 13 models |
| layout (lnoi400 straight build) | ✓ | lane `test_proofs.py`: `straight_rwg1000(L10)`, ports o1/o2, bbox 10.0×10.0 um, layers {(2,0),(3,0)}, 23 cells / 9 models |
| optical-sim (sax, ltoi300) | ✓ | lane `test_proofs.py`: `PDK.models['straight_rwg900_cband'](wl=1.55)` → dict with (o2,o1); \|s21\|=0.9999424370 (0.5 dB/cm), reciprocal, no reflection |
| optical-sim (sax, lnoi400) | ✓ | lane `test_proofs.py`: `PDK.models['straight_rwg1000'](wl=1.55)` → (o2,o1); \|s\|=0.9999769744 (0.2 dB/cm) |
| drc (klayout .lydrc deck) | gated (G1) | NOT proven — deck ships only via the Luxtelligence access gate. Lane proves the honest remainder: gate requirement pinned in profile, user-supplied-deck flow (register/resolve hash-pin/verify, loud `unknown_pdk` on miss) via `test_user_deck.py`, + a labelled 100 nm geometry sanity check (0 violations, NOT DRC) via `test_proofs.py` |
| tech install (klayout) | ✓ with caveat T1 | recipe: `install_tech.py` verified (scratch HOME, klayout 0.28.16 sees `LNOI400`); manual `ln -s` still required for ltoi300 |
| lvs | n/a (photonic) | No transistors to recognize; no LVS deck ships or is gated upstream |

Caveats (honest n/a + limits, keep with the rows):

- G1: The DRC deck is GATED. Requirement: request access at
  <https://resources.luxtelligence.ai/request-access?resource=drc>,
  download the stack-specific `.lydrc`, place it in
  `<home>/Klayout/drc/` (one file at a time — KLayout uses only the
  first), run via GUI Tools → DRC. No batch command exists upstream.
  `.lydrc` rows must render "gated", never ✓, until a granted deck is
  registered. The lane's stand-in `.lydrc` encodes zero rules.
- O1: Straight-model goldens pin compact-model behavior
  (loss/neff/ng from upstream `models.py` via `sax.models.straight`),
  not foundry measurement data. MMI/coupler/MZM models are
  polynomial-fit (`data/*.json`) and are inventoried, not proven,
  in this lane.
- P1: `pip install -e .` was NOT run here — sandbox has no PyPI
  route. Lane proofs ran against the byte-identical pinned clone via
  PYTHONPATH + gplugins 1.4.2 source, with repo-env gdsfactory
  9.51.0 / sax 0.18.2 standing in for pinned ~=9.34 / ~=0.16.3. The
  integrator MUST re-run `LXT_LIVE=1 pytest tests/pdk_lxt` in the
  pinned env; goldens will flag drift as failure.
- T1: Upstream `install_tech.py` links only `lnoi400/klayout`; ltoi300
  (ships `.lyp` only, no `.lyt`) needs the manual symlink in
  recipe.md §1. Consider proposing the two-line upstream patch.
