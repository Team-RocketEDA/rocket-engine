# ASAP7 DRM rule inventory (lane ASAP7-DRC-DECK)

Source: the r1p7 DRM alone (ASU `asap7_drm_201207a.pdf`, Dec 2020),
ch. 3 tables. Rule names, values, and section citations below are
transcribed facts. Stream numbers used by the deck come from the r1p7
layermap. No other deck was consulted (see report.md source list).

Machine-readable counts (pinned by `tests/test_asap7deck_inventory.py`):

table-rows: 201
note-rules: 1
instantiated: 331
implemented-instantiated: 112

`table-rows` = DRM ch. 3 table rows. `note-rules` = V3.M3.EN.1, stated
in §3.13 note 2 rather than the table (implemented, marked IMPL-NOTE).
`instantiated` = rules after the DRM's own layer fan-out (M1-M3 x3,
M4-M5/M6-M7/M8-M9/V-pairs x2, NSELECT-family x5 with the note-1
exception, V1-V3 per §3.13 head text + note 2).

WEAK = implemented check flags a sound subset of the DRM rule: every
flag is a genuine violation, but some violations need follow-up
checks (named in the Deferred section).

## Implemented

- IMPL GEOMETRY.NONORTHOGONAL | §3.1 | non-orthogonal shapes not allowed | non-rectilinear over all drawn layers
- IMPL FIN.W.1 | §3.3 | ==7nm vertical width | exact bbox-height check
- IMPL FIN.W.2 | §3.3 | >=108nm horizontal width | bbox-width check
- IMPL FIN.S.1 | §3.3 | ==27nm vertical pitch | WEAK minimum-side space 20nm (pitch minus width)
- IMPL GATE.W.1 | §3.4 | ==20nm horizontal width | exact bbox-width check
- IMPL GATE.W.2 | §3.4 | >=40nm vertical width | bbox-height check
- IMPL GATE.S.2 | §3.4 | >=34nm horizontal spacing | vertical-edge space check
- IMPL GATE.ACTIVE.EX.1 | §3.4 | >=4nm vertical GATE extension past ACTIVE | shrink-difference check
- IMPL GATE.ACTIVE.EX.2 | §3.4 | >=25nm horizontal ACTIVE extension past GATE | shrink-difference check
- IMPL GATE.ACTIVE.S.4 | §3.4 | >=9nm horizontal ACTIVE-GATE spacing | vertical-edge two-layer space check
- IMPL ACTIVE.FIN.EX.1 | §3.5 | >=10nm vertical ACTIVE extension past FIN | shrink-difference check
- IMPL ACTIVE.W.1 | §3.5 | >=27nm vertical width | bbox-height check
- IMPL ACTIVE.W.3 | §3.5 | >=16nm horizontal width | bbox-width check
- IMPL ACTIVE.S.1 | §3.5 | >=27nm vertical spacing | horizontal-edge space check
- IMPL ACTIVE.S.2B | §3.5 | >=38nm horizontal spacing | vertical-edge space check
- IMPL ACTIVE.WELL.S.4 | §3.5 | >=27nm ACTIVE-to-WELL spacing | outside-ACTIVE separation check
- IMPL ACTIVE.WELL.EN.1 | §3.5 | >=27nm ACTIVE enclosure by WELL | enclosure check
- IMPL ACTIVE.A.1A | §3.5 | >=864nm2 area (non-SRAM) | area check
- IMPL M1.W.1 | §3.12 | >=18nm width (x M1/M2/M3) | width check
- IMPL M1.S.1 | §3.12 | >=18nm side-to-side spacing (x M1/M2/M3) | WEAK plain space check (tip tables deferred)
- IMPL M1.A.1 | §3.12 | >=504nm2 area (x M1/M2/M3) | area check
- IMPL V0.W.1 | §3.11 | >=18nm width along M1 | WEAK isotropic min-dim check
- IMPL V0.S.1 | §3.11 | >=[18|27|18]nm spacing set | WEAK 18nm floor check
- IMPL V0.AUX.1 | §3.11 | V0 must interact with M1 and [LISD|LIG] | inside-M1 + interacts-MOL checks
- IMPL V1.W.1 | §3.13 | >=18nm width along M(x+1) (x V1/V2/V3) | WEAK isotropic min-dim check
- IMPL V1.S.1 | §3.13 | >=[18|27|18]nm spacing set (x V1/V2/V3) | WEAK 18nm floor check
- IMPL V1.M1.EN.1 | §3.13 | 5&2nm enclosure by M1, two opposite sides | WEAK 2nm floor + opposite-side filter
- IMPL V2.M2.EN.1 | §3.13 | >=5nm enclosure by M2, two opposite sides | enclosure + opposite-side filter
- IMPL V1.AUX.1 | §3.13 | V(x) inside M(x) and M(x+1) (x V1/V2/V3) | boolean inside checks
- IMPL V3.M4.EN.2 | §3.13 | >=11nm enclosure by M4, two opposite sides | enclosure + opposite-side filter
- IMPL M4.W.1 | §3.14 | >=24nm vertical width (x M4/M5 perp) | directional bbox check
- IMPL M4.W.5 | §3.14 | >=44nm horizontal width (x M4/M5 perp) | directional bbox check
- IMPL M4.W.2 | §3.14 | <=480nm vertical width (x M4/M5 perp) | directional opening check
- IMPL M4.S.1 | §3.14 | >=24nm vertical spacing (x M4/M5 perp) | directional edge space check
- IMPL M4.S.2 | §3.14 | >=40nm horizontal spacing (x M4/M5 perp) | directional edge space check
- IMPL M4.AUX.1 | §3.14 | horizontal edges on 24nm grid (x M4/M5 perp, offset 0) | on-grid check
- IMPL V4.W.1 | §3.15 | ==24nm width along M(x+1) (x V4/V5) | WEAK isotropic exact min-dim check
- IMPL V4.S.1 | §3.15 | >=33nm spacing, same net (x V4/V5) | net-agnostic space check (value equals S.2)
- IMPL V4.S.2 | §3.15 | >=33nm spacing, different nets (x V4/V5) | same check as S.1, second category
- IMPL V4.M4.EN.1 | §3.15 | >=11nm enclosure, two opposite sides (x V4/V5) | enclosure + opposite-side filter
- IMPL V4.M5.EN.2 | §3.15 | >=11nm enclosure, two opposite sides (x V4/V5) | enclosure + opposite-side filter
- IMPL V4.AUX.1 | §3.15 | V(x) inside M(x) and M(x+1) (x V4/V5) | boolean inside checks
- IMPL M6.W.1 | §3.16 | >=32nm vertical width (x M6/M7 perp) | directional bbox check
- IMPL M6.W.5 | §3.16 | >=44nm horizontal width (x M6/M7 perp) | directional bbox check
- IMPL M6.W.2 | §3.16 | <=640nm vertical width (x M6/M7 perp) | directional opening check
- IMPL M6.S.1 | §3.16 | >=32nm vertical spacing (x M6/M7 perp) | directional edge space check
- IMPL M6.S.2 | §3.16 | >=40nm horizontal spacing (x M6/M7 perp) | directional edge space check
- IMPL M6.AUX.1 | §3.16 | horizontal edges on 32nm grid (x M6/M7 perp, offset 0) | on-grid check
- IMPL V6.W.1 | §3.17 | ==32nm width (x V6/V7) | WEAK isotropic exact min-dim check
- IMPL V6.S.1 | §3.17 | >=45nm spacing, same net (x V6/V7) | net-agnostic space check (value equals S.2)
- IMPL V6.S.2 | §3.17 | >=45nm spacing, different nets (x V6/V7) | same check as S.1, second category
- IMPL V6.M6.EN.1 | §3.17 | >=11nm enclosure, two opposite sides (x V6/V7) | enclosure + opposite-side filter
- IMPL V6.M7.EN.2 | §3.17 | >=11nm enclosure, two opposite sides (x V6/V7) | enclosure + opposite-side filter
- IMPL V6.AUX.1 | §3.17 | V(x) inside M(x) and M(x+1) (x V6/V7) | boolean inside checks
- IMPL M8.W.1 | §3.18 | >=40nm width (x M8/M9) | width check
- IMPL M8.W.2 | §3.18 | >=60nm width for length 400-1200nm (x M8/M9) | bbox max+min check
- IMPL M8.W.3 | §3.18 | >=80nm width for length 1200-1800nm (x M8/M9) | bbox max+min check
- IMPL M8.W.4 | §3.18 | >=120nm width for length over 1800nm (x M8/M9) | bbox max+min check
- IMPL M8.S.1 | §3.18 | >=40nm side-to-side spacing (x M8/M9) | WEAK plain space check (tables deferred)
- IMPL M8.A.1 | §3.18 | >=7520nm2 area (x M8/M9) | area check
- IMPL V8.W.1 | §3.19 | 40x40/40x120/120x40nm exact sizes (x V8/V9) | min-dim + max-dim range checks
- IMPL V8.S.1 | §3.19 | >=57nm spacing (x V8/V9) | space check
- IMPL V8.M8.EN.1 | §3.19 | >=20nm enclosure, two opposite sides (x V8; V9 bottom) | enclosure + opposite-side filter
- IMPL V8.M9.EN.2 | §3.19 | >=20nm enclosure, two opposite sides (V8 only; V9 top is Pad) | enclosure + opposite-side filter
- IMPL V8.AUX.1 | §3.19 | V8 inside M8+M9; V9 inside M9 (Pad part deferred) | boolean inside checks
- IMPL-NOTE V3.M3.EN.1 | §3.13 note 2 | >=5nm enclosure by M3, as V2.M2.EN.1 | enclosure + opposite-side filter

## Deferred

- DEFER WELL.W.1 | §3.2 | >=108nm horizontal width | out of core (not metal/via/active/poly/fin)
- DEFER WELL.W.2 | §3.2 | >=54nm vertical width | out of core
- DEFER WELL.S.1 | §3.2 | >=108nm vertical spacing | out of core
- DEFER WELL.S.2 | §3.2 | >=54nm horizontal spacing | out of core
- DEFER WELL.A.1A | §3.2 | >=5832nm2 area | out of core
- DEFER WELL.A.1B | §3.2 | >=5832nm2 enclosed area | out of core
- DEFER WELL.GATE.EX.1 | §3.2 | >=7nm horizontal extension past GATE | out of core
- DEFER WELL.GATE.EX.2 | §3.2 | >=7nm vertical extension past GATE | out of core
- DEFER FIN.AUX.1 | §3.3 | FIN may not bend | needs per-shape bend analysis
- DEFER GATE.S.1 | §3.4 | ==54nm horizontal pitch | needs center-distance pitch measurement
- DEFER GATE.S.3 | §3.4 | solitary GATE within 54nm centers | needs neighbor-count analysis
- DEFER GATE.AUX.1 | §3.4 | GATE may not bend | needs per-shape bend analysis
- DEFER GATE.AUX.2 | §3.4 | GATE may not be discontinuous vertically | needs topology analysis (GCUT interplay)
- DEFER GATE.ACTIVE.AUX.3 | §3.4 | ACTIVE vertical edge may not lie inside/coincide GATE | needs edge-in-polygon analysis
- DEFER ACTIVE.W.2 | §3.5 | 27nm vertical-width increment multiple | needs per-shape modulo pass
- DEFER ACTIVE.S.2A | §3.5 | >=92nm horizontal S/D spacing, different nets | needs connectivity (nets)
- DEFER SRAM.ACTIVE.WELL.S.5 | §3.5 | >=13.5nm spacing to WELL (SRAM) | SRAM-gated variant
- DEFER SRAM.ACTIVE.WELL.EN.2 | §3.5 | >=13.5nm enclosure by WELL (SRAM) | SRAM-gated variant
- DEFER ACTIVE.A.1B | §3.5 | >=864nm2 enclosed area | needs hole-area analysis
- DEFER SRAM.ACTIVE.A.2A | §3.5 | >=432nm2 area (SRAM) | SRAM-gated variant
- DEFER SRAM.ACTIVE.A.2B | §3.5 | >=432nm2 enclosed area (SRAM) | SRAM-gated variant
- DEFER ACTIVE.AUX.1 | §3.5 | ACTIVE enclosed by NSELECT/PSELECT | implant layers out of core
- DEFER SRAM.ACTIVE.AUX.2 | §3.5 | non-SRAM ACTIVE may not touch SRAMDRC | SRAM-gated variant
- DEFER ACTIVE.AUX.3 | §3.5 | no vertical notch in ACTIVE | needs notch orientation analysis
- DEFER ACTIVE.LUP.1 | §3.5 | <=30um latch-up distance | needs device/contact recognition
- DEFER GCUT.W.1 | §3.6 | >=17nm vertical width | out of core
- DEFER GCUT.ACTIVE.S.1 | §3.6 | >=4nm vertical spacing to channel | out of core
- DEFER GCUT.GATE.EX.1 | §3.6 | >=17nm horizontal extension past GATE | out of core
- DEFER GCUT.GATE.S.2 | §3.6 | >=17nm spacing to GATE | out of core
- DEFER GCUT.S.3 | §3.6 | >=35nm vertical spacing | out of core
- DEFER GCUT.AUX.1 | §3.6 | no GCUT without GATE | out of core
- DEFER GCUT.AUX.2 | §3.6 | vertical edge may not lie inside/coincide GATE | out of core
- DEFER GCUT.AUX.3 | §3.6 | may not interact with channel | out of core
- DEFER NSELECT.W.1 | §3.7 | >=108nm horizontal width (x5 layers) | out of core
- DEFER NSELECT.W.2 | §3.7 | >=54nm vertical width (x5 layers) | out of core
- DEFER NSELECT.ACTIVE.EN.1 | §3.7 | >=46nm horizontal enclosure (x5 layers) | out of core
- DEFER NSELECT.ACTIVE.EN.2 | §3.7 | >=27nm vertical enclosure (x5 layers) | out of core
- DEFER SRAM.NSELECT.ACTIVE.EN.3 | §3.7 | >=13.5nm horizontal enclosure (x5 layers) | out of core
- DEFER SRAM.NSELECT.ACTIVE.EN.4 | §3.7 | >=13.5nm vertical enclosure (x5 layers) | out of core
- DEFER NSELECT.GATE.EX.1 | §3.7 | >=7nm horizontal extension (x5 layers) | out of core
- DEFER NSELECT.GATE.EX.2 | §3.7 | >=7nm vertical extension (x5 layers) | out of core
- DEFER NSELECT.PSELECT.AUX.1 | §3.7 | NSELECT/PSELECT may not overlap | out of core
- DEFER VT.AUX.2 | §3.7 | VT layers may not overlap | out of core
- DEFER SDT.W.1 | §3.8 | >=24nm horizontal width | out of core
- DEFER SDT.W.2 | §3.8 | >=27nm vertical width (non-SRAM) | out of core
- DEFER SDT.W.3 | §3.8 | 27nm vertical-width increment | out of core
- DEFER SRAM.SDT.W.4 | §3.8 | >=17nm vertical width (SRAM) | out of core
- DEFER SDT.S.1 | §3.8 | >=30nm horizontal spacing | out of core
- DEFER SDT.GATE.S.2 | §3.8 | >=5nm horizontal spacing to GATE | out of core
- DEFER SDT.ACTIVE.OV.1 | §3.8 | >=27nm vertical overlap with ACTIVE | out of core
- DEFER SDT.LISD.OV.2 | §3.8 | >=27nm vertical overlap with LISD | out of core
- DEFER SRAM.SDT.ACTIVE.OV.3 | §3.8 | >=17nm overlap (SRAM) | out of core
- DEFER SRAM.SDT.LISD.OV.4 | §3.8 | >=17nm overlap (SRAM) | out of core
- DEFER SDT.GATE.AUX.1 | §3.8 | SDT/GATE may not overlap or touch | out of core
- DEFER SDT.ACTIVE.AUX.2 | §3.8 | horizontal edges coincide with ACTIVE | out of core
- DEFER SDT.ACTIVE.AUX.3 | §3.8 | SDT may not be entirely outside ACTIVE | out of core
- DEFER SDT.LISD.AUX.4 | §3.8 | SDT always inside LISD | out of core
- DEFER LISD.W.1 | §3.9 | >=24nm width | out of core
- DEFER LISD.S.1 | §3.9 | >=18nm side-to-side spacing | out of core
- DEFER LISD.S.2 | §3.9 | >=25nm tip-to-side spacing | out of core
- DEFER LISD.S.3 | §3.9 | >=27nm tip-to-tip spacing (non-SRAM) | out of core
- DEFER SRAM.LISD.S.4 | §3.9 | >=27nm tip-to-tip spacing (SRAM) | out of core
- DEFER LISD.A.1 | §3.9 | >=648nm2 area | out of core
- DEFER SRAM.LISD.AUX.1 | §3.9 | non-SRAM may not touch SRAMDRC | out of core
- DEFER LIG.W.1 | §3.10 | >=16nm width | out of core
- DEFER LIG.S.1 | §3.10 | >=18nm side-to-side spacing | out of core
- DEFER LIG.S.2 | §3.10 | >=25nm tip-to-side spacing | out of core
- DEFER LIG.S.3 | §3.10 | >=27nm tip-to-tip spacing (non-SRAM, 24-36nm) | out of core
- DEFER LIG.S.4 | §3.10 | >=31nm tip-to-tip spacing (non-SRAM, <24nm) | out of core
- DEFER LIG.S.5 | §3.10 | >=31nm tip-to-tip spacing (non-SRAM, mixed) | out of core
- DEFER LIG.LISD.S.6 | §3.10 | >=14nm spacing to LISD, different nets | out of core
- DEFER LIG.LISD.S.7 | §3.10 | >=15nm corner-to-corner spacing | out of core
- DEFER LIG.SDT.S.8 | §3.10 | >=14nm spacing to SDT, different nets | out of core
- DEFER LIG.GATE.S.9A | §3.10 | >=14nm vertical spacing to GATE | out of core
- DEFER LIG.GATE.S.9B | §3.10 | >=17nm horizontal spacing to GATE | out of core
- DEFER LIG.GATE.S.10 | §3.10 | >=5nm spacing to channel GATE | out of core
- DEFER LIG.GCUT.S.11 | §3.10 | >=5nm vertical spacing to GCUT | out of core
- DEFER LIG.A.1 | §3.10 | >=324nm2 area | out of core
- DEFER LIG.LISD.A.2 | §3.10 | >=128nm2 overlap area | out of core
- DEFER LIG.GATE.A.3 | §3.10 | >=320nm2 overlap area (non-SRAM) | out of core
- DEFER SRAM.LIG.GATE.A.4 | §3.10 | >=240nm2 overlap area (SRAM) | out of core
- DEFER LIG.GATE.AUX.1 | §3.10 | vertical edge may not lie inside/coincide GATE | out of core
- DEFER SRAM.LIG.AUX.2 | §3.10 | non-SRAM may not touch SRAMDRC | out of core
- DEFER LIG.GATE.EX.1 | §3.10 | >=1nm extension over GATE, both sides | out of core
- DEFER LIG.LISD.OV.1 | §3.10 | >=8nm overlap with connected LISD | out of core
- DEFER SRAM.LIG.GATE.OV.2 | §3.10 | >=15nm overlap with GATE (SRAM) | out of core
- DEFER V0.S.2 | §3.11 | >=23nm corner-to-corner, both 5nm end-cap | needs corner-pair + end-cap analysis
- DEFER V0.S.3 | §3.11 | >=30nm corner-to-corner, no 5nm end-cap | needs corner-pair + end-cap analysis
- DEFER V0.S.4 | §3.11 | >=27nm corner-to-corner, mixed end-cap | needs corner-pair + end-cap analysis
- DEFER V0.M1.EN.1 | §3.11 | (5&5)|(5&0)nm enclosure by M1 | asymmetric alternative needs directional enclosure
- DEFER V0.LISD.EN.2 | §3.11 | ==3nm enclosure by LISD, inside | exact-enclosure + MOL interplay
- DEFER V0.LISD.EN.3 | §3.11 | ==3nm enclosure by LISD, partial | exact-enclosure + MOL interplay
- DEFER V0.LIG.EN.4 | §3.11 | >=1nm enclosure of LIG by V0 | MOL interplay
- DEFER V0.LIG.A.1 | §3.11 | >=288nm2 overlap area with LIG | MOL interplay
- DEFER V0.LIG.AUX.2 | §3.11 | V0 edge in LIG forbidden | MOL interplay
- DEFER V0.M1.AUX.3 | §3.11 | V0 same width as M1 perpendicular to length | needs orientation analysis
- DEFER M1.S.2 | §3.12 | >=25nm tip-to-side spacing (x M1/M2/M3) | needs edge-width-binned spacing
- DEFER M1.S.3 | §3.12 | >=27nm tip-to-tip spacing 24-36nm (x M1/M2/M3) | needs edge-width-binned spacing
- DEFER M1.S.4 | §3.12 | >=31nm tip-to-tip spacing <24nm (x M1/M2/M3) | needs edge-width-binned spacing
- DEFER M1.S.5 | §3.12 | >=31nm tip-to-tip spacing mixed (x M1/M2/M3) | needs edge-width-binned spacing
- DEFER M1.S.6 | §3.12 | >=20nm corner-to-corner (x M1/M2/M3) | needs corner-pair analysis
- DEFER V1.S.2 | §3.13 | >=23nm corner-to-corner, both end-cap (x V1/V2/V3) | needs corner-pair + end-cap analysis
- DEFER V1.S.3 | §3.13 | >=30nm corner-to-corner, no end-cap (x V1/V2/V3) | needs corner-pair + end-cap analysis
- DEFER V1.S.4 | §3.13 | >=27nm corner-to-corner, mixed end-cap (x V1/V2/V3) | needs corner-pair + end-cap analysis
- DEFER V1.M2.EN.2 | §3.13 | (5&5)|(5&0)nm enclosure, V1 by M2 + generalized V2.M3.EN.2 | asymmetric alternative needs directional enclosure
- DEFER V1.M2.AUX.2 | §3.13 | V(x) same width as M(x+1) perpendicular (x V1/V2/V3) | needs orientation analysis
- DEFER M4.W.3 | §3.14 | width may not be even multiple of min (x M4/M5) | needs per-shape modulo pass
- DEFER M4.W.4 | §3.14 | may not span even track count (x M4/M5) | needs track-origin analysis
- DEFER M4.S.3 | §3.14 | >=40nm tip-to-tip, no run length (x M4/M5) | needs tip/runlength analysis
- DEFER M4.S.4 | §3.14 | >=40nm tip-to-tip with run length (x M4/M5) | needs tip/runlength analysis
- DEFER M4.S.5 | §3.14 | >=44nm parallel run length (x M4/M5) | needs runlength analysis
- DEFER M4.AUX.2 | §3.14 | min-width tracks on 2N grid + offset (x M4/M5) | needs track-origin + env offsets
- DEFER M4.AUX.3 | §3.14 | M4 may not bend (x M4/M5) | needs per-shape bend analysis
- DEFER M4.AUX.4 | §3.14 | wide outer edge may not touch track edge (x M4/M5) | needs track-edge analysis
- DEFER V4.S.3 | §3.15 | >=33nm corner-to-corner (x V4/V5) | needs corner-pair analysis
- DEFER V4.M5.AUX.2 | §3.15 | V(x) same width as M(x+1) perpendicular (x V4/V5) | needs orientation analysis
- DEFER M6.W.3 | §3.16 | width may not be even multiple of min (x M6/M7) | needs per-shape modulo pass
- DEFER M6.W.4 | §3.16 | may not span even track count (x M6/M7) | needs track-origin analysis
- DEFER M6.S.3 | §3.16 | >=40nm tip-to-tip, no run length (x M6/M7) | needs tip/runlength analysis
- DEFER M6.S.4 | §3.16 | >=40nm tip-to-tip with run length (x M6/M7) | needs tip/runlength analysis
- DEFER M6.S.5 | §3.16 | >=44nm parallel run length (x M6/M7) | needs runlength analysis
- DEFER M6.AUX.2 | §3.16 | min-width tracks on 2N grid + offset (x M6/M7) | needs track-origin + env offsets
- DEFER M6.AUX.3 | §3.16 | M6 may not bend (x M6/M7) | needs per-shape bend analysis
- DEFER M6.AUX.4 | §3.16 | wide outer edge may not touch track edge (x M6/M7) | needs track-edge analysis
- DEFER V6.S.3 | §3.17 | >=45nm corner-to-corner (x V6/V7) | needs corner-pair analysis
- DEFER V6.M7.AUX.2 | §3.17 | V(x) same width as M(x+1) perpendicular (x V6/V7) | needs orientation analysis
- DEFER M8.W.5 | §3.18 | maximum width 2000nm, operator >= as-stated [sic] (x M8/M9) | contradictory operator; needs DRM clarification
- DEFER M8.S.2 | §3.18 | >=43nm tip-to-side spacing (x M8/M9) | needs edge-width-binned spacing
- DEFER M8.S.3 | §3.18 | >=46nm tip-to-tip spacing (x M8/M9) | needs edge-width-binned spacing
- DEFER M8.S.4 | §3.18 | >=60nm spacing, edge 60-80nm (x M8/M9) | needs edge-width-binned spacing
- DEFER M8.S.5 | §3.18 | >=80nm spacing, edge 80-120nm (x M8/M9) | needs edge-width-binned spacing
- DEFER M8.S.6 | §3.18 | >=120nm spacing, edge 120-500nm (x M8/M9) | needs edge-width-binned spacing
- DEFER M8.S.7 | §3.18 | >=500nm spacing, edge 500-1000nm (x M8/M9) | needs edge-width-binned spacing
- DEFER M8.S.8 | §3.18 | >=1000nm spacing, edge over 1000nm (x M8/M9) | needs edge-width-binned spacing
- DEFER M8.L.1 | §3.18 | >=40nm feature length (x M8/M9) | weak form subsumed by W.1; true length semantics follow-up
- DEFER V8.S.2 | §3.19 | >=57nm corner-to-corner (x V8/V9) | needs corner-pair analysis

Partial instantiations (deferred parts of implemented rows, not rows):
- V9 top-metal checks (generalized V9.PAD.EN.2 and the Pad part of
  V9.AUX.1): Pad has no drawing stream in the layermap (DRM mask 96
  unmapped), so only the M9-side checks are implemented.

## Companion allowances (breaker `also`)

A breaker trips exactly its rule except for the companions below,
each a geometric implication of the breaker's own violation (the deck
is correct to flag both; the test encodes the implication):

- m4_w1/m6_w1 -> M4.AUX.1/M6.AUX.1: vertical width below the 24/32nm
  grid cannot have both horizontal edges on-grid.
- m5_w1/m7_w1 -> M5.AUX.1/M7.AUX.1: same, perpendicular (grid on x).
- m4_s1/m6_s1 -> M4.AUX.1/M6.AUX.1: a sub-grid vertical gap forces an
  off-grid horizontal edge. m5_s1/m7_s1 likewise, perpendicular.
- v4_s1/v5_s1/v6_s1/v7_s1 -> V4.S.2/V5.S.2/V6.S.2/V7.S.2: S.1 and S.2
  share one value (33/45nm), so one net-agnostic check serves both
  categories and both fire together.

## DRM sic notes (transcribed as-stated, never silently reinterpreted)

- §3.17 V6.W.1 reads "along the length of M5" [sic]: V6 connects
  M6/M7, so M5 looks like a typo for M7. The weak isotropic check is
  unaffected by the direction naming.
- §3.18 M8.W.5 reads "Maximum width of M8" with operator >= [sic]:
  self-contradictory as-stated (a maximum with a lower bound).
  Deferred pending clarification; not implemented under either guess.
- §3.13 V1.AUX.1 is typed "Enclosure" in the DRM table [sic]:
  cosmetic only ("V1 must be inside M1 and M2" is an AUX rule).
- Fig. 3.9.1 labels LISD.S.5 and SRAM.LISD.S.6, but Table 3.9.1 has
  no such rows: figure-only labels, no values to implement.
- §3.13 head text generalizes V1 rules to V(x) with M(x)/M(x+1);
  V2.M2.EN.1 and V3.M4.EN.2 are explicit overrides and V3.M3.EN.1
  comes from note 2; V2.M3.EN.2 inherits the (5&5)|(5&0) form and is
  deferred with V1.M2.EN.2.
- §3.15/§3.17 head text notes those via rules "will be revised in
  the subsequent version"; implemented as-stated.
- Grid offsets (§3.14/§3.16 note 1: env variables, default 0):
  the deck implements offset 0 only; nonzero offsets are deferred.
- GCUT-cut GATE (used by several GATE rules): the deck checks
  uncut GATE, a sound weak direction (cuts only remove GATE, and
  less GATE cannot create an extension/width violation the uncut
  check would miss... precisely: uncut GATE over-approximates
  extension and width, so flags on uncut GATE are genuine).
