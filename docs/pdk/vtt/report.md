# PDK-VTT lane report: verdict BLOCKED (upstream broken as-shipped)

## Verdict

Upstream gvtt 0.1.0 (`https://github.com/gdsfactory/vtt.git` @
`001df503792a0297165c239d3c63de1322add10a`, 2026-09-15) is **broken in its
documented install path**: `import gvtt` raises
`ImportError: cannot import name 'constants' from 'gdsfactory.pdk'` under
every gdsfactory installable here (9.40.2, 9.45.0 in its declared range;
9.51.0, the repo's pin). It is also **excluded from the repo layout
closure** by its own `<9.46.0` ceiling vs the repo's `>=9.51,<10` floor.
No DRC/LVS deck and no models ship at all. Per the lane contract this is
reported as the verdict with evidence; no behavioral proof is fabricated.
The lane ships inventory + verdict-pin tests, one fixture, and matrix rows
marked `blocked`/`n/a` with unblock conditions.

Diagnostic (not proof): the rot is exactly one stale import line. With a
process-local shim (`gdsfactory.pdk.constants = Constants()`, ships
nowhere) all 12 cells build under 9.45.0 and 9.51.0 with identical bboxes,
and KLayout-XOR vs upstream `tests/ref` is clean (bend_euler, straights)
or sub-nm drift (mmi1x2). Upstream is one line + one bound-bump away from
healthy; see "Shared-change requests".

## Files added (lane dirs only, nothing committed)

- `tests/pdk_vtt/__init__.py` -- lane docstring.
- `tests/pdk_vtt/_profile.py` -- YAML/sha256 loaders (ruamel + stdlib).
- `tests/pdk_vtt/test_profile.py` -- 5 tests: identity/schema, pins vs
  upstream lock, variant inventory, pinned `blocked` verdict, repo-closure
  exclusion (VTT ceiling vs repo floor parsed and compared).
- `tests/pdk_vtt/test_inventory.py` -- 4 tests: fixture provenance +
  sha256 golden, 67 view count vs profile, 16 golden (layer, datatype)
  pairs, wellformedness/uniqueness + documented absence of 89/x views.
- `tests/pdk_vtt/fixtures/layers.yaml` -- verbatim upstream
  `gvtt/layers.yaml` (MIT; sha256
  `0735910f...430e3b85e`, pinned by test).
- `docs/pdk/vtt/profile.yaml` -- pins, single `3umsoi` variant, tech/deck
  (null)/model (absent) relpaths, fixture provenance, verdict block.
- `docs/pdk/vtt/recipe.md` -- upstream's own commands with per-command
  verification outcomes (one VERIFIED, rest BLOCKED offline w/ errors).
- `docs/pdk/vtt/matrix.md` -- proposed rows: layout/drc/optical-sim
  `blocked`, lvs `n/a (photonic)`, with caveats B1/B2/B3/P1/P2/P3.
- `docs/pdk/vtt/report.md` -- this file.

## Pins

- gvtt `0.1.0` (pyproject + `__version__`), MIT, requires-python `>=3.11`.
- gdsfactory range `>=9.0.1,<9.46.0` (pyproject, verbatim); uv.lock pins
  `9.0.1` (what upstream CI installs).
- Upstream commit `001df503792a0297165c239d3c63de1322add10a` (shallow).
- Repo layout group `gdsfactory>=9.51,<10`, locked `9.51.0` (read-only
  from repo `pyproject.toml`/`uv.lock`; recorded in profile as
  `verified_against`, never edited).

## Upstream health evidence

Package health (commands run; env was `PYTHONPATH` closures of 92-94
unpacked wheels from the local uv cache + `/tmp/pdk-sources/vtt` --
repo `.venv` untouched, `uv sync` never run, no network):

- `import gvtt` on gf 9.40.2 -> ImportError `constants` (tail of trace
  in verdict block). Same on 9.45.0. Same on 9.51.0 (repo pin; probe env
  forced pydantic 2.14.1 against kfactory's `<2.14` bound -- wart noted,
  does not affect the missing-symbol conclusion, which comes from
  gdsfactory's own `pdk.py` source).
- `grep from gdsfactory.pdk import` over all five pre-cloned PDKs: only
  VTT imports `constants`; cspdk/ubc/gf180/ihp import `Pdk` alone.
- `Pdk.constants` in modern gf is `kfactory.layout.Constants` with a
  default factory, so the kwarg gvtt passes is unnecessary -- the fix is
  to delete it (exactly the sibling-PDK shape).
- Locked-9.0.1 path: uninstallable offline (`uv run --with` ->
  `failed to fetch ... files.pythonhosted.org ... tunnel error:
  unsuccessful`); "healthy at lock" is UNVERIFIED, claimed nowhere.
- `python install_tech.py` with `HOME=/tmp/...`: exit 0, KLayout tech
  symlink created -- the one upstream command verified working.
- Wheel/editable build: unverifiable offline (`flit_core` backend not in
  cache, no network). `pyproject.toml` metadata parses (tomllib).

Docs: README install lines only; `docs/index.md` includes README;
`docs/changelog.md` is an empty header; `docs/cells.rst` lists 12 cells
with defaults; of 5 tutorials only t4 (gvtt import commented out) and t5
(imports gvtt, uses generic gf cells) touch gvtt. No VTT-specific usage,
rule, or model docs.

Decks/models (`find` for `*drc* *lvs* *.lydrc *.lyd25 *sparam* *model*
`*.xschem* *magic* *netgen* *.spice* *.lib*` -> empty): `gvtt/klayout`
holds only `tech.lyt` (tech `VTT`, dbu 0.001), `layers.lyp`, and
`layer_boolean.lym` (ADD/SUB/CPY boolean-merge helper macro, not a deck).
No `models.py`, no `sparameters/` dir (despite `PATH.sparameters`), no
stimulus data. 11 upstream `tests/ref/*.gds` regression refs exist
(2-36 KB) plus settings yml per cell.

## RED -> GREEN

TDD gate, lane tests only (never the full suite):

- RED: tests written before profile/fixture existed; command
  `PYTHONPATH="$(cat /tmp/vtt-lane/pypath.txt)" MPLCONFIGDIR=/tmp/vtt-lane/mpl
  python3 -m pytest tests/pdk_vtt/ -p no:cacheprovider -q`
  (from repo root) -> **9 failed** (`missing lane profile ...`,
  `missing fixture ...`).
- GREEN: after adding `docs/pdk/vtt/profile.yaml` +
  `tests/pdk_vtt/fixtures/layers.yaml`, same command ->
  **9 passed in 0.19s**.

## Test results

`tests/pdk_vtt/`: 9/9 pass. They assert inventoried facts + the pinned
verdict (stdlib + `ruamel.yaml`, a repo base dep, + pytest; no
gdsfactory/network/KLayout needed, so they run in any repo env).

## Shared-change requests for the integrator (lane made none of these)

All paths below are FORBIDDEN to this lane; exact edits requested:

1. Upstream fix (preferred, unblocks everything): in `gvtt/__init__.py`,
   change `from gdsfactory.pdk import Pdk, constants` to
   `from gdsfactory.pdk import Pdk` and drop `constants=constants` from
   the `Pdk(...)` call; in `pyproject.toml` raise
   `gdsfactory>=9.0.1,<9.46.0` to admit `9.51` (diagnostic evidence:
   shimmed builds are bbox-identical on 9.45.0 and 9.51.0 and XOR-clean
   vs upstream refs). Then this lane flips `profile.yaml` verdict to
   healthy and adds behavioral proofs (cell builds + XOR goldens) -- do
   NOT flip the profile without re-running those.
2. Catalogue/matrix placement: put the `docs/pdk/vtt/matrix.md` rows in
   the ENGINE-SETUP matrix as `blocked`/`n/a` with caveats attached;
   do not mark drc/optical-sim `✓ with caveat` (no rule values or models
   ship to derive goldens from -- any threshold would be invented).
3. No `install.sh` mode, no dependency change, no `setup_catalogue.yaml`
   row beyond the matrix placement: VTT must NOT enter the layout
   closure until (1) lands (its ceiling conflicts with `gdsfactory>=9.51`).
4. Networked-host re-run (integrator, when PyPI is reachable): `pip install
   "gvtt==0.1.0"` then `python -c "import gvtt"` to confirm the ImportError
   on a stock host, and `uv sync --all-extras && make test` inside the
   upstream clone to check the locked-9.0.1 "healthy at lock" question
   this sandbox could not answer.
