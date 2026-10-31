# PDK-ASAP7: ASAP7 predictive 7nm support (spike enablement first)

*Status: Backlog · Size: M · Roadmap: pdk-onboarding (MVP track)*

## Why

ASAP7 (ASU + ARM predictive 7nm FinFET, BSD-3-Clause) is the
most widely used open PDK below 10nm — the only way to
exercise the engine on FinFET-era design rules, BSIMCMG
models, and 7.5-track standard cells without an NDA. The
canonical source is `github.com/The-OpenROAD-Project/asap7`
(+ `asap7sc7p5t_28` stdcells), and known-good enablement
already exists: the OpenROAD asap7 platform for digital
flow, and the OpenLayout pattern (KLayout + xschem +
ngspice with BSIMCMG-OSDI via OpenVAF) for custom IC. Two
caveats shape this slice. First, ASAP7 is predictive, NOT
manufacturable — the matrix must label it predictive-only,
and it must never look better-proven than measured silicon.
Second, gdsfactory-first does NOT cover ASAP7 (no gf PDK
package exists), so this slice starts with a spike to pick
the enablement before climbing the standard ladder.

## What

- Spike (RED-first, timeboxed): confirm the enablement —
  OpenROAD asap7 platform for digital? KLayout tech +
  xschem/ngspice-OSDI for custom analog? Document versions,
  licenses, and what each flow can honestly claim.
- Then the standard ladder shape: profile entry (variant →
  tech/deck/model relpaths), provision recipe (git pin +
  tool install + verify probe), live proofs (digital flow
  proof and/or xschem+ngspice sim proof) with golden
  expectations.
- Capability matrix rows with the predictive-only label;
  no bespoke engine integration beyond the profile shape.

## Acceptance

- Spike verdict recorded (enablement picked with evidence);
  fresh-store provision → register → verify → proofs green;
  matrix truthful incl. predictive-only caveat; no other
  PDK's proofs regress.

## Field notes (2026-11-01): OpenLayout custom-flow recipe

`github.com/vhdani04/OpenLayout` (cloned to
`/tmp/openlayout`) is a full custom-IC environment on
ASAP7 and shows exactly how our `n/a` custom rows get
enabled — study it, do NOT copy it (**GPLv3**: no
OpenLayout code in-tree, ever; DRM rule names/values are
facts and may inform a clean-room deck):

- DRC: KLayout deck written rule-by-rule from the ASAP7
  DRM r1p7 (`pdk/asap7/klayout/drc/asap7.drc`), checks
  named per DRM rule (M1.S.2); validated against ~190
  rule-breaker layouts + all 848 7.5T cells clean (1
  documented waiver). Our KLayout DRC adapter (deck mode)
  can run a deck of this shape unchanged.
- Tech: generated (`gen_asap7_lyt.py`/`gen_asap7_lyp.py`)
  — r1p7 ships no KLayout tech, OpenLayout builds it.
- LVS: KLayout LVS script (`klayout/lvs/asap7.lvs`) with
  FinFET extraction (fins, 4 VT flavors) vs xschem
  schematic + stdcell CDL.
- Models: BSIM-CMG Verilog-A (OpenVAF-reloaded
  integration tests) compiled with `openvaf-r` to
  `bsimcmg.osdi`; ngspice 47 `--enable-osdi` loads it;
  `convert_asap7_models.py` turns r1p7 HSPICE cards into
  ngspice cards + `asap7.lib`.
- Pins: KLayout 0.30.12, ngspice 47, OpenVAF-reloaded
  build, xschem ref, FasterCap stack (`setup/versions.env`).
- Follow-up (new ticket, not this spike): clean-room
  ASAP7 custom flow — generated tech, OSDI model build,
  card conversion, DRM-derived DRC, KLayout LVS — wired
  through existing engine surfaces (klayout deck mode,
  ngspice, xschem netlist).
