# SETTINGS-STORE lane report — engine-owned design-truth settings store

Ticket: `docs/tickets/SETTINGS-STORE.md` · Branch: GREEN-the-tests · No commits, no pushes (integrator commits).

## Files added (new files only — zero edits to existing files)

- `src/interfaces/settings_store.py` (1188 lines) — the store: five versioned schemas,
  `meta.version` per file, chained `register_migration`, additive-params-first `migrate`,
  merge-onto-original, future-format autosave block, byte-compare skip, atomic write,
  one-writer-per-key unset-fill merge, resolved-config snapshots. Stdlib + `ruamel.yaml`
  only (leaf module, no new deps, no package-internal imports — no import cycle).
- `tests/interfaces/test_settings_store.py` (411 lines, 30 tests) — unit suite loading the
  module by path; all passing standalone.
- `tests/interfaces/test_settings_store_wiring.py` (244 lines, 10 tests) — post-patch
  integration tests the integrator runs AFTER applying the wiring patch below (skip until
  then; proven 10/10 in a patched throwaway copy).
- `docs/work/SETTINGS-STORE/wiring.patch` (365 lines) — the exact wiring patch, also
  inlined below. Validated with `git apply --check` and end-to-end in a throwaway copy.
- `docs/work/SETTINGS-STORE/report.md` — this file.

## Contract implemented (ticket clause → behavior)

- `chip.manifest` — name, PDK ref+version, canvas list (`fresh_project_settings`,
  `default_settings`, `_check_manifest`).
- `design.rules` nested — ERC bool default + per-check on/off map, DRC deck ref,
  LVS mapping (`_check_rules`).
- `net.classes` — default class plus per-net color/visibility split (color/visible live
  on classes; `default` and every net must name a known class).
- `text.vars` scalar map, ClearUnknownKeys delete semantics — a patch carrying `vars`
  replaces the whole map; omitted keys are deleted (`apply_update`, `SettingsStore.update`).
- `lib.tables` resolve-only refs — `resolve_library`/`resolve_libraries` are pure reads
  (absolute ref in place, relative refs tried per root in order); resolution never writes.
- `meta.version` per file + chained `register_migration(old, new, fn)` — one-step links
  only (`invalid_migration` on skips, `migration_conflict` on duplicates); `migrate`
  walks file version → head, `future_format` above the head, `missing_migration` on gaps.
- Additive-params-first — each migration step lands the migrator output on top of
  defaults, so new params exist even where the migrator says nothing (chained-order test).
- Merge-onto-original preserving unknown keys — validators ignore unknown keys; saves
  merge new truth onto stored bytes recursively; data-map paths (`vars`, `nets`,
  `classes`, `erc.checks`, `tables`; all lists) replace wholesale so deletes propagate.
- Future-format blocks autosave — future files load for inspection (`SettingsFile.future`)
  but every save path refuses before touching bytes; stored bytes verified untouched.
- Byte-compare skip — unchanged writes return `written: False` with no revision/event.
- Atomic write — sibling temp + `os.replace` (mirrors `ProjectService`), no `.tmp`
  leftovers (asserted).
- One writer per key with unset-fill merge — `merge_writer_maps` raises `writer_conflict`
  naming both writers; unset keys fill from the base.
- Resolved-config snapshot per session/run — `snapshot_settings` / `SettingsStore.snapshot`
  bundle all five kinds + versions + library refs under session/run ids; strict reads
  (`resolve_libraries`) stay separate so a missing lib never breaks a read.
- Save hygiene extras from the ticket's KiCad rule — absent-default-is-clean (reads serve
  defaults for missing files; `ensure_fresh` only fills gaps, never clobbers), loads
  migrate in memory and never write.

## TDD gates: RED → GREEN evidence

RED first (module missing → collection error), then GREEN. Commands run from
`rocket-engine/` with the pre-existing `.venv` interpreter (no installs, no `uv sync`):

- RED: `.venv/bin/python -m pytest tests/interfaces/test_settings_store.py -q` →
  `ERROR ... FileNotFoundError: .../src/interfaces/settings_store.py`, 1 collection error.
- GREEN: same command after writing the module → `26 passed`; grew to `30 passed`
  as the wiring seams (`dump_settings_text`, `merge_settings`, `snapshot_settings`,
  `settings_version`) landed with their tests.
- Wiring file pre-patch: `10 skipped` (`SETTINGS-STORE wiring not applied yet`).
- Docstring gate: `.venv/bin/python scripts/check_docstrings.py
  src/interfaces/settings_store.py` → clean (full `src` tree is enforced; every public
  callable carries summary + Args/Returns/Raises).
- Named neighbors (real tree, unpatched): `tests/test_api_spec.py`,
  `tests/test_contract.py`, `tests/test_check_contract.py` → 25 passed (no drift from the
  new module); `tests/project/test_crud_api.py` → green alongside (54 passed incl. mine in
  the patched copy, see below); `tests/test_docstrings.py` → green on the final tree.

## Integrator runbook (verified in a throwaway copy — see evidence)

The wiring persists settings as `settings/<kind>.yaml` documents through the existing
admission machinery, so the ledger law holds for free: revision gate, idempotent request
ids, one revision + event per accepted write, atomic persist, rewind snapshots, and MCP /
api_spec / contract derivation from `ProjectService` docstrings (verified: CRUD ops and
`QUERY_METHODS` queries document from `ProjectService.<name>`; MCP resolves the same way).
No `service.py` admission changes were needed beyond additive methods; no `__init__.py`
export (that module is contract-only: no I/O).

1. `git apply --check docs/work/SETTINGS-STORE/wiring.patch` (must print nothing),
   then `git apply docs/work/SETTINGS-STORE/wiring.patch`.
2. Reinstall so `rocket_engine.interfaces.settings_store` resolves, then regen:
   `python scripts/api_spec.py --write && python scripts/contract.py --write`
   (both report stale before, fresh after — no `STUB_OVERLAP` additions: new engine
   names have no stub counterpart yet, which the contract tolerates).
3. Run: `.venv/bin/python -m pytest tests/interfaces/test_settings_store.py
   tests/interfaces/test_settings_store_wiring.py tests/project/test_crud_api.py
   tests/test_api_spec.py tests/test_contract.py tests/test_check_contract.py
   tests/test_docstrings.py -q` → all green (82 passed + 1 pre-existing skip in the copy).

Evidence: applied the patch in `/tmp/ss-verify-inre` (throwaway tree copy, real tree
untouched), imported it via a `rocket_engine` symlink + `PYTHONPATH` with the project
venv (no reinstall): 30 unit + 10 wiring + 14 CRUD = 54 passed, 0 skipped; api_spec and
contract both went stale → `--write` → `--check` clean; gate suites 28 passed + 1 skip.
Scratch copies left under `/tmp` for review, out of the deliverable.

## Wiring patch (exact — also in `wiring.patch`)

```diff
diff --git a/src/interfaces/vocabulary.py b/src/interfaces/vocabulary.py
--- a/src/interfaces/vocabulary.py
+++ b/src/interfaces/vocabulary.py
@@ -13,6 +13,6 @@
         "run_view_sync", "run_job",
         "create_project", "write_doc", "delete_doc", "apply_mutations",
-        "rewind",
+        "rewind", "write_settings",
     }
 )
 QUERIES = frozenset(
@@ -22,5 +22,6 @@
         "plan_checks", "get_job_status", "get_check_results",
         "get_events_since", "list_artifacts", "get_logs",
         "list_projects", "list_docs", "read_doc",
+        "read_settings", "get_resolved_config",
     }
 )
diff --git a/src/composition.py b/src/composition.py
--- a/src/composition.py
+++ b/src/composition.py
@@ -68,9 +68,11 @@
 QUERY_METHODS = {
     "get_project_snapshot": "snapshot",
     "get_events_since": "events_since",
     "list_projects": "list_projects",
     "list_docs": "list_docs",
     "read_doc": "read_doc",
+    "read_settings": "read_settings",
+    "get_resolved_config": "resolved_config",
 }
 
 # Wired query -> Engine method serving it. Same docs/help seam as
@@ -101,10 +101,11 @@
 _CRUD_OPERATIONS = frozenset(
     {
         "create_project",
         "write_doc",
         "delete_doc",
         "apply_mutations",
         "rewind",
+        "write_settings",
     }
 )
 
@@ -268,8 +268,12 @@
                 expected_revision, invalid_command for a malformed
-                get_events_since cursor, a malformed mutation, or
-                a rewind that lacks a target or targets the live
-                head, resync_required when a get_events_since
-                contiguity demand cannot be met, invalid_project
+                get_events_since cursor, a malformed mutation, a
+                rewind that lacks a target or targets the live
+                head, a write_settings missing kind or settings,
+                an unknown settings kind, or settings that break
+                the kind schema, future_format for a settings
+                write over a newer on-disk file, resync_required
+                when a get_events_since contiguity demand cannot
+                be met, invalid_project
                 for a bad project id, project_exists for a
                 duplicate create, unknown_document for a missing
                 document, unknown_revision for a rewind target
@@ -305,9 +305,20 @@
         if name == "read_doc":
             if "path" not in arguments:
                 raise ProjectError(
                     "invalid_command", "read_doc needs a path argument."
                 )
             return self._project.read_doc(arguments["path"])
+        if name == "read_settings":
+            if "kind" not in arguments:
+                raise ProjectError(
+                    "invalid_command", "read_settings needs a kind argument."
+                )
+            return self._project.read_settings(arguments["kind"])
+        if name == "get_resolved_config":
+            return self._project.resolved_config(
+                session_id=arguments.get("session_id"),
+                run_id=arguments.get("run_id"),
+            )
         if name in _JOB_QUERIES:
             return self._query_job(name, arguments)
         if name in _WIRED_QUERIES:
@@ -428,11 +428,24 @@
             return self._project.rewind(
                 arguments["target_revision"],
                 request_id,
                 command_text,
                 expected_revision=arguments.get("expected_revision"),
             )
+        if name == "write_settings":
+            if "kind" not in arguments or "settings" not in arguments:
+                raise ProjectError(
+                    "invalid_command",
+                    "write_settings needs kind and settings arguments.",
+                )
+            return self._project.write_settings(
+                arguments["kind"],
+                arguments["settings"],
+                request_id,
+                command_text,
+                expected_revision=arguments.get("expected_revision"),
+            )
         if "mutations" not in arguments:
             raise ProjectError(
                 "invalid_command",
                 "apply_mutations needs a mutations argument.",
             )
diff --git a/src/project/service.py b/src/project/service.py
--- a/src/project/service.py
+++ b/src/project/service.py
@@ -42,5 +42,6 @@
 from ruamel.yaml import YAML
 
+from ..interfaces import settings_store
 from ..interfaces.paths import join_contained, to_unix
 from .errors import ProjectError
 
@@ -54,6 +54,9 @@
 _PROJECT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")
 _RUN_OUTCOMES = ("run_completed", "run_failed")
 _RESERVED_DOCS = frozenset({_LEDGER_FILENAME, _EVENTS_FILENAME})
+
+# Document prefix owning the five design-truth settings files.
+_SETTINGS_DOC_PREFIX = "settings/"
 
 
 def _advance_revision(revision):
@@ -1289,6 +1289,111 @@
             "content": content,
             "bytes": len(content.encode("utf-8")),
         }
+
+    def read_settings(self, kind):
+        """Read one settings kind at the current head.
+
+        Absent files read as defaults (absent-default-is-clean):
+        a fresh project needs no seeding write. Stored files
+        migrate in memory to the known head; future files fail
+        instead of serving truth this engine cannot validate.
+
+        Args:
+            kind: Settings kind (chip.manifest, design.rules,
+                net.classes, text.vars, lib.tables).
+
+        Returns:
+            Mapping with project id, head revision, kind, stored
+            flag, version, and the settings mapping.
+
+        Raises:
+            ProjectError: invalid_command for an unknown kind or
+                stored settings that break the kind schema;
+                invalid_document for stored settings that do not
+                parse; future_format for a file newer than the
+                head; missing_migration when no link covers the
+                stored version.
+        """
+        self._refresh_durable()
+        if kind not in settings_store.CURRENT_VERSIONS:
+            raise ProjectError(
+                "invalid_command", f"Unknown settings kind: {kind}."
+            )
+        canonical = _canonical_doc_path(f"{_SETTINGS_DOC_PREFIX}{kind}.yaml")
+        text = self._read_doc_text(canonical, canonical)
+        if text is None:
+            return {
+                "project_id": self._project_id,
+                "current_revision": self._current_revision,
+                "kind": kind,
+                "stored": False,
+                "version": settings_store.CURRENT_VERSIONS[kind],
+                "settings": settings_store.default_settings(kind),
+            }
+        try:
+            data = self._yaml.load(text)
+        except Exception as exc:
+            raise ProjectError(
+                "invalid_document",
+                f"Stored {kind} settings do not parse: {exc}.",
+            ) from exc
+        if not isinstance(data, dict):
+            raise ProjectError(
+                "invalid_document",
+                f"Stored {kind} settings must be a mapping.",
+            )
+        try:
+            migrated = settings_store.migrate(kind, data)
+        except settings_store.SettingsError as exc:
+            if exc.code in ("future_format", "missing_migration"):
+                raise ProjectError(exc.code, str(exc)) from exc
+            raise ProjectError(
+                "invalid_command",
+                f"Stored {kind} settings are invalid: {exc}.",
+            ) from exc
+        return {
+            "project_id": self._project_id,
+            "current_revision": self._current_revision,
+            "kind": kind,
+            "stored": True,
+            "version": migrated["meta"]["version"],
+            "settings": migrated,
+        }
+
+    def resolved_config(self, session_id=None, run_id=None):
+        """Bundle the resolved config for one session/run fetch.
+
+        All five kinds in one call — clients render from this
+        snapshot instead of per-event round-trips. Absent files
+        resolve to defaults; library refs stay unresolved here
+        (callers resolve lib.tables refs against their own roots).
+
+        Args:
+            session_id: Client session this snapshot serves.
+            run_id: Run this snapshot was resolved for, if any.
+
+        Returns:
+            Snapshot mapping with project id, head revision,
+            session/run ids, per-kind versions, all five settings
+            mappings, and library refs.
+
+        Raises:
+            ProjectError: future_format when any stored file is
+                newer than the head; missing_migration when no
+                link covers a stored version; invalid_document
+                for stored settings that do not parse.
+        """
+        self._refresh_durable()
+        settings = {}
+        for kind in settings_store.CURRENT_VERSIONS:
+            read = self.read_settings(kind)
+            settings[read["kind"]] = read["settings"]
+        snapshot = settings_store.snapshot_settings(
+            settings, session_id=session_id, run_id=run_id
+        )
+        snapshot["project_id"] = self._project_id
+        snapshot["current_revision"] = self._current_revision
+        return snapshot
 
     def write_doc(self, path, content, request_id, command_text,
                   expected_revision=None):
@@ -1401,6 +1401,124 @@
         self._requests[request_id] = (command_text, response)
         self._persist_after_mutation()
         return response
+
+    def write_settings(self, kind, settings, request_id, command_text,
+                       expected_revision=None):
+        """Write one settings kind: validate, gate, merge, log.
+
+        Full replacement of the kind's truth, persisted as the
+        settings/<kind>.yaml document through the same admission
+        machinery as write_doc (idempotent request ids, revision
+        gate, one new revision, one event, atomic persist, rewind
+        snapshots). The write merges onto the stored bytes so
+        unknown keys survive; data maps replace wholesale, so
+        text.vars deletes propagate. Unchanged bytes skip the
+        write: no new revision, no event.
+
+        A resubmitted envelope returns its stored response without
+        advancing.
+
+        Args:
+            kind: Settings kind (chip.manifest, design.rules,
+                net.classes, text.vars, lib.tables).
+            settings: Complete settings mapping at the head
+                version.
+            request_id: Client envelope id; resubmitting the
+                identical text returns the identical response
+                without advancing.
+            command_text: YAML command text for identity comparison.
+            expected_revision: Revision the writer read.
+
+        Returns:
+            Mutation mapping with path, revision transition, new
+            head, actor, diff summary, rewind handle, the
+            appended event, cursor, request id, written flag, and
+            settings version.
+
+        Raises:
+            ProjectError: request_conflict for a reused id with
+                new text; invalid_command for an unknown kind or
+                settings that break the kind schema;
+                revision_conflict for a stale head; future_format
+                when the stored file is newer than the head;
+                invalid_document for stored settings that do not
+                parse; invalid_ledger when the durable write fails.
+
+        Caution: Every accepted write advances the revision — a
+            second writer at the old head fails instead of
+            merging — and text.vars writes delete vars the new
+            map omits.
+        """
+        self._refresh_durable()
+        replay = self._check_replay(request_id, command_text)
+        if replay is not None:
+            return replay
+        try:
+            settings_store.validate_settings(kind, settings)
+        except settings_store.SettingsError as exc:
+            raise ProjectError(
+                "invalid_command", f"Bad {kind} settings: {exc}."
+            ) from exc
+        self._gate_revision(expected_revision)
+        canonical = _canonical_doc_path(f"{_SETTINGS_DOC_PREFIX}{kind}.yaml")
+        old_text = self._read_doc_text(canonical, canonical)
+        old_data = None
+        if old_text is not None:
+            try:
+                old_data = self._yaml.load(old_text)
+            except Exception as exc:
+                raise ProjectError(
+                    "invalid_document",
+                    f"Stored {kind} settings do not parse: {exc}.",
+                ) from exc
+            if not isinstance(old_data, dict):
+                raise ProjectError(
+                    "invalid_document",
+                    f"Stored {kind} settings must be a mapping.",
+                )
+            old_version = settings_store.settings_version(kind, old_data)
+            if old_version > settings_store.settings_version(kind, settings):
+                raise ProjectError(
+                    "future_format",
+                    f"Stored {kind} settings are newer than this "
+                    "engine knows; refusing autosave.",
+                )
+        merged = settings_store.merge_settings(kind, old_data, settings)
+        text = settings_store.dump_settings_text(merged)
+        version = settings_store.settings_version(kind, merged)
+        if old_text is not None and text == old_text:
+            response = {
+                "project_id": self._project_id,
+                "path": canonical,
+                "previous_revision": self._current_revision,
+                "current_revision": self._current_revision,
+                "revision_transition": {
+                    "from": self._current_revision,
+                    "to": self._current_revision,
+                },
+                "actor": self._actor,
+                "diff_summary": f"unchanged {canonical}",
+                "rewind_handle": {
+                    "project_id": self._project_id,
+                    "revision": self._current_revision,
+                    "request_id": request_id,
+                },
+                "events": [],
+                "event_cursor": self._cursor(),
+                "request_id": request_id,
+                "written": False,
+                "settings_version": version,
+            }
+            self._requests[request_id] = (command_text, response)
+            self._persist_after_mutation()
+            return response
+        response = self.write_doc(
+            canonical, text, request_id, command_text,
+            expected_revision=expected_revision,
+        )
+        response["written"] = True
+        response["settings_version"] = version
+        return response
 
     def delete_doc(self, path, request_id, command_text,
                    expected_revision=None):
```

## Refused / not changed (with reasons)

- No existing file edited — ownership rule: composition, service, vocabulary, scripts,
  pyproject/uv.lock, conftest, generated docs (`docs/engine-api.md`, `docs/api-*.json`,
  `docs/contract.json`) are all integrator-applied via the patch + regen runbook above.
- `tests/pdk_*/` and `docs/pdk/*/` untouched (PDK-lane ownership); full suite never run
  (only lane tests + named neighbors).
- No `STUB_OVERLAP` additions: the new engine names have no fuel-stub counterpart yet;
  verified `scripts/contract.py --write/--check` tolerates that (contract regen green).
- `.venv` used only as a test interpreter; no installs, no `uv sync` (forbidden).
- Filenames use the ticket-suggested bare `settings_store` stem: the name IS the ticket
  (`SETTINGS-STORE`), so prefixing would duplicate it; no second ticket claims it, and
  peer lanes own disjoint paths (verified in `git status` — no collisions).

## Findings for the integrator

- `expected_revision` is effectively mandatory for mutations (`None` → `revision_conflict`,
  probed on `write_doc`); the wiring tests thread the head revision through every write.
- Mid-task, `tests/test_docstrings.py` failed on `src/workflows/connectgraph.py`
  (a peer lane's untracked file, 3 missing docstrings) — not this lane; the final tree
  scans clean.
- `get_resolved_config` deliberately takes no `library_roots` (caller-supplied server
  paths would need path-escape review); refs resolve client-side or via a later ticket.
