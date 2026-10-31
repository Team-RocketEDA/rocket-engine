# REPLAY-SAFE lane report

Base: `7b59990` (`GREEN-the-tests`). Ownership kept: only new files
created, no tracked file touched (`git status` shows `??` entries only
— this lane plus peers'). The wiring patch was built on scratch copies
under `/tmp` (never in the tree) and verified with `git apply --check`
at this HEAD.

## Outcome

Boot auto-replay is replaced by report-not-run survivors plus explicit,
gated resume. All ticket scope items are implemented as one new module
with passing tests, plus an exact, machine-verified wiring patch:

- Boot reports survivors (ledger-admitted, no completion event) and
  NEVER executes — zero executions after kill -9 mid-queue.
- Survivor taxonomy RETRYABLE / AMBIGUOUS / POISON with
  admitted→interrupted counting per content key in the ledger.
- Per-run Resume/Discard plus resume-all-retryable; quarantine (resume
  only with force).
- Typed refusal codes with friendly user-facing messages (no internals)
  and full dev-side logging.
- The pkill-then-boot message; every replay surface gated by explicit
  user decision.

## Files added

- `src/execution/replay_safe.py` — `ReplaySafe` (boot/resume/discard/
  resume-all), pure helpers (`content_key_for`,
  `interrupt_counts_from_events`, `survivors_from_events`,
  `boot_message`, `user_message_for`, `refuse`), taxonomy constants and
  `USER_MESSAGES`. Gate-clean per `scripts/check_docstrings.py`.
- `tests/test_replay_safe.py` (16) — RED-first lane tests, all passing.
- `docs/work/REPLAY-SAFE/report.md` (this file).
- `docs/work/REPLAY-SAFE/wiring.patch` — same bytes as the inline patch
  below; apply with `git apply -p1` from the repo root.

No fixtures: tests use a `FakeLedger` port plus real `ProjectService`
handles under `tmp_path`. Forbidden areas untouched: no `tests/pdk_*/`
or `docs/pdk/*/`, no ASAP7-DRC-DECK files, `.venv` used read-only as
the interpreter (no `uv sync` — a `PYTHONPATH` shim pointed at `src`).

## Design notes (per scope item)

- **Boot reports, never executes.** `ReplaySafe.boot()` lists
  ledger-admitted runs with no completion/discard event and returns the
  report; the executor is unreachable from it. Started-but-uncompleted
  runs gain one idempotent ledger `run_interrupted` mark each (a mark
  counts until the next `run_started`), so repeated boots never
  double-count.
- **Taxonomy.** Never-started → RETRYABLE; started, no completion →
  AMBIGUOUS; content key interrupted twice (`POISON_THRESHOLD = 2`) →
  POISON. Counts are derived from ledger `run_interrupted` events, so a
  rebooted process classifies with no in-memory state. A poisoned key
  quarantines every run sharing it, including never-started siblings.
- **Counting per content key.** `content_key_for(operation, arguments)`
  is `ck_` + 16 sha256 hex chars over canonical JSON (key-order
  stable). `expected_revision` is excluded — the poison is the content
  (the deck), not the revision it was admitted at.
- **Quarantine.** POISON resumes only with `force=True`; force bypasses
  quarantine only — the run still executes for real.
- **Refusals.** Typed codes (`unknown_survivor`, `already_completed`,
  `already_decided`, `poison_quarantined`,
  `ambiguous_requires_explicit_resume`) carried on `ExecutionError`;
  user messages are friendly with no ids/keys/traces, while every
  refusal logs run id, content key, and counts dev-side.
- **Pkill-then-boot message.** `boot_message(N)`: "Last session ended
  unexpectedly. N runs unfinished — nothing re-ran automatically.
  Review each run to Resume or Discard it." (plus a clean-session
  variant at zero). Every survivor carries `actions: ["resume",
  "discard"]`.
- **Gating.** The executor fires solely inside explicit `resume()` /
  `resume_all_retryable()` calls. Finished runs are never re-executed
  and there is deliberately no transcript re-run API (`replay_all` /
  `replay_transcript` do not exist — asserted). Unattended auto-resume
  stays backlog: no flag/config added.

## Wiring patch (what the integrator applies)

Same bytes as `wiring.patch`. Covers 4 files; `git apply --check -p1`
clean at `7b59990`:

- `src/project/service.py`: `content_key` (sans `expected_revision`)
  on `job_queued` data; new `append_replay_event()` for
  `run_started` / `run_interrupted` / `run_discarded` (revision never
  advances — replay bookkeeping only).
- `src/composition.py`: `Engine` owns a `ReplaySafe`; `_replay_once`
  builds the boot report instead of draining; new `boot_report`,
  `resume_survivor`, `discard_survivor`, `resume_all_retryable`;
  `replay_pending` becomes gated explicit-call compat (same
  `{replayed, completions, skipped}` shape, only RETRYABLE executes);
  `_pool_execute` appends `run_started` before running; `submit()`
  routes `resume_run` / `discard_run` / `resume_all_retryable` /
  `list_survivors`.
- `src/interfaces/vocabulary.py`: the three operations + the
  `list_survivors` query.
- `src/execution/__init__.py`: export the new symbols.

Deliberately NOT patched: `ApigPool.replay` (explicit pool-level
primitive, still covered by `test_apig_pool.py`), `dispatch.py` (new
names flow through the vocabulary gate), `McpTransport`/MCP server
(routes through `engine.submit`; new names flow like `place_cell`),
`scripts/*` (generators read the maps dynamically — APIG precedent).

```diff
--- rocket-engine.orig/src/project/service.py
+++ rocket-engine/src/project/service.py
@@ -54,6 +54,7 @@
 _REVISION_RE = re.compile(r"^(.*?)(\d+)$")
 _PROJECT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")
 _RUN_OUTCOMES = ("run_completed", "run_failed")
+_REPLAY_EVENTS = ("run_started", "run_interrupted", "run_discarded")
 _RESERVED_DOCS = frozenset({_LEDGER_FILENAME, _EVENTS_FILENAME})
 
 # Document prefix owning the five design-truth settings files.
@@ -726,6 +727,14 @@
             "current_revision": self._current_revision,
         }
         self._requests[request_id] = (command_text, ack)
+        # Lazy: keeps the project import chain free of the execution
+        # package (REPLAY-SAFE content keys).
+        from ..execution.replay_safe import content_key_for
+        key_arguments = {
+            key: value
+            for key, value in (command.get("arguments") or {}).items()
+            if key != "expected_revision"
+        }
         self._append_event(
             "job_queued",
             request_id,
@@ -733,6 +742,9 @@
                 "run_id": ack["run_id"],
                 "revision": self._current_revision,
                 "operation": command.get("operation"),
+                "content_key": content_key_for(
+                    command.get("operation"), key_arguments
+                ),
             },
         )
         ack["event_cursor"] = self._cursor()
@@ -776,6 +788,46 @@
         self._persist_after_mutation()
         return record
 
+    def append_replay_event(self, event, request_id, data):
+        """Append a replay-lifecycle event for one run.
+
+        `run_started` marks execution begin (a kill after it reads as
+        an interruption at the next boot); `run_interrupted` records
+        one admitted->interrupted transition for its content key (two
+        quarantines the key); `run_discarded` retires a survivor the
+        user chose not to resume.
+
+        Args:
+            event: Replay event name (run_started, run_interrupted,
+                or run_discarded).
+            request_id: Queued request the run belongs to.
+            data: Event data carrying the run_id (plus content_key
+                for started/interrupted marks).
+
+        Returns:
+            The appended event record with its seq.
+
+        Raises:
+            ProjectError: invalid_command for an unknown replay
+                event or data without a run_id.
+
+        Caution: Appends to the ordered log (and the cursor) but
+            never advances the project revision — replay
+            bookkeeping judges nothing and mutates nothing.
+        """
+        if event not in _REPLAY_EVENTS:
+            raise ProjectError(
+                "invalid_command", f"Unknown replay event: {event}."
+            )
+        if not isinstance(data, dict) or data.get("run_id") is None:
+            raise ProjectError(
+                "invalid_command", "Replay event needs a data.run_id."
+            )
+        self._refresh_durable()
+        record = self._append_event(event, request_id, dict(data))
+        self._persist_after_mutation()
+        return record
+
     def command_for(self, request_id):
         """Return the admitted (command, ack) for a queued request.
 
--- rocket-engine.orig/src/composition.py
+++ rocket-engine/src/composition.py
@@ -15,8 +15,10 @@
 the one run id; `run_job` stays for explicit/deferred/batch pumping
 plus idempotent result fetch — over `run()` directly or over
 submit-only transports via `submit(run_job)`. Replays return the
-stored completion without re-executing, and a fresh Engine drains
-crash survivors once (boot replay) on its first mutating call.
+stored completion without re-executing, and a fresh Engine reports
+crash survivors once (boot report, never executed) on its first
+mutating call; every replay surface stays gated behind an explicit
+resume decision (REPLAY-SAFE).
 With `constraints` (metric -> {min, max, unit[, expr, control]}),
 run_spice targets come from the project, never the caller:
 caller-supplied min/max — or a caller expr where the project defines
@@ -65,6 +67,7 @@
 from .execution.dispatch import OpDispatcher
 from .execution.errors import ExecutionError
 from .execution.python_exec import PythonExecService
+from .execution.replay_safe import ReplaySafe, content_key_for
 from .execution.service import ExecutionService
 from .interfaces import apig_assets
 from .interfaces.celllink import resolve_run as resolve_celllink_run
@@ -134,6 +137,7 @@
     "save_layer_preset": "layer_preset_save",
     "delete_layer_preset": "layer_preset_delete",
     "apply_layer_preset": "layer_preset_apply",
+    "list_survivors": "boot_report",
 }
 
 # Job-result queries served from execution state (plus the captured run log).
@@ -145,6 +149,11 @@
 # index and the PDK store); read-only, never replay the backlog.
 _APIG_QUERIES = frozenset({"list_cells", "serve_asset", "list_assets"})
 
+# Replay-safety query (REPLAY-SAFE): the boot survivor report, served
+# from ledger state. Report-only — never executes, only records
+# idempotent interruption marks for newly found outages.
+_REPLAY_QUERIES = frozenset({"list_survivors"})
+
 # Layer-serving queries (LAYER-SERVING): stackup/rows/presets served
 # from the PDK store plus Engine-memory user presets (PresetStore).
 _LAYER_QUERIES = frozenset(
@@ -249,6 +258,7 @@
         self._pool = ApigPool(
             self._project, self._pool_execute, max_depth=pool_max_depth
         )
+        self._replay = ReplaySafe(self._project, self._replay_execute)
         self._cells = ApigCatalog(
             catalog_root, providers=[gdsfactory_provider()]
         )
@@ -360,7 +370,10 @@
             bytes for the catalogue/asset queries, the
             stackup/rows/presets for the layer-serving queries,
             the stored-or-fresh completion for run_job, the
-            approval handle for python_execute, or the console
+            boot survivor report for list_survivors, the resume
+            completion for resume_run, the discard record for
+            discard_run, the gated batch for resume_all_retryable,
+            the approval handle for python_execute, or the console
             view for get_python_console.
 
         Raises:
@@ -383,7 +396,8 @@
                 kind or settings, an unknown settings kind, or
                 settings that break the kind schema, future_format
                 for a settings write over a newer on-disk file,
-                or a layer query missing its pdk_id/name,
+                or a layer query missing its pdk_id/name, a
+                resume_run or discard_run without a run_id,
                 resync_required when a get_events_since contiguity
                 demand cannot be met, invalid_project
                 for a bad project id,
@@ -399,13 +413,18 @@
                 unknown_request for an id never admitted.
             ExecutionError: pool_full when the execution backlog
                 is saturated — drain (run_job) before submitting
-                more; nothing was admitted.
+                more; nothing was admitted. Resume refusals carry
+                unknown_survivor, already_completed,
+                already_decided, or poison_quarantined with a
+                user-facing message (full context is logged
+                dev-side).
 
         Caution: Bound to one project: cross-project envelopes are
             denied, never routed — and a stale expected_revision
             fails instead of merging. The first mutating call per
-            Engine also drains crash survivors (boot replay);
-            queries never do.
+            Engine also builds the crash-survivor boot report
+            (report-only — nothing executes without an explicit
+            resume decision); queries never do.
         """
         envelope = command.get("project_id")
         if envelope != self._project_id:
@@ -453,6 +472,8 @@
             return self._query_apig(name, arguments)
         if name in _LAYER_QUERIES:
             return self._query_layer(name, arguments)
+        if name in _REPLAY_QUERIES:
+            return self.boot_report()
         if name in _WIRED_QUERIES:
             return self._project.snapshot()
         if name in QUERIES or name not in OPERATIONS:
@@ -464,6 +485,25 @@
             # Deferred/batch pumping plus idempotent fetch: admission
             # (and its revision gate) already happened at submit time.
             return self.run(command)
+        if name == "resume_run":
+            if "run_id" not in arguments:
+                raise ProjectError(
+                    "invalid_command",
+                    "resume_run needs a run_id argument.",
+                )
+            return self.resume_survivor(
+                arguments["run_id"],
+                force=bool(arguments.get("force", False)),
+            )
+        if name == "discard_run":
+            if "run_id" not in arguments:
+                raise ProjectError(
+                    "invalid_command",
+                    "discard_run needs a run_id argument.",
+                )
+            return self.discard_survivor(arguments["run_id"])
+        if name == "resume_all_retryable":
+            return self.resume_all_retryable()
         if name in _CRUD_OPERATIONS:
             return self._submit_crud(name, arguments, command)
         if name == "place_cell":
@@ -841,6 +881,18 @@
             }
         run_arguments = dict(arguments)
         run_arguments.pop("expected_revision", None)
+        # REPLAY-SAFE: a kill after this mark reads as an
+        # interruption at the next boot (AMBIGUOUS, counted toward
+        # poison); a kill before it stays RETRYABLE.
+        self._project.append_replay_event(
+            "run_started",
+            request_id,
+            {
+                "run_id": run_id,
+                "content_key": content_key_for(operation, run_arguments),
+                "operation": operation,
+            },
+        )
         return self._run_operation(
             operation,
             run_arguments,
@@ -932,28 +984,121 @@
             "refused": refused,
         }
 
-    def replay_pending(self):
-        """Drain crash-surviving admissions oldest first (boot replay).
+    def boot_report(self):
+        """Report crash survivors without executing anything (boot report).
 
         Survivors are ledger admissions without a run event —
-        typically a kill between admit and drain. Finished runs
-        are never re-executed; unresolvable survivors are skipped
-        loudly in the report.
+        typically a kill between admit and drain. Each carries its
+        taxonomy kind (retryable, ambiguous, poison), quarantine
+        state, and per-run Resume/Discard actions.
 
         Returns:
-            Report with replayed run ids (seq order), their
-                completions, and skipped entries.
+            Report with the session-ended message, the unfinished
+                count, survivors in admit order, quarantined run
+                ids, and unresolved entries.
+
+        Caution: Report-only by construction: nothing executes
+            here — every replay surface needs an explicit resume
+            decision (resume_run, discard_run, resume_all_retryable).
         """
-        return self._pool.replay(
-            self._project.events_since(0), self._resolve_pending
-        )
+        return self._replay.boot()
+
+    def resume_survivor(self, run_id, force=False):
+        """Explicitly resume one crash survivor through its solver.
+
+        Args:
+            run_id: Survivor to resume.
+            force: Required for quarantined (poison) runs; force
+                bypasses quarantine only — the run still executes
+                for real.
+
+        Returns:
+            Executor completion for the run.
+
+        Raises:
+            ExecutionError: unknown_survivor for an id with no
+                unfinished run, already_completed for a finished
+                run, already_decided for a run handled this
+                session, poison_quarantined for a quarantined run
+                resumed without force.
+
+        Caution: This executes the run — the one replay surface
+            that does, and only on this explicit call.
+        """
+        return self._replay.resume(run_id, force=force)
+
+    def discard_survivor(self, run_id):
+        """Explicitly discard one crash survivor, never executing it.
+
+        Args:
+            run_id: Survivor to discard.
+
+        Returns:
+            Discard record with run_id, discarded state, and the
+                run's operation.
+
+        Raises:
+            ExecutionError: unknown_survivor for an id with no
+                unfinished run, already_completed for a finished
+                run, already_decided for a run handled this
+                session.
+        """
+        return self._replay.discard(run_id)
+
+    def resume_all_retryable(self):
+        """Resume every RETRYABLE survivor, oldest first (gated).
+
+        Ambiguous runs need individual review and poison runs need
+        per-run force, so both are skipped loudly — never swept up.
+
+        Returns:
+            Batch with resumed run ids, their completions, and
+                skipped entries (each with run_id, typed code, and
+                user-facing message).
+
+        Raises:
+            ExecutionError: Propagates the first executor failure
+                unchanged — earlier resumes stand, later ones never
+                fire.
+
+        Caution: This executes runs — only the RETRYABLE,
+            non-quarantined survivors, and only on this call.
+        """
+        return self._replay.resume_all_retryable()
+
+    def replay_pending(self):
+        """Resume crash-surviving RETRYABLE admissions, oldest first.
+
+        Explicit-call compat over the gated batch: same survivor
+        set as the boot report, but only RETRYABLE runs execute —
+        ambiguous and poison survivors are skipped loudly in the
+        report instead of re-running.
+
+        Returns:
+            Report with replayed run ids (the resumed set, seq
+                order), their completions, and skipped entries.
+        """
+        batch = self._replay.resume_all_retryable()
+        return {
+            "replayed": batch["resumed"],
+            "completions": batch["completions"],
+            "skipped": batch["skipped"],
+        }
 
     def _replay_once(self):
-        """Drain crash survivors once per Engine (lazy boot replay)."""
+        """Build the crash-survivor boot report once per Engine."""
         if self._replayed:
             return None
         self._replayed = True
-        return self.replay_pending()
+        return self.boot_report()
+
+    def _replay_execute(self, operation, arguments, snapshot_id, request_id,
+                        run_id):
+        """Registered pool execution for one explicit resume."""
+        self._resolve_pending(request_id)
+        return self._pool_execute(
+            operation, arguments, snapshot_id, request_id, run_id
+        )
 
     def _submit_pyexec(self, arguments, command):
         """Admit a python_execute request: gate, then open an approval.
--- rocket-engine.orig/src/interfaces/vocabulary.py
+++ rocket-engine/src/interfaces/vocabulary.py
@@ -11,6 +11,7 @@
         "run_optical", "run_digital_flow", "run_timing", "run_extraction",
         "run_post_layout", "run_em", "run_thermal", "python_execute",
         "run_view_sync", "run_job",
+        "resume_run", "discard_run", "resume_all_retryable",
         "create_project", "write_doc", "delete_doc", "apply_mutations",
         "rewind", "place_cell", "write_settings",
     }
@@ -26,5 +27,6 @@
         "read_settings", "get_resolved_config",
         "get_layer_stackup", "get_layer_rows", "list_layer_presets",
         "save_layer_preset", "delete_layer_preset", "apply_layer_preset",
+        "list_survivors",
     }
 )
--- rocket-engine.orig/src/execution/__init__.py
+++ rocket-engine/src/execution/__init__.py
@@ -36,14 +36,32 @@
     prelude_digest_for,
     resolve_script_path,
 )
+from .replay_safe import (
+    AMBIGUOUS,
+    POISON,
+    POISON_THRESHOLD,
+    REPLAY_SAFE_VERSION,
+    RETRYABLE,
+    ReplaySafe,
+    boot_message,
+    content_key_for,
+    interrupt_counts_from_events,
+    survivors_from_events,
+    user_message_for,
+)
 from .runner import BwrapRunner
 from .service import ExecutionService
 from .worker import CellRunner, CredentialGate, worker_profile
 
 __all__ = [
+    "AMBIGUOUS",
     "BLOCK_RUN_OPERATIONS",
     "BLOCK_SCOPE",
+    "POISON",
+    "POISON_THRESHOLD",
     "PROJECT_SCOPE",
+    "REPLAY_SAFE_VERSION",
+    "RETRYABLE",
     "SUPPORTED_SCOPES",
     "ApigPool",
     "BlockScopeError",
@@ -57,13 +75,17 @@
     "OpDispatcher",
     "PythonExecRunner",
     "PythonExecService",
+    "ReplaySafe",
     "SubmitImmediate",
     "UsageError",
+    "boot_message",
     "build_scope_record",
     "build_worker_source",
     "check_operation_scope",
     "closure_hash",
+    "content_key_for",
     "get_help",
+    "interrupt_counts_from_events",
     "merge_ack_completion",
     "narrow_job_for_block",
     "not_run_verdict",
@@ -80,5 +102,7 @@
     "snapshot_closure",
     "stamp_verdict",
     "stored_completion_from_events",
+    "survivors_from_events",
+    "user_message_for",
     "worker_profile",
 ]
```

## Integrator steps

1. From the repo root on `GREEN-the-tests`:
   `git apply --check -p1 docs/work/REPLAY-SAFE/wiring.patch`, then
   `git apply -p1 docs/work/REPLAY-SAFE/wiring.patch`.
2. Regen the contract + API surface (acceptance step — the patch adds
   the `run_started` envelope, `content_key` on `job_queued`, three
   operations, and the `list_survivors` query):
   `python scripts/contract.py --write` then
   `python scripts/api_spec.py --write`.
3. Run the gates: `python scripts/check_docstrings.py`,
   `python scripts/contract.py --check`,
   `python scripts/api_spec.py --check`, then
   `pytest tests/test_replay_safe.py tests/test_apig_integration.py
   tests/test_contract.py tests/test_api_spec.py tests/test_docstrings.py`
   and finally the full suite.
4. Optional touch-up (stale prose, harmless): the comment at
   `tests/test_apig_integration.py:122-124` ("Consume the lazy boot
   replay…") predates report-only boot; the test passes unchanged, but
   the comment may be reworded to "first submit builds the boot
   report".
5. Sequence with peer lanes before applying: this patch touches
   `composition.py`, `vocabulary.py`, and `execution/__init__.py` —
   re-run `git apply --check` at apply time; on conflict, prefer
   additive merge (all hunks here are additive except the
   `replay_pending`/`_replay_once` behavior change, which this ticket
   owns).

## RED → GREEN evidence (unpatched tree)

- RED: `tests/test_replay_safe.py` failed before the module landed —
  `FileNotFoundError: .../src/execution/replay_safe.py` on all 16
  tests (loader pattern, same as `test_apig_pool.py`).
- GREEN: `16 passed in 0.16s`; `scripts/check_docstrings.py` clean on
  the new module; no line over 100 cols in either new file.
- No-regression (unpatched tree): `test_apig_pool` + `test_apig_submit`
  + `test_docstrings` (full-tree gate, new file included) +
  `test_api_spec`: 26 passed.
- Patched-tree proof (scratch copy under `/tmp`, real tree untouched):
  `test_apig_integration` (7, incl. kill-reboot + batch pump) +
  `test_replay_safe` (16): 23 passed — `replay_pending` compat keeps
  the APIG kill-reboot test green while enforcing the taxonomy.
- Contract drift pre-regen is exactly the new `run_started` envelope
  (+ `content_key` on `job_queued`): the expected acceptance regen,
  not a break. After `--write` on the scratch copy:
  `test_contract` + `test_api_spec` + `test_docstrings`: 19 passed,
  both `--check` modes clean.

All runs used the repo `.venv` interpreter read-only with a
`PYTHONPATH` shim over `src` (no `uv sync`, no `.venv` writes).

## Interactions and deliberate decisions

- `Engine.replay_pending` keeps its `{replayed, completions, skipped}`
  shape but only RETRYABLE runs execute — the APIG kill-reboot test
  (never-started survivor) stays green while ambiguous/poison runs are
  newly protected. `ApigPool.replay` is untouched as the explicit
  pool-level primitive.
- `list_survivors` is a query that also records idempotent
  interruption marks. Pure-read would be cleaner, but the marks ARE
  the outage accounting: a mark-free first read would silently drop
  interruption counts and poison could never trigger. Marks never
  advance the revision and never execute.
- Explicit resume executes directly through the registered pool
  runner, not through the bounded backlog: the bound governs new
  admissions (UI-spam protection), while a resume is a deliberate
  per-run decision that must not be refused by backlog pressure.
- `resume_run` / `discard_run` / `resume_all_retryable` render in the
  generated API reference via the same "declared operation" template
  as `place_cell` (api_spec has no Engine-direct operation branch);
  `list_survivors` renders fully wired via `QUERY_ENGINE_METHODS`.
  No `scripts/*` changes, per APIG precedent.
- Pre-wiring ledgers (no `content_key` on old `job_queued` events)
  resolve keys via `command_for`; unresolvable admissions stay
  keyless (never quarantined, kind by started-ness) and are listed
  under `unresolved` in the boot report.
- The unsupported-operation drain branch completes synchronously with
  `run_failed`, so it takes no `run_started` mark — there is no crash
  window that could strand it.
- `run_job` single/batch paths are unchanged: idempotent fetch still
  answers finished runs, and explicit `run_job` pumping remains the
  caller's deliberate act.


## Integrator note (merged after WIRE-PLACE a2dedad)

The shipped patch drifted on composition.py (wire dispatch + ECS
docstrings) and vocabulary.py (ECS + wire names), so the integrator
applied service.py + execution/__init__.py via `git apply --include`
and hand-merged composition.py (docstrings, import, QUERY_METHODS,
_REPLAY_QUERIES, __init__, submit routing/docstrings, run_started
mark, boot_report/resume/discard/resume_all + replay_pending compat,
_replay_once, _replay_execute) and vocabulary.py with patch-identical
added lines. `wiring.patch` was refreshed to the exact merged bytes
(diff of the four wiring files against a2dedad). Live: 16 replay +
22 APIG (kill-reboot compat green) + neighbors = 170 passed,
api_spec/contract/docstrings fresh, no >100-col additions.
