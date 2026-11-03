# PDK-GF180 lane report

## Files added (lane dirs only)

`tests/pdk_gf180/`:

- `__init__.py` — lane package marker.
- `_profile.py` — profile loader (`FileNotFoundError` on the empty
  lane) + `gf180mcu` resolution (installed import, else
  `$PDK_GF180_SRC`), with loud-skip helper.
- `test_profile.py` — 8 tests: identity, pins, variant, tech +
  model relpaths resolve, honest DRC position, uninitialized
  libraries, proof goldens present.
- `test_inv_build.py` — 2 tests: fixture build vs goldens
  (ports/layers/bbox/size), deterministic rebuild.
- `test_drc.py` — 3 tests: clean proof (width 0, space total
  pinned 16, lane routing 0/0, shape/net counts) + width-dirty
  and space-dirty tripwires. Rules read from profile data; the
  KLayout batch script converts um→DBU.
- `test_ngspice_sim.py` — 1 test: inverter DC sweep vs goldens
  (rails + switching window); include strategy adapts to the
  provision path (corner wrappers exist post-release only).
- `fixtures/inv_pair.py` — the proof fixture (inverter-class
  CMOS cell; see below) + standalone `main`.
- `fixtures/README.md` — fixture provenance (no usable PDK
  inverter: stdcell submodules uninitialized; BJTs not CMOS).

`docs/pdk/gf180/`:

- `profile.yaml` — pins, one proven `mcu` variant (tech/deck/
  models relpaths), inventoried libraries, proof goldens.
- `recipe.md` — provision commands, each verified by running.
- `matrix.md` — proposed capability-matrix rows (PASS + honest
  N/A with promotion notes).
- `report.md` — this file.

No other paths created or modified (forbidden dirs untouched;
no commits; nothing pushed).

## Proof fixture

`gf180_inv_pair` (lane-authored composition on PDK primitives):
guardless `nfet` (W/L 0.5/0.28 um) + guardless `pfet` (W/L
1.0/0.28 um) from `gf180mcu/cells/fet.py` (upstream,
Apache-2.0), single-metal1 routing (gate/drain straps, VSS/VDD
stubs), explicit p-tap/n-tap bulk ties, hand-drawn n-well, ports
IN/OUT/VDD/VSS. Guard rings omitted (`grw=0`) — the closed ring
cannot be crossed on one layer; a guarded inverter needs a
metal2 hop the stand-in deck cannot qualify. Goldens: bbox
[[-1.15,-0.71],[1.97,4.3]], 7 layers, 16 metal1 shapes →
6 nets, sim rails + 1.32–1.65 V switching window.

## Pins

- `gf180mcu==1.0.0` (both paths).
- Release path: `gdsfactory==9.40.2` (release requires
  `~=9.40.0`) — CONFLICTS with the repo `.venv` (9.51.0).
- Source-tree path: `d422b86` + `gdsfactory==9.51.0` (tree
  allows `>=9.45,<=9.51`; repo `layout` group).
- Tools: KLayout 0.28.16 batch, ngspice-42, Python 3.12.

## RED → GREEN evidence

RED (empty lane: tests + fixture present, profile absent):

```sh
PYTHONPATH=/tmp/pdk-sources/gf180 PDK_GF180_SRC=/tmp/pdk-sources/gf180 \
  .venv/bin/python -m pytest tests/pdk_gf180 -q
# 11 failed, 3 errors in 0.08s — every case FileNotFoundError on
# docs/pdk/gf180/profile.yaml (sample: test_profile_identifies_gf180)
```

GREEN (profile + docs landed; two lane bugs fixed along the way:
`write_gds` returns `PosixPath`, and the KLayout script needs DBU
units — the um bug initially masked 16 real PDK-interior space
hits, now pinned as goldens with lane routing at 0/0):

```sh
PYTHONPATH=/tmp/pdk-sources/gf180 PDK_GF180_SRC=/tmp/pdk-sources/gf180 \
  .venv/bin/python -m pytest tests/pdk_gf180 -q
# 14 passed in 4.35s
```

Recipe verifications (all ephemeral/scratch; repo `.venv` used
read-only as interpreter, never synced):

- `uv run --with "gf180mcu==1.0.0" --no-project` → 1.0.0 /
  gdsfactory 9.40.2; fixture build identical geometry; sim table
  bit-identical to the source path.
- `python install_tech.py` under scratch HOME → KLayout batch
  `TECHS: ['', 'gf180mcu']`.
- `ngspice -b` inverter sweep both paths → rails + window goldens.

Only the lane's tests were run (no full suite; another agent owns
the live gates).

## Test results

14 passed: 8 profile + 2 build + 3 DRC + 1 sim. No skips in this
sandbox (PDK via `$PDK_GF180_SRC`, klayout + ngspice ambient).
Tests skip loudly (never fake-green) where the PDK, klayout, or
ngspice is absent.

## Shared-change requests for the integrator (exact edits)

The lane makes none of these (forbidden paths); each is listed
for the later commit:

1. `src/interfaces/setup_catalogue.yaml` — append a PDK entry
   after the `sky130A` block (same shape):
   `id: pdk-gf180, kind: pdk, label: PDK gf180mcu, pdk_id:
   gf180mcu, source_default: ~/.local/share/pdk/gf180mcu,
   decks: []` (no PDK deck ships — stand-in rules live in
   `docs/pdk/gf180/profile.yaml`), `remedy:` register the tree
   via `scripts/install.sh --pdk-only` with `PDK_SOURCE` set,
   `recipe: "docs/pdk/gf180/recipe.md (PDK-GF180)."`.
2. `scripts/install.sh` `--pdk-only` — accept `PDK_ID=gf180mcu`
   (today it defaults to the sky130A tree); no new mode needed
   if `--pdk-only` already honors `PDK_ID`/`PDK_SOURCE`/revision
   env (it does per `--help` header) — just document the gf180
   invocation: `PDK_ID=gf180mcu PDK_SOURCE=<tree>
   PDK_REVISION=d422b86... scripts/install.sh --pdk-only`, plus
   the KLayout tech step `python install_tech.py` from recipe §2
   (or a `--klayout-tech` hook if B10 adds one).
3. Deps — NO pyproject change for the source path (repo
   `layout` group already pins `gdsfactory>=9.51,<10` ✓).
   Release-path caveat: PyPI `gf180mcu==1.0.0` needs
   `gdsfactory~=9.40.0`, unsatisfiable beside the lock —
   document "release path needs its own env" wherever PDK deps
   are listed; do NOT downgrade the lock.
4. Future (not this lane): stdcell/corner/signoff promotions
   need submodule fetch (`git submodule update --init` for
   `gf180mcu/src/*`, network), user-supplied fd_pr/volare
   decks, and new proofs — matrix rows name each trigger.
