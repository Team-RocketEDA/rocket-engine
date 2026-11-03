# BLOCK-RUNS lane report — Block-scoped run targets (run-from-block)

Ticket: `docs/tickets/BLOCK-RUNS.md` · Branch: GREEN-the-tests · No commits, no pushes (integrator commits).

## Files added (new files only — zero edits to existing files)

- `src/execution/block_runs_scope.py` — block-scope substrate: target
  validation, operation gating (SPICE + syntax first), entity
  resolution, component-closure snapshot + hash, job narrowing, and
  verdict/provenance stamping. Stdlib only (`copy`, `hashlib`, `json`,
  `collections.abc`); no imports from the composition root, adapters,
  or sibling lanes.
- `tests/test_block_runs_scope.py` — 26 unit tests for every module
  entry point incl. all named rejection reasons.
- `tests/test_block_runs_isolation.py` — 4 sibling-breakage isolation
  tests: amp greens against its golden while the bias sibling's
  breakage leaves it untouched (closure-hash stability + findings
  confinement).
- `tests/test_block_runs_wiring.py` — 5 post-patch integration tests
  the integrator runs AFTER applying the wiring patch below (skip
  until then): narrowed submit→run_job, run-event provenance,
  wired sibling isolation, unknown-block submit refusal, project
  runs unaffected.
- `docs/work/BLOCK-RUNS/wiring.patch` — the exact wiring patch as a
  file (same text as inline below; apply with `patch -p1`).
- `docs/work/BLOCK-RUNS/report.md` — this file.

## Contract implemented (ticket clause → behavior)

- `target.scope: block` accepted on run verbs (SPICE + syntax first,
  decks following) — `parse_target` normalizes the caller target
  (absent means project); `check_operation_scope` admits block scope
  only for `run_spice`/`run_syntax` (`BLOCK_RUN_OPERATIONS`) and
  rejects later verbs with named `unsupported_scope` citing the
  serving verbs. No new verbs: scope rides the existing `target`
  argument shape end to end.
- Preflight resolves the entity — `resolve_block` against the block
  store (mapping or list); unknown ids fail with named
  `unknown_block` (message + fields name the id), malformed stores
  with `invalid_block`.
- Snapshots its component closure (sources, CellLink, params,
  constraints) — `snapshot_closure` pins all four plus an optional
  resolved link and variant; every collection is a copy (storage is
  never mutated or aliased — tested). CellLink resolution arrives as
  an optional caller callable (`resolve_celllink(block, variant)`,
  compatible with the CELL-LINK lane's `resolve_link` signature) so
  this substrate never imports uncommitted lane code; without it the
  stored link pins verbatim. `closure_hash` is content-addressed and
  key-order stable, so a rerun after a sibling edit proves isolation
  by hashing identically.
- Narrowing before adapter preflight — `narrow_job_for_block`
  replaces job sources wholesale with the closure sources and rides
  the closure hash along; SPICE/syntax adapters need no changes
  (they preflight what they are given, and project sources never
  leak in).
- Scope recorded in verdicts + provenance — `scope_provenance`
  cites `(run_id, revision, block_id, deck)` with the deck copied
  verbatim; `stamp_verdict` records it under `verdict["scope"]`
  without mutating; `build_scope_record` binds provenance + hash +
  a private closure copy and refuses closures belonging to another
  block. The run event stores the verdict, so provenance lands in
  the ledger with no `ProjectService` change.
- Unknown block id fails submit with a named reason — the wiring
  patch maps `BlockScopeError` to `ProjectError` preserving the
  code, so submit raises `unknown_block` (likewise `invalid_target`
  / `unsupported_scope`).

## RED → GREEN evidence

Toolchain: `/tmp/celllink-venv` (existing /tmp scratch env: pytest +
ruamel, `rocket_engine -> src` symlink). A fresh `/tmp/blockruns-venv`
was attempted first but pip could not reach the index (proxy down),
so the pre-built scratch env was reused. Repo `.venv` untouched, no
`uv sync`, no full suite (lane rules).

RED (tests written before the module):

    /tmp/celllink-venv/bin/python -m pytest tests/test_block_runs_scope.py \
      tests/test_block_runs_isolation.py tests/test_block_runs_wiring.py -q
    # 30 failed, 5 skipped — every failure is
    # ImportError: cannot import name 'block_runs_scope'
    #   from 'rocket_engine.execution'
    # (skips = wiring tests awaiting the patch)

GREEN (after adding `src/execution/block_runs_scope.py`):

    # same command
    # 30 passed, 5 skipped in 0.06s

POST-PATCH (wiring patch applied to a /tmp tree copy; engine imports
verified to resolve to the patched copy; the repo tree itself was
never edited):

    PYTHONPATH=/tmp/br-tree /tmp/celllink-venv/bin/python -m pytest /tmp/br-tests/ -q
    # 35 passed, 0 skipped in 0.07s (all 5 wiring tests green)

Named neighbors (never the full suite):

    /tmp/celllink-venv/bin/python -m pytest tests/execution/test_execution_service.py \
      tests/execution/test_dispatch.py tests/test_docstrings.py tests/test_no_cloud.py -q
    # 27 passed
    /tmp/celllink-venv/bin/python -m pytest tests/test_engine_run.py -q
    # 16 passed, 2 skipped (slang not on PATH; magic + ngspice present)
    PYTHONPATH=/tmp/br-tree /tmp/celllink-venv/bin/python -m pytest \
      tests/execution/test_execution_service.py tests/execution/test_dispatch.py \
      tests/test_engine_run.py tests/test_no_cloud.py -q
    # 39 passed, 2 skipped (patched tree: no regressions)
    /tmp/celllink-venv/bin/python scripts/check_docstrings.py \
      src/execution/block_runs_scope.py
    # clean (exit 0); also clean on both patched copies
    python scripts/api_spec.py --check && python scripts/contract.py --check
    # exit 0 on the real tree AND the patched tree: regen-neutral,
    # no new operations/queries (integrator re-runs --write to confirm no diff)

Style: no line over 100 chars in new/patched files (repo ruff limit).

## Wiring patch for the integrator (exact unified diff)

Verified: `patch -p1 --dry-run` applies cleanly to a pristine copy,
the applied result is byte-identical to the tested tree (`diff -r`),
both files `py_compile`, `check_docstrings.py` passes on both, and
the patched tree runs 35/35 block tests plus 39 neighbor tests with
`api_spec`/`contract --check` green. Apply with
`patch -p1 < docs/work/BLOCK-RUNS/wiring.patch`, then run the
verification below. Copy of this diff:
`docs/work/BLOCK-RUNS/wiring.patch`.

What the patch does (`src/composition.py` + `src/execution/__init__.py`
exports; no vocabulary, adapter, or ledger changes):

- `Engine(..., blocks=None)`: optional block store (mapping or list);
  runs without a block target never read it.
- `Engine._admit_block_scope` (new): validates `arguments["target"]`,
  gates the verb, resolves the entity, snapshots the closure;
  `BlockScopeError` becomes `ProjectError` with the code preserved.
- `submit`: admits before queueing (unknown blocks fail submit, never
  queue); binds the `(run_id, revision, block_id, deck)` record after
  the ack (revision read post-admission; replayed acks keep their
  first record); the execution dispatch target carries
  `scope`/`block_id` alongside `cell`.
- `_run_operation`: queued runs read the stored record; direct runs
  bind the admitted closure to the dispatched id; the solver job
  narrows onto the closure sources before adapter preflight; all
  four verdict sites (selector failure, adapter failure, internal
  failure, judged) stamp scope and re-store so `status`/`checks`
  show it; run events carry the stamped verdict as provenance.
- `run`: admits block scope on the direct path and threads it into
  `_run_operation`. `run_job`/CRUD dispatch order is unchanged.

```diff
--- a/src/composition.py
+++ b/src/composition.py
@@ -42,6 +42,16 @@
 from .adapters.ngspice import NgspiceAdapter
 from .adapters.sax import SaxAdapter
 from .adapters.syntax import SyntaxAdapter
+from .execution.block_runs_scope import (
+    BlockScopeError,
+    build_scope_record,
+    check_operation_scope,
+    narrow_job_for_block,
+    parse_target,
+    resolve_block,
+    snapshot_closure,
+    stamp_verdict,
+)
 from .execution.errors import ExecutionError
 from .execution.service import ExecutionService
 from .interfaces.setup import report_capabilities
@@ -140,12 +150,17 @@
         constraints: Optional run_spice metric targets
             ({metric: {min, max, unit[, expr, control]}}); caller
             targets are refused, unknown metrics fail loudly.
+        blocks: Optional block store for block-scoped runs (a
+            mapping of id to block entity, or a list of block
+            mappings); runs without a block target never read it.
     """
 
     def __init__(self, project_id, actor, catalog_root=".",
-                 engine_root=None, linked_root=None, constraints=None):
+                 engine_root=None, linked_root=None, constraints=None,
+                 blocks=None):
         self._project_id = project_id
         self._actor = actor
+        self._blocks = blocks if blocks is not None else {}
         self._project = ProjectService(
             project_id, actor, engine_root=engine_root,
             linked_root=linked_root,
@@ -263,8 +278,12 @@
         Raises:
             ProjectError: cross_project_denied for a foreign
                 envelope, unsupported_operation for an unwired or
-                unknown name, invalid_command for caller-supplied
-                run_spice targets, revision_conflict for a stale
+                unknown name, unknown_block for a block target
+                naming no block, invalid_target for a malformed
+                target, unsupported_scope for a block target on a
+                verb serving no block runs yet, invalid_command
+                for caller-supplied run_spice targets,
+                revision_conflict for a stale
                 expected_revision, invalid_command for a malformed
                 get_events_since cursor, a malformed mutation, or
                 a rewind that lacks a target or targets the live
@@ -325,6 +344,7 @@
             raise ProjectError(
                 "unsupported_operation", f"No solver registered: {name}."
             )
+        scope_request = self._admit_block_scope(name, arguments)
         buf = io.StringIO()
         self._yaml.dump({"operation": name, "arguments": arguments}, buf)
         request_id = command.get("request_id") or uuid.uuid4().hex
@@ -338,11 +358,12 @@
         # execute it — under the one id. A replay returns the same
         # ack; its record already exists, so register it only once.
         if not self._execution.known(ack["run_id"]):
+            target = {"cell": arguments.get("cell")}
+            if scope_request is not None:
+                target["scope"] = "block"
+                target["block_id"] = scope_request["block_id"]
             self._execution.dispatch(
-                name,
-                {"cell": arguments.get("cell")},
-                ack["snapshot_id"],
-                run_id=ack["run_id"],
+                name, target, ack["snapshot_id"], run_id=ack["run_id"]
             )
         self._run_jobs.setdefault(
             ack["run_id"],
@@ -353,6 +374,16 @@
                 "request_id": str(request_id),
             },
         )
+        if scope_request is not None:
+            pending = self._run_jobs[ack["run_id"]]
+            if "block_scope" not in pending:
+                pending["block_scope"] = build_scope_record(
+                    run_id=ack["run_id"],
+                    revision=self._project.snapshot()["current_revision"],
+                    block_id=scope_request["block_id"],
+                    deck=arguments.get("deck"),
+                    closure=scope_request["closure"],
+                )
         return ack
 
     def _query_events_since(self, arguments):
@@ -514,6 +545,41 @@
             updated["analyses"] = list(arguments.get("analyses") or []) + control
         return updated
 
+    def _admit_block_scope(self, name, arguments):
+        """Validate a block run target and snapshot its closure.
+
+        Arguments without a target run at project scope and skip
+        this path untouched; block targets resolve their entity
+        and pin the component closure the verdict later cites.
+
+        Args:
+            name: Cataloged operation about to run.
+            arguments: Operation arguments (target rides here).
+
+        Returns:
+            None for project runs, else the admitted scope with
+                block_id and closure keys (the run_id-bound record
+                is built once the ack id exists).
+
+        Raises:
+            ProjectError: unknown_block for a block target naming
+                no block, invalid_target for a malformed target,
+                unsupported_scope for a block target on a verb
+                serving no block runs yet.
+        """
+        if "target" not in arguments:
+            return None
+        try:
+            parsed = parse_target(arguments["target"])
+            check_operation_scope(name, parsed["scope"])
+            if parsed["scope"] != "block":
+                return None
+            block = resolve_block(parsed["id"], self._blocks)
+            closure = snapshot_closure(block)
+        except BlockScopeError as exc:
+            raise ProjectError(exc.code, str(exc)) from exc
+        return {"block_id": parsed["id"], "closure": closure}
+
     def job_status(self, run_id=None):
         """Read one run's state, verdict, and evidence links.
 
@@ -763,7 +829,8 @@
             contain=True,
         )
 
-    def _run_operation(self, name, arguments, snapshot_id, request_id, run_id=None, contain=False):
+    def _run_operation(self, name, arguments, snapshot_id, request_id, run_id=None,
+                       contain=False, block_scope=None):
         """Select the solver, run it, judge the verdict, log completion."""
         solvers = self._solvers.get(name) or {}
         if not solvers:
@@ -779,6 +846,10 @@
             self._latest[name] = run_id
             self._logs[run_id] = f"{exc.code}: {exc}"
             verdict = self._execution.record_not_run(run_id, f"{exc.code}: {exc}")
+            stored_scope = self._run_jobs.get(run_id, {}).get("block_scope")
+            if stored_scope is not None:
+                verdict = stamp_verdict(verdict, stored_scope["provenance"])
+                self._execution.mark_completed(run_id, verdict)
             self._project.append_run_event(
                 "run_failed", run_id, name, verdict, request_id
             )
@@ -798,6 +869,20 @@
             self._execution.status(run_id)
         self._execution.mark_running(run_id)
         self._latest[name] = run_id
+        scope_record = block_scope
+        if scope_record is None:
+            scope_record = self._run_jobs.get(run_id, {}).get("block_scope")
+        elif "provenance" not in scope_record:
+            # Direct runs admit the closure without a run_id; bind it now.
+            scope_record = build_scope_record(
+                run_id=run_id,
+                revision=self._project.snapshot()["current_revision"],
+                block_id=scope_record["block_id"],
+                deck=arguments.get("deck"),
+                closure=scope_record["closure"],
+            )
+        if scope_record is not None:
+            arguments = narrow_job_for_block(arguments, scope_record["closure"])
         try:
             adapter.preflight({"operation": name, **arguments})
             native = adapter.execute({"operation": name, **arguments})
@@ -805,6 +890,9 @@
         except AdapterError as exc:
             self._logs[run_id] = f"{exc.code}: {exc}"
             verdict = self._execution.record_not_run(run_id, f"{exc.code}: {exc}")
+            if scope_record is not None:
+                verdict = stamp_verdict(verdict, scope_record["provenance"])
+                self._execution.mark_completed(run_id, verdict)
             self._project.append_run_event(
                 "run_failed", run_id, name, verdict, request_id
             )
@@ -821,6 +909,9 @@
                 raise
             self._logs[run_id] = f"internal_error: {exc!r}"
             verdict = self._execution.record_not_run(run_id, f"internal_error: {exc}")
+            if scope_record is not None:
+                verdict = stamp_verdict(verdict, scope_record["provenance"])
+                self._execution.mark_completed(run_id, verdict)
             self._project.append_run_event(
                 "run_failed", run_id, name, verdict, request_id
             )
@@ -858,6 +949,9 @@
         if result.get("measurements") is not None:
             verdict = dict(verdict, measurements=result["measurements"])
             self._execution.mark_completed(run_id, verdict)
+        if scope_record is not None:
+            verdict = stamp_verdict(verdict, scope_record["provenance"])
+            self._execution.mark_completed(run_id, verdict)
         if (verdict or {}).get("status") == "NOT_RUN":
             outcome = "run_failed"
         else:
@@ -897,9 +991,13 @@
         Raises:
             ProjectError: cross_project_denied for a foreign
                 envelope, unsupported_operation for an unregistered
-                operation or unknown deck tool, invalid_command
-                when run_job lacks a run_id/request_id argument,
-                for caller-supplied run_spice targets, when a CRUD
+                operation or unknown deck tool, unknown_block for
+                a block target naming no block, invalid_target for
+                a malformed target, unsupported_scope for a block
+                target on a verb serving no block runs yet,
+                invalid_command when run_job lacks a
+                run_id/request_id argument, for caller-supplied
+                run_spice targets, when a CRUD
                 mutation is malformed, or a rewind lacks a target
                 or targets the live head, revision_conflict for a
                 stale CRUD/rewind expected_revision,
@@ -923,9 +1021,11 @@
         if name in _CRUD_OPERATIONS:
             return self.submit(command)
         arguments = self._apply_targets(name, dict(command.get("arguments") or {}))
+        block_scope = self._admit_block_scope(name, arguments)
         return self._run_operation(
             name,
             arguments,
             command.get("snapshot_id", ""),
             None,
+            block_scope=block_scope,
         )
--- a/src/execution/__init__.py
+++ b/src/execution/__init__.py
@@ -1,5 +1,21 @@
 """Admission, queue, dispatch, isolated workers, cancel, evidence, evaluation. Owns execution."""
 
+from .block_runs_scope import (
+    BLOCK_RUN_OPERATIONS,
+    BLOCK_SCOPE,
+    PROJECT_SCOPE,
+    SUPPORTED_SCOPES,
+    BlockScopeError,
+    build_scope_record,
+    check_operation_scope,
+    closure_hash,
+    narrow_job_for_block,
+    parse_target,
+    resolve_block,
+    scope_provenance,
+    snapshot_closure,
+    stamp_verdict,
+)
 from .console import ConsoleSession, get_help
 from .dispatch import OpDispatcher, parse_op_call, parse_op_tokens
 from .errors import ExecutionError, UsageError
@@ -8,6 +24,11 @@
 from .worker import CellRunner, CredentialGate, worker_profile
 
 __all__ = [
+    "BLOCK_RUN_OPERATIONS",
+    "BLOCK_SCOPE",
+    "PROJECT_SCOPE",
+    "SUPPORTED_SCOPES",
+    "BlockScopeError",
     "BwrapRunner",
     "CellRunner",
     "ConsoleSession",
@@ -16,8 +37,17 @@
     "ExecutionService",
     "OpDispatcher",
     "UsageError",
+    "build_scope_record",
+    "check_operation_scope",
+    "closure_hash",
     "get_help",
+    "narrow_job_for_block",
     "parse_op_call",
     "parse_op_tokens",
+    "parse_target",
+    "resolve_block",
+    "scope_provenance",
+    "snapshot_closure",
+    "stamp_verdict",
     "worker_profile",
 ]
```

Post-patch verification (integrator, full env):

    patch -p1 < docs/work/BLOCK-RUNS/wiring.patch
    python scripts/api_spec.py --write && git diff --stat docs/   # expect no changes: no new ops/queries
    python scripts/contract.py --write && git diff --stat docs/   # expect no changes
    python -m pytest tests/test_block_runs_scope.py tests/test_block_runs_isolation.py \
      tests/test_block_runs_wiring.py -q                          # expect 35 passed, 0 skipped
    # then the full suite + gate per ticket acceptance.

## Refusals with reasons

- No edits to any existing file (`src/**`, `scripts/**`, docs,
  `tests/pdk_*/`, `docs/pdk/*/`): ownership allows creates only; all
  wiring is delivered as the patch above (developed and tested on
  /tmp tree copies; the repo tree was never modified in place).
- No full-suite run: lane rules forbid it on this shared tree; ran
  only the new tests plus the named neighbors above.
- No `api_spec`/`contract --write` run: both rewrite tracked `docs/*`
  files, which I may not edit; `--check` passes on both the real and
  patched trees, with the exact `--write` commands above for the
  integrator to confirm the no-op.
- No use of repo `.venv` or `uv sync`: all runs used the
  `/tmp/celllink-venv` scratch env (a fresh scratch venv failed:
  pip index unreachable); the empty `/tmp/blockruns-venv` dir from
  that attempt was left in place.
- No CELL-LINK composition in the wiring: `snapshot_closure` takes
  an optional resolver (signature-compatible with that lane's
  `resolve_link`) but the patch passes none, so the stored link pins
  verbatim — the lanes stay independently committable; composing
  `Engine.resolve_celllinks` (if that patch lands) is a one-line
  follow-up inside `_admit_block_scope`.
- No deck-lane verbs beyond SPICE + syntax: `run_drc` etc. with a
  block target get named `unsupported_scope` per the ticket's
  "decks following" phasing; widening `BLOCK_RUN_OPERATIONS` is the
  only change when a deck lane wires narrowing.
- One known edge, kept honest: a direct (non-submit) block run whose
  deck tool selects no solver fails before any run id exists, so its
  NOT_RUN verdict cites no scope (there is no run to cite); the
  queued path always cites scope on every outcome.
