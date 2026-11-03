# sky130gf provision recipe (PDK-SKY130GF)

Fresh-store provision for the SkyWater sky130 pip distribution
(`sky130` 1.0.0, gdsfactory form). Every command below is taken
from the PDK's own docs; each carries the verification status
from this lane (2026-10-31, x86-64, KLayout 0.28.16, repo venv
with gdsfactory 9.51.0).

Upstream install doc: `uv pip install sky130 --upgrade`
(PDK README, "Installation for users",
https://github.com/gdsfactory/skywater130).

## 1. Pip pin

Pinned for this lane:

```sh
uv pip install --python "$ROOT/.venv/bin/python" --no-deps "sky130==1.0.0"
```

Status: VERIFIED (scratch venvs, gf 9.51.0 + gf 9.40.2; the repo
.venv itself was never touched).

Why `--no-deps` (verified, not assumed):

- A plain `uv pip install "sky130==1.0.0"` resolves
  `gdsfactory~=9.40.1` and DOWNGRAADES the repo's gdsfactory
  9.51.0 to 9.40.2 (observed in scratch venvA). The lane verified
  the wheel is forward-compatible with 9.51.0: identical cell
  goldens under 9.40.2 and 9.51.0 (see §3), so the downgrade buys
  nothing.
- Every skipped dependency is either already satisfied or
  provably unused by the lane path:
  - `gdsfactory` — repo already at 9.51.0 (verified compatible).
  - `gdsfactoryplus` (cloud) — zero imports anywhere in the
    sky130 package (`grep -rn gdsfactoryplus` clean); skipping
    it keeps `check_no_cloud` green by construction.
  - `PySpice` — imported only by `sky130/spice_models.py`
    (unproven here); the repo `analog` group already provides
    `PySpice>=1.5` if a later slice needs it.
  - `doroutes` — imported only by `sky130/routing_utils.py`
    (unproven here); routing stays n/a in this lane.
  - `python-dotenv` — unused by the lane path.

As-shipped resolution (plain install, scratch venvA):
gdsfactory 9.40.2, gdsfactoryplus 1.8.20, PySpice 1.5,
doroutes 0.5.0. Wheel 38 MB, installed 204 MB (202 MB is the
vendored SkyWater `src/` GDS + models tree).

Rejected alternative: `volare` (efabless PDK fetcher) installs
light but only fetches the same open_pdks tree content (not a
distinct distribution), needs GitHub network + token at
provision time (`ls-remote` timed out in evaluation), and would
register a second confusing path to identical decks. See
profile.yaml `decision.rejected`.

## 2. KLayout tech install (manual — no upstream installer)

The package ships `sky130/klayout/` (sky130.lyt, tech.lyt,
layers.lyp, layers.yaml, d25/sky130.lyd25) but NO
`install_tech.py`; the README only says to restart KLayout.
Link the tech dir manually (same shape as the cspdk si340
manual step):

```sh
SKY130=$(python -c "import sky130, os; print(os.path.dirname(sky130.__file__))")
mkdir -p ~/.klayout/tech
ln -s "$SKY130/klayout" ~/.klayout/tech/sky130gf
```

Status: VERIFIED (same commands against a scratch HOME, KLayout
0.28.16 batch):

```sh
mkdir -p /tmp/fakehome/.klayout/tech
ln -s <sky130>/sky130/klayout /tmp/fakehome/.klayout/tech/sky130gf
HOME=/tmp/fakehome klayout -b -r probe_tech.py
# TECHS: ['', 'sky130']
# HAS_SKY130: True
```

The real `~/.klayout` was not touched; the recipe above is the
operator's command. The lane's `test_tech.py` repeats this
proof per-run against a tmp HOME.

## 3. Verify probe (PDK package + proof cells)

```sh
python -c "import sky130; sky130.PDK.activate();
print('sky130', sky130.__version__, '| pdk', sky130.PDK.name,
'| cells', len(sky130.cells))"
```

Expected output:

```text
sky130 1.0.0 | pdk sky130 | cells 767
```

Status: VERIFIED (ran green in scratch venvA under gdsfactory
9.40.2 and in scratch venvC under gdsfactory 9.51.0 with the
`--no-deps` install; identical output both times).

Cell-build goldens (the lane's `test_cell_build.py` executes
this shape live):

```python
import sky130
nfet = sky130.cells["sky130_fd_pr__nfet_01v8"]()
# ports ['BODY', 'DRAIN', 'GATE', 'SOURCE'], 48 polygons,
# bbox (-1.0, -1.205, 1.0, 1.205)
inv = sky130.cells["sky130_fd_sc_hd__inv_2"]()
# ports ['VGND', 'VPWR'], 46 polygons,
# bbox (-0.19, -0.24, 1.57, 2.96)
```

Status: VERIFIED — byte-identical GDS export across processes
(nfet sha256 `0bd23411…54a3e34`, 5050 bytes).

## 4. DRC position (no local deck ships)

There is no step-2-style deck install for this distribution:
the package contains ZERO `.lydrc` files; the only deck-like
file is the d25 GUI macro `klayout/d25/sky130.lyd25`, which is
not batch-runnable:

```sh
klayout -b -rd input=nfet_01v8.gds -rd report=out.lyrdb \
  -r <sky130>/sky130/klayout/d25/sky130.lyd25
# ERROR: RuntimeError: No layout loaded for running 2.5d view ...
# (exit nonzero; verified 2026-10-31, KLayout 0.28.16)
```

Upstream DRC CI (`.github/workflows/drc.yml` on master) runs
through the gdsfactoryplus cloud workflow (needs `GFP_API_KEY`),
which the engine cannot use. DRC authority therefore stays with
the open_pdks tree deck `libs.tech/klayout/drc/sky130A.lydrc`
(pdk-sky130A catalogue entry, already proven by DRC-SKY130).
The lane's `test_tech.py` guards this: it asserts the `.lyd25`
is present-but-not-batch-runnable and the profile keeps
`deck: null`.
