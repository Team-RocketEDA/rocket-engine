# IHP SG13G2 capability matrix rows (PDK-IHP proposal)

Proposed rows for the engine capability matrix. ✓ = proven live in
this lane at the pinned revisions (ihp-gdsfactory 2.0.1 @ d7643aa,
gdsfactory 9.51.0, sax 0.18.2, ngspice-42); n/a = honestly absent
with the reason, never promised.

## Flavor key

SG13G2 is one 130nm SiGe BiCMOS flow. `bicmos` = core flow (LV/HV
CMOS + NPN/PNP HBTs + base R/C + stdcells); `rf` = RF options on
that flow (guard-ring RF FETs + RF MIM + spiral inductors +
varicap + RF SAX models). Both flavors share one KLayout tech, one
DRC deck, and one model tree.

| capability | bicmos | rf | evidence / caveat |
|---|---|---|---|
| layout build (gdsfactory cells) | ✓ | ✓ | `test_cells_build.py`: nmos/rfnmos/npn13G2/rsil/cmim goldens + stdcell import |
| KLayout tech install | ✓ | ✓ (shared) | `install_tech.py` verified; techs `IHP` + `sg13g2` register |
| DRC (PDK deck) | preview-gated | preview-gated | deck ships but needs KLayout newer than sandbox 0.28.16/0.30.7 (`euclidean` metric); re-run `run_drc.py` on newer host |
| DRC (engine M1.a/M1.b stand-in) | ✓ | ✓ (shared) | deck's own 0.16/0.18 um values; clean fixture 0 vio, dirty 1+1 golden |
| LVS | n/a | n/a | no LVS deck in wrapper (only `*LVS*.gds` reference layouts) |
| extraction (Magic/KLayout) | n/a | n/a | no extraction deck/tech in wrapper |
| ngspice: passive + HBT DC | ✓ | — | ptap1 divider 0.9 V; npn13G2 VBIC op −576.845 uA |
| ngspice: MOS / R3 resistors | n/a | n/a | need `pspnqs103va` / `r3_cmc` VA modules stock ngspice-42 lacks; VA sources ship for openvaf flow |
| SAX RF S-params | ✓ (rsil) | ✓ | 10-model registry; 5 GHz goldens for rsil + inductor_with_loss |
| stdcells | ✓ layout-only | — | 84 cells import with ports; no LEF/Liberty (n/a) |
| xschem symbols/testbenches | n/a | n/a | none in wrapper |
| SRAM / IO libs | n/a | n/a | none in wrapper |
| xyce models | n/a (unrun) | n/a (unrun) | libs ship (`ihp/models/xyce/`) but no xyce binary here |
| VACASK models | n/a (unrun) | n/a (unrun) | libs ship (`ihp/models/vacask/`) but vacask not installed here |

## Preview gates (upstream's own caveat, honored)

Upstream labels SG13G2 open-kit support preview, not production.
The lane pins exact revisions and treats drift as failure; the PDK
deck row stays preview-gated until `run_drc.py` goes green on a
newer-KLayout host, and RF peak-fmax / EM items (Palace notebooks,
material cards) are inventoried only — profiled, never promised.
