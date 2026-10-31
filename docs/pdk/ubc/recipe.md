# ubcpdk provision recipe (PDK-UBC)

Fresh-store provision for the SiEPIC EBeam UBC PDK, ebeam variant.
Every command below is taken from the PDK's own docs/source; each
carries the verification status from this lane (2026-10-31, x86-64,
KLayout 0.28.16, repo .venv with gdsfactory 9.51.0 + sax 0.18.2).

## 1. Pip pin (PDK README, "Installation for users")

Upstream says:

```sh
uv pip install ubcpdk --upgrade
```

Pinned for this lane:

```sh
uv pip install "ubcpdk==3.3.5"
```

Status: NOT-RUN-HERE. This sandbox has no PyPI route (`uv run
--with cowsay --no-project` fails after 3 retries: `Failed to
fetch: https://files.pythonhosted.org/…`, connect timeout), so the
download step could not execute here. The integrator re-runs it on
a networked host. Verified equivalent: the pre-cloned source this
lane's proofs ran against is ubcpdk 3.3.5 — `pyproject.toml:
version = "3.3.5"`, `ubcpdk.__version__ == "3.3.5"`, git rev
`598a773b6439a4fb5049198ecf88d5f6a30ef3fc` — and the verify probe
below ran green against it (via PYTHONPATH; identical command
works against the pip install once step 1 runs on a networked
host). Version note: the PDK README header still says 3.3.4; the
pin follows pyproject + `__init__.py` (3.3.5).

Companion pins (already in this repo's lockfile / groups):
gdsfactory 9.51.0 (`layout` group), sax 0.18.2 (`photonic` group).
The PDK's own dependency floor is `gdsfactory~=9.51.0`, so the
lane pins agree with upstream. Note: `pip install ubcpdk` also
pulls `gdsfactoryplus` (cloud) + `gplugins`; the engine lane path
needs neither (verified: both absent here, all proofs green) and
must never import gdsfactoryplus.

## 2. KLayout tech install (PDK install_tech.py, Makefile `tech`)

Upstream (`install_tech.py`) symlinks `ubcpdk/klayout/tech` into
`~/.klayout/tech/ubcpdk`:

```sh
cd /path/to/ubc
python install_tech.py
```

Status: VERIFIED (same script against a scratch HOME, KLayout
0.28.16 batch):

```sh
HOME=/tmp/ubc-fakehome python install_tech.py
# link made:
# From: /tmp/pdk-sources/ubc/ubcpdk/klayout/tech
# To:   /tmp/ubc-fakehome/.klayout/tech/ubcpdk
HOME=/tmp/ubc-fakehome klayout -b -r probe_tech.py
# VIA-TECH-technology_names: ['', 'UBCPDK']
# TECH-NAME: UBCPDK
```

The real `~/.klayout` was not touched; the recipe above is the
operator's command.

## 3. Verify probe (PDK package + cell build + models)

```sh
python -c "import ubcpdk; from ubcpdk import PDK; \
PDK.activate(); c = PDK.cells['mzi'](delta_length=10.0); \
print('ubcpdk', ubcpdk.__version__, '| pdk', PDK.name, \
'| mzi ports', sorted(p.name for p in c.ports), \
'| cells', len(PDK.cells), '| models', len(PDK.models))"
```

Observed output (verified):

```text
ubcpdk 3.3.5 | pdk ubcpdk | mzi ports ['o1', 'o2', 'o3', 'o4'] | cells 118 | models 32
```

SAX-over-ubcpdk follows the standard gdsfactory shape
(`sax.circuit(netlist, models=PDK.models)`):

```python
import jax.numpy as jnp
import sax
from ubcpdk import PDK
PDK.activate()
circuit, _ = sax.circuit(
    PDK.cells["mzi"](delta_length=10.0).get_netlist(), models=PDK.models
)
s = circuit(wl=jnp.asarray([1.55]))
```

Status: VERIFIED — the lane's `test_sax_sim.py` executes this
shape live (sax 0.18.2) and pins the 1550 nm goldens
(o1>o4 = 0.7948270469902452 at dl=10).

## 4. DRC position (PDK deck + 2-line batch header)

The PDK ships a real DRC deck,
`ubcpdk/klayout/tech/drc/SiEPIC_EBeam_DRC.lyp` (KLayout DRC DSL in
an XML macro, Lukas Chrostowski 2016 / updates to 2021), but it is
GUI-oriented: it has no `source($input)` / report-to-file batch
hooks, so the unmodified deck under batch errors and writes no
report (verified):

```sh
klayout -b -rd input=mzi.gds -rd report=report.lyrdb -r SiEPIC_EBeam_DRC.lyp-as-lydrc
# ERROR: 'report': No cell name specified - either the source was not
#   specified before 'report' or there is no default source.
```

The lane adds only the 2-line batch header — `source($input)` /
`report(name, $report)`, the same shape the sky130 deck carries
inline — with the checks verbatim (harness generated at test time,
asserted verbatim), and runs it through `KlayoutDrcAdapter` deck
mode. Status: VERIFIED — reference MZI → total 6, all `Boundary`
(bare cell, no layer-99 floorplan), zero physical violations,
deterministic across reruns; synthesized bad layout → `Si_width`
+ `Si_space` at the golden counts (see `test_drc.py`).
