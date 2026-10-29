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
