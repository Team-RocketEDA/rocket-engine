# CONSOLE-ROUTE lane report — console tier-2 mutations via admission

Ticket: `docs/tickets/CONSOLE-ROUTE.md` (+ console-routing field notes in
`docs/tickets/PYTHON-EXEC.md`) · Branch: GREEN-the-tests · No commits,
no pushes (integrator commits).

## Files added (new files only — zero edits to existing files)

- `src/execution/console_route.py` — the lane: tier classifier
  (`tier_for`/`is_tier2`, 20 tier-2 verbs), host-side `ConsoleNamespace`
  (one admission-routed wrapper per verb, Engine-identical call shape),
  worker-side `ConsoleTools` (one recording wrapper per verb in the
  prelude shape + generic fallback), admission envelopes
  (`admission_envelope`), replay stamping (`stamp_tier2_call`),
  effects reporting (`collect_run_ids`, `build_effects_report`,
  `report_completions`), and shared ENGINE-ECS addressing wrappers
  (`entity_doc_path`, `parse_address`, `format_address`). Imports:
  stdlib + ruamel + the `engine_ecs_store` leaf + `LibraryError` /
  `ProjectError` / `ExecutionError` (no cycle: nothing imported
  imports execution back).
- `tests/execution/test_console_route.py` — 123 unit tests: tiers,
  envelopes, stamping, namespace admission (gate/replay/conflict)
  over the real `ProjectService`, cell placement, zero-direct-write
  proof (source scan + delegation shape), ECS/wire exposure and
  pre-patch honesty, shared addressing parity, recorder parity,
  effects report-never-rereport, and the acceptance flow.
- `tests/execution/test_console_route_wiring.py` — 8 post-patch
  integration tests the integrator runs AFTER applying the wiring
  patch below (skip until then; 8/8 green on the patched throwaway
  copy except the ECS-live probe, which awaits the ENGINE-ECS peer
  patch by design).
- `docs/work/CONSOLE-ROUTE/wiring.patch` — the exact wiring patch
  (`git diff --no-index` bytes; `git apply --check` clean on the
  real tree). Inlined verbatim below so this report alone suffices.
- `docs/work/CONSOLE-ROUTE/report.md` — this file.

## Contract implemented (ticket clause → behavior)

- Tier-2 routes through admission — `ConsoleNamespace` calls the
  matching `ProjectService` verb with the Engine call shape (verb
  args, envelope id + identity text, revision by keyword):
  `expected_revision` gating, one actor-attributed ledger record
  per accepted mutation, idempotent envelope ids. Proven over the
  real service for doc writes, batch, cell placement, project
  siblings; ECS/wire delegate identically once peer-wired.
- Identical verbs to CRUD/MCP, shared substrate — wrapper names
  are exactly the Engine operation names (doc/cell/ECS/wire/
  project families); addressing reuses `engine_ecs_store`
  functions (no second implementation — parity asserted); wire
  call shapes mirror the WIRE-PLACE Engine dispatch.
- Console namespace exposes ECS/wire verbs — both namespaces
  carry explicit wrappers for all 13 ECS/wire verbs (thin
  wrappers naming them, asserted callable); the worker recorder
  additionally keeps the generic fallback for every other op.
- Zero direct doc-store writes from tier-2 paths — the module
  names no private doc-store writer (source scan test pins the
  full token list), and a recording stand-in proves each wrapper
  makes exactly one public admission call with the envelope
  plumbed.
- Effects report-with-run_ids, never re-execute —
  `collect_run_ids` lifts child ids off replayed results,
  records carry `effects: {run_ids, replayed}`, and
  `report_completions` reads stored completions back by id
  (duplicates/unknowns refused per entry); double reports read
  identical values with zero ledger touch.
- Acceptance flow — terminal session (cell + doc write) bumps
  the head per mutation with actor + revision on each record,
  rewind covers the session, and a fresh service on the same
  root regenerates identically (unit + wiring tests).

## Design notes

- Tier-2 is every project-state mutation: the ticket's cell /
  wire / doc families plus the three sibling project mutations
  (`create_project`, `rewind`, `write_settings`), which share
  the identical admission path. Reads, solver runs, and unknown
  names stay tier-1 (dispatch and the vocabulary gate own those).
- Replay stamps what the cell left open
  (`stamp_tier2_call`): tier-2 calls gain the live head plus a
  fresh envelope id; caller-bound revisions win verbatim (stale
  bindings fail as `revision_conflict`, recorded per-op, never
  raised). Engines without a snapshot (older fakes) replay
  unstamped — pre-patch behavior, unchanged.
- Pre-patch honesty: ECS/wire wrappers raise
  `unsupported_operation` naming the missing peer wiring when
  the verb is absent from the project port; refused calls write
  nothing and advance nothing. The wiring tests flip to live
  assertions once the peer verbs exist.
- Finding (no tracked edits — reported, not fixed): a failed
  ruamel `YAML(typ="safe").dump` poisons that dumper instance —
  every later dump emits empty text, which would collapse
  distinct admissions onto one identity. This module dumps with
  a fresh instance per call (regression test pinned); the
  long-lived Engine/ProjectService dumpers share the exposure
  and deserve a follow-up.
- `python_execute` replay is untouched by the patch (verbatim
  caller binding stands); it can adopt `build_effects_report`
  in a follow-up for one shared effects constructor.

## RED → GREEN evidence

Toolchain: `/tmp/wireplace-venv` scratch interpreter (pytest +
ruamel, read-only reuse — not the repo `.venv`, no `uv sync`)
with a `rocket_engine -> src` symlink shim at
`/tmp/console_rocket` (patched-copy runs shim `/tmp/cr-shim`
at `/tmp/cr-edit/src`). Repo `.venv` never executed.

RED (tests written before the module):

    PYTHONPATH=/tmp/console_rocket /tmp/wireplace-venv/bin/python \
      -m pytest tests/execution/test_console_route.py \
      tests/execution/test_console_route_wiring.py -q
    # ERROR: ModuleNotFoundError:
    #   No module named 'rocket_engine.execution.console_route'
    PYTHONPATH=/tmp/console_rocket /tmp/wireplace-venv/bin/python \
      -m pytest tests/execution/test_console_route_wiring.py -q
    # 8 skipped (pre-patch wiring)

GREEN (after adding `src/execution/console_route.py`; one
module fix along the way — fresh YAML dumper per envelope
after the suite caught cross-test dumper poisoning — plus one
test fix asserting the Engine positional call shape):

    # same two-file command
    # 123 passed, 8 skipped in 0.30s (skips = wiring pre-patch)

Patched throwaway copy (`/tmp/cr-edit`, new files + patch):

    # same two-file command against /tmp/cr-shim
    # 130 passed, 1 skipped in 0.28s (the skip awaits the
    # ENGINE-ECS peer verb, by design)

Named neighbors (never the full suite):

    # unpatched tree: console + dispatch + execution-service +
    #   stdio-console + docstrings → 72 passed
    # unpatched tree: project-service + api_spec + contract +
    #   check-contract + apig-catalog → 40 passed, 1 skipped
    #   (pre-existing environmental skip)
    # patched copy: the 72-set + python_exec modes → 104 passed

Gates: `scripts/check_docstrings.py` on the new module clean;
on the patched `__init__.py`/`stdio_console.py` clean; no line
over 100 chars in new files or patch-added lines; patched copy
`scripts/api_spec.py --check` and `scripts/contract.py --check`
both exit 0 (no regen needed — the patch adds no
Engine/ProjectService verbs, only execution exports and replay
behavior).

## Integrator runbook

1. Commit the new files (`src/execution/console_route.py`,
   both test files, this directory), then
   `git apply --check docs/work/CONSOLE-ROUTE/wiring.patch`
   (must print nothing), then
   `git apply docs/work/CONSOLE-ROUTE/wiring.patch`.
   Order with the ENGINE-ECS / WIRE-PLACE patches does not
   matter: pre-peer, ECS/wire calls refuse loudly; post-peer,
   they admit. No vocabulary, composition, MCP, or api_spec
   changes ride here.
2. Regen is NOT needed for this patch (verified: both
   `--check` gates exit 0 on the patched copy — no new
   handlers). If other lane patches land alongside, regen
   after ALL of them per their runbooks, then re-verify.
3. Reinstall so `rocket_engine.execution.console_route`
   resolves without the shim, then run:
   `.venv/bin/python -m pytest
   tests/execution/test_console_route.py
   tests/execution/test_console_route_wiring.py
   tests/execution/test_console.py
   tests/execution/test_dispatch.py
   tests/adapters/test_stdio_console.py
   tests/test_docstrings.py -q`
   → all green (wiring ECS-live probe flips green once the
   ENGINE-ECS patch lands).

Evidence: built the patch between two throwaway tree copies
(`/tmp/cr-orig` pristine, `/tmp/cr-edit` edited; real tree
untouched), ran the suites above via the `/tmp/cr-shim`
symlink + scratch interpreter, and dry-ran `git apply
--check` on the real tree. Scratch copies left under `/tmp`
for review, out of the deliverable.

## Wiring patch summary (exact bytes in `wiring.patch`)

`src/execution/__init__.py` (+37): import + `__all__` for the
console-route surface (namespaces, tier helpers, envelope,
stamp, recorder builder, effects reporters, addressing).

`src/adapters/stdio_console.py` (+20/−3): import the replay
helpers; `_replay` reads the live head once (missing snapshot
replays unstamped, pre-patch behavior) and stamps tier-2 calls
with head + request id before shared dispatch; both terminal
record shapes gain `effects: {run_ids, replayed}`.

## Wiring patch (exact, also in `wiring.patch`)

```diff
diff --git a/src/execution/__init__.py b/src/execution/__init__.py
index b8a5b48..3d0bc3f 100644
--- a/src/execution/__init__.py
+++ b/src/execution/__init__.py
@@ -24,6 +24,23 @@ from .block_runs_scope import (
     stamp_verdict,
 )
 from .console import ConsoleSession, get_help
+from .console_route import (
+    CONSOLE_TOOL_VERBS,
+    TIER_2_OPERATIONS,
+    ConsoleNamespace,
+    ConsoleTools,
+    admission_envelope,
+    build_effects_report,
+    collect_run_ids,
+    entity_doc_path,
+    format_address,
+    is_tier2,
+    parse_address,
+    report_completions,
+    stamp_tier2_call,
+    tier_for,
+    tool_call,
+)
 from .dispatch import OpDispatcher, parse_op_call, parse_op_tokens
 from .errors import ExecutionError, UsageError
 from .python_exec import (
@@ -49,7 +66,10 @@ __all__ = [
     "BlockScopeError",
     "BwrapRunner",
     "CellRunner",
+    "CONSOLE_TOOL_VERBS",
+    "ConsoleNamespace",
     "ConsoleSession",
+    "ConsoleTools",
     "CredentialGate",
     "ExecutionError",
     "ExecutionService",
@@ -58,19 +78,28 @@ __all__ = [
     "PythonExecRunner",
     "PythonExecService",
     "SubmitImmediate",
+    "TIER_2_OPERATIONS",
     "UsageError",
+    "admission_envelope",
     "build_scope_record",
+    "build_effects_report",
     "build_worker_source",
     "check_operation_scope",
     "closure_hash",
+    "collect_run_ids",
+    "entity_doc_path",
+    "format_address",
     "get_help",
+    "is_tier2",
     "merge_ack_completion",
     "narrow_job_for_block",
     "not_run_verdict",
+    "parse_address",
     "parse_exception",
     "parse_op_call",
     "parse_op_tokens",
     "prelude_digest_for",
+    "report_completions",
     "resolve_script_path",
     "parse_target",
     "pending_from_events",
@@ -78,7 +107,10 @@ __all__ = [
     "resolve_block",
     "scope_provenance",
     "snapshot_closure",
+    "stamp_tier2_call",
     "stamp_verdict",
     "stored_completion_from_events",
+    "tier_for",
+    "tool_call",
     "worker_profile",
 ]
diff --git a/src/adapters/stdio_console.py b/src/adapters/stdio_console.py
index 5b87622..57e5c31 100644
--- a/src/adapters/stdio_console.py
+++ b/src/adapters/stdio_console.py
@@ -49,6 +49,11 @@ from ruamel.yaml import YAML
 
 from ..composition import Engine
 from ..execution.console import ConsoleSession
+from ..execution.console_route import (
+    collect_run_ids,
+    is_tier2,
+    stamp_tier2_call,
+)
 from ..execution.dispatch import OpDispatcher
 from ..execution.errors import ExecutionError, UsageError
 from ..execution.worker import CellRunner
@@ -612,6 +617,7 @@ class StdioConsole:
                 "op_results": [],
                 "ops_ok": True,
                 "ops_skipped": 0,
+                "effects": {"run_ids": [], "replayed": True},
                 "cli_script": [],
                 "artifacts": [],
                 "rejected_artifacts": [],
@@ -637,6 +643,8 @@ class StdioConsole:
             "op_results": op_results,
             "ops_ok": all(item["ok"] for item in op_results),
             "ops_skipped": skipped,
+            "effects": {"run_ids": collect_run_ids(op_results),
+                        "replayed": True},
             "cli_script": [
                 format_op_call(op["operation"], op["arguments"]) for op in ops
             ],
@@ -699,14 +707,25 @@ class StdioConsole:
 
     def _replay(self, ops):
         replayed = []
+        try:
+            head = self._engine.snapshot()["current_revision"]
+        except Exception:
+            head = None
         for op in ops:
+            operation = op["operation"]
+            arguments = op["arguments"]
+            request_id = None
+            if head is not None and is_tier2(operation):
+                arguments, request_id = stamp_tier2_call(
+                    operation, arguments, head
+                )
             try:
                 payload = self._dispatch.execute(
-                    op["operation"], op["arguments"]
+                    operation, arguments, request_id=request_id
                 )
             except Exception as exc:  # per-op truth: record, never raise
                 replayed.append({
-                    "operation": op["operation"],
+                    "operation": operation,
                     "ok": False,
                     "error": {
                         "code": getattr(exc, "code", None)
@@ -716,7 +735,7 @@ class StdioConsole:
                 })
                 continue
             replayed.append({
-                "operation": op["operation"],
+                "operation": operation,
                 "ok": True,
                 "result": json.loads(json.dumps(payload, default=str)),
             })
```

## Refusals / constraints honored

- No existing file edited in the real tree (all wiring
  delivered as the patch above); nothing committed, nothing
  pushed.
- `tests/pdk_*/`, `docs/pdk/*/`, and ASAP7-DRC-DECK files
  untouched; ENGINE-ECS / WIRE-PLACE modules read read-only,
  never edited.
- No `.venv` use, no `uv sync` (scratch interpreter +
  `PYTHONPATH` shims only).
- Full suite never run (new tests plus named neighbors only,
  per lane rules).
- Nothing in the ticket was refused: every clause above is
  implemented, tested, and wiring-verified.

## Integrator note (merged after fix b72c7cd on REPLAY-SAFE 65bd9a4)

The shipped patch drifted on src/execution/__init__.py (REPLAY-SAFE
exports), so the integrator applied the stdio_console.py hunks via
`git apply --include` and hand-merged the console_route import +
__all__ entries with patch-identical names. `wiring.patch` was
refreshed to the exact merged bytes (diff of the two wiring files).
Regen is a no-op for this lane (no new Engine/ProjectService verbs).
Live: 118 passed + 13 skipped-by-design (the unwired-verb refusal
test skips per verb once the ECS/wire peer patches land); neighbor
gate 269 passed + 13 skipped.

Neighbor finding fixed alongside: REPLAY-SAFE's mandated run_started
marks broke 3 tests/project/test_ledger_durable.py closed-universe
event assertions (missed by that lane's gate); updated
intent-preserving (sequences extended, linkage strengthened) in
commit b72c7cd, verified green on both sides of the lane merge.
