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
