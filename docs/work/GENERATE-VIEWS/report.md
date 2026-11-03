# GENERATE-VIEWS lane report — generate_views ToolAdapter over real gdsfactory

Ticket: `docs/tickets/GENERATE-VIEWS.md` · Branch: GREEN-the-tests ·
No commits, no pushes (integrator commits).

## Files added (new files only — zero edits to existing files)

- `src/adapters/gdsfactory/adapter.py` — `GdsfactoryViewsAdapter`
  behind `generate_views` (ToolAdapter: capabilities/preflight/
  execute/parse), registered `RECIPES` (import_gds, build_cells,
  export_gds, export_oasis) with project sources in and identity
  mappings + diagnostics out.
- `src/adapters/gdsfactory/_driver.py` — staged driver (job JSON in,
  envelope JSON on stdout): real gdsfactory import/build/export,
  macro pin/obstruction artifacts with provenance, loud
  missing-dependency/invalid-cell errors. Nothing hardcoded.
- `tests/adapters/test_generate_views.py` — 29 tests proving RED→GREEN:
  file-loader RED, preflight/parse/execute units on canned envelopes,
  FakeRunner engine dispatch (PASS + FAIL-carries-run_id), driver
  generalization pin, real-driver loud-missing proof, and 4
  skip-gated live tests (generic straight, cspdk MZI identity,
  export→import roundtrip, smoke agreement).
- `tests/adapters/fixtures/generate_views/mzi_views.yml` — project view
  spec: cspdk si340 MZI + `mzi.gds` export.
- `tests/adapters/fixtures/generate_views/straight_views.yml` —
  project view spec: generic straight, no cspdk needed.
- `tests/adapters/fixtures/generate_views/macro_pin_map.yml` — project
  macro pin map (pins + obstructions for import binding).
- `docs/work/GENERATE-VIEWS/wiring.patch` — the integrator patch as a
  file (byte-identical to the embedded diff below).
- `docs/work/GENERATE-VIEWS/report.md` — this file.

## Contract implemented (ticket clause → behavior)

- RED-first `generate_views` ToolAdapter over the real installed
  gdsfactory — `GdsfactoryViewsAdapter` follows the SAX/Circulax
  stage-driver-plus-job-JSON protocol; the verdict always comes from
  parsed output, and a gdsfactory-less or PDK-less interpreter raises
  `missing_dependency`, never fake-green.
- Registered recipes (GDS import, PDK cell build, GDS/OASIS export)
  with project sources in and identity mappings + diagnostics out —
  `RECIPES` names the four recipes; capabilities advertises them;
  build/export take a project view-spec YAML (PDK, cells, params,
  export filenames), import takes project `.gds` files. Parse returns
  per-source identity mappings (`source` → `component`, ports,
  polygon count, bbox), per-cell measurements, diagnostics (recipe,
  versions, active PDK, roundtrip readback, notes), and artifact
  paths. Unknown recipes, unknown PDKs, empty cells, scalar params,
  and wrong export extensions fail in preflight with stable codes.
- The MZI smoke demotes to a qualification fixture — the adapter never
  names the MZI (pinned by the driver-generalization test); one live
  test asserts op-vs-`run_layout_smoke` agreement on ports, polygon
  count, and bbox; the wiring patch rewords the smoke docstring to
  name the adapter as the full op and the smoke as its fixture.
- PDK-cell coverage rides the PDK lanes — no cell catalogue here; the
  op consumes whatever cells the project spec names.
- Macro pin/obstruction mapping published as artifacts per the PRD
  boundary note — every recipe writes `<cell>.pins.json` and
  `<cell>.obstructions.json` into the workdir and reports them as
  `artifacts`. A bound project `pin_map` reconstructs them
  (`reconstructed: true`, source `project-pin-map`); otherwise the
  artifact carries the boundary note (import alone does not
  reconstruct them). Built-cell pins are authoritative
  (`built-ports`, reconstructed); built obstructions are honestly
  absent with a note.
- GDS roundtrip is an artifact, not the test — the export recipes
  publish the layout file as a `layout` artifact; GDS readback match
  lands in `diagnostics.roundtrip_match` (a measurement-free note),
  never in the verdict. OASIS refuses loudly (`unsupported_format`)
  where `Component.write_oas` is absent, and reports bytes-written
  with an explicit no-readback note where present.

Error codes (`AdapterError`): `unsupported_operation` (another op),
`invalid_command` (bad recipe/timeout/spec/pin-map/export name),
`invalid_reference` (missing sources/workdir/cspdk path, unparsable
YAML), `missing_dependency` (no layout python, no gdsfactory/PDK),
`runner_unavailable` (timeout, no envelope, no result). Driver
failures synthesize `views.unknown_cell` / `views.unreadable_source` /
`views.unsupported_format` / `views.failed` error violations with
file/line. Duplex routing: violations → ledger findings, measurements
→ verdict, artifacts → workdir paths in the parse result.

## RED → GREEN evidence

Toolchain: repo `.venv` via `scripts/install.sh --install` (the only
env path; `UV_CACHE_DIR=/tmp/uv-cache UV_LINK_MODE=copy`). The layout
group is not installed by install.sh, so live tests skip exactly like
the smoke's own live tests; one test executes the real staged driver
to prove it fails loud (`missing_dependency`, exit 3) without the
solver.

RED (adapter + driver absent):

    .venv/bin/python -m pytest tests/adapters/test_generate_views.py -q
    # 25 failed, 4 skipped — every failure is FileNotFoundError for
    # src/adapters/gdsfactory/adapter.py; skips are the live tests.

GREEN (adapter + driver added; first run green, no fixes needed):

    .venv/bin/python -m pytest tests/adapters/test_generate_views.py -q
    # 25 passed, 4 skipped in 0.18s

Gates and neighbors:

    .venv/bin/python scripts/check_docstrings.py
    # clean (exit 0) — full-tree gate, new files included
    .venv/bin/python scripts/check_docstrings.py \
      src/adapters/gdsfactory/adapter.py src/adapters/gdsfactory/_driver.py
    # clean (exit 0)
    .venv/bin/python -m pytest tests/adapters/test_gdsfactory.py \
      tests/adapters/test_circulax_optical.py \
      tests/adapters/test_meow_em.py tests/test_docstrings.py \
      tests/test_api_spec.py tests/test_contract.py tests/test_no_cloud.py -q
    # 1 failed, 59 passed, 9 skipped — the single failure was
    # test_mcp_description_matches_docs_summary failing with a
    # ModuleNotFoundError inside the installed mcp package while a
    # parallel lane rebuilt the shared .venv; it passes in isolation
    # (1 passed in 9.87s) and is unrelated to this lane.

Style: no line over 100 chars in new files or patch-added lines.

## Wiring verification (integrator pre-check, all on /tmp copies)

- `/tmp/gv_base` = pristine `git archive HEAD` + this lane's 6 new
  files; `/tmp/gv_wired` = base + the patch below. The patch was
  generated as the exact diff between them.
- `git apply --check docs/work/GENERATE-VIEWS/wiring.patch` clean on
  the real tree at HEAD `272c9cf`.
- All patched files `py_compile` clean.
- `scripts/api_spec.py --write` then `--check` clean on the wired
  copy: `generate_views` wired=True, handler
  `rocket_engine.adapters.gdsfactory.adapter.GdsfactoryViewsAdapter`,
  required Job keys `recipe` + `sources`, help + reference sections
  generated. (Needs the api_spec hunk: `solver_map` previously
  resolved only `adapters/<name>/__init__.py`; `_handler_ref` already
  anticipated submodule adapters. This also unblocks the
  Circulax/Meow lanes' future wiring.)
- `scripts/contract.py --write` then `--check` clean on the wired
  copy; `scripts/check_docstrings.py` clean on the wired copy.
- Wired end-to-end (`/tmp/gv_wired_endtoend.py`, engine imported from
  the wired copy via a throwaway symlink, repo env untouched):
  `generate_views` appears in capabilities, the op is
  default-registered, and a build run without gdsfactory judges
  NOT_RUN with a `missing_dependency` reason — loud, never green.
- Full wired-copy suite (HEAD tests + this lane, PDK dirs excluded —
  see suite note): 23 failed, 1387 passed, 261 skipped. Pristine-base
  suite in the same window: 50 failed, 1370 passed, 251 skipped
  (same 1671 total; the base window caught shared-.venv churn from
  parallel lanes). Every wired failure also fails on pristine base —
  the patch introduces zero new failures (verified by diffing the
  FAILED sets: wired-minus-base is empty). The 23 shared failures are
  environmental: 5 drc_kl + 1 klayout-scenario + 1 engine_run
  deck-selection (missing git-ignored fixture GDS files under
  `tests/adapters/fixtures/drc_kl/`, absent from `git archive` in
  both copies equally), 13 mutate fixture-pristine, 3 demo-path PDK
  register (ROCKETEDA_HOME is read-only in this sandbox).

## Wiring patch for the integrator (exact unified diff)

Also shipped as `docs/work/GENERATE-VIEWS/wiring.patch` (byte-identical
to the block below; prefer the file). Apply with
`patch -p1 < docs/work/GENERATE-VIEWS/wiring.patch` from the repo root
at HEAD `272c9cf`, then run the integrator steps below. Order with
other lanes does not matter (no shared hunks beyond the _solvers tail;
re-check `git apply --check` at apply time on the shared tree).

```diff
--- a/src/composition.py
+++ b/src/composition.py
@@ -43,6 +43,7 @@
 from .adapters.drc_kl import KlayoutDrcAdapter
 from .adapters.errors import AdapterError
 from .adapters.extract_magic import MagicExtractAdapter
+from .adapters.gdsfactory.adapter import GdsfactoryViewsAdapter
 from .adapters.hdl_sim import HdlSimAdapter
 from .adapters.lvs_netgen import NetgenLvsAdapter
 from .adapters.ngspice import NgspiceAdapter
@@ -270,6 +271,7 @@
             "run_syntax": {"slang": SyntaxAdapter()},
             "run_connectivity": {"connectgraph": ConnectivityAdapter()},
             "run_erc": {"connectgraph": ConnectivityAdapter()},
+            "generate_views": {"gdsfactory": GdsfactoryViewsAdapter()},
         }
         self._yaml = YAML(typ="safe")
         self._constraints = dict(constraints) if constraints is not None else None
--- a/src/interfaces/setup.py
+++ b/src/interfaces/setup.py
@@ -61,6 +61,7 @@
     ("run_syntax", "slang"): {"binaries": ["slang"]},
     ("run_connectivity", "connectgraph"): {},
     ("run_erc", "connectgraph"): {},
+    ("generate_views", "gdsfactory"): {"python": ["gdsfactory"]},
 }
 
 
--- a/src/interfaces/setup_catalogue.yaml
+++ b/src/interfaces/setup_catalogue.yaml
@@ -65,6 +65,12 @@
     python: [sax]
     remedy: "sax not installed, uv sync --group photonic (B10-owned tooling)"
     recipe: "pyproject.toml [dependency-groups] photonic: uv sync --group photonic (B10)."
+  - id: gdsfactory
+    kind: python
+    label: gdsfactory (layout views)
+    python: [gdsfactory]
+    remedy: "gdsfactory not installed, uv sync --group layout (B10-owned tooling)"
+    recipe: "pyproject.toml [dependency-groups] layout: uv sync --group layout (B10)."
   - id: cvc
     kind: tool
     label: cvc
--- a/scripts/api_spec.py
+++ b/scripts/api_spec.py
@@ -147,6 +147,10 @@
             rel = f"adapters/{parts[1]}/__init__.py"
             for alias in node.names:
                 locations[alias.asname or alias.name] = rel
+        if len(parts) == 3 and parts[0] == "adapters":
+            rel = f"adapters/{parts[1]}/{parts[2]}.py"
+            for alias in node.names:
+                locations[alias.asname or alias.name] = rel
     solvers = {}
     for node in ast.walk(tree):
         if not isinstance(node, ast.ClassDef) or node.name != "Engine":
--- a/src/adapters/gdsfactory/__init__.py
+++ b/src/adapters/gdsfactory/__init__.py
@@ -8,8 +8,9 @@
 fail loud (`missing_dependency`), never fake-green. The cspdk
 tree is git-ignored vendor data: pass `cspdk_path`
 (`scripts/fetch_fixtures.py --only cspdk`) where the package
-is not installed. A full layout Engine adapter is follow-up,
-out of scope.
+is not installed. The full layout Engine adapter is
+GdsfactoryViewsAdapter (generate_views, adapter.py); this smoke is
+its qualification fixture.
 """
 
 import sys
```

## Integrator steps

1. `git apply --check docs/work/GENERATE-VIEWS/wiring.patch`, then
   `patch -p1 < docs/work/GENERATE-VIEWS/wiring.patch` from the repo
   root.
2. `export UV_CACHE_DIR=/tmp/uv-cache UV_LINK_MODE=copy` (the default
   uv cache is read-only in this sandbox), then
   `scripts/install.sh --install` to refresh the sealed engine copy.
3. `python scripts/api_spec.py --write && python scripts/api_spec.py
   --check` — regenerates `docs/engine-api.md`,
   `docs/api-schema.json`, `docs/api-help.json` with the wired
   `generate_views` section (verified on the wired copy).
4. `python scripts/contract.py --write && python scripts/contract.py
   --check` — regenerates `docs/contract.json` (verified).
5. `.venv/bin/python -m pytest tests/ -q` — full suite green
   (see suite note); plus `scripts/check_docstrings.py` clean.
6. Live proof (needs the layout group + cspdk, neither shipped by
   install.sh): `uv sync --group layout`,
   `scripts/fetch_fixtures.py --only cspdk`, then
   `.venv/bin/python -m pytest tests/adapters/test_generate_views.py
   -q` — the 4 skipped live tests (generic straight, cspdk MZI
   identity, export→import roundtrip, smoke agreement) must pass.

Suite note: this lane never touches `tests/pdk_*/` or `docs/pdk/*`;
the PDK dirs were excluded from the lane's full-suite runs. The
transient `test_api_spec` mcp-import failure seen mid-lane came from
shared-venv churn and passes in isolation. The wired-vs-base failure
sets were diffed above — the patch introduces zero new failures.
