# PDK-UBC lane report (SiEPIC EBeam UBC, ubcpdk)

## Files added (lane-owned only)

- `tests/pdk_ubc/__init__.py` — lane marker.
- `tests/pdk_ubc/_profile.py` — profile loading + ubcpdk
  resolution (installed → fixtures/upstream/ubc → /tmp/pdk-sources/ubc).
- `tests/pdk_ubc/test_profile.py` — 8 tests: identity, pins,
  single ebeam variant, tech/deck/model relpaths resolve, proof
  goldens recorded.
- `tests/pdk_ubc/test_mzi_build.py` — 2 tests: mzi build goldens
  (ports/polygons/bbox), GDS roundtrip, fixture agreement.
- `tests/pdk_ubc/test_sax_sim.py` — 1 test: SAX 1550 nm goldens
  (dl=10/100) + reciprocity/isolation structure.
- `tests/pdk_ubc/test_drc.py` — 2 tests: PDK deck on reference
  MZI (6×Boundary, zero physical) + bad layout (Si_width/Si_space).
- `tests/pdk_ubc/fixtures/mzi_ref.gds` — byte copy of
  `tests/gds_ref_si220/mzi.gds` in gdsfactory/ubc @598a773 (MIT),
  sha256 `722b1aea…fbc1bb1`, 24676 bytes.
- `docs/pdk/ubc/profile.yaml` — ebeam variant, pins, tech/deck/model
  relpaths, proof goldens.
- `docs/pdk/ubc/recipe.md` — provision commands from the PDK's own
  docs, each with run status.
- `docs/pdk/ubc/matrix.md` — proposed matrix rows (lvs n/a photonic).
- `docs/pdk/ubc/report.md` — this file.

## Pins (all verified by running)

- ubcpdk 3.3.5 (`__version__`, pyproject; README header says 3.3.4,
  stale — pin follows pyproject + `__init__.py`).
- Pre-cloned source rev `598a773b6439a4fb5049198ecf88d5f6a30ef3fc`.
- gdsfactory 9.51.0, sax 0.18.2 (repo .venv, read-only use),
  KLayout 0.28.16 (`klayout -b -v`).
- PDK surface: 118 cells, 32 SAX models (`get_models`).

## RED → GREEN evidence

RED (empty lane: tests only, no profile/fixture), 2026-10-31:

```sh
cd /home/alrida-ismail/github/rocketEDA/rocket-engine
.venv/bin/pytest tests/pdk_ubc -q
# 13 failed in 1.73s — every test on FileNotFoundError for
# docs/pdk/ubc/profile.yaml (nothing else ran).
```

GREEN (after fixture + docs/pdk/ubc landed), same command:

```sh
.venv/bin/pytest tests/pdk_ubc -q
# 13 passed
```

Only the lane's tests were run (no full suite — live-gate repairs
in progress elsewhere in the tree). KLayout batch runs used the
system 0.28.16 binary (read-only input); the repo .venv was used
read-only (no sync/install); PyPI was unreachable so pip install
is documented NOT-RUN-HERE with the integrator re-run.

## Test results (GREEN)

- `test_profile.py`: 8/8 — identity/pins/variant, all relpaths
  resolve against the 3.3.5 tree, deck anchor + Si 60 nm rules
  present, 32 models, layout/optical/drc proof records.
- `test_mzi_build.py`: 2/2 — mzi(dl=10): ports o1..o4, 34 polys,
  bbox ≈ [[-10.0,-29.4],[99.1,25.1]]; roundtrip preserves
  name+polys+bbox; upstream fixture agrees (34 polys, same bbox).
- `test_sax_sim.py`: 1/1 — dl=10 o1>o4=0.7948270469902452,
  o1>o3=0.18527868264398265; dl=100 pair pinned; reciprocity +
  zero reflection/isolation hold; deterministic rerun identical.
- `test_drc.py`: 2/2 — reference MZI: total 6, all Boundary, zero
  physical (deterministic ×2 runs); bad layout: total 5 =
  {Boundary:3, Si_space:1, Si_width:1}.

## Shared-change requests for the integrator (exact edits)

Lane ownership forbids touching these paths; each item below is
the exact change requested (files + content shape):

1. `scripts/fetch_fixtures.py` — add `--only ubc`: clone
   `https://github.com/gdsfactory/ubc` @
   `598a773b6439a4fb5049198ecf88d5f6a30ef3fc` into
   `fixtures/upstream/ubc` (git-ignored vendor data, same shape as
   the existing `--only cspdk` mode). Lane `_profile.py` already
   resolves that path first.
2. Catalogue / ENGINE-SETUP matrix — place the four rows from
   `docs/pdk/ubc/matrix.md` verbatim (layout ✓, drc ✓+D1,
   optical-sim ✓+O1, lvs n/a) with caveats D1/O1/P1/P2 attached.
3. `src/adapters/gdsfactory/__init__.py` — generalize
   `run_layout_smoke` beyond its cspdk-wired shape (accept a
   `pdk="ubcpdk"` / `ubc_path` pair mirroring `cspdk_path`, or a
   profile-driven attach per PDK-PROFILE); the UBC lane builds
   through ubcpdk directly until then. No adapter behavior change
   for existing callers.
4. Deps — none. The lane path needs only the existing `layout`
   (gdsfactory 9.51.0) + `photonic` (sax 0.18.2) groups;
   `gdsfactoryplus`/`gplugins`/`jsondiff`/`pytz` are absent here
   and unneeded (only `ubcpdk/simulation/modes_waveguide.py`
   imports gplugins — off the lane path). Operator step on a
   networked host: `uv pip install "ubcpdk==3.3.5"`.
