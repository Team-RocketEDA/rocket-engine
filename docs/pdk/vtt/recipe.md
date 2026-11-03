# VTT provision recipe (PDK-VTT lane)

EXACT commands from the PDK's own docs/source, each with its verification
outcome. Source commit `001df50` (`001df503792a0297165c239d3c63de1322add10a`).
Sandbox had no PyPI route, so network steps are recorded BLOCKED with the
observed error, never assumed.

## 1. User install (README: "Installation for users")

Upstream command:

```
pip install gvtt --upgrade
```

Then restart KLayout so the new technology appears.

Outcome: BLOCKED offline. `uv run --with gdsfactory` fails in this
sandbox with a proxy tunnel error (`failed to fetch ... files.pythonhosted.org
... tunnel error: unsuccessful`), so no install-from-PyPI step could run
here. On a networked host this pulls the newest gdsfactory `<9.46.0`
(i.e. 9.45.x), under which `import gvtt` raises
`ImportError: cannot import name 'constants' from 'gdsfactory.pdk'`
(verified on 9.40.2 and 9.45.0, see report.md). The documented user path
is therefore broken as-shipped, independent of this sandbox.

## 2. Developer install (README: "Installation for developers")

Upstream commands:

```
git clone https://github.com/gdsfactory/vtt.git
cd vtt
pip install -e . pre-commit
pre-commit install
python install_tech.py
```

Outcomes:

- `git clone ...`: not re-run; the lane verifies against the pre-cloned
  source. Remote confirmed: `git remote -v` ->
  `https://github.com/gdsfactory/vtt.git` (fetch+push).
- `pip install -e . pre-commit`: BLOCKED offline (needs the `flit_core`
  build backend plus gdsfactory from PyPI; neither is installable here).
  Editable-install + wheel build could not be verified in this lane.
- `pre-commit install`: not run (no provisioned env; hook config only).
- `python install_tech.py`: VERIFIED. Ran with a redirected HOME so the
  real `$HOME/.klayout` is untouched:

```
HOME=/tmp/vtt-lane/fakehome python3 /tmp/pdk-sources/vtt/install_tech.py
```

  exit 0, output `link made: From: .../gvtt/klayout To: .../.klayout/tech/vtt`,
  symlink confirmed present. The script symlinks `gvtt/klayout`
  (`layers.lyp`, `tech.lyt`, `layer_boolean.lym`) into the KLayout tech dir.

## 3. CI / dev sync (`.github/workflows/test_code.yml`, `Makefile`)

Upstream commands:

```
uv sync --all-extras
make test            # -> uv run pytest -s
```

Outcome: BLOCKED offline. `uv sync` needs the registry; the lockfile pins
gdsfactory 9.0.1, which is the only dependency set under which upstream's
own suite might still pass -- uninstallable here, so "healthy at lock" is
UNVERIFIED and claimed nowhere in this lane. Upstream `make test` also
needs the `dev` extras (`pytest`, `pytest_regressions`).

## 4. What the lane ran instead (offline, read-only inputs)

Because PyPI was unreachable, behavioral probing used unpacked wheels
already in the local uv cache (92-94 package closures resolved
name-by-name from `~/.cache/uv/archive-v0`, exposed via `PYTHONPATH`;
the repo `.venv` was never touched and `uv sync` never run):

- `import gvtt` matrix on gdsfactory 9.40.2 / 9.45.0 / 9.51.0 ->
  all three raise the `constants` ImportError (report.md has the traces).
- Diagnostic shim probe (`gdsfactory.pdk.constants = Constants()`,
  process-local, ships nowhere): all 12 cells build under 9.45.0 and
  9.51.0 with identical bboxes; KLayout-XOR vs upstream `tests/ref`
  is clean for bend_euler/straight/straight_rib/straight_sc and shows
  only sub-nm vertex drift for mmi1x2. Evidence for the unblock note,
  not a proof: the lane's committed tests assert inventory + verdict,
  never shimmed behavior.

## 5. Lane test command (runs anywhere the repo tests run)

```
python -m pytest tests/pdk_vtt/ -q
```

Stdlib + `ruamel.yaml` (a repo base dependency) + pytest only. No
gdsfactory, no network, no KLayout needed.
