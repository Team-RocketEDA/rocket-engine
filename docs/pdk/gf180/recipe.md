# gf180mcu provision recipe (PDK-GF180)

Fresh-store provision for GlobalFoundries 180nm MCU via the
gdsfactory wrapper. Every command below is taken from the PDK's own
docs/source; each carries the verification status from this lane
(2026-10-31, x86-64, KLayout 0.28.16, ngspice-42, Python 3.12).

Two provision paths exist because the source tree is post-release:
the PyPI release and the pre-cloned source disagree on the
gdsfactory floor (see pins). Both paths are verified GREEN for the
lane proofs (identical layout geometry, identical sim results).

## 0. Source (pre-cloned — do not re-clone)

`/tmp/pdk-sources/gf180` at `d422b86` (2026-10-31). Its
`pyproject.toml` requires `gdsfactory>=9.45,<=9.51`, which the
repo's `layout` group (`gdsfactory>=9.51,<10`, locked 9.51.0)
satisfies. Submodules (`gf180mcu/src/*`: stdcells, IO, fd_pr)
are intentionally NOT initialized — the lane inventoriess them
as unproven (see profile `libraries`).

## 1. Pip pin (PDK README, "Installation for users")

Upstream says:

```sh
uv pip install gf180mcu --upgrade
```

Pinned for this lane (release path):

```sh
uv pip install "gf180mcu==1.0.0"
```

Status: VERIFIED (ephemeral env, no project env touched):

```sh
export UV_CACHE_DIR=/tmp/uv-cache MPLCONFIGDIR=/tmp/mpl
uv run --with "gf180mcu==1.0.0" --no-project -- python -c \
  "import gf180mcu, gdsfactory; print(gf180mcu.__version__, gdsfactory.__version__)"
# 1.0.0 9.40.2
```

The release pulls `gdsfactory~=9.40.0` (observed 9.40.2), which
CONFLICTS with the repo `.venv` lock (gdsfactory 9.51.0): the
release path needs its own env. The lane fixture builds with
identical geometry there (see report), and the sim proof adapts
(the release ships the vendor model files but NOT the
post-release `fets.lib`/`settings.inc` corner wrappers).

Source-tree path (used by the lane tests here): no install step —
the provisioned tree plus `gdsfactory==9.51.0`:

```sh
PYTHONPATH=/tmp/pdk-sources/gf180 PDK_GF180_SRC=/tmp/pdk-sources/gf180 \
  python -c "import gf180mcu; from gf180mcu import PDK; \
  print(gf180mcu.__version__, PDK.name, len(PDK.cells))"
# 1.0.0 gf180mcu 504
```

Status: VERIFIED (repo `.venv` interpreter, read-only use).

## 2. KLayout tech install (PDK Makefile `tech` target)

Upstream `install_tech.py` symlinks the wrapper `klayout/` dir into
`~/.klayout/tech/gf180mcu`:

```sh
cd <gf180mcu-source> && python install_tech.py
```

Status: VERIFIED (scratch HOME, KLayout 0.28.16 batch):

```sh
HOME=/tmp/fakehome python install_tech.py
# link made: .../gf180mcu/klayout -> /tmp/fakehome/.klayout/tech/gf180mcu
HOME=/tmp/fakehome klayout -b -r probe_tech.py
# TECHS: ['', 'gf180mcu']
# HAS_GF180MCU: True
```

The real `~/.klayout` was not touched; the recipe above is the
operator's command.

## 3. Verify probe (fixture build + sim)

Build (lane fixture script, imports the provisioned package):

```sh
python tests/pdk_gf180/fixtures/inv_pair.py /tmp/gf180_inv_pair.gds
```

Expected output:

```text
cell: gf180_inv_pair
bbox_um: [[-1.15, -0.71], [1.97, 4.30]]
layers: [(21, 0), (22, 0), (30, 0), (31, 0), (32, 0), (33, 0), (34, 0)]
ports: ['IN', 'OUT', 'VDD', 'VSS']
```

Status: VERIFIED (both provision paths, byte-identical geometry;
GDS bytes differ across gdsfactory versions — timestamps/cell
order — so geometry numbers, not bytes, are golden).

Sim (typical corner, same W/L as the layout: Wn 0.5 / Wp 1.0 /
L 0.28 um; source-tree wrapper form — the release form inlines
the switch params and includes `sm141064.ngspice` directly):

```spice
.lib '<pkg>/models/ngspice/fets.lib' typical
VDD vdd 0 3.3
VIN in 0 0
XM1 out in 0 0 nmos_3p3 w=0.5u l=0.28u
XM2 out in vdd vdd pmos_3p3 w=1.0u l=0.28u
.DC VIN 0 3.3 0.33
```

Expected: `v(out)` 3.30 at Vin 0, ~0 at Vin 3.3, switching
between 1.32 V (out 2.82) and 1.65 V (out 0.45). Both paths give
bit-identical tables. Status: VERIFIED (`ngspice -b`).

## 4. Lane tests

```sh
PYTHONPATH=/tmp/pdk-sources/gf180 PDK_GF180_SRC=/tmp/pdk-sources/gf180 \
  .venv/bin/python -m pytest tests/pdk_gf180 -q
# 14 passed
```

## Caveats (honest gaps)

- No foundry DRC/LVS deck ships in the wrapper (upstream DRC is a
  gdsfactoryplus cloud workflow). Signoff decks come from the
  `gf180mcu_fd_pr` submodule / volare builds (user-supplied).
- The engine stand-in rule (metal1 0.23/0.23) is stricter in one
  corner than the PDK's own FET geometry (gate-contact diagonal
  0.209): the clean proof pins 16 PDK-interior space hits and
  requires 0 on lane routing. This is asserted, not waived.
- Guard rings omitted in the fixture (`grw=0`) for single-layer
  routability; bulks are explicit taps. The n-well rect is
  hand-drawn with generous enclosure.
- Xyce models ship but are unproven here (upstream docs flag the
  passive translations as broken); ngspice typical only.
