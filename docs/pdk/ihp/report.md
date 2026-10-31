# PDK-IHP lane report (IHP SG13G2 BiCMOS + RF flavors)

## Files added (lane-owned dirs only)

`docs/pdk/ihp/`:

- `profile.yaml` — flavors (bicmos vs rf explicit), pins, tech/deck/model
  relpaths, honest gaps, golden proofs
- `recipe.md` — exact provision commands from PDK docs, each with status
- `matrix.md` — proposed capability-matrix rows (✓ / n/a / preview-gated)
- `report.md` — this file

`tests/pdk_ihp/`:

- `__init__.py`, `_profile.py` (profile load + ihp resolution helper)
- `test_profile.py` (7 tests), `test_cells_build.py` (5),
  `test_drc.py` (3), `test_ngspice_sim.py` (2), `test_sax_sim.py` (3)
- `fixtures/nmos_ref.gds` — 1228-byte upstream artifact, byte copy of
  `ihp/gds/nmos.gds` @ d7643aa (sha256
  `cda80d8a…63fef1f`), Apache-2.0, same license file as wrapper root

No other paths touched. No commits (integrator commits).

## Pins

- ihp-gdsfactory **2.0.1** @ `d7643aafba2c610ea752a9b8fc2958de3e98ee87`
  (2026-10-27), `https://github.com/gdsfactory/ihp`, Apache-2.0
- gdsfactory 9.51.0, sax 0.18.2, jax 0.9.2 (observed backend),
  klayout-python 0.30.12, system klayout 0.28.16, ngspice-42
- Referenced, not proven: upstream IHP-Open-PDK @ `5e6d592…`
  (material-card provenance) and @ `6e27ed59…` (VACASK conversion
  inputs) — recorded in profile, no claims depend on them

## Proof fixture

`tests/pdk_ihp/fixtures/nmos_ref.gds`: upstream `ihp/gds/nmos.gds`
verbatim (top `nmos`, bbox [[0, −0.105], [0.87, 0.405]] um,
13 shapes on 7 layers). Chosen because it is the smallest
BiCMOS-device artifact (1228 B), DRC-clean under the engine M1.a/M1.b
checks, and needs no build toolchain to consume.

## RED → GREEN evidence

RED (empty lane, no profile/fixture, no IHP on path):

```sh
cd rocket-engine
MPLCONFIGDIR=/tmp/mplconfig-ihp ./.venv/bin/python -m pytest tests/pdk_ihp/ -q
# 11 failed, 9 skipped in 0.09s
# every failure: FileNotFoundError docs/pdk/ihp/profile.yaml
```

GREEN (profile + fixture landed; sandbox harness = pre-cloned
2.0.1 tree on PYTHONPATH + 20-line `pdk_schema` type-stub, see
recipe §1 — all executed PDK code is the pinned wrapper):

```sh
PYTHONPATH=/tmp/pdk-sources/ihp:/tmp/ihp-stubs IHP_SOURCE=/tmp/pdk-sources/ihp \
MPLCONFIGDIR=/tmp/mplconfig-ihp JAX_PLATFORMS=cpu \
./.venv/bin/python -m pytest tests/pdk_ihp/ -q
# 20 passed in 3.20s
```

20/20 live, zero skips: 5 cell builds (BiCMOS + RF + HBT),
3 DRC (clean/dirty/fixture-shape), 2 ngspice (ptap1 divider,
npn13G2 VBIC op), 3 SAX (registry + 2 S-param goldens),
7 profile (flavors/pins/relpaths/gaps/package-exports).
Full suite deliberately NOT run (another agent owns live gates).

## Commands run (verification highlights)

- `python install_tech.py` with scratch HOME + `klayout -b -r`
  probe → techs `['', 'sg13g2', 'IHP']` ✓
- `run_drc.py --path=…nmos.gds --run_mode=flat --no_density` →
  refused on 0.28.16 (needs ≥0.29.11), `NameError: euclidean` on
  nix 0.30.7 → deck `needs-newer-klayout`, engine stand-in green
- ngspice batch: ptap1 divider `v(mid)=0.9`; HBT `i(VCC)=-5.76845e-04`;
  MOS `Unknown model type pspnqs103va` (honest n/a, VA sources ship)
- SAX: `rsil(f=5GHz,w=1,l=10)` S11/S21 goldens; `inductor_with_loss`
  goldens + passivity ✓

## Shared-change requests for the integrator (NOT made by this lane)

1. Deps: add `ihp-gdsfactory==2.0.1` (+ transitive `pdk-schema`,
   `gplugins`, `gdsfactoryplus`) to the `layout` group or a new
   `ihp` group in `pyproject.toml`; re-lock (`uv.lock`).
2. Catalogue: add `ihp` rows from `docs/pdk/ihp/matrix.md`
   (`src/interfaces/setup_catalogue.yaml` shape, owner decides).
3. Fixture fetch (optional): teach `scripts/fetch_fixtures.py` an
   `--only ihp` that records rev d7643aa (mirrors the cspdk
   `fixtures/upstream` pattern); the lane fixture stays small either way.
4. Doc index: link `docs/pdk/ihp/` from wherever PDK lanes get indexed.
5. Re-run on networked + newer-KLayout host: recipe steps 1 (pip) and 4
   (full `run_drc.py`); flip `deck_status` when green.
