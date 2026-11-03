# PDK-ASAP7 lane report (ASAP7 predictive 7nm FinFET, predictive-only)

SPIKE-FIRST outcome: gdsfactory does not cover ASAP7 (verified:
zero refs in the installed gdsfactory package, the engine
`docs/gdsfactory-api-map.md`/`src`, and the upstream open-PDK
list), so this lane proves the pre-cloned trees directly with
stdlib parsing + KLayout batch + 7z. Nothing here is
manufacturable or measured silicon; every matrix row is labeled
predictive-only and must render below any measured-silicon row.

## Files added (lane-owned only)

- `tests/pdk_asap7/__init__.py` — lane marker.
- `tests/pdk_asap7/_profile.py` — profile loading + wrapper/lib
  resolution (`/tmp/pdk-sources/asap7`, `/tmp/pdk-sources/
  asap7sc7p5t_28`; no pip package exists) + KLayout-batch runner.
- `tests/pdk_asap7/test_profile.py` — 8 tests: predictive-only
  identity, verified revs/pins, single 4-Vt variant,
  wrapper/lib relpaths resolve, honest deck/model status,
  proof goldens recorded.
- `tests/pdk_asap7/test_cells_inventory.py` — 8 tests: Verilog
  812 modules (42/37/34/33/56/1 × 4 VTs), headline cells, LEF
  213 × 4, exact RVT Verilog⊆LEF + 10 physical-only, 24
  techlef layers, 73 NLDM + 218 CCS archives, single-entry
  `7z l` × 2, TBUF NLDM extract → 1 cell @0.7 V.
- `tests/pdk_asap7/test_gds_proof.py` — 3 tests: GDS 213 cells
  == LEF macros (all 4 VTs, KLayout batch JSON), INVx1_R
  geometry golden, fixture agreement.
- `tests/pdk_asap7/fixtures/invx1_r.gds` — single cell
  `INVx1_ASAP7_75t_R` copied from upstream
  `GDS/asap7sc7p5t_28_R_220121a.gds` (BSD-3, ASU), sha256
  `c1c99056…3ff5caa4b`, 3476 bytes.
- `docs/pdk/asap7/profile.yaml` — variant, pins, tech/deck/
  model relpaths, spike record, proof goldens.
- `docs/pdk/asap7/recipe.md` — provision commands from the
  PDK's own docs/source, each with run status.
- `docs/pdk/asap7/matrix.md` — proposed matrix rows (all
  predictive-only; drc/lvs/sim/schematic honest n/a).
- `docs/pdk/asap7/report.md` — this file.

## Pins (all verified by running)

- Wrapper `d24f8b857ff74cf5b21ab18a7e1b11a3954c449b`
  (2025-03-12); submodules NOT initialized (5 empty dirs).
- Lib `e5bd25da72cd297b8c0ec6f77600e0cbaa1124d0`
  (2026-10-17, TBUF PR #8); r1p7 `58d72c9d291e186a774685
  86ab0c43d8a21eda6a` (2024-07-18, shallow probe clone).
- KLayout 0.28.16 (`klayout -b -v`, Ubuntu noble-updates),
  ngspice 42 (`42+ds-3build1`, OSDI symbols present, RC
  divider sim `v(out)=0.35` green), xschem V3.4.8RC
  (text mode), 7z present.
- Absent (verified MISSING): openroad, yosys, openvaf.
- Library surface: 812 Verilog modules, 213 macros/cells per
  VT, 24 techlef layers, 291 LIB archives, TT 0.7 V / 25 °C.

## RED → GREEN evidence

RED (tests only, no profile/fixture docs), 2026-10-31:

```sh
cd /home/alrida-ismail/github/rocketEDA/rocket-engine
.venv/bin/pytest tests/pdk_asap7 -q
# 19 failed in 0.11s — every test on FileNotFoundError for
# docs/pdk/asap7/profile.yaml (nothing else ran).
```

GREEN (after docs/pdk/asap7 landed + one real census fix),
same command:

```sh
.venv/bin/pytest tests/pdk_asap7 -q
# 19 passed in 3.05s
```

The first GREEN run caught a genuine lane bug: the NLDM census
was 74 by `ls|wc` but the `.lib.7z` glob is 73 — NLDM also
carries an uncompressed `IO_cell/` subdir (my assumption was
wrong, not the PDK). Fixed in test + profile + recipe + matrix;
re-run green.

Only the lane's tests were run (no full suite — live-gate
repairs in progress elsewhere). The repo .venv was used
read-only (pytest runner only; no sync/install); PyPI is
unreachable so no ephemeral env could be provisioned. The
shared pre-cloned trees were never written (LIB extraction and
the r1p7 probe clone went to /tmp scratch).

## Test results (GREEN)

- `test_profile.py`: 8/8 — predictive-only identity, revs
  (wrapper/lib/r1p7), tool pins, 4-Vt variant, all relpaths
  resolve, deck `missing-open-source`, models
  `blocked-openvaf-missing`, goldens recorded.
- `test_cells_inventory.py`: 8/8 — Verilog 812 with exact
  per-group counts; 203 RVT modules ⊆ LEF with exactly the 10
  named DECAP/FILLER/TAPCELL extras; techlef 24 layers in
  order; 73+218 archives match the filename regex; 2
  single-entry listings; TBUF extract → `TBUFx1_ASAP7_75t_R`.
- `test_gds_proof.py`: 3/3 — 4 GDS × 213 cells, names
  byte-identical to LEF; INVx1_R bbox (0,-88;824,1168) dbu =
  (0.0,-0.022,0.206,0.292) µm, 51 shapes, exact 16-layer
  table; fixture reproduces all of it (3476 bytes).

## Spike record (enablement verdicts)

- Digital via OpenROAD: ORFS `flow/platforms/asap7` exists
  upstream (page HTTP 200, `drc/`+`gds/`+`KLayout/`
  collateral, 2026-10-31) — claimed-upstream, NOT-RUN here
  (no openroad/yosys). Library LEF/LIB/techlef/Verilog are
  the verified flow inputs.
- gdsfactory: no ASAP7 coverage (verified three ways) — the
  engine gdsfactory adapter path is n/a for this lane.
- Custom via KLayout+xschem+ngspice/OSDI: tools present
  (KLayout/xschem/ngspice-42+OSDI all smoke-verified) but the
  PDK side is missing — r1p7 is Cadence+Calibre+HSPICE only
  (no KLayout tech, no xschem, HSPICE-only BSIMCMG level=72
  v107 cards, Calibre placeholder READMEs). OpenVAF absent →
  no FinFET model can compile. All custom rows honestly n/a.

## Shared-change requests for the integrator (exact edits)

Lane ownership forbids touching these paths; each item below is
the exact change requested (files + content shape):

1. `scripts/fetch_fixtures.py` — add `--only asap7`: clone
   `https://github.com/The-OpenROAD-Project/asap7` @
   `d24f8b857ff74cf5b21ab18a7e1b11a3954c449b` into
   `fixtures/upstream/asap7`, run `git submodule update
   --init --depth 1 asap7_pdk_r1p7` inside it, and clone
   `https://github.com/The-OpenROAD-Project/asap7sc7p5t_28.git`
   @ `e5bd25da72cd297b8c0ec6f77600e0cbaa1124d0` into
   `fixtures/upstream/asap7sc7p5t_28` (git-ignored vendor
   data, same shape as the existing `--only cspdk` mode;
   warn: lib tree is 5.7 GB).
2. Catalogue / ENGINE-SETUP matrix — place the seven rows
   from `docs/pdk/asap7/matrix.md` verbatim (inventory ✓
   predictive-only, layout-view ✓ predictive-only,
   digital-flow claimed-upstream, drc/lvs/sim/schematic n/a)
   with caveats P0/D1–D4 attached, rendered below every
   measured-silicon row.
3. Deps — none. The lane path needs only stdlib + PyYAML +
   the system `klayout`/`7z` binaries; no pip package exists
   for ASAP7 and none is proposed. No adapter change is
   requested either (gdsfactory path is n/a for ASAP7).
