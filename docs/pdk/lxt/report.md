# PDK-LXT lane report

Branch GREEN-the-tests, 2026-10-31. No commits made (integrator
commits); nothing pushed; full suite never run (lane tests only).

Canonical source (found by this lane, no central clone existed):
`https://github.com/Luxtelligence/lxt_pdk_gf.git` @
`d16db6a4882657feb1ce696c16c604ff6cb7ccfa` (2026-06-01, merge PR
\#124; package `lxt_pdk_gf` 2.0, MIT). Evidence: PyPI `lnoi400` page
names the repo + clone URL; `git ls-remote` HEAD equals the shallow
clone HEAD (`/tmp/lxt-pdk`, depth 1).

## Files added (lane dirs only)

```text
tests/pdk_lxt/
  __init__.py              # package marker
  test_profile.py          # 8 tests: id/pins/variants/relpaths/gate honesty
  test_proofs.py           # 5 tests: cell build, SAX goldens, klayout sanity,
                           #   lnoi400 variant, frozen-fixture structure
  test_user_deck.py        # 4 tests: stand-in deck flow + missing-deck loudness
  fixtures/straight_L10.gds        # 2554-byte proof fixture (see PROVENANCE.md)
  fixtures/ltoi300.layers.yaml     # verbatim upstream copy
  fixtures/PROVENANCE.md           # source + license + hashes
  fixtures/standin_deck/ltoi300.stand-in.lydrc  # labelled stand-in, zero rules
docs/pdk/lxt/
  profile.yaml             # 2 variants, pins, tech/deck/model relpaths
  recipe.md                # provision commands + per-command verification
  matrix.md                # proposed capability-matrix rows + caveats
  report.md                # this file
```

No other paths created or modified (verified via `git status`).

## Pins

Upstream `d16db6a…` · `lxt_pdk_gf` 2.0 · python 3.12 ·
`gdsfactory~=9.34` · `gplugins>=1.4,<2` (used 1.4.2 source @`f47ed3d`)
· `sax~=0.16.3` · KLayout 0.28.16 (batch) · MIT.

Run env for the GREEN evidence below (PyPI-blocked sandbox, see P1):
repo env gdsfactory 9.51.0 + sax 0.18.2 + klayout-python 0.30.12,
upstream tree via `PYTHONPATH=/tmp/lxt-pdk` (byte-identical pinned
clone), gplugins 1.4.2 via `PYTHONPATH=/tmp/gplugins`.

## RED → GREEN evidence

RED (empty lane — tests written first, profile/recipe/fixtures absent):

```sh
cd /home/alrida-ismail/github/rocketEDA/rocket-engine
LXT_LIVE=1 .venv/bin/python -m pytest tests/pdk_lxt -p no:cacheprovider -q
# 17 failed in 0.12s — profile tests on missing profile.yaml, live
# proofs on missing provision (LXT_LIVE=1 fails instead of skipping),
# deck tests on missing fixtures.
```

GREEN, unprovisioned (repo env only — live proofs skip LOUDLY):

```sh
MPLCONFIGDIR=/tmp/mpl-lxt .venv/bin/python -m pytest tests/pdk_lxt -p no:cacheprovider -q
# 13 passed, 4 skipped in 1.20s (skips name docs/pdk/lxt/recipe.md)
```

GREEN, provisioned (real upstream code, goldens asserted):

```sh
MPLCONFIGDIR=/tmp/mpl-lxt PYTHONPATH=/tmp/lxt-pdk:/tmp/gplugins \
LXT_LIVE=1 .venv/bin/python -m pytest tests/pdk_lxt -p no:cacheprovider -q
# 17 passed in 4.62s
```

Two lane-local bugs were fixed between RED and GREEN (both in lane
files, both before any pass): unquoted `~=`/colon YAML scalars in
profile.yaml, and a `%`-format binding bug in the klayout batch
script builders in test_proofs.py.

## Test results (what was proven)

- Profile contract (8): upstream repo + full-sha revision,
  package/license, verbatim dep pins from upstream pyproject, both
  variant stacks + tech/model/cell relpaths + counts (26/13 ltoi,
  23/9 lnoi), the `install_tech.py`-covers-only-lnoi400 gap, DRC
  marked gated with fetch URL + gate requirement on both variants,
  SAX sim path, recipe command presence.
- Live proofs (5): `straight_rwg900_cband(L10)` ports/bbox/layers
  goldens; `straight_rwg900_cband(wl=1.55)` |s21|=0.9999424370 +
  complex golden, reciprocal, no reflection;
  klayout-batch GDS structure (`straight_rwg900_cband*`, {2/10:1,
  3/10:1}, ridge bbox [0,-0.45,10,0.45]) + 100 nm width/space sanity
  0 violations (labelled NOT-DRC); lnoi400 build + model goldens
  (|s|=0.9999769744); frozen fixture GDS reads back identically.
- User-deck flow (4): stand-in labelled + points at gate;
  register→resolve hash-pin→verify roundtrip; missing deck raises
  loud `unknown_pdk` naming the deck; layers fixture + provenance.

Golden measurement commands (throwaway probes, kept under /tmp, not
in the repo): `/tmp/lxt-probe-measure.py` (geometry + SAX),
klayout `-b -r` structure/sanity scripts, `install_tech.py` with
`HOME=/tmp/fakehome-lxt` + tech-visibility probe.

## Gated rows (honest, not faked)

DRC `.lydrc` for both variants: gated. Requirement (upstream README "KLayout DRC", verified 2026-10-31):
request access at
<https://resources.luxtelligence.ai/request-access?resource=drc>,
download the stack-specific `.lydrc`, place in `<home>/Klayout/drc/`
(one file at a time), run via GUI Tools → DRC. Verified ungated:
zero deck files in the pinned tree; `.lyd25` is a 2.5D view script,
not a deck; no numeric rule values published anywhere in-repo, so
the lane invents no engine rules. Matrix rows for the deck read
"gated (G1)".

## Shared-change requests for the integrator

(Student-lane ownership forbids touching these; exact edits wanted.)

1. NONE REQUIRED for this lane to land — it is self-contained under
   `tests/pdk_lxt/` + `docs/pdk/lxt/` and imports only the existing
   `rocket_engine.interfaces.pdks` API.
2. Requested re-runs on a networked host (PyPI-blocked here):
   `pip install -e .` per recipe §1, then
   `LXT_LIVE=1 pytest tests/pdk_lxt` in the pinned env
   (gdsfactory~=9.34, sax~=0.16.3) — goldens flag drift as failure.
3. Optional catalogue follow-ups (integrator's call, not needed for
   lane GREEN): add an `lxt` PDK entry to
   `src/interfaces/setup_catalogue.yaml` pointing at
   `docs/pdk/lxt/recipe.md`; add an `lxt` provision mode to
   `scripts/install.sh`; consider proposing upstream the two-line
   `install_tech.py` fix to also link `ltoi300/klayout`.
