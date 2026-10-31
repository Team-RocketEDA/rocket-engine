# API-GENERALIZE lane report

Base: `20239f3` (`GREEN-the-tests`, verified clean of `src/**` edits at
handoff — see git status below). Ownership kept: only new files
created, no existing file touched. The wiring patch was built and
verified against `20239f3` and re-checked with `git apply --check`
at handoff HEAD `7f52bf4`: zero drift on all six patched files,
still applies clean.

## Outcome

All four remaining scope items are implemented as new modules with
passing tests, plus integration tests and an exact, machine-verified
wiring patch for the integrator:

- (a) worker pool: `src/execution/apig_pool.py`
- (b) catalogue index + `place_cell`: `src/library/apig_catalog.py`
- (c) raw asset serving (I29): `src/interfaces/apig_assets.py`
- (d) SUBMIT-IMMEDIATE reference: `src/execution/apig_submit.py`

## Files added

New modules (all gate-clean per `scripts/check_docstrings.py`):

- `src/execution/apig_pool.py` — `ApigPool` (bounded FIFO drain over
  the durable ledger, `pool_full` refusal before admission, replay),
  pure helpers `pending_from_events`,
  `stored_completion_from_events`, `request_for_run`.
- `src/execution/apig_submit.py` — `merge_ack_completion` plus
  `SubmitImmediate`, the public-port reference client (pump-once
  against queueing engines, pass-through against wired engines,
  completion cache for idempotent replay/fetch).
- `src/library/apig_catalog.py` — `ApigCatalog` (cached versioned
  index, `list_cells`/`get_cell`/`place_cell`), `static_provider`,
  `gdsfactory_provider` (lazy engine-side introspection; `[]` when
  gdsfactory is absent, never raises).
- `src/interfaces/apig_assets.py` — `serve_asset` (verbatim bytes,
  base64 transport encoding, sha256 over raw bytes), `list_assets`,
  `asset_manifest` (bulk `tree_sha256`).

New tests (all passing standalone on the unpatched tree):

- `tests/test_apig_pool.py` (10) — spam/order, replay-once,
  backpressure-before-admission, error capture + continue, kill-reboot
  across a durable root, completed-resubmit, loud skips, pure helpers,
  subset drain.
- `tests/test_apig_catalog.py` (11) — versioned/sorted/JSON-clean
  listing, unknown/ambiguous cells, durable placement + replay,
  port/param/identity validation, stale revision, provider absence /
  fake-module introspection / broken factories, cache + copy
  semantics, real gdsfactory components (343 cells).
- `tests/test_apig_assets.py` (6) — verbatim `.sym` + hash identity,
  odd-bytes preservation, nested paths + display id, escape/missing/
  directory/unknown-PDK refusals, listing granularity, manifest
  stability.
- `tests/test_apig_submit.py` (5) — merge shape, inline-once for
  replays, idempotent fetch, wired-engine pass-through, real-Engine
  round trip through the public port.
- `tests/test_apig_integration.py` (7, for the integrator) — skips
  with a named reason on the unpatched tree; `APIG_PROBE_WIRING=1`
  lifts the skips to prove RED. Covers submit-inline shape,
  run_job idempotent fetch, batch pump + refusal, 25-place spam,
  catalogue round-trip, engine kill-reboot, asset serving.

Lane files:

- `docs/work/API-GENERALIZE/report.md` (this file)
- `docs/work/API-GENERALIZE/wiring.patch` (same bytes as the inline
  patch below; apply with `git apply -p1` or `patch -p1` from the
  repo root)

No fixtures: all tests build their trees under `tmp_path`.

## Design notes (per scope item)

- (a) The pool delegates admission to the ledger (same ack bytes,
  same dedupe) and owns only order + bound + replay. Refusal is a
  typed `ExecutionError(pool_full)` raised before the ledger is
  touched, so a refusal never advances the revision. Replay reads
  ledger events only (`job_queued` minus `run_*`), so a rebooted
  process replays correctly with no in-memory state. Runner
  exceptions become recorded `failed` completions; the drain
  continues.
- (b) Entries are `{cell, pdk, pdk_revision, ports, default_params,
  catalog_version, source}`, always JSON-serializable. Providers are
  callables, so the upstream stays replaceable; the gdsfactory one
  imports lazily, reads defaults from signatures, and best-effort
  instantiates for ports (quiet stdout, never raises). The index is
  cached per catalog (`refresh()` rebuilds; `add_provider` /
  `register_cells` invalidate) because full introspection costs
  ~1.4 s; served entries are deep copies. `place_cell` writes
  `components/<instance>.yaml` through `apply_mutations` (one
  revision, one event, idempotent replay), refusing unknown cells /
  params / ports / duplicate instances loudly.
- (c) Bytes are served verbatim — no conversion, no rendering — with
  sha256 computed over the raw bytes. All paths go through
  PATH-GUARD containment; escapes, missing files, directories, and
  unknown PDKs raise `invalid_reference`. Symlinks are listable
  metadata, never served by `serve_asset`.
- (d) `merge_ack_completion` keeps every ack identity field and adds
  state/verdict/operation — the ticket's "same run_id ack shape +
  verdict payload". `run_job` keeps its single deferred form and
  gains `{"run_ids": [...]}` batch pumping; every listed id lands
  in exactly one of `completions`/`refused`.

## Wiring patch (what the integrator applies)

Covers 6 files; verified byte-identical output under both `patch
-p0 --fuzz=0` and `git apply -p1` on a scratch tree (see evidence).
Apply from the repo root with `git apply -p1
docs/work/API-GENERALIZE/wiring.patch` (or `patch -p1 < ...`).

- `src/interfaces/vocabulary.py`: `place_cell` operation;
  `list_cells`, `serve_asset`, `list_assets` queries.
- `src/composition.py`: imports; `QUERY_ENGINE_METHODS` +
  `_APIG_QUERIES`; `Engine(pool_max_depth=64)` owning the pool, the
  cell catalog (gdsfactory provider by default), and the replay
  flag; `submit()` admits via the pool and drains inline, returning
  the merged mapping (replays of finished runs return the stored
  completion); `run_job` single (idempotent fetch, reboot
  resolution/registration) + batch; `place_cell` immediate path;
  `catalog_cells` / `register_cells` / `serve_asset` /
  `list_assets` / `replay_pending` (+ lazy `_replay_once` on the
  first mutating call only — queries never replay);
  `capabilities()` serves `place_cell`. New Engine methods all
  carry gate-conformant docstrings.
- `src/execution/__init__.py`, `src/library/__init__.py`,
  `src/interfaces/__init__.py`: export the new symbols.
- `src/adapters/mcp/server.py`: docstrings updated to
  submit-inline; `_call_once` skips the redundant `run_job` pump
  when the ack already carries a verdict but still writes run
  evidence for inline completions (verified by the previously
  failing evidence test).

Deliberately NOT patched (verified unnecessary): `dispatch.py`
(new names flow through the vocabulary gate; `place_cell` rides
the `run()`→`submit()` delegation like CRUD), `McpTransport`
(routes everything through `engine.submit`), `scripts/*` (the
spec/contract generators read the new maps dynamically).

Known interaction: lazy replay drains staged backlog before an
explicit batch runs (replay is idempotent, so the batch then
fetches stored completions). The batch-refusal test consumes
replay first with one inline submit; refusal stays reachable
whenever backlog accumulates after the first call (direct ledger
admissions, future concurrent transports) and is unit-proven at
pool level regardless.

## RED → GREEN evidence (unpatched tree)

- `pytest tests/test_apig_pool.py tests/test_apig_catalog.py
  tests/test_apig_assets.py tests/test_apig_submit.py` → **31
  failed** (module loaders, `FileNotFoundError`) before the
  modules; **33 passed** after (31 + 2 cache tests added with the
  caching change).
- `pytest tests/test_apig_integration.py` → **7 skipped** (named
  reason); `APIG_PROBE_WIRING=1 pytest
  tests/test_apig_integration.py` → **7 failed** (missing wired
  surface).
- Neighbors on the unpatched tree:
  `tests/execution/test_execution_service.py`,
  `tests/library/test_catalog.py`, `tests/test_docstrings.py` →
  **14 passed**; `scripts/check_docstrings.py` on the four new
  modules → exit 0.

## Patched-tree verification (scratch `/tmp` tree, both applicators)

Applied `wiring.patch` to a pristine copy with `patch -p0
--fuzz=0` and separately with `git apply -p1`; both produced
byte-identical trees, which also match a line-surgery reference
application. Against the patched tree:

- All APIG tests: **40 passed** (7 integration + 33 unit).
- `scripts/check_docstrings.py` (full enforced tree): exit 0.
- `scripts/api_spec.py --write` + `tests/test_api_spec.py` +
  `tests/test_docstrings.py`: **11 passed** (freshness holds after
  regen).
- Pre-existing queue-assumption pins fail as intended (ticket
  changed the contract; integrator updates them, see runbook):
  `tests/test_contract.py` (4), `tests/test_engine_run.py` (2),
  `tests/adapters/test_mcp_agent_path.py` (4) — every failure is
  `assert 'completed' == 'queued'` (or the contract-JSON key pin
  derived from it); 18 + 29 neighboring tests in those files still
  pass. `scripts/contract.py::build_envelopes` stops at its
  `ack["state"] == "queued"` assert (line 225); the printed ack
  shows the correct new shape (same run_id keys + verdict +
  operation).
- One genuine breakage was found and fixed during verification:
  the first `_call_once` cut skipped evidence writing for inline
  completions (`test_one_shot_call_runs_a_job_and_writes_evidence`
  failed); the shipped hunk hoists evidence out of the pump
  branch and the test passes.

## Integrator runbook

1. `git apply -p1 docs/work/API-GENERALIZE/wiring.patch` (from the
   repo root; base `20239f3`).
2. `MPLCONFIGDIR=/tmp/mplcfg .venv/bin/python -m pytest
   tests/test_apig_integration.py tests/test_apig_pool.py
   tests/test_apig_catalog.py tests/test_apig_assets.py
   tests/test_apig_submit.py` → expect 40 passed.
3. Update the queue-by-default pins to submit-immediate (10
   tests): `tests/test_contract.py` (4),
   `tests/test_engine_run.py` (2),
   `tests/adapters/test_mcp_agent_path.py` (4); update
   `scripts/contract.py::build_envelopes` (line ~225: assert the
   merged shape — completed + verdict — instead of `queued`),
   then regenerate `docs/contract.json`,
   `docs/engine-api.md`, `docs/api-schema.json`,
   `docs/api-help.json` (`scripts/contract.py` +
   `scripts/api_spec.py --write`) and re-run those suites.
4. `scripts/check_docstrings.py` (bare) must stay exit 0.

## Refusals

None — every scope item is delivered. Two judgment calls are
recorded above rather than refused: (1) catalog index caching
with `refresh()` (full gdsfactory introspection costs ~1.4 s and
some factories print; the probe is now quiet and cached, served
entries are copies); (2) lazy boot replay runs on the first
mutating Engine call (queries stay read-only), which the batch
test accommodates as documented.

## Exact wiring patch

```diff
diff -u -r rocket-engine.orig/src/adapters/mcp/server.py rocket-engine/src/adapters/mcp/server.py
--- rocket-engine.orig/src/adapters/mcp/server.py
+++ rocket-engine/src/adapters/mcp/server.py
@@ -7,11 +7,12 @@
 is transport-free; only main() touches stdio.
 
 Bound to a project (`--project`), the server fills project_id and the
-current expected_revision itself; execution stays explicit (submit,
-then run_job — nothing runs implicitly), and run_spice targets come
-from the project's constraints.yaml (`--project-dir`): the agent
-never sets them. Finished runs are recorded under
-results/engine-runs for IDE and agent alike.
+current expected_revision itself; submit runs inline (same run_id ack
+shape plus the verdict), run_job stays for deferred/batch pumping
+plus idempotent fetch, and run_spice targets come from the
+project's constraints.yaml (`--project-dir`): the agent never sets
+them. Finished runs are recorded under results/engine-runs for IDE
+and agent alike.
 """
 
 import argparse
@@ -207,9 +208,9 @@
     """Build transport-free list/call handlers over McpTransport.
 
     Handlers route through McpTransport so validation stays
-    single-sourced; engines are cached per project id. Execution
-    stays explicit: submit admits (state queued), run_job executes
-    — the handler never runs a job implicitly.
+    single-sourced; engines are cached per project id. Submit runs
+    inline (ack plus verdict); run_job stays the deferred/batch
+    pump and idempotent fetch.
 
     Args:
         engine_factory: Callable turning a project id into an
@@ -352,14 +352,25 @@
         return result.is_error, json.loads(result.content[0].text)
 
     failed, body = invoke(args.call, json.loads(args.args))
-    if not failed and args.call in OPERATIONS and "run_id" in body:
-        failed, body = invoke("run_job", {"run_id": body["run_id"]})
-        if not failed and args.project_dir is not None and body.get("state") == "completed":
-            engine = created.get(args.project)
-            if engine is not None:
-                write_evidence(args.project_dir, engine, [body], json.loads(args.args))
-        if not failed and "run_id" in body:
-            failed, body = invoke("get_job_status", {"run_id": body["run_id"]})
+    if (
+        not failed
+        and args.call in OPERATIONS
+        and "run_id" in body
+        and "verdict" not in body
+    ):
+        failed, body = invoke("run_job", {"run_id": body["run_id"]})
+        if not failed and "run_id" in body:
+            failed, body = invoke("get_job_status", {"run_id": body["run_id"]})
+    if (
+        not failed
+        and args.call in OPERATIONS
+        and args.project_dir is not None
+        and "run_id" in body
+        and body.get("state") == "completed"
+    ):
+        engine = created.get(args.project)
+        if engine is not None:
+            write_evidence(args.project_dir, engine, [body], json.loads(args.args))
     print(json.dumps(body))
     return 1 if failed else 0
 
diff -u -r rocket-engine.orig/src/composition.py rocket-engine/src/composition.py
--- rocket-engine.orig/src/composition.py
+++ rocket-engine/src/composition.py
@@ -10,11 +10,13 @@
 actor-attributed event to the durable ledger (LEDGER-DURABLE/I30),
 and every run appends its completion with a verdict link. Only wired
 queries read state, the rest honestly report unwired.
-Two-phase execution: `submit(op)` admits and returns an ack, then
-`run_job` executes the admitted command — over `run()` directly or
-over submit-only transports via `submit(run_job)`. The ack run_id is
-the execution id: `get_job_status` reports queued after submit and the
-verdict after `run_job`; nothing runs implicitly (no auto-drain).
+Submit-immediate execution (API-GENERALIZE): `submit(op)` admits and
+runs inline, returning the ack shape plus the verdict payload under
+the one run id; `run_job` stays for explicit/deferred/batch pumping
+plus idempotent result fetch — over `run()` directly or over
+submit-only transports via `submit(run_job)`. Replays return the
+stored completion without re-executing, and a fresh Engine drains
+crash survivors once (boot replay) on its first mutating call.
 With `constraints` (metric -> {min, max, unit[, expr, control]}),
 run_spice targets come from the project, never the caller:
 caller-supplied min/max — or a caller expr where the project defines
@@ -42,11 +44,25 @@
 from .adapters.ngspice import NgspiceAdapter
 from .adapters.sax import SaxAdapter
 from .adapters.syntax import SyntaxAdapter
+from .execution.apig_pool import (
+    ApigPool,
+    request_for_run,
+    stored_completion_from_events,
+)
+from .execution.apig_submit import merge_ack_completion
 from .execution.errors import ExecutionError
 from .execution.service import ExecutionService
+from .interfaces import apig_assets
+from .interfaces.errors import ContractError
 from .interfaces.setup import report_capabilities
 from .interfaces.vocabulary import OPERATIONS, QUERIES
+from .library.apig_catalog import (
+    ApigCatalog,
+    gdsfactory_provider,
+    static_provider,
+)
 from .library.catalog import Catalog
+from .library.errors import LibraryError
 from .project.errors import ProjectError
 from .project.service import ProjectService
 
@@ -84,6 +100,9 @@
     "get_check_results": "check_results",
     "get_logs": "run_logs",
     "list_job_kinds": "job_kinds",
+    "list_cells": "catalog_cells",
+    "serve_asset": "serve_asset",
+    "list_assets": "list_assets",
 }
 
 # Job-result queries served from execution state (plus the captured run log).
@@ -91,6 +110,10 @@
     {"get_job_status", "get_check_results", "get_logs", "list_job_kinds"}
 )
 
+# Catalogue + raw-asset queries served from engine state (the cell
+# index and the PDK store); read-only, never replay the backlog.
+_APIG_QUERIES = frozenset({"list_cells", "serve_asset", "list_assets"})
+
 # A get_logs page never dumps more than this many lines at once.
 _LOG_PAGE_MAX = 200
 
@@ -140,10 +163,13 @@
         constraints: Optional run_spice metric targets
             ({metric: {min, max, unit[, expr, control]}}); caller
             targets are refused, unknown metrics fail loudly.
+        pool_max_depth: Maximum undrained execution backlog;
+            admissions past it are refused, never queued.
     """
 
     def __init__(self, project_id, actor, catalog_root=".",
-                 engine_root=None, linked_root=None, constraints=None):
+                 engine_root=None, linked_root=None, constraints=None,
+                 pool_max_depth=64):
         self._project_id = project_id
         self._actor = actor
         self._project = ProjectService(
@@ -166,6 +192,13 @@
         self._logs = {}
         self._latest = {}
         self._run_jobs = {}
+        self._pool = ApigPool(
+            self._project, self._pool_execute, max_depth=pool_max_depth
+        )
+        self._cells = ApigCatalog(
+            catalog_root, providers=[gdsfactory_provider()]
+        )
+        self._replayed = False
 
     def snapshot(self):
         """Read the current project snapshot.
@@ -233,32 +266,38 @@
             self._solvers,
             target=target,
             engine_root=engine_root,
-            served=_CRUD_OPERATIONS | {"run_job"},
+            served=_CRUD_OPERATIONS | {"run_job", "place_cell"},
         )
 
     def submit(self, command):
-        """Admit an operation (phase 1) or serve a wired query.
+        """Admit and run an operation inline, or serve a wired query.
 
-        Operations queue through the project service with revision
-        gating and envelope-id idempotency; CRUD mutations and
-        rewind execute immediately through the same admission
-        machinery (no queue, no solver); only wired queries read
-        state, the rest honestly report unwired.
+        Solver operations admit through the project service with
+        revision gating and envelope-id idempotency, then execute
+        immediately: the returned mapping is the admission ack
+        shape plus the completion (state, verdict, operation) under
+        the one run id. CRUD mutations, rewind, and place_cell
+        execute immediately through the same admission machinery
+        (no queue, no solver); only wired queries read state, the
+        rest honestly report unwired.
 
         Args:
             command: Envelope with project_id, operation, arguments,
                 and request_id.
 
         Returns:
-            Admission ack for queued operations, the immediate
-            mutation mapping (new revision + events + approval-UI
-            fields) for CRUD/rewind operations, the snapshot for
-            the wired get_project_snapshot query, the capability
-            mapping for get_capabilities, the event page for
+            Merged ack-plus-completion for solver operations (ack
+            identity fields plus state, verdict, operation), the
+            immediate mutation mapping (new revision + events +
+            approval-UI fields) for CRUD/rewind/place_cell
+            operations, the snapshot for the wired
+            get_project_snapshot query, the capability mapping
+            for get_capabilities, the event page for
             get_events_since, the project/document listing for
             the CRUD queries, the status/checks/logs/kinds for
-            the job-result queries, or the completed mapping for
-            run_job.
+            the job-result queries, the cell listing or asset
+            bytes for the catalogue/asset queries, or the
+            stored-or-fresh completion for run_job.
 
         Raises:
             ProjectError: cross_project_denied for a foreign
@@ -266,20 +305,31 @@
                 unknown name, invalid_command for caller-supplied
                 run_spice targets, revision_conflict for a stale
                 expected_revision, invalid_command for a malformed
-                get_events_since cursor, a malformed mutation, or
-                a rewind that lacks a target or targets the live
-                head, resync_required when a get_events_since
-                contiguity demand cannot be met, invalid_project
-                for a bad project id, project_exists for a
-                duplicate create, unknown_document for a missing
-                document, unknown_revision for a rewind target
-                with no snapshot, invalid_path or path_escape for
-                a bad document path, request_conflict for a reused
-                envelope id with new text.
+                get_events_since cursor, a malformed mutation, a
+                place_cell without a cell, a serve_asset without
+                pdk id/revision/path, or a rewind that lacks a
+                target or targets the live head, resync_required
+                when a get_events_since contiguity demand cannot
+                be met, invalid_project for a bad project id,
+                project_exists for a duplicate create,
+                unknown_document for a missing document,
+                unknown_revision for a rewind target with no
+                snapshot, invalid_path or path_escape for a bad
+                document path, request_conflict for a reused
+                envelope id with new text, unknown_cell,
+                ambiguous_cell, unknown_param, incompatible_port,
+                or instance_exists for a bad placement,
+                invalid_reference for a bad asset address,
+                unknown_request for an id never admitted.
+            ExecutionError: pool_full when the execution backlog
+                is saturated — drain (run_job) before submitting
+                more; nothing was admitted.
 
         Caution: Bound to one project: cross-project envelopes are
             denied, never routed — and a stale expected_revision
-            fails instead of merging.
+            fails instead of merging. The first mutating call per
+            Engine also drains crash survivors (boot replay);
+            queries never do.
         """
         envelope = command.get("project_id")
         if envelope != self._project_id:
@@ -309,18 +359,23 @@
             return self._project.read_doc(arguments["path"])
         if name in _JOB_QUERIES:
             return self._query_job(name, arguments)
+        if name in _APIG_QUERIES:
+            return self._query_apig(name, arguments)
         if name in _WIRED_QUERIES:
             return self._project.snapshot()
         if name in QUERIES or name not in OPERATIONS:
             raise ProjectError(
                 "unsupported_operation", f"Operation not wired yet: {name}."
             )
+        self._replay_once()
         if name == "run_job":
-            # Phase 2 executes immediately: admission (and its revision
-            # gate) already happened at submit time.
+            # Deferred/batch pumping plus idempotent fetch: admission
+            # (and its revision gate) already happened at submit time.
             return self.run(command)
         if name in _CRUD_OPERATIONS:
             return self._submit_crud(name, arguments, command)
+        if name == "place_cell":
+            return self._submit_place_cell(arguments, command)
         if not self._solvers.get(name):
             raise ProjectError(
                 "unsupported_operation", f"No solver registered: {name}."
@@ -328,15 +383,19 @@
         buf = io.StringIO()
         self._yaml.dump({"operation": name, "arguments": arguments}, buf)
         request_id = command.get("request_id") or uuid.uuid4().hex
-        ack = self._project.submit(
+        ack = self._pool.submit_request(
             buf.getvalue(),
             str(request_id),
             expected_revision=arguments.get("expected_revision"),
         )
-        # The ack run_id is the execution id: register its queued
-        # record now so get_job_status can poll it — and run_job can
-        # execute it — under the one id. A replay returns the same
-        # ack; its record already exists, so register it only once.
+        # SUBMIT-IMMEDIATE: the ack run_id is the execution id. A
+        # replay of a completed run returns the stored completion
+        # without re-executing; otherwise register the record (a
+        # replay returns the same ack, so register it only once)
+        # and drain this run inline.
+        stored = self._stored_completion(ack["run_id"])
+        if stored is not None:
+            return merge_ack_completion(ack, stored)
         if not self._execution.known(ack["run_id"]):
             self._execution.dispatch(
                 name,
@@ -353,7 +412,8 @@
                 "request_id": str(request_id),
             },
         )
-        return ack
+        completion = self._pool.drain_ids([ack["run_id"]])[0]
+        return merge_ack_completion(ack, completion)
 
     def _query_events_since(self, arguments):
         """Serve the wired get_events_since query (cursor + resync)."""
@@ -443,6 +503,339 @@
             expected_revision=arguments.get("expected_revision"),
         )
 
+    def _submit_place_cell(self, arguments, command):
+        """Place a catalogue cell immediately (no queue, no solver)."""
+        if "cell" not in arguments:
+            raise ProjectError(
+                "invalid_command", "place_cell needs a cell argument."
+            )
+        request_id = str(command.get("request_id") or uuid.uuid4().hex)
+        try:
+            return self._cells.place_cell(
+                self._project,
+                arguments["cell"],
+                request_id,
+                expected_revision=arguments.get("expected_revision"),
+                pdk=arguments.get("pdk"),
+                instance_id=arguments.get("instance_id"),
+                params=arguments.get("params"),
+                connections=arguments.get("connections"),
+            )
+        except LibraryError as exc:
+            raise ProjectError(exc.code, str(exc)) from exc
+
+    def _query_apig(self, name, arguments):
+        """Route a catalogue/asset query to its Engine reader."""
+        if name == "list_cells":
+            return self.catalog_cells(pdk=arguments.get("pdk"))
+        if name == "serve_asset":
+            return self.serve_asset(
+                arguments.get("pdk_id"),
+                arguments.get("revision"),
+                arguments.get("path"),
+                engine_root=arguments.get("engine_root"),
+            )
+        if name == "list_assets":
+            return self.list_assets(
+                arguments.get("pdk_id"),
+                arguments.get("revision"),
+                prefix=arguments.get("prefix"),
+                engine_root=arguments.get("engine_root"),
+            )
+        raise ProjectError("unsupported_operation", f"Operation not wired yet: {name}.")
+
+    def catalog_cells(self, pdk=None):
+        """List versioned component cells, optionally for one PDK.
+
+        The engine introspects cell libraries upstream and serves
+        plain data (cell, PDK, ports, default params), so the
+        frontend never imports gdsfactory.
+
+        Args:
+            pdk: Restrict to one PDK label; all entries when
+                omitted.
+
+        Returns:
+            Listing with catalog_version and cells sorted by
+                (pdk, cell).
+        """
+        return self._cells.list_cells(pdk=pdk)
+
+    def register_cells(self, entries, source="static"):
+        """Seed the component catalogue with static entries.
+
+        Args:
+            entries: Entry mappings with cell, pdk, pdk_revision,
+                ports, and default params.
+            source: Source label stamped on every entry.
+
+        Returns:
+            Mapping with the cell count now served.
+        """
+        self._cells.add_provider(static_provider(entries, source=source))
+        return {"cells": len(self._cells.list_cells()["cells"])}
+
+    def serve_asset(self, pdk_id=None, revision=None, path=None,
+                    engine_root=None):
+        """Serve one PDK file's bytes verbatim with hash identity.
+
+        No conversion, no rendering: the sha256 is computed over
+        the raw bytes, base64 is transport encoding only.
+
+        Args:
+            pdk_id: PDK id (either display spelling resolves).
+            revision: PDK revision pin.
+            path: Store-relative file path.
+            engine_root: Explicit store root; ROCKETEDA_HOME
+                resolution when omitted.
+
+        Returns:
+            Mapping with asset_version, pdk_id, display_id,
+                revision, canonical path, size, sha256, and the
+                verbatim bytes base64-encoded.
+
+        Raises:
+            ProjectError: invalid_command when pdk id, revision,
+                or path is missing; invalid_reference for an
+                unknown PDK, a missing file, or an escaping path.
+
+        Caution: No size cap — bulk reads belong to list_assets
+            plus selective serve_asset calls, never a blind loop.
+        """
+        if pdk_id is None or revision is None or path is None:
+            raise ProjectError(
+                "invalid_command",
+                "serve_asset needs pdk_id, revision, and path arguments.",
+            )
+        try:
+            return apig_assets.serve_asset(
+                pdk_id, revision, path, engine_root=engine_root
+            )
+        except ContractError as exc:
+            raise ProjectError(exc.code, str(exc)) from exc
+
+    def list_assets(self, pdk_id=None, revision=None, prefix=None,
+                    engine_root=None):
+        """List PDK file metadata with per-file hash identity.
+
+        Args:
+            pdk_id: PDK id (either display spelling resolves).
+            revision: PDK revision pin.
+            prefix: Optional store-relative prefix filter.
+            engine_root: Explicit store root; ROCKETEDA_HOME
+                resolution when omitted.
+
+        Returns:
+            Mapping with asset_version, pdk_id, display_id,
+                revision, sorted file entries (path, size,
+                sha256), symlink entries, and the file count.
+
+        Raises:
+            ProjectError: invalid_command when pdk id or revision
+                is missing; invalid_reference for an unknown PDK
+                or an escaping prefix.
+        """
+        if pdk_id is None or revision is None:
+            raise ProjectError(
+                "invalid_command",
+                "list_assets needs pdk_id and revision arguments.",
+            )
+        try:
+            return apig_assets.list_assets(
+                pdk_id, revision, prefix=prefix, engine_root=engine_root
+            )
+        except ContractError as exc:
+            raise ProjectError(exc.code, str(exc)) from exc
+
+    def _stored_completion(self, run_id):
+        """Stored completion for a finished run, without executing.
+
+        In-memory verdicts answer first; across a reboot the
+        ledger's run event answers instead. Runs that never
+        finished (or never ran) answer None.
+        """
+        try:
+            status = self._execution.status(run_id)
+        except ExecutionError:
+            status = None
+        if (
+            status is not None
+            and status.get("state") in ("completed", "cancelled")
+            and status.get("verdict") is not None
+        ):
+            pending = self._run_jobs.get(run_id, {})
+            return {
+                "run_id": run_id,
+                "state": status["state"],
+                "verdict": status["verdict"],
+                "operation": pending.get("operation"),
+            }
+        return stored_completion_from_events(
+            self._project.events_since(0), run_id
+        )
+
+    def _resolve_pending(self, request_id):
+        """Admitted (command, ack) for a queued request, registered.
+
+        Reboot path: unknown execution records are registered and
+        the run job stashed, so the pool runner finds both.
+        """
+        stored_command, ack = self._project.command_for(request_id)
+        run_id = ack.get("run_id")
+        if not self._execution.known(run_id):
+            self._execution.dispatch(
+                stored_command.get("operation"),
+                {"cell": (stored_command.get("arguments") or {}).get("cell")},
+                ack.get("snapshot_id", ""),
+                run_id=run_id,
+            )
+        self._run_jobs.setdefault(
+            run_id,
+            {
+                "operation": stored_command.get("operation"),
+                "arguments": dict(stored_command.get("arguments") or {}),
+                "snapshot_id": ack.get("snapshot_id", ""),
+                "request_id": str(request_id),
+            },
+        )
+        return stored_command, ack
+
+    def _pool_execute(self, operation, arguments, snapshot_id, request_id,
+                      run_id):
+        """Execute one pooled run through its solver, contained."""
+        if not self._solvers.get(operation):
+            self._latest[operation] = run_id
+            self._logs[run_id] = (
+                f"unsupported_operation: No solver registered: {operation}."
+            )
+            verdict = self._execution.record_not_run(
+                run_id, self._logs[run_id]
+            )
+            self._project.append_run_event(
+                "run_failed", run_id, operation, verdict, request_id
+            )
+            return {
+                "run_id": run_id,
+                "state": "completed",
+                "verdict": verdict,
+                "operation": operation,
+            }
+        run_arguments = dict(arguments)
+        run_arguments.pop("expected_revision", None)
+        return self._run_operation(
+            operation,
+            run_arguments,
+            snapshot_id,
+            request_id,
+            run_id=run_id,
+            contain=True,
+        )
+
+    def _run_batch(self, run_ids):
+        """Pump a batch of admitted runs oldest-listed first.
+
+        Finished runs contribute their stored completion without
+        re-executing; the rest are admitted to the pool (pool_full
+        refuses loudly past the bound) and drained in order. Every
+        listed id lands in exactly one of completions/refused.
+        """
+        if not isinstance(run_ids, list) or not run_ids:
+            raise ProjectError(
+                "invalid_command",
+                "run_job batch needs a non-empty run_ids list.",
+            )
+        completions = []
+        refused = []
+        seen = set()
+        admitted = []
+        for run_id in run_ids:
+            if run_id in seen:
+                refused.append({
+                    "run_id": run_id,
+                    "code": "duplicate_in_batch",
+                    "message": f"Run listed twice in one batch: {run_id}.",
+                })
+                continue
+            seen.add(run_id)
+            stored = self._stored_completion(run_id)
+            if stored is not None:
+                completions.append(stored)
+                continue
+            pending = self._run_jobs.get(run_id)
+            if pending is not None:
+                request_id = pending["request_id"]
+            else:
+                request_id = request_for_run(
+                    self._project.events_since(0), run_id
+                )
+            if request_id is None:
+                refused.append({
+                    "run_id": run_id,
+                    "code": "unknown_request",
+                    "message": f"No queued request: {run_id}.",
+                })
+                continue
+            stored_command, ack = self._project.command_for(request_id)
+            if not self._solvers.get(stored_command.get("operation")):
+                refused.append({
+                    "run_id": run_id,
+                    "code": "unsupported_operation",
+                    "message": (
+                        "No solver registered: "
+                        f"{stored_command.get('operation')}."
+                    ),
+                })
+                continue
+            self._resolve_pending(request_id)
+            try:
+                adopted = self._pool.adopt(
+                    request_id, run_id, stored_command,
+                    ack.get("snapshot_id", ""),
+                )
+            except ExecutionError as exc:
+                refused.append({
+                    "run_id": run_id,
+                    "code": exc.code,
+                    "message": str(exc),
+                })
+                continue
+            if not adopted:
+                stored = self._stored_completion(run_id)
+                if stored is not None:
+                    completions.append(stored)
+                    continue
+            admitted.append(run_id)
+        if admitted:
+            completions.extend(self._pool.drain_ids(admitted))
+        return {
+            "run_ids": list(run_ids),
+            "completions": completions,
+            "refused": refused,
+        }
+
+    def replay_pending(self):
+        """Drain crash-surviving admissions oldest first (boot replay).
+
+        Survivors are ledger admissions without a run event —
+        typically a kill between admit and drain. Finished runs
+        are never re-executed; unresolvable survivors are skipped
+        loudly in the report.
+
+        Returns:
+            Report with replayed run ids (seq order), their
+                completions, and skipped entries.
+        """
+        return self._pool.replay(
+            self._project.events_since(0), self._resolve_pending
+        )
+
+    def _replay_once(self):
+        """Drain crash survivors once per Engine (lazy boot replay)."""
+        if self._replayed:
+            return None
+        self._replayed = True
+        return self.replay_pending()
+
     def _select_solver(self, name, arguments):
         solvers = self._solvers.get(name) or {}
         if not solvers:
@@ -701,35 +1094,70 @@
         return self._execution.findings(run_id, limit=limit, cursor=cursor)
 
     def _run_queued(self, command):
-        """Execute an admitted request by id (phase 2 of submit-then-run).
+        """Execute admitted requests by id: deferred singles, fetch, batches.
+
+        Submit already ran inline, so this is the explicit path:
+        deferred execution for admissions drained elsewhere
+        (crash survivors, staged backlog), idempotent fetch for
+        finished runs, and ordered batch pumping.
 
         Request keys:
-            request_id (required): Envelope id admitted by an
-                earlier submit.
+            run_id: Admitted run to execute or fetch.
+            request_id: Envelope id admitted by an earlier submit
+                (resolves to its run when run_id is absent).
+            run_ids: Batch form — admitted runs to pump oldest
+                listed first.
 
         Args:
-            command: Envelope whose arguments carry request_id, the
-                id admitted by an earlier submit.
+            command: Envelope whose arguments carry run_id,
+                request_id, or run_ids.
 
         Returns:
             Completion mapping with run_id, state, verdict, and
-            operation for the admitted command.
+            operation for a single id (stored, never
+            re-executed, when the run already finished); batch
+            mapping with run_ids, completions, and refused for
+            the batch form (every listed id lands in exactly
+            one of the two lists).
 
         Raises:
             ProjectError: invalid_command when the arguments lack a
-                request_id, unknown_request for an id never
-                admitted, unsupported_operation when the admitted
+                run id or the batch list is malformed,
+                unknown_request for an id never admitted,
+                unsupported_operation when the admitted
                 operation has no registered solver.
         """
         arguments = dict(command.get("arguments") or {})
+        if arguments.get("run_ids") is not None:
+            return self._run_batch(arguments.get("run_ids"))
         run_id = arguments.get("run_id")
         if run_id is not None:
-            try:
-                pending = self._run_jobs[run_id]
-            except KeyError:
-                raise ProjectError(
-                    "unknown_request", f"No queued request: {run_id}."
-                ) from None
+            # Idempotent fetch: a finished run returns its stored
+            # completion instead of executing again.
+            stored = self._stored_completion(run_id)
+            if stored is not None:
+                return stored
+            pending = self._run_jobs.get(run_id)
+            if pending is None:
+                # Reboot path: the admitting request survives in
+                # the ledger even though this process never saw it.
+                queued_request = request_for_run(
+                    self._project.events_since(0), run_id
+                )
+                if queued_request is None:
+                    raise ProjectError(
+                        "unknown_request", f"No queued request: {run_id}."
+                    ) from None
+                stored_command, ack = self._project.command_for(
+                    queued_request
+                )
+                pending = {
+                    "operation": stored_command.get("operation"),
+                    "arguments": dict(stored_command.get("arguments") or {}),
+                    "snapshot_id": ack.get("snapshot_id", ""),
+                    "request_id": str(queued_request),
+                }
+                self._run_jobs[run_id] = pending
             stored_operation = pending["operation"]
             run_arguments = dict(pending["arguments"])
             snapshot_id = pending["snapshot_id"]
@@ -738,18 +1166,31 @@
             request_id = arguments.get("request_id")
             if request_id is None:
                 raise ProjectError(
-                    "invalid_command", "run_job needs a run_id or request_id argument."
+                    "invalid_command",
+                    "run_job needs a run_id, request_id, or run_ids argument.",
                 )
-            stored, ack = self._project.command_for(request_id)
-            stored_operation = stored.get("operation")
-            run_arguments = dict(stored.get("arguments") or {})
+            stored_command, ack = self._project.command_for(request_id)
+            stored_operation = stored_command.get("operation")
+            run_arguments = dict(stored_command.get("arguments") or {})
             snapshot_id = ack.get("snapshot_id", "")
             request_id = str(request_id)
             run_id = ack.get("run_id")
+            completion = self._stored_completion(run_id)
+            if completion is not None:
+                return completion
         if not self._solvers.get(stored_operation):
             raise ProjectError(
                 "unsupported_operation", f"No solver registered: {stored_operation}."
             )
+        if not self._execution.known(run_id):
+            # Reboot path: the ledger admitted this run, but this
+            # process holds no execution record for it yet.
+            self._execution.dispatch(
+                stored_operation,
+                {"cell": run_arguments.get("cell")},
+                snapshot_id,
+                run_id=run_id,
+            )
         # Submit-time admission data stays out of the solver job.
         # Targets were already filled at submit time; never re-fill
         # here (filled min/max would read as caller targets).
@@ -890,9 +1331,9 @@
             never exceptions. Every judged run appends
             run_completed (PASS/FAIL) or run_failed (NOT_RUN) to
             the ledger with the engine's actor and the verdict.
-            CRUD/rewind operations return the immediate mutation
-            mapping instead (new revision + events + approval-UI
-            fields).
+            CRUD/rewind/place_cell operations return the immediate
+            mutation mapping instead (new revision + events +
+            approval-UI fields).
 
         Raises:
             ProjectError: cross_project_denied for a foreign
@@ -900,9 +1341,10 @@
                 operation or unknown deck tool, invalid_command
                 when run_job lacks a run_id/request_id argument,
                 for caller-supplied run_spice targets, when a CRUD
-                mutation is malformed, or a rewind lacks a target
-                or targets the live head, revision_conflict for a
-                stale CRUD/rewind expected_revision,
+                mutation or place_cell is malformed, or a rewind
+                lacks a target or targets the live head,
+                revision_conflict for a stale CRUD/rewind/
+                place_cell expected_revision,
                 unknown_document for a missing CRUD document,
                 unknown_revision for a rewind target with no
                 snapshot.
@@ -917,10 +1359,11 @@
                 "cross_project_denied",
                 f"Bound to {self._project_id}, got {envelope}.",
             )
+        self._replay_once()
         name = command.get("operation")
         if name == "run_job":
             return self._run_queued(command)
-        if name in _CRUD_OPERATIONS:
+        if name in _CRUD_OPERATIONS or name == "place_cell":
             return self.submit(command)
         arguments = self._apply_targets(name, dict(command.get("arguments") or {}))
         return self._run_operation(
diff -u -r rocket-engine.orig/src/execution/__init__.py rocket-engine/src/execution/__init__.py
--- rocket-engine.orig/src/execution/__init__.py
+++ rocket-engine/src/execution/__init__.py
@@ -1,5 +1,12 @@
 """Admission, queue, dispatch, isolated workers, cancel, evidence, evaluation. Owns execution."""
 
+from .apig_pool import (
+    ApigPool,
+    pending_from_events,
+    request_for_run,
+    stored_completion_from_events,
+)
+from .apig_submit import SubmitImmediate, merge_ack_completion
 from .console import ConsoleSession, get_help
 from .dispatch import OpDispatcher, parse_op_call, parse_op_tokens
 from .errors import ExecutionError, UsageError
@@ -8,6 +15,7 @@
 from .worker import CellRunner, CredentialGate, worker_profile
 
 __all__ = [
+    "ApigPool",
     "BwrapRunner",
     "CellRunner",
     "ConsoleSession",
@@ -15,9 +23,14 @@
     "ExecutionError",
     "ExecutionService",
     "OpDispatcher",
+    "SubmitImmediate",
     "UsageError",
     "get_help",
+    "merge_ack_completion",
     "parse_op_call",
     "parse_op_tokens",
+    "pending_from_events",
+    "request_for_run",
+    "stored_completion_from_events",
     "worker_profile",
 ]
diff -u -r rocket-engine.orig/src/interfaces/__init__.py rocket-engine/src/interfaces/__init__.py
--- rocket-engine.orig/src/interfaces/__init__.py
+++ rocket-engine/src/interfaces/__init__.py
@@ -1,6 +1,7 @@
 """Single source of truth for engine contracts: wire schemas, typed
 commands, events, and outbound ports. No I/O, no logic."""
 
+from .apig_assets import asset_manifest, list_assets, serve_asset
 from .documents import validate_document
 from .errors import ContractError
 from .ports import ToolAdapter
@@ -9,7 +10,10 @@
 __all__ = [
     "ContractError",
     "ToolAdapter",
+    "asset_manifest",
     "check_connection",
+    "list_assets",
     "resolve_reference",
+    "serve_asset",
     "validate_document",
 ]
diff -u -r rocket-engine.orig/src/interfaces/vocabulary.py rocket-engine/src/interfaces/vocabulary.py
--- rocket-engine.orig/src/interfaces/vocabulary.py
+++ rocket-engine/src/interfaces/vocabulary.py
@@ -12,7 +12,7 @@
         "run_post_layout", "run_em", "run_thermal", "python_execute",
         "run_view_sync", "run_job",
         "create_project", "write_doc", "delete_doc", "apply_mutations",
-        "rewind",
+        "rewind", "place_cell",
     }
 )
 QUERIES = frozenset(
@@ -22,5 +22,6 @@
         "plan_checks", "get_job_status", "get_check_results",
         "get_events_since", "list_artifacts", "get_logs",
         "list_projects", "list_docs", "read_doc",
+        "list_cells", "serve_asset", "list_assets",
     }
 )
diff -u -r rocket-engine.orig/src/library/__init__.py rocket-engine/src/library/__init__.py
--- rocket-engine.orig/src/library/__init__.py
+++ rocket-engine/src/library/__init__.py
@@ -1,6 +1,13 @@
 """PDK registry, prepared-profile catalog, IP search/register/instantiate."""
 
+from .apig_catalog import ApigCatalog, gdsfactory_provider, static_provider
 from .catalog import Catalog
 from .errors import LibraryError
 
-__all__ = ["Catalog", "LibraryError"]
+__all__ = [
+    "ApigCatalog",
+    "Catalog",
+    "LibraryError",
+    "gdsfactory_provider",
+    "static_provider",
+]
```
