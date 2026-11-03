# COALESCE-I33 lane report — Request coalescing (I33)

Ticket: `docs/tickets/COALESCE-I33.md` + I33 text in
`docs/tickets/API-GENERALIZE.md` · Branch: GREEN-the-tests · No
commits, no pushes (integrator commits).

## Files added (new files only — zero edits to existing files)

- `src/execution/coalesce.py` — coalescing substrate: content keys
  (`i33:<operation>:<sha256>` over operation + normalized arguments
  incl. deck hash + frozen run.request), the revision-pinned
  `Coalescer` registry (lookup/join/attach/register/complete/
  discard + completion waiters + the admission `guard`).
  Stdlib only (`copy`, `hashlib`, `json`, `threading`,
  `collections.abc`); the one import is `ExecutionError` via the
  standard relative/install shim. No imports from the composition
  root, adapters, or sibling lanes.
- `tests/test_coalesce.py` — 24 unit tests: key stability (order,
  deck reorder, envelope exclusion), key sensitivity (operation,
  request knobs, deck content, tuple/list, bytes/str, int/str-key
  collisions), normalization (copy semantics, deck pinning,
  non-mapping refusal), and every registry transition incl.
  revision-move miss, complete-then-evict, discard wake, first-wins
  vs. stale-revision replacement, replay dedupe, waiter timeout,
  and threaded join fan-out.
- `tests/test_coalesce_wiring.py` — 4 post-patch integration tests
  the integrator runs AFTER applying the wiring patch below (skip
  until then): 5 identical concurrent submits → 1 execution;
  mutation between submits → 2 executions; forced duplicate →
  fresh execution + zero registration; completed run never
  coalesces + idempotent fetch still serves it.
- `docs/work/COALESCE-I33/wiring.patch` — the exact wiring patch as
  a file (same text as inline below; apply with `patch -p1`).
- `docs/work/COALESCE-I33/report.md` — this file.

## Contract implemented (ticket clause → behavior)

- Content key = operation + normalized arguments incl. deck hash +
  run.request — `content_key` hashes the operation with
  `normalize_arguments` output: envelope keys (`request_id`,
  `expected_revision`) dropped, `deck` replaced by its
  content-addressed `deck_hash`, the frozen `request` knobs riding
  verbatim (RUN-PARAMS freezes omitted/partial `request` before the
  key is computed, so all-defaults spellings coalesce).
  Canonicalization is type-tagged, not `str()`-based: tuple/list,
  bytes/str, and int/str-keyed mappings key distinctly, so
  distinct content can never share a verdict.
- Coalesce only across overlapping lifetime (queued/running) on the
  SAME project revision — `Coalescer` entries pin the
  post-admission head; `lookup`/`join` hit only on exact revision
  equality, and `complete`/`discard` evict, so finished runs never
  coalesce. The revision pin IS the no-intervening-mutation check:
  ledger law guarantees every mutation advances the revision and
  only mutations do (`log_coalesced_request` and run events never
  advance), so same-revision ⟺ no intervening mutation — one check,
  nothing to drift.
- Shared run_id fanned out; every request_id logged mapping to it —
  the owner drains inline while joiners park on the entry event;
  `complete` delivers one completion to all waiters. Joiners record
  via `ProjectService.log_coalesced_request`: their envelope maps
  to the shared run_id in the request map (replays and run_job
  resolve it) and a `request_coalesced` ledger event cites
  (request_id, run_id, revision, operation). Joiner responses carry
  `coalesced: true`; the owner/fresh shape is byte-unchanged.
- Completed results via idempotent fetch, never coalescing — after
  eviction a duplicate misses and executes fresh; fetching the old
  run_id still returns the stored completion (wiring test 4 pins
  both halves).
- Force bypasses coalescing — envelope `force: true` (strict)
  skips lookup AND registration: forced runs neither join nor
  serve. Forced replays of one envelope still dedupe (force
  bypasses coalescing, not request-id idempotency).
- Revision moved between requests → separate executions,
  unconditionally — any intervening mutation (solver submit, CRUD,
  rewind, place_cell, pyexec admit) advances the head and the pin
  misses. Joiners skip the expected_revision gate (they mutate
  nothing — the pin, not their gate token, guards freshness), which
  is what makes spam-click coalesce at all: the owner's admission
  already moved the head out from under the other four tokens.

## RED → GREEN evidence

Toolchain: `/tmp/celllink-venv` scratch env (pytest + ruamel,
`rocket_engine -> repo src` symlink). Patched-tree runs used
`PYTHONPATH` shims (`/tmp/i33-pkg`, `/tmp/i33-vpkg`) pointing at
`/tmp` copies; imports verified resolving to the patched copy
every time. Repo `.venv` untouched, no `uv sync`, no full suite
(lane rules).

RED (tests written before the module):

    /tmp/celllink-venv/bin/python -m pytest tests/test_coalesce.py \
      tests/test_coalesce_wiring.py -q
    # 24 failed, 4 skipped in 0.18s — every failure is
    # ImportError: cannot import name 'coalesce'
    #   from 'rocket_engine.execution'
    # (skips = wiring tests awaiting the patch)

One RED-phase design catch, fixed before GREEN: the admission
guard started as a plain `Lock`, but the wiring calls
lock-taking entry methods while holding it — the first GREEN run
hung. The guard is now a reentrant leaf lock (entry methods may
run under it; waits and drains never do), pinned by
`test_guard_serializes_admission_sections`, which deadlocks
otherwise.

GREEN (after adding `src/execution/coalesce.py`, real tree):

    # same command
    # 24 passed, 4 skipped in 0.08s

POST-PATCH (wiring developed on a /tmp tree copy; the repo tree
itself was never edited):

    PYTHONPATH=/tmp/i33-pkg /tmp/celllink-venv/bin/python -m pytest \
      tests/test_coalesce.py tests/test_coalesce_wiring.py -q
    # 28 passed, 0 skipped in 0.12s (all 4 wiring tests green)

Named neighbors (never the full suite):

    # real tree (new module present, patch absent):
    /tmp/celllink-venv/bin/python -m pytest \
      tests/execution/test_execution_service.py \
      tests/execution/test_dispatch.py tests/test_docstrings.py \
      tests/test_no_cloud.py -q
    # 27 passed
    # patched tree:
    PYTHONPATH=/tmp/i33-pkg .../python -m pytest \
      tests/execution/test_execution_service.py \
      tests/execution/test_dispatch.py tests/test_docstrings.py \
      tests/test_no_cloud.py tests/test_apig_submit.py \
      tests/test_apig_pool.py tests/test_block_runs_wiring.py \
      tests/test_block_runs_scope.py -q
    # 73 passed
    PYTHONPATH=/tmp/i33-pkg .../python -m pytest \
      tests/project/test_project_service.py \
      tests/project/test_crud_api.py \
      tests/project/test_ledger_durable.py \
      tests/project/test_rewind.py tests/test_engine_run.py -q
    # 58 passed, 2 skipped (slang not on PATH)
    # verified tree (patch applied to a pristine copy):
    PYTHONPATH=/tmp/i33-vpkg .../python -m pytest \
      tests/test_coalesce.py tests/test_coalesce_wiring.py \
      tests/execution/test_execution_service.py \
      tests/test_apig_submit.py tests/test_apig_pool.py \
      tests/test_docstrings.py tests/test_no_cloud.py -q
    # 55 passed
    /tmp/celllink-venv/bin/python scripts/check_docstrings.py \
      src/execution/coalesce.py
    # clean (exit 0); also clean on src/composition.py,
    # src/project/service.py, src/execution/__init__.py + module
    # in both patched copies
    python scripts/api_spec.py --check && python scripts/contract.py --check
    # exit 0 on the real tree AND both patched trees:
    # regen-neutral, no new operations/queries (integrator
    # re-runs --write to confirm no diff)

Style: no line over 100 chars in new files or patch-added lines
(the one `awk` hit, `src/project/service.py:707`, pre-exists in
the untouched `submit` and is outside every hunk).

## Wiring patch for the integrator (exact unified diff)

Verified: `patch -p1 --dry-run` applies cleanly to a pristine copy,
all three applied files are byte-identical to the tested tree
(`cmp`), all four files `py_compile`, `check_docstrings.py` passes
on all touched files, and the applied tree runs 28/28 lane tests
plus 55 neighbor tests with `api_spec`/`contract --check` green.
Apply with `patch -p1 < docs/work/COALESCE-I33/wiring.patch`, then
run the verification below. Copy of this diff:
`docs/work/COALESCE-I33/wiring.patch`.

What the patch does (`src/composition.py` + `src/project/service.py`
+ `src/execution/__init__.py` exports; no vocabulary, adapter,
query, CRUD, or replay changes):

- `Engine.__init__`: owns one `Coalescer` (the Engine is bound to
  one project, so same-revision implies same-project by
  construction).
- `Engine.submit` solver path: computes the content key, then holds
  the guard across lookup → ledger admit → register so identical
  concurrent submits cannot both miss. Hits log via
  `log_coalesced_request` (no revision advance, no gate) and wait
  outside the guard; misses admit as today and register the
  post-admission head; forced calls skip both. Drains run outside
  the guard with try/finally discard-then-complete, so waiters can
  never hang while the owner lives.
- `Engine._await_shared` (new): waiter delivery with stored-
  completion fallback (the run event precedes eviction) and a loud
  `coalesced_run_lost` when a joined run finished with nothing
  stored (owner died mid-drain).
- `ProjectService.log_coalesced_request` (new): records the
  envelope → shared run_id mapping (replays + run_job resolve it),
  appends the `request_coalesced` event, advances nothing.
- Raises prose gains `coalesced_run_lost` on `submit`.

```diff
diff --git a/src/composition.py b/src/composition.py
index 39a103a..baeea9a 100644
--- a/src/composition.py
+++ b/src/composition.py
@@ -62,6 +62,7 @@ from .execution.block_runs_scope import (
     snapshot_closure,
     stamp_verdict,
 )
+from .execution.coalesce import Coalescer, content_key
 from .execution.dispatch import OpDispatcher
 from .execution.errors import ExecutionError
 from .execution.python_exec import PythonExecService
@@ -228,6 +229,7 @@ class Engine:
             linked_root=linked_root,
         )
         self._execution = ExecutionService(project_id)
+        self._coalescer = Coalescer()
         self._layer_presets = PresetStore()
         self._catalog = Catalog(catalog_root)
         self._solvers = {
@@ -399,7 +401,9 @@ class Engine:
                 unknown_request for an id never admitted.
             ExecutionError: pool_full when the execution backlog
                 is saturated — drain (run_job) before submitting
-                more; nothing was admitted.
+                more; nothing was admitted. coalesced_run_lost
+                when a joined run finished with no completion
+                stored (its owner died mid-drain).
 
         Caution: Bound to one project: cross-project envelopes are
             denied, never routed — and a stale expected_revision
@@ -477,48 +481,82 @@ class Engine:
         scope_request = self._admit_block_scope(name, arguments)
         buf = io.StringIO()
         self._yaml.dump({"operation": name, "arguments": arguments}, buf)
+        command_text = buf.getvalue()
         request_id = command.get("request_id") or uuid.uuid4().hex
-        ack = self._pool.submit_request(
-            buf.getvalue(),
-            str(request_id),
-            expected_revision=arguments.get("expected_revision"),
-        )
-        # SUBMIT-IMMEDIATE: the ack run_id is the execution id. A
-        # replay of a completed run returns the stored completion
-        # without re-executing; otherwise register the record (a
-        # replay returns the same ack, so register it only once)
-        # and drain this run inline.
-        stored = self._stored_completion(ack["run_id"])
-        if stored is not None:
-            return merge_ack_completion(ack, stored)
-        if not self._execution.known(ack["run_id"]):
-            target = {"cell": arguments.get("cell")}
-            if scope_request is not None:
-                target["scope"] = "block"
-                target["block_id"] = scope_request["block_id"]
-            self._execution.dispatch(
-                name, target, ack["snapshot_id"], run_id=ack["run_id"]
-            )
-        self._run_jobs.setdefault(
-            ack["run_id"],
-            {
-                "operation": name,
-                "arguments": arguments,
-                "snapshot_id": ack["snapshot_id"],
-                "request_id": str(request_id),
-            },
-        )
-        if scope_request is not None:
-            pending = self._run_jobs[ack["run_id"]]
-            if "block_scope" not in pending:
-                pending["block_scope"] = build_scope_record(
-                    run_id=ack["run_id"],
-                    revision=self._project.snapshot()["current_revision"],
-                    block_id=scope_request["block_id"],
-                    deck=arguments.get("deck"),
-                    closure=scope_request["closure"],
+        # COALESCE-I33: identical concurrent content on an unchanged
+        # revision executes once. The guard holds the whole admission
+        # section — lookup, ledger admit, register — so two identical
+        # submits cannot both miss; drains and completion waits run
+        # outside it. Force bypasses the lane both ways: a forced run
+        # neither joins a live run nor registers as one.
+        force = command.get("force") is True
+        key = content_key(name, arguments)
+        with self._coalescer.guard:
+            head = self._project.snapshot()["current_revision"]
+            hit = None if force else self._coalescer.lookup(key, head)
+            if hit is not None:
+                ack = self._project.log_coalesced_request(
+                    command_text, str(request_id), hit["run_id"],
+                    hit["snapshot_id"],
+                )
+                waiter = self._coalescer.attach(hit["run_id"], str(request_id))
+            else:
+                ack = self._pool.submit_request(
+                    command_text,
+                    str(request_id),
+                    expected_revision=arguments.get("expected_revision"),
                 )
-        completion = self._pool.drain_ids([ack["run_id"]])[0]
+                # SUBMIT-IMMEDIATE: the ack run_id is the execution id. A
+                # replay of a completed run returns the stored completion
+                # without re-executing; otherwise register the record (a
+                # replay returns the same ack, so register it only once)
+                # and drain this run inline.
+                stored = self._stored_completion(ack["run_id"])
+                if stored is not None:
+                    return merge_ack_completion(ack, stored)
+                if not self._execution.known(ack["run_id"]):
+                    target = {"cell": arguments.get("cell")}
+                    if scope_request is not None:
+                        target["scope"] = "block"
+                        target["block_id"] = scope_request["block_id"]
+                    self._execution.dispatch(
+                        name, target, ack["snapshot_id"], run_id=ack["run_id"]
+                    )
+                self._run_jobs.setdefault(
+                    ack["run_id"],
+                    {
+                        "operation": name,
+                        "arguments": arguments,
+                        "snapshot_id": ack["snapshot_id"],
+                        "request_id": str(request_id),
+                    },
+                )
+                if scope_request is not None:
+                    pending = self._run_jobs[ack["run_id"]]
+                    if "block_scope" not in pending:
+                        pending["block_scope"] = build_scope_record(
+                            run_id=ack["run_id"],
+                            revision=self._project.snapshot()["current_revision"],
+                            block_id=scope_request["block_id"],
+                            deck=arguments.get("deck"),
+                            closure=scope_request["closure"],
+                        )
+                waiter = None
+                if not force:
+                    self._coalescer.register(
+                        key, ack["current_revision"], str(request_id),
+                        ack["run_id"], ack["snapshot_id"],
+                    )
+        if hit is not None:
+            return self._await_shared(ack, hit["run_id"], waiter)
+        try:
+            completion = self._pool.drain_ids([ack["run_id"]])[0]
+        except BaseException:
+            if not force:
+                self._coalescer.discard(ack["run_id"])
+            raise
+        if not force:
+            self._coalescer.complete(ack["run_id"], completion)
         return merge_ack_completion(ack, completion)
 
     def _query_events_since(self, arguments):
@@ -793,6 +831,26 @@ class Engine:
             self._project.events_since(0), run_id
         )
 
+    def _await_shared(self, ack, run_id, waiter):
+        """Resolve a coalesced envelope to the shared completion.
+
+        The waiter delivers the owner's completion; a run evicted
+        just before attach (or discarded when its drain raised)
+        falls back to the stored completion — the run event
+        precedes eviction, so fetch cannot miss a finished run.
+        """
+        completion = None
+        if waiter is not None:
+            completion = self._coalescer.await_completion(waiter)
+        if completion is None:
+            completion = self._stored_completion(run_id)
+        if completion is None:
+            raise ExecutionError(
+                "coalesced_run_lost",
+                f"Shared run finished with no completion: {run_id}.",
+            )
+        return merge_ack_completion(ack, completion)
+
     def _resolve_pending(self, request_id):
         """Admitted (command, ack) for a queued request, registered.
 
diff --git a/src/execution/__init__.py b/src/execution/__init__.py
index b8a5b48..27b17f7 100644
--- a/src/execution/__init__.py
+++ b/src/execution/__init__.py
@@ -23,6 +23,12 @@ from .block_runs_scope import (
     snapshot_closure,
     stamp_verdict,
 )
+from .coalesce import (
+    Coalescer,
+    content_key,
+    deck_hash,
+    normalize_arguments,
+)
 from .console import ConsoleSession, get_help
 from .dispatch import OpDispatcher, parse_op_call, parse_op_tokens
 from .errors import ExecutionError, UsageError
@@ -49,6 +55,7 @@ __all__ = [
     "BlockScopeError",
     "BwrapRunner",
     "CellRunner",
+    "Coalescer",
     "ConsoleSession",
     "CredentialGate",
     "ExecutionError",
@@ -63,9 +70,12 @@ __all__ = [
     "build_worker_source",
     "check_operation_scope",
     "closure_hash",
+    "content_key",
+    "deck_hash",
     "get_help",
     "merge_ack_completion",
     "narrow_job_for_block",
+    "normalize_arguments",
     "not_run_verdict",
     "parse_exception",
     "parse_op_call",
diff --git a/src/project/service.py b/src/project/service.py
index dfd6504..9cafb38 100644
--- a/src/project/service.py
+++ b/src/project/service.py
@@ -776,6 +776,78 @@ class ProjectService:
         self._persist_after_mutation()
         return record
 
+    def log_coalesced_request(self, command_text, request_id, run_id,
+                              snapshot_id):
+        """Log a coalesced envelope against its shared run (COALESCE-I33).
+
+        A duplicate submit that joins a live run records its envelope
+        here instead of admitting: the request_id maps to the shared
+        run_id in the request map (so replays and run_job resolve it)
+        and a `request_coalesced` event lands in the log — but the
+        revision never advances, no snapshot is captured, and the
+        project never mutates. Joining callers are readers of a
+        shared verdict, not writers.
+
+        Args:
+            command_text: YAML command mapping with an operation.
+            request_id: Joining envelope id; resubmitting the
+                identical text returns the identical ack.
+            run_id: Shared live run the envelope joins.
+            snapshot_id: Shared run's snapshot (one revision pins
+                one snapshot).
+
+        Returns:
+            Coalesced ack with the caller's request_id, the shared
+                run_id and snapshot_id, queued state, the current
+                (unadvanced) revision, the event cursor, and a
+                coalesced marker.
+
+        Raises:
+            ProjectError: invalid_yaml for an unparsable command or
+                one without an operation, request_conflict for a
+                reused id with new text.
+
+        Caution: Never advances the revision — a coalesced envelope
+            must not break the pin later duplicates join under.
+        """
+        self._refresh_durable()
+        replay = self._check_replay(request_id, command_text)
+        if replay is not None:
+            return replay
+        try:
+            command = self._yaml.load(command_text)
+        except Exception as exc:
+            raise ProjectError(
+                "invalid_yaml", f"Cannot parse command: {exc}"
+            ) from exc
+        if not isinstance(command, dict) or "operation" not in command:
+            raise ProjectError(
+                "invalid_yaml",
+                "Command must be a mapping with an operation.",
+            )
+        ack = {
+            "request_id": request_id,
+            "project_id": self._project_id,
+            "run_id": run_id,
+            "snapshot_id": snapshot_id,
+            "state": "queued",
+            "current_revision": self._current_revision,
+            "coalesced": True,
+        }
+        self._requests[request_id] = (command_text, ack)
+        self._append_event(
+            "request_coalesced",
+            request_id,
+            {
+                "run_id": run_id,
+                "revision": self._current_revision,
+                "operation": command.get("operation"),
+            },
+        )
+        ack["event_cursor"] = self._cursor()
+        self._persist_after_mutation()
+        return ack
+
     def command_for(self, request_id):
         """Return the admitted (command, ack) for a queued request.
 
```

Post-patch verification (integrator, full env):

    patch -p1 < docs/work/COALESCE-I33/wiring.patch
    python scripts/api_spec.py --write && git diff --stat docs/
    # expect no changes: no new ops/queries
    python scripts/contract.py --write && git diff --stat docs/
    # expect no changes
    python -m pytest tests/test_coalesce.py \
      tests/test_coalesce_wiring.py -q  # expect 28 passed, 0 skipped
    # then the full suite + gate per ticket acceptance.

## Refusals with reasons

- No edits to any existing file: ownership allows creates only; all
  wiring is delivered as the patch above (developed and tested on
  /tmp tree copies; the repo tree was never modified in place).
- No full-suite run: lane rules forbid it on this shared tree; ran
  only the new tests plus the named neighbors above.
- No `api_spec`/`contract --write` run: both rewrite tracked `docs/*`
  files, which I may not edit; `--check` passes on the real tree
  and both patched trees, with the exact `--write` commands above
  for the integrator to confirm the no-op.
- No use of repo `.venv` or `uv sync`: all runs used the
  `/tmp/celllink-venv` scratch env plus `PYTHONPATH` shims for the
  patched copies.
- No `tests/pdk_*/`, `docs/pdk/*/`, or ASAP7-DRC-DECK contact of
  any kind.

## Deliberate scope edges (kept honest)

- Solver submits only: CRUD/rewind/place_cell/python_execute never
  coalesce (each mutation is a distinct revision advance — sharing
  one would lose writes), and direct `run()` executes fresh always
  (no request_id, no ledger admission — nothing to join under).
- In-memory, same-process: a reboot clears live entries, so a fresh
  submit never joins a crash survivor being boot-replayed — it
  executes (a second execution after a replay race is honest;
  cross-reboot sharing would need durable join state, out of
  scope).
- No cancel wiring: `cancel_job` reaches only python_execute
  workers today, so no solver waiter can be stranded by it; if a
  solver cancel path lands, it must call `Coalescer.discard` for
  the run (one line, joiners then fail loudly with
  `coalesced_run_lost` instead of hanging).
- `force` is envelope-level strict (`command["force"] is True`):
  truthy-but-not-`True` values do not bypass, and an arguments-level
  `force` is inert content, never a bypass. Human-approval gating
  for force (API-GENERALIZE) stays a separate lane.
- Thread-safety boundary: the patch serializes the whole submit
  admission section (lookup, ledger admit, coalesced logging,
  register) under the guard, and the tests prove one owner + four
  joiners race-free. Two concurrent owners of DIFFERENT content
  still share the pre-existing Engine caveat (drain-time YAML dumps
  on the shared instance while another thread admits) — unchanged
  by this lane, never exercised by its tests.

## Integrator note (merged after CONSOLE-ROUTE 616c912)

The shipped patch drifted on composition.py (replay submit routing
+ docstrings) and execution/__init__.py (replay + console-route
exports), so the integrator applied the service.py hunk
(log_coalesced_request) via `git apply --include` and hand-merged
composition.py (import, __init__, submit docstring, the guarded
submit admission block, _await_shared) and the coalesce import +
__all__ entries with patch-identical added lines. `wiring.patch`
was refreshed to the exact merged bytes. Regen is a no-op for this
lane (no new Engine/ProjectService verbs face the contract).
Live: 28/28 coalesce tests, neighbor gate 155 passed,
api_spec/contract/docstrings fresh, no >100-col additions.
