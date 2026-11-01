# PROV-DEFERRED: Provision + qualify post/off-MVP packs (not a B10 gate)

*Status: Backlog · Depends: PROV · Size: M ·
Roadmap: post-MVP provisioning (explicitly NOT the MVP B10 gate)*

## Why

PROV's MVP gate covers the MVP delivery subset only
(oss-cad-suite, librelane, opensta, magic, netgen,
klayout, ngspice, xyce, xschem, cace + MVP pip groups).
The deferred packs — nextpnr (off_mvp FPGA), pymeep,
openEMS, palace, gmsh (EM), elmer (thermal), devsim
(device) — keep their provisioner recipes and RED
conformance evidence (`contracts/conformance/deferred/`)
but must never block the MVP bundle claim. See
PRD/tech-stack.md matrix rows and task `delivery` in
`contracts/v1/catalog/tasks.json`.

## What

- Keep install recipes for deferred packs working;
  fix the live-install failure class with tests, as
  with MVP packs.
- Qualify each deferred pack with good/bad fixtures
  before any post-MVP bundle claim.
- Palace stays unsourced until its install docs are
  read; nextpnr/openvaf have no recipe yet (record,
  do not fake).
- Contract + api_spec regen; full suite + gate green.

## Acceptance

- Each deferred pack installs pinned + asserted on a
  networked host, or carries an exactly-named remedy.
- MVP `--check-only` verdict never mentions deferred
  packs as missing (separate deferred verdict line).
