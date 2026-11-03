# ihp provision recipe (PDK-IHP)

Fresh-store provision for IHP SG13G2 (BiCMOS core + RF flavors via
the gdsfactory wrapper). Every command below is taken from the PDK's
own docs/source; each carries the verification status from this lane
(2026-10-31, x86-64, system KLayout 0.28.16 + nix KLayout 0.30.7,
ngspice-42, repo .venv with gdsfactory 9.51.0 + sax 0.18.2 + jax
0.9.2 + klayout-python 0.30.12).

## 1. Pip pin (PDK README, "Quick start")

Upstream says:

```sh
uv pip install ihp-gdsfactory --upgrade
```

Pinned for this lane:

```sh
uv pip install "ihp-gdsfactory==2.0.1"
```

Status: NOT-RUN-HERE. This sandbox has no PyPI route (`uv run
--with ...` fails: `Failed to fetch: https://pypi.org/simple/...`,
connect timeout), so the download step could not execute here. The
integrator re-runs it on a networked host. Verified equivalent: the
pre-cloned source this lane ran against is byte-pinned
ihp-gdsfactory 2.0.1 — `pyproject.toml: version = "2.0.1"`,
`ihp.__version__ == "2.0.1"`, git rev
`d7643aafba2c610ea752a9b8fc2958de3e98ee87` (2026-10-27, "Port
importing IHP sample project (#289)") — and every probe below ran
green against it.

Companion pins (already in this repo's lockfile / groups):
gdsfactory 9.51.0 (`layout` group), sax 0.18.2 (`photonic` group).
The wrapper's own floor is `gdsfactory~=9.51.0`, so the lane pins
agree with upstream. Note: `pip install ihp-gdsfactory` also pulls
`gdsfactoryplus` (cloud) plus `gplugins` and `pdk-schema`; the
engine lane path imports gdsfactory + sax + klayout only
(`test_no_cloud.py` posture unchanged — the wrapper never imports
gdsfactoryplus itself).

Sandbox harness note: with no PyPI, `pdk-schema` could not be
installed here, and `import ihp` needs it (type-only: MaterialCard
et al). Lane runs used a 20-line permissive stub on PYTHONPATH
(`/tmp/ihp-stubs/pdk_schema.py`, NOT committed) purely to satisfy
those type imports; all geometry/model code executed is the real
pinned wrapper. The integrator's pip install makes the stub moot.

## 2. KLayout tech install (PDK install_tech.py)

Upstream `install_tech.py` (repo root) symlinks `ihp/klayout/tech`
into `~/.klayout/tech/ihp`:

```sh
python install_tech.py
```

Status: VERIFIED (same script against a scratch HOME, real
`~/.klayout` untouched):

```sh
HOME=/tmp/fakehome-ihp2 python install_tech.py
# link made:
# From: /tmp/pdk-sources/ihp/ihp/klayout/tech
# To:   /tmp/fakehome-ihp2/.klayout/tech/ihp
HOME=/tmp/fakehome-ihp2 klayout -b -r probe_tech.py
# TECHS: ['', 'sg13g2', 'IHP']
# HAS_IHP: True
```

Both tech names (`IHP` from `tech.lyt`, `sg13g2` from `sg13g2.lyt`)
register under system KLayout 0.28.16 batch.

## 3. Verify probe (PDK README quick-start snippet)

```sh
python -c "import gdsfactory as gf; from ihp import PDK; \
from ihp.cells import nmos, rfnmos, npn13G2, rsil, cmim; \
PDK.activate(); c = nmos(width=1.0, length=0.13, nf=4); \
print('ihp', __import__('ihp').__version__, '| pdk', PDK.name, \
'| nmos ports', sorted(p.name for p in c.ports), \
'| npoly', len(c.get_polygons()))"
```

Expected output:

```text
ihp 2.0.1 | pdk IHP | nmos ports ['D', 'G', 'S'] | npoly 7
```

Status: VERIFIED (ran green against the pre-cloned 2.0.1 tree via
PYTHONPATH + the import stub; identical command works against the
pip install once step 1 runs on a networked host). The lane's
`test_cells_build.py` executes this shape live for all five goldens
(nmos / rfnmos / npn13G2 / rsil / cmim + stdcell import).

## 4. DRC position (PDK deck ships, needs newer KLayout)

The wrapper ships a local deck + runner
(`ihp/klayout/tech/drc/`, README "Usage / CLI"):

```sh
cd ihp/klayout/tech/drc
python3 run_drc.py --path=<design>.gds --run_mode=flat \
  --run_dir=<run_dir> --no_density
```

Status: ATTEMPTED, VERIFIED-INSUFFICIENT-HERE. The runner refuses
system KLayout 0.28.16 (`Minimum required KLayout version is
0.29.11`); under nix KLayout 0.30.7 the deck starts (FEOL/BEOL/PIN
tables, rules NW.b … PWB.e) then dies with `NameError: undefined
local variable or method 'euclidean'` — the deck's edge metric
needs a KLayout newer than 0.30.7 (deck README claims 0.30.3+,
which is stale). The integrator re-runs the exact command above on
a newer-KLayout host; the profile marks the deck
`needs-newer-klayout`.

Verified stand-in: engine-side KLayout batch checks with the deck's
own values — M1.a min width 0.16 um, M1.b min space 0.18 um on GDS
8/0 (`rule_decks/beol/5_16_metal1.drc` + `sg13g2_tech_default.json`
M1_a/M1_b). Status: VERIFIED — reference fixture → 0 violations;
synthesized bad layout → 1 width + 1 space at golden bboxes (see
`test_drc.py`). Caveat: default (square) metrics vs the deck's
euclidean — identical on Manhattan geometry.

## 5. ngspice models (corner-lib sections, verified live)

The `*_mod.lib` files need their corner parents (global params +
`.include` chain). Run from the models dir:

```sh
cd ihp/models/ngspice/models
```

then in the deck:

```spice
.lib cornerRES.lib res_typ     ; ptap1/ntap1/Rparasitic (pure SPICE)
.lib cornerHBT.lib hbt_typ     ; npn13G2/L/V VBIC + pnpMPA
.lib cornerMOSlv.lib mos_tt    ; LV MOS — needs pspnqs103va (NOT stock ngspice)
.lib cornerCAP.lib cap_typ     ; cap_cmim / cap_rfcmim
```

Status: VERIFIED — ptap1 divider DC op gives `v(mid) = 0.9 V`
exact; npn13G2 (Nx=1, Vbe=0.85 V, Vce=1.0 V) gives
`i(VCC) = -5.76845e-04 A` (see `test_ngspice_sim.py`). Honest n/a:
`sg13_lv_*` MOS (PSP103) and `rsil/rppd/rhigh` (r3_cmc) abort on
stock ngspice-42 with `Unknown model type ... - ignored`; the PDK
ships the Verilog-A sources under `ihp/models/ngspice/va/` for an
openvaf flow the lane does not claim.

## 6. SAX RF models (ihp.models.sax docstring shape)

```python
import jax.numpy as jnp
from ihp.models.sax import models, rsil
f = jnp.linspace(1e9, 20e9, 201)
s_res = rsil(f=f, width=1.0, length=10.0)
```

Status: VERIFIED — 10-model registry (`cmim cmom inductor2
inductor3 inductor_with_loss resistor rfcmim rhigh rppd rsil`);
5 GHz goldens pinned in `test_sax_sim.py`.
