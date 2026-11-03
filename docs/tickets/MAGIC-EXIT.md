# MAGIC-EXIT: Track Magic phase-out triggers

*Status: Deferred until post-MVP/hackathon (owner call 2026-10-29) · Depends: none · Size: S · Roadmap: orch-build-mvp*

## Why

Magic is declared phased-out-in-waiting (README matrix), but
declarations rot without a watch. The three triggers that retire
it — upstream `sky130.lvs` fix (#531), klayout-pex native 2.5D
engine, gdsfactory 10.x stable + PDK-supported — need periodic
checking and a recorded verdict each time, so the phase-out fires
on evidence, not vibes.

## What

- Watch file noting each trigger's status + last-checked date;
  re-verify on a cadence (e.g. each sprint); record verdicts.
- First check DONE 2026-10-29 (EXTRACT-SKY130,
  `docs/probe-extract-lvs.md`): `sky130.lvs` FAILS on the
  known-good cell — case bug #531 reproduced (schematic classes
  UPPERCASE vs layout lowercase), so Magic extraction + Netgen
  LVS is evidence-locked and no KLayout LVS solver lands. Re-run
  probe attempt 2 against each new tree; a `Congratulations!
  Netlists match.` reopens the migration slice.

## Acceptance

- Triggers documented with check commands/links; first check
  recorded; a fired trigger spawns the extraction-migration slice.

## Brainstorm (2026-10-30, talk only — no decisions)

- **Windows blocker = Magic.** Rest of the stack (KLayout,
  ngspice, slang, Python, Icarus) is cross-platform or close;
  Magic's X11/Tcl/C build is the portability wall.
- **Idea: transliterate Magic's extractor into Rust in-repo.**
  Verdict sketch: the extractor is inseparable from the
  corner-stitched DB + CIF/GDS readers + tech-file compiler
  — "surgical rip" means porting all of it, then carrying a
  differential-testing burden against Magic goldens forever.
  If ever attempted: FFI seam into Magic's C first (learn
  the boundary), strangler-port module by module, corpus
  differential tests as the gate. Honest call: bad trade vs
  the KLayout-shaped exit below; man-years for parity.
- **Independent open-source extraction (preferred exit):**
  klayout-pex (2.5D extraction, KLayout-native — already a
  trigger), KLayout netlist/LVS scripting for connectivity,
  gdsfactory 10.x stack (already a trigger). The exit is
  KLayout-shaped, not Rust-shaped.
- **Idea: TCL interpreter in the console.** No as a product:
  the Python console covers scripting and the Magic exit
  removes the motive. Transition shim only: stdlib
  `tkinter.Tcl()` embeds a real Tcl interpreter at zero deps
  IF a specific Magic-Tcl flow must be preserved mid-exit.
- **Harness upskilling with skills:** parked for a later
  session (fuel-side); not part of this ticket.
- **FasterCap evaluated 2026-11-01, parked:** field solver
  only (capacitance matrix from pre-assigned conductor
  surfaces) — it refines coupling caps but cannot do
  connectivity/device-recognition/netlisting, so it does
  NOT replace Magic. Optional stage-2 refiner after a
  KLayout-shaped exit, never the exit itself. License
  (research-distribution, non-OSI) needs checking before
  it goes near the tree.
