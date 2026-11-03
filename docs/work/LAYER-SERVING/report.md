# LAYER-SERVING lane report — layer stackup + preset serving

Ticket: `docs/tickets/LAYER-SERVING.md`. Branch `GREEN-the-tests`.
Nothing committed, nothing pushed (integrator commits).

## Outcome

Delivered a read-only-per-PDK Stackup authority plus KiCad-shaped
`LAYER_PRESET{layers, renderLayers, flip, active}` presets and a
viewer-row query surface, all served from PDK truth (KLayout `.lyp` /
`.lyt` + xsection `.xs` through the hash-checked PDK store). sky130A
serves complete: 429 layers, 292 enabled, `z_complete=True`, viewer
rows + presets round-trip, 3D heights derive from the served spans.

## Files added (new files only; no existing file touched)

- `src/interfaces/layer_serving_stackup.py` — the module: `.lyp` /
  `.lyt` / `.xs` parsers, `build_stackup`, `get_stackup` (store) +
  `get_stackup_from_dir` (plain tree), `builtin_preset`,
  `PresetStore` (save/overwrite/delete/apply), `viewer_rows` +
  `viewer_rows_for_preset`, `LayerServingError`.
- `tests/test_layer_serving_stackup.py` — 35 unit tests incl. live
  sky130A completeness (user tree parsed read-only when present,
  never copied; store test skips unless a sky130a entry exists).
- `tests/test_layer_serving_wiring.py` — 6 integration tests the
  integrator runs AFTER applying the wiring patch (1 fails + 5 skip
  pre-patch by design; must be 6 passed / 0 skipped post-patch).
- `docs/work/LAYER-SERVING/report.md` (this file).
- `docs/work/LAYER-SERVING/wiring.patch` — byte-identical copy of
  the wiring patch embedded below (apply with `patch -p1 <`).

## Served shapes (summary; module docstrings are normative)

- Stackup: `{stackup_version: 1, pdk_id, revision, source, tech,
  dbu_um, layers[], order: "file", enabled[], groups{metal, via,
  frontend, tech, other}, z_complete, z_missing, z_reason}`. Layer:
  `{name, label, base, purpose, gds:[L,D], group, color{frame,fill},
  visible, enabled, z_base_um, z_top_um, thickness_um, z_source,
  stack_index}`. Name is `base.purpose`, `@L/D`-suffixed when one
  head repeats on several GDS (sky130A's four `boundary` entries);
  same head on the SAME GDS is `invalid_stackup`.
- Preset: `{preset_version: 1, name, builtin, stackup_ref, layers
  (full name→bool map), renderLayers, flip, active}`. Built-ins:
  All (every PDK-enabled visible), None (all hidden), All-metal
  (metal+via groups, enabled only), Top (top metal + back-end tech,
  flip=False, active=topmost visible drawing), Bottom (frontend
  group, flip=True, active=lowest visible drawing). Without heights
  Top/Bottom active is None. Saves are sparse (missing→hidden,
  KiCad LSET semantics); unknown names are `invalid_preset`, never
  dropped. Built-in names are reserved (`preset_conflict`).
- Viewer rows: file-order rows with visibility + color + active;
  `visibility=None` honors PDK defaults, overrides win over the
  preset map but never clear its flip.
- Errors: `LayerServingError` codes `unknown_stackup`,
  `invalid_stackup`, `unknown_preset`, `preset_conflict`,
  `invalid_preset`, `invalid_visibility`; store failures reuse
  `PdkError` (`unknown_pdk`, `pdk_drift`) so tamper/deck codes stay
  single-sourced. Missing xsect serves `z_complete=False` + reason
  — heights are never invented.
- sky130A live numbers (user tree, this machine): met1 1.37–1.73,
  met2 2.00–2.36, met3 2.78–3.625, met4 4.015–4.86, met5 5.365–6.625
  µm; via3 spans 2.78→4.015; capm plate 3.635–3.695; All-metal shows
  96 rows; Top→met5.drawing/flip=False, Bottom→poly.drawing/flip=True.

## RED → GREEN evidence

Test runner note: the sealed `.venv` package lags `src/` (peer
lanes' new files are absent there too), and lane rules forbid
touching `.venv`/`uv sync`. RED ran against the sealed package;
GREEN ran with `PYTHONPATH=<overlay>` where the overlay is the
sealed tree + only this lane's new module (mirrors post-merge
reinstall for exactly this deliverable).

- RED: `.venv/bin/pytest tests/test_layer_serving_stackup.py -q`
  → `35 failed` (`ModuleNotFoundError: No module named
  'rocket_engine.interfaces.layer_serving_stackup'`).
- GREEN: `PYTHONPATH=/tmp/ls_overlay2 .venv/bin/pytest
  tests/test_layer_serving_stackup.py -q` → `34 passed, 1 skipped`
  (skip = registered-store live test; no sky130a entry in the
  default store on this machine. The user-tree live test PASSED).
- Wiring pre-patch: `.venv/bin/pytest
  tests/test_layer_serving_wiring.py -q` → `1 failed, 5 skipped`
  (the failure is the catalog test with the patch pointer —
  the integrator's RED).
- Wiring post-patch proof (patch applied to an overlay copy, not
  the repo): `PYTHONPATH=/tmp/ls_wired .venv/bin/pytest
  tests/test_layer_serving_wiring.py
  tests/test_layer_serving_stackup.py -q` → `40 passed, 1 skipped`
  (same single store skip; 0 wiring skips).
- Neighbors (sealed package, untouched by this lane):
  `.venv/bin/pytest tests/interfaces/test_pdk_store.py
  tests/test_docstrings.py -q` → `26 passed`.
- Gates: `.venv/bin/python scripts/check_docstrings.py
  src/interfaces/layer_serving_stackup.py` → clean (no output);
  `scripts/api_spec.py` smoke (`endpoint_spec` + `section_body`
  for all six queries against the patched tree) → all wired with
  doc-derived bodies.

## Integrator instructions

1. Apply: `patch -p1 < docs/work/LAYER-SERVING/wiring.patch`
   (verified: applies with zero fuzz; output byte-identical to the
   functionally tested tree). Touches only
   `src/interfaces/vocabulary.py` (+6 QUERIES) and
   `src/composition.py` (import, `QUERY_ENGINE_METHODS`,
   `_LAYER_QUERIES`, `PresetStore` state, six `Engine.layer_*`
   methods + `_query_layer` dispatch, submit prose).
2. Regen: `python scripts/api_spec.py --write` then `python
   scripts/contract.py --write` (expect `docs/engine-api.md`,
   `docs/api-schema.json`, `docs/api-help.json`,
   `docs/contract.json` to gain the six queries), then
   `python scripts/api_spec.py --check` and `python
   scripts/contract.py --check`.
3. Verify: reinstall the package per project flow, then run
   `.venv/bin/pytest tests/test_layer_serving_stackup.py
   tests/test_layer_serving_wiring.py -q` → expect all passed
   except possibly the registered-store live test (passes only
   with a registered sky130a entry) and ZERO wiring skips.
   Then the full suite + gate per ticket acceptance.

## Refused / known limits

- Edited no existing file (ownership): vocabulary/composition
  wiring, api-spec/contract regen outputs, and any conftest or
  catalogue edits are the integrator's via the patch above.
- Never ran the full suite (lane rule); ran only the new tests +
  named neighbors (`test_pdk_store`, `test_docstrings`).
- Never touched `tests/pdk_*/` or `docs/pdk/*/`; never committed
  or pushed.
- User presets are Engine-memory in MVP (documented `Caution:`
  on save/delete): no revision advance, no ledger event, lost on
  restart. A durable preset store is follow-up work, not this
  ticket (stackup itself is stateless and always fresh).
- `LayerServingError` follows the `SetupError` precedent: raised
  from query handlers, not in the MCP server's `_ENGINE_ERRORS`
  tuple. Widening that tuple is a server-owned follow-up, left
  out of the patch on purpose.
- The `.xs` Z recipe assumes the klayoutmatthias sky130 xsection
  variable shape (noted `shortcut:` in code); only `sky130a` is
  mapped in `STACKUP_FILES`, so no other PDK can hit it.

## Wiring patch (exact; also in `wiring.patch`)

```diff
diff -ruN a/src/composition.py b/src/composition.py
--- a/src/composition.py	2026-10-31 15:55:17.631725353 +0400
+++ b/src/composition.py	2026-10-31 15:55:17.653406471 +0400
@@ -44,6 +44,12 @@
 from .adapters.syntax import SyntaxAdapter
 from .execution.errors import ExecutionError
 from .execution.service import ExecutionService
+from .interfaces.layer_serving_stackup import (
+    PresetStore,
+    get_stackup,
+    viewer_rows,
+    viewer_rows_for_preset,
+)
 from .interfaces.setup import report_capabilities
 from .interfaces.vocabulary import OPERATIONS, QUERIES
 from .library.catalog import Catalog
@@ -84,6 +90,12 @@
     "get_check_results": "check_results",
     "get_logs": "run_logs",
     "list_job_kinds": "job_kinds",
+    "get_layer_stackup": "layer_stackup",
+    "get_layer_rows": "layer_rows",
+    "list_layer_presets": "layer_presets",
+    "save_layer_preset": "layer_preset_save",
+    "delete_layer_preset": "layer_preset_delete",
+    "apply_layer_preset": "layer_preset_apply",
 }
 
 # Job-result queries served from execution state (plus the captured run log).
@@ -91,6 +103,19 @@
     {"get_job_status", "get_check_results", "get_logs", "list_job_kinds"}
 )
 
+# Layer-serving queries (LAYER-SERVING): stackup/rows/presets served
+# from the PDK store plus Engine-memory user presets (PresetStore).
+_LAYER_QUERIES = frozenset(
+    {
+        "get_layer_stackup",
+        "get_layer_rows",
+        "list_layer_presets",
+        "save_layer_preset",
+        "delete_layer_preset",
+        "apply_layer_preset",
+    }
+)
+
 # A get_logs page never dumps more than this many lines at once.
 _LOG_PAGE_MAX = 200
 
@@ -151,6 +176,7 @@
             linked_root=linked_root,
         )
         self._execution = ExecutionService(project_id)
+        self._layer_presets = PresetStore()
         self._catalog = Catalog(catalog_root)
         self._solvers = {
             "run_drc": {"magic": MagicDrcAdapter(), "klayout": KlayoutDrcAdapter()},
@@ -257,8 +283,9 @@
             mapping for get_capabilities, the event page for
             get_events_since, the project/document listing for
             the CRUD queries, the status/checks/logs/kinds for
-            the job-result queries, or the completed mapping for
-            run_job.
+            the job-result queries, the stackup/rows/presets for
+            the layer-serving queries, or the completed mapping
+            for run_job.
 
         Raises:
             ProjectError: cross_project_denied for a foreign
@@ -266,9 +293,10 @@
                 unknown name, invalid_command for caller-supplied
                 run_spice targets, revision_conflict for a stale
                 expected_revision, invalid_command for a malformed
-                get_events_since cursor, a malformed mutation, or
+                get_events_since cursor, a malformed mutation,
                 a rewind that lacks a target or targets the live
-                head, resync_required when a get_events_since
+                head, or a layer query missing its pdk_id/name,
+                resync_required when a get_events_since
                 contiguity demand cannot be met, invalid_project
                 for a bad project id, project_exists for a
                 duplicate create, unknown_document for a missing
@@ -309,6 +337,8 @@
             return self._project.read_doc(arguments["path"])
         if name in _JOB_QUERIES:
             return self._query_job(name, arguments)
+        if name in _LAYER_QUERIES:
+            return self._query_layer(name, arguments)
         if name in _WIRED_QUERIES:
             return self._project.snapshot()
         if name in QUERIES or name not in OPERATIONS:
@@ -611,6 +641,235 @@
             return self.job_kinds()
         raise ProjectError("unsupported_operation", f"Operation not wired yet: {name}.")
 
+    def layer_stackup(self, pdk_id, revision=None, engine_root=None):
+        """Serve one PDK's read-only layer stackup.
+
+        The viewer/3D authority: ordered layers, metal/tech
+        grouping, enabled set, colors, and Z heights parsed from
+        the registered PDK's KLayout tech files (hash-verified
+        through the PDK store).
+
+        Args:
+            pdk_id: Canonical display id (either spelling resolves).
+            revision: Revision pin; the newest registered revision
+                when omitted.
+            engine_root: Explicit store root; resolved when omitted.
+
+        Returns:
+            Stackup record with layers, enabled set, groups, and
+                Z completeness.
+
+        Raises:
+            ProjectError: invalid_command for a missing pdk_id.
+            PdkError: unknown_pdk for a missing store/id/revision
+                or .lyp deck, pdk_drift for a tampered file.
+            LayerServingError: unknown_stackup for a PDK with no
+                stackup mapping.
+        """
+        if not pdk_id:
+            raise ProjectError(
+                "invalid_command", "get_layer_stackup needs a pdk_id argument."
+            )
+        return get_stackup(pdk_id, revision=revision, engine_root=engine_root)
+
+    def layer_rows(self, pdk_id, preset=None, overrides=None, active=None,
+                   revision=None, engine_root=None):
+        """Render viewer rows for one PDK's stackup.
+
+        Row visibility defaults to the PDK flags; an explicit
+        preset applies first, then per-layer overrides, then the
+        active layer.
+
+        Args:
+            pdk_id: Canonical display id (either spelling resolves).
+            preset: Built-in or user preset to apply; PDK defaults
+                when omitted.
+            overrides: Sparse {layer name: visible} wins over the
+                preset map.
+            active: Active layer override; the preset active when
+                omitted.
+            revision: Revision pin; the newest registered revision
+                when omitted.
+            engine_root: Explicit store root; resolved when omitted.
+
+        Returns:
+            Page with stackup_ref, preset, flip, active, and
+                file-order rows.
+
+        Raises:
+            ProjectError: invalid_command for a missing pdk_id.
+            PdkError: unknown_pdk for a missing store/id/revision.
+            LayerServingError: unknown_stackup for an unmapped
+                PDK, unknown_preset for a missing preset,
+                invalid_preset for a stale user preset,
+                invalid_visibility for bad overrides/active.
+        """
+        if not pdk_id:
+            raise ProjectError(
+                "invalid_command", "get_layer_rows needs a pdk_id argument."
+            )
+        stackup = get_stackup(pdk_id, revision=revision, engine_root=engine_root)
+        if preset is None:
+            return viewer_rows(stackup, visibility=overrides, active=active)
+        return viewer_rows_for_preset(
+            self._layer_presets, stackup, preset,
+            overrides=overrides, active=active,
+        )
+
+    def layer_presets(self):
+        """List built-in plus user layer preset names.
+
+        Returns:
+            Mapping with preset name records (name + builtin),
+                built-ins first in pinned order.
+        """
+        return {"presets": self._layer_presets.list_presets()}
+
+    def layer_preset_save(self, pdk_id, name, layers, render_layers=None,
+                          flip=False, active=None, overwrite=False,
+                          revision=None, engine_root=None):
+        """Save a user layer preset against one PDK's stackup.
+
+        Missing layer names default to hidden; apply() resolves
+        the full map.
+
+        Args:
+            pdk_id: Canonical display id (either spelling resolves).
+            name: Preset name (built-in names are reserved).
+            layers: Sparse {layer name: visible} map.
+            render_layers: {toggle: bool} viewer aids; the default
+                set when omitted.
+            flip: View-from-bottom flag.
+            active: Active layer name, or None.
+            overwrite: Replace an existing user preset of the same
+                name instead of conflicting.
+            revision: Revision pin; the newest registered revision
+                when omitted.
+            engine_root: Explicit store root; resolved when omitted.
+
+        Returns:
+            Stored preset record (builtin False).
+
+        Raises:
+            ProjectError: invalid_command for a missing pdk_id.
+            PdkError: unknown_pdk for a missing store/id/revision.
+            LayerServingError: unknown_stackup for an unmapped
+                PDK, invalid_preset for a bad name/shape,
+                preset_conflict for a built-in name or an
+                existing preset without overwrite.
+
+        Caution: View state, not project state: presets live in
+            Engine memory (no revision advance, no ledger event)
+            and are lost on restart until a durable store lands.
+        """
+        if not pdk_id:
+            raise ProjectError(
+                "invalid_command", "save_layer_preset needs a pdk_id argument."
+            )
+        stackup = get_stackup(pdk_id, revision=revision, engine_root=engine_root)
+        return self._layer_presets.save(
+            stackup, name, layers, render_layers=render_layers,
+            flip=flip, active=active, overwrite=overwrite,
+        )
+
+    def layer_preset_delete(self, name):
+        """Delete one user layer preset (built-ins are undeletable).
+
+        Args:
+            name: Preset name to delete.
+
+        Returns:
+            Deletion record with the deleted name.
+
+        Raises:
+            ProjectError: invalid_command for a missing name.
+            LayerServingError: preset_conflict for a built-in
+                name; unknown_preset for a missing user preset.
+
+        Caution: In-memory only: deletes the Engine-memory preset,
+            no revision advance, no ledger event.
+        """
+        if not name:
+            raise ProjectError(
+                "invalid_command", "delete_layer_preset needs a name argument."
+            )
+        return self._layer_presets.delete(name)
+
+    def layer_preset_apply(self, pdk_id, name, revision=None, engine_root=None):
+        """Explicitly apply one layer preset to a Stackup.
+
+        Args:
+            pdk_id: Canonical display id (either spelling resolves).
+            name: Built-in or user preset name.
+            revision: Revision pin; the newest registered revision
+                when omitted.
+            engine_root: Explicit store root; resolved when omitted.
+
+        Returns:
+            Full preset record with the complete layers map,
+                renderLayers, flip, and active.
+
+        Raises:
+            ProjectError: invalid_command for a missing pdk_id
+                or name.
+            PdkError: unknown_pdk for a missing store/id/revision.
+            LayerServingError: unknown_stackup for an unmapped
+                PDK, unknown_preset for a missing preset,
+                invalid_preset for a stale user preset.
+        """
+        if not pdk_id:
+            raise ProjectError(
+                "invalid_command", "apply_layer_preset needs a pdk_id argument."
+            )
+        if not name:
+            raise ProjectError(
+                "invalid_command", "apply_layer_preset needs a name argument."
+            )
+        stackup = get_stackup(pdk_id, revision=revision, engine_root=engine_root)
+        return self._layer_presets.apply(stackup, name)
+
+    def _query_layer(self, name, arguments):
+        """Route a layer-serving query to its Engine reader."""
+        if name == "get_layer_stackup":
+            return self.layer_stackup(
+                arguments.get("pdk_id"),
+                revision=arguments.get("revision"),
+                engine_root=arguments.get("engine_root"),
+            )
+        if name == "get_layer_rows":
+            return self.layer_rows(
+                arguments.get("pdk_id"),
+                preset=arguments.get("preset"),
+                overrides=arguments.get("overrides"),
+                active=arguments.get("active"),
+                revision=arguments.get("revision"),
+                engine_root=arguments.get("engine_root"),
+            )
+        if name == "list_layer_presets":
+            return self.layer_presets()
+        if name == "save_layer_preset":
+            return self.layer_preset_save(
+                arguments.get("pdk_id"),
+                arguments.get("name"),
+                arguments.get("layers"),
+                render_layers=arguments.get("render_layers"),
+                flip=arguments.get("flip", False),
+                active=arguments.get("active"),
+                overwrite=arguments.get("overwrite", False),
+                revision=arguments.get("revision"),
+                engine_root=arguments.get("engine_root"),
+            )
+        if name == "delete_layer_preset":
+            return self.layer_preset_delete(arguments.get("name"))
+        if name == "apply_layer_preset":
+            return self.layer_preset_apply(
+                arguments.get("pdk_id"),
+                arguments.get("name"),
+                revision=arguments.get("revision"),
+                engine_root=arguments.get("engine_root"),
+            )
+        raise ProjectError("unsupported_operation", f"Operation not wired yet: {name}.")
+
     def _logs_page(self, arguments):
         run_id = arguments.get("run_id")
         self._execution.status(run_id)  # unknown runs raise unknown_run
diff -ruN a/src/interfaces/vocabulary.py b/src/interfaces/vocabulary.py
--- a/src/interfaces/vocabulary.py	2026-10-31 15:55:17.630786143 +0400
+++ b/src/interfaces/vocabulary.py	2026-10-31 15:55:17.649166145 +0400
@@ -22,5 +22,7 @@
         "plan_checks", "get_job_status", "get_check_results",
         "get_events_since", "list_artifacts", "get_logs",
         "list_projects", "list_docs", "read_doc",
+        "get_layer_stackup", "get_layer_rows", "list_layer_presets",
+        "save_layer_preset", "delete_layer_preset", "apply_layer_preset",
     }
 )
```
