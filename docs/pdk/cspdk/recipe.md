# cspdk provision recipe (PDK-CSPDK)

Fresh-store provision for the CORNERSTONE PDK, si340 variant. Every
command below is taken from the PDK's own docs/source; each carries
the verification status from this lane (2026-10-31, x86-64, KLayout
0.28.16, repo env with gdsfactory 9.51.0 + sax 0.18.2).

## 1. Pip pin (PDK README, "Installation for users")

Upstream says:

```sh
uv pip install cspdk --upgrade
```

Pinned for this lane:

```sh
uv pip install "cspdk==2.1.0"
```

Status: NOT-RUN-HERE. This sandbox has no PyPI route (`uv run
--with "cspdk==2.1.0" --no-project` fails after 3 retries:
`Failed to fetch: .../cspdk-2.1.0-py3-none-any.whl.metadata ...
operation timed out`), so the download step could not execute here.
The integrator re-runs it on a networked host. Verified equivalent:
the pre-cloned source this lane verified against is cspdk 2.1.0 —
`pyproject.toml: version = "2.1.0"`, `cspdk.__version__ == "2.1.0"`,
git rev `3323b17b` — byte-identical to the repo's
`fixtures/upstream/cspdk` tree (`diff -rq` clean), and every probe
below ran green against it.

Companion pins (already in this repo's `uv.lock` + groups):
gdsfactory 9.51.0 (`layout` group), sax 0.18.2 (`photonic` group).
The PDK's own dependency floor is `gdsfactory~=9.51.0`, so the lane
pins agree with upstream. Note: `pip install cspdk` also pulls
`gdsfactoryplus` (cloud); the engine must never import it
(`tests/test_no_cloud.py` stays green — the si340 lane path imports
gdsfactory + sax only).

## 2. KLayout tech install (PDK install_tech.py pattern)

Upstream `install_tech.py` symlinks variant `klayout/` dirs into
`~/.klayout/tech/` — but only wires si220 and sin300. si340 needs
the same shape done manually:

```sh
CSPDK=$(python -c "import cspdk, os; print(os.path.dirname(cspdk.__file__))")
mkdir -p ~/.klayout/tech
ln -s "$CSPDK/si340/klayout" ~/.klayout/tech/cspdk_si340
```

Status: VERIFIED (same commands against a scratch HOME, KLayout
0.28.16 batch):

```sh
mkdir -p /tmp/fakehome/.klayout/tech
ln -s <cspdk>/cspdk/si340/klayout /tmp/fakehome/.klayout/tech/cspdk_si340
HOME=/tmp/fakehome klayout -b -r probe_tech.py
# TECHS: ['', 'Cornerstone_si340']
# HAS_SI340: True
```

The real `~/.klayout` was not touched; the recipe above is the
operator's command. Quirk for the integrator: si340 is missing from
upstream `install_tech.py` (only si220/sin300 are linked). Either
keep the manual step or propose the two-line upstream patch.

Second quirk: `cspdk.si340.config.PATH.lyp/lyt` point at
`klayout/tech/*`, which does not exist on disk; the real files sit
directly under `cspdk/si340/klayout/`. The profile records the real
paths (asserted by `test_profile.py`).

## 3. Verify probe (PDK si340 package + sample flow)

```sh
python -c "import cspdk; from cspdk.si340 import PDK, cells; \
PDK.activate(); c = cells.mzi(); \
print('cspdk', cspdk.__version__, '| pdk', PDK.name, \
'| mzi ports', sorted(p.name for p in c.ports), \
'| models', len(PDK.models))"
```

Expected output:

```text
cspdk 2.1.0 | pdk cornerstone_si340 | mzi ports ['o1', 'o2', 'o3'] | models 39
```

Status: VERIFIED (ran green via the pre-cloned 2.1.0 tree on
PYTHONPATH; identical command works against the pip install once
step 1 runs on a networked host).

SAX-over-cspdk follows the PDK's own sample
(`cspdk/si340/samples/circuit_simulations_sc340.py`):

```python
from cspdk.si340 import PDK, cells
import sax
PDK.activate()
circuit, _ = sax.circuit(
    cells.mzi_sc(delta_length=10.0).get_netlist(), models=PDK.models
)
```

Status: VERIFIED — the lane's `test_sax_sim.py` executes this shape
live (sax 0.18.2) and pins the 1550 nm goldens (cross 0.81408256,
bar 0.05688103).

## 4. DRC position (no PDK deck for si340)

There is no step-2-style deck install for si340: the package ships
`tech.lyt` + `layers.lyp` only, and upstream DRC runs through the
gdsfactoryplus cloud workflow (needs `GFP_API_KEY`), which the
engine must never touch. The lane instead runs the engine KLayout
batch check (`KlayoutDrcAdapter`, `run_drc`) with the profile's
engine rules — GDS 3/0, 350 nm feature / 200 nm gap from the
49th-call guidelines Table 4 (verified against the source PDF with
pdftotext). Status: VERIFIED — reference MZI → 0 violations;
synthesized bad layout → 1 width + 1 space at the golden bboxes
(see `test_drc.py`).
