# PDK-CSPDK lane report (si340, CornerStone 340nm SOI)

## Files added (lane dirs only)

- `tests/pdk_cspdk/__init__.py` — lane marker.
- `tests/pdk_cspdk/_profile.py` — profile loader + cspdk-tree
  resolution (installed → `fixtures/upstream/cspdk` → `/tmp/pdk-sources/cspdk`).
- `tests/pdk_cspdk/test_profile.py` — 6 tests: pin, shape, variant
  coverage, engine-rule citation, relpath existence, live version match.
- `tests/pdk_cspdk/test_mzi_build.py` — 4 tests: golden ports /
  geometry / GDS roundtrip on 3/0, fixture provenance.
- `tests/pdk_cspdk/test_drc.py` — 2 tests: ref MZI 0 violations,
  bad layout 1 width + 1 space at golden bboxes.
- `tests/pdk_cspdk/test_sax_sim.py` — 2 tests: 1550 nm cross/bar goldens.
- `tests/pdk_cspdk/fixtures/mzi_ref.gds` — upstream
  `tests/gds_ref_si340/mzi.gds` @ 3323b17b, MIT (see `SOURCE.md`).
- `docs/pdk/cspdk/profile.yaml` — pins + 8 variants + proofs.
- `docs/pdk/cspdk/recipe.md` — provision recipe with per-step status.
- `docs/pdk/cspdk/matrix.md` — proposed matrix rows.
- `docs/pdk/cspdk/report.md` — this file.

## Pins (all verified first-hand)

- `cspdk==2.1.0` — `pyproject.toml` version, `cspdk.__version__`,
  live import, git rev `3323b17b`, all against `/tmp/pdk-sources/cspdk`.
- `gdsfactory==9.51.0`, `sax==0.18.2` — repo `uv.lock` + live imports.
- Pre-cloned source is byte-identical to the repo's
  `fixtures/upstream/cspdk` tree (`diff -rq -x .git` clean).

## RED → GREEN evidence

RED (empty lane, profile + fixture absent):

```sh
.venv/bin/python -m pytest tests/pdk_cspdk -q
# 14 failed in 0.40s — all FileNotFoundError on docs/pdk/cspdk/profile.yaml
```

GREEN (profile + fixture + docs landed):

```sh
.venv/bin/python -m pytest tests/pdk_cspdk -q
# 14 passed in 6.02s
```

Two test-side bugs were fixed between runs (goldens never moved):
`pytest.approx` rejects nested lists (bbox compare flattened), and
the expected `sorted(variants)` order put `si_sus` after `sin300`
(`_` sorts before `n`). Full suite was NOT run (another agent owns
live-gate repairs); only `tests/pdk_cspdk` executed.

## Commands run (verification probes, all in /tmp, none committed)

- `uv run --with cspdk==2.1.0 --no-project` → PyPI unreachable
  (connect timeout after 3 retries); pip step is NOT-RUN-HERE,
  re-run by the integrator on a networked host.
- Repo `.venv` python (read-only execution, no installs) with the
  pre-cloned tree: MZI build goldens, 39 models, SAX 1550 nm pair,
  engine `KlayoutDrcAdapter` ref-0 / bad-2 runs.
- `klayout -b` (0.28.16) tech-install probe against scratch HOME:
  `TECHS: ['', 'Cornerstone_si340']`, `HAS_SI340: True`.
- `pdftotext` on `references/CORNERSTONE-49th-Call-Design-Guidelines-1.pdf`:
  Table 4 (GDS 3/0 → 350 nm feature / 200 nm gap) confirmed.

## Shared-change requests for the integrator (not made — outside lane ownership)

1. `git add -f tests/pdk_cspdk/fixtures/mzi_ref.gds` — `*.gds` is
   git-ignored; the fixture must be force-added (or add a
   `!tests/pdk_cspdk/fixtures/*.gds` negation to `.gitignore`).
2. Catalogue/matrix: add the `docs/pdk/cspdk/matrix.md` rows
   (layout ✓, drc ✓ klayout-engine-rules, optical-sim ✓ sax,
   lvs n/a photonic) wherever sibling lanes land theirs.
3. Re-run `uv pip install "cspdk==2.1.0"` on a networked host, then
   re-run `pytest tests/pdk_cspdk` to confirm the pip path.
4. Optional upstream patch (two lines): link si340 in
   `install_tech.py` alongside si220/sin300; optionally fix
   `cspdk.si340.config.PATH` (`klayout/tech/*` does not exist).
