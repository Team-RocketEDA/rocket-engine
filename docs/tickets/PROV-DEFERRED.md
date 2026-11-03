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

## Qualify verdict (2026-11-02, recipe-review + pin-record)

Live `--install` needs a networked host: this host has no
route to PyPI (https fetch times out) and no Docker daemon
(permission denied on the socket), so live provisioning is
loud-skipped here. Each pack below is qualified by
recipe-review (pinned installer + upstream source present in
`scripts/provision_toolchain.sh`, untouched by this slice) and
pin-record; the live `--install` + assert stays BLOCKED-needs-host
(a networked machine), never faked green.

| pack | pin-record | recipe-review | live `--install` |
|---|---|---|---|
| pymeep | `PYMEEP_PIN="1.35.0"` | `install_pymeep` (conda-forge env) + `meep.readthedocs.io` | loud-skip |
| openems | `OPENEMS_REF="v0.37.0"` + `CSXCAD_REF="v0.7.0"` | `install_openems` + `openEMS.de` | loud-skip |
| devsim | `DEVSIM_PIN="2.11.2"` | `install_devsim` (venv pip) + `pypi.org/project/devsim` | loud-skip |
| elmer | `ELMER_PPA="ppa:elmer-csc-ubuntu/elmer-csc-ppa"` (PPA-tracked, needs sudo) | `install_elmer` + `csc.fi/web/elmer` | loud-skip |
| palace | unsourced (`install_palace` is remedy-only, returns 1) | `docs/provision-sources.md` section 12 (not yet read) | unsourced, no row action |
| nextpnr | no recipe yet | recorded, do not fake | BLOCKED-needs-host |
| openvaf | no recipe yet | recorded, do not fake | BLOCKED-needs-host |
| gmsh | no recipe yet | recorded, do not fake | BLOCKED-needs-host |

Setup-surface cross-check: the provision catalogue carries
remedy + recipe rows for pymeep, openems, elmer, and devsim;
palace stays `provisionable: false` with its unsourced remedy
(`tests/interfaces/test_setup.py` deferred-qual). The
`--check-only` MVP verdict never gates on these packs
(separate `PROV-DEFERRED:` line).
