# ASAP7 provision recipe (PDK-ASAP7, predictive-only)

Fresh-store provision for the ASAP7 predictive 7nm FinFET PDK
(ASU+ARM, BSD-3-Clause), 7.5-track stdcell library v28. Every
command below is taken from the PDK's own docs/source or is the
standard git/7z/KLayout invocation the sources assume; each
carries the verification status from this lane (2026-10-31,
x86-64, KLayout 0.28.16, ngspice 42, xschem 3.4.8RC).

 predictive-only: nothing here is manufacturable or measured
 silicon. Do not present these rows as better-proven than a
 measured-silicon PDK.

## 0. What the pre-cloned sources contain (verified, do not re-clone)

```sh
ls /tmp/pdk-sources/asap7            # wrapper: README + LICENSE + .gitmodules
ls /tmp/pdk-sources/asap7sc7p5t_28   # full lib: CDL GDS LEF LIB Verilog ...
git -C /tmp/pdk-sources/asap7 log -1 --format='%H %ad %s'
# d24f8b857ff74cf5b21ab18a7e1b11a3954c449b ... Improve wording for snps enablement
git -C /tmp/pdk-sources/asap7sc7p5t_28 log -1 --format='%H %ad %s'
# e5bd25da72cd297b8c0ec6f77600e0cbaa1124d0 ... Merge pull request #8 (TBUFx1)
```

Status: VERIFIED. The wrapper's five submodule dirs
(`asap7_pdk_r1p7`, `asap7sc6t_26`, `asap7sc7p5t_27`,
`asap7sc7p5t_28`, `asap7_sram_0p0`) are EMPTY — submodules were
never initialized. The lib tree is complete (5.7 GB, 291
compressed LIB archives, GDS/LEF/Verilog uncompressed).

## 1. PDK core: initialize the r1p7 submodule (PDK README + git)

The wrapper README points at `./asap7_pdk_r1p7` with setup
instructions in `README_ASAP7PDK_INSTALL_201210a.txt`. The
mechanical fetch is the standard submodule init:

```sh
cd /path/to/asap7   # wrapper clone
git submodule update --init --depth 1 asap7_pdk_r1p7
```

Status: EQUIVALENT-VERIFIED. The shared pre-cloned wrapper was
left untouched; the identical fetch was run as a shallow clone
into scratch and inspected instead:

```sh
git clone --depth 1 https://github.com/The-OpenROAD-Project/asap7_pdk_r1p7.git /tmp/asap7r1p7-probe
# 9.5 MB @ 58d72c9d291e186a77468586ab0c43d8a21eda6a (2024-07-18)
ls /tmp/asap7r1p7-probe
# Calibre_Usage_Instructions.txt README_ASAP7PDK_INSTALL_201210a.txt
# asap7ssc7p5t_05/ calibre/ cdslib/ docs/ models/
```

What r1p7 actually contains (all verified by inspection):
`cdslib/` (Cadence Virtuoso techlib + `setup/setup_asap7.csh`),
`models/hspice/` (6 HSPICE BSIMCMG level=72 v107 cards:
TT/SS/FF × {160803,v1.0}, 8 `.model` cards each = 4 VTs × N/P),
`docs/` (DRM PDF + paper), `calibre/ruledirs/` with ONLY
placeholder `README.txt` files. There is NO KLayout tech, NO
xschem collateral, NO Verilog-A, and NO open-source DRC/LVS deck
in r1p7 — custom/open-source enablement is not in-repo.

Provision commands inside r1p7 are Cadence-only (from
`README_ASAP7PDK_INSTALL_201210a.txt`, NOT run — commercial):

```csh
setenv PDK_DIR PDKDirectory
source $PDK_DIR/cdslib/setup/setup_asap7.csh   # once, in run dir
source set_pdk_path.csh
virtuoso &
```

## 2. Calibre decks: manual download (PDK README, NOT-RUN-HERE)

Upstream (wrapper README + `calibre/ruledirs/*/README.txt`):

> Calibre Decks are not a part of this repository and must be
> downloaded from http://asap.asu.edu/asap/ ... Use the "calibre"
> directory thus downloaded to replace the "calibre" directory
> provided in this Github repository.

Status: NOT-RUN-HERE (manual click-through download + commercial
Calibre). The integrator performs it on a licensed host. Until
then the lane's DRC row is honestly `missing-open-source`.

## 3. Stdcell library: already cloned; verify the census (lane)

```sh
cd /tmp/pdk-sources/asap7sc7p5t_28
ls Verilog/*.v | wc -l                        # 24
grep -h '^module ' Verilog/*.v | wc -l        # 812
grep -c '^MACRO ' LEF/*.lef                   # 213 each × 4
ls LIB/NLDM/*.lib.7z | wc -l                  # 73 (+ uncompressed IO_cell/ subdir)
ls LIB/CCS/*.lib.7z | wc -l                   # 218
grep -c '^LAYER ' techlef_misc/asap7_tech_1x_201209.lef   # 24
```

Status: VERIFIED — outputs match the lane goldens exactly
(AO 42 / INVBUF 37 / OA 34 / SEQ 33 / SIMPLE 56 / TBUF 1 per
VT × LVT/RVT/SLVT/SRAM).

## 4. LIB archives: list + extract with 7z (lane, VERIFIED)

Archives are single-entry 7z; list without extracting:

```sh
7z l LIB/NLDM/asap7sc7p5t_SIMPLE_RVT_TT_nldm_211120.lib.7z
# ....A  2306883  333739  asap7sc7p5t_SIMPLE_RVT_TT_nldm_211120.lib
# 1 files
```

Extract to scratch (never into the pre-cloned tree) and check
the cell census against Verilog:

```sh
mkdir -p /tmp/asap7-libprobe && cd /tmp/asap7-libprobe
7z x -y /tmp/pdk-sources/asap7sc7p5t_28/LIB/NLDM/asap7sc7p5t_SIMPLE_RVT_TT_nldm_211120.lib.7z
grep -c 'cell (' asap7sc7p5t_SIMPLE_RVT_TT_nldm_211120.lib   # 56
# cell names identical to asap7sc7p5t_SIMPLE_RVT_TT_201020.v modules (diff-clean)
grep -m1 'voltage_map' *.lib    # voltage_map (VDD, 0.7)
grep -m1 'temperature :' *.lib  # temperature : 25
```

Status: VERIFIED. Corner facts: TT = 0.7 V / 25 °C,
`delay_model : table_lookup` (NLDM).

## 5. GDS proof with KLayout batch (lane, VERIFIED)

```sh
klayout -b -v   # KLayout 0.28.16
klayout -b -r gds_inventory.py
# L/R/SL/SRAM: ncells=213, dbu=0.00025, names == LEF macros (exact)
# INVx1_ASAP7_75t_R: bbox dbu (0,-88;824,1168),
#   um (0.0,-0.022,0.206,0.292), 51 shapes, 16 layers
```

Status: VERIFIED — the lane's `test_gds_proof.py` executes this
shape live and pins the goldens. Fixture
`tests/pdk_asap7/fixtures/invx1_r.gds` (3476 bytes, BSD-3,
single cell copied from `GDS/asap7sc7p5t_28_R_220121a.gds`)
reproduces the INV golden exactly.

## 6. Custom-lane spike: xschem + ngspice present, OSDI blocked

```sh
xschem -v              # XSCHEM V3.4.8RC (text mode without X)
ngspice -b rc_divider.cir   # v(out) = 3.500000e-01  (verified smoke)
strings /usr/bin/ngspice | grep -m1 OSDI_VERSION_MAJOR   # present: OSDI compiled in
command -v openvaf     # MISSING
command -v openroad    # MISSING
command -v yosys       # MISSING
```

Status: VERIFIED. ngspice 42 (`42+ds-3build1`) can load OSDI
models, but the compile step is impossible here: OpenVAF is not
installed AND the PDK ships no Verilog-A (HSPICE-only cards).
The BSIMCMG-OSDI route is therefore precisely blocked, recorded
as `blocked-openvaf-missing`, not as a soft "todo".

## 7. Digital-lane pointer: ORFS asap7 platform (NOT-RUN-HERE)

Upstream OpenROAD-flow-scripts ships `flow/platforms/asap7`
(verified 2026-10-31: directory page HTTP 200 with `drc/`,
`gds/`, `KLayout/` collateral). The integrator's digital step on
a tooled host is the standard ORFS flow with `PLATFORM=asap7`
against this library's LEF/LIB/techlef. No openroad/yosys here,
so NOTHING digital was run in this lane — the matrix row says
`claimed-upstream`, never ✓.
