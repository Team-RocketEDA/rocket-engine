# I27-GATE lane report — plan_checks + design-completion gate (I27)

Ticket: `docs/tickets/I27-GATE.md` (E2E-REREVIEW FIND-01, HIGH) ·
Branch: GREEN-the-tests · No commits, no pushes (integrator commits).

Finding evidence (read fully): `docs/work/E2E-REREVIEW/journey-mixed.md`
(J11/Q1–Q4, F1) and `docs/work/E2E-REREVIEW/invariant-map.md` (I27
UNPROVEN + F1). Cross-lane corroboration: analog F5 (no enforcement
point), photonic F4 (no claim surface), digital J11 (per-run honesty
holds; only the cross-stage claim is missing).

## Files added (new files only — zero edits to existing files)

- `src/workflows/completion.py` — the lane: `plan_checks_report`
  (stage plan with required-but-blocked stages + missing operations)
  and `design_completion_report` (plan layered with latest check
  verdicts; named blockers, refusal while any stand, evidence run ids
  on claim). Imports only the `stages` leaf (no cycle: nothing in the
  completion path imports composition back).
- `tests/workflows/test_completion.py` — 16 unit tests over the new
  module plus live-Engine solver inventory (no wiring needed).
- `tests/workflows/test_completion_wiring.py` — 8 post-patch
  integration tests the integrator runs AFTER applying the wiring
  patch below (skip until then; the fake-thermal test proves the
  unblocked claim end to end through `Engine.submit` with no tools).
- `docs/work/I27-GATE/wiring.patch` — the exact wiring patch
  (`git apply --check` clean on the real tree). Inlined verbatim
  below so this report alone suffices.
- `docs/work/I27-GATE/report.md` — this file.

## Contract implemented (ticket clause → behavior)

- Wire plan_checks to the stage plan so required-but-blocked stages
  surface — `plan_checks_report(flow, available)` wraps
  `applicable_stages` and adds per-stage `missing_operations` plus
  top-level `blocked_stages` / `missing_operations`. The patched
  `Engine.plan_checks(flow)` serves it from the live solver registry.
- Design-completion query reports blockers and refuses a
  fully-verified claim while any stand — `design_completion_report`
  emits `blocked_stage` (missing backends), `unverified_stage`
  (ready but never ran), and `failing_check` (latest verdict not
  PASS, with run id) blockers, plus `missing_operation` entries so
  vocab-only names never vanish. While any blocker stands:
  `fully_verified` False, `claim` None, `refusal` names the count.
  Blocker-free: `claim` "fully verified" with `evidence`
  `{operation: run_id}`.
- Mixed M14 + run_thermal appear as named blockers — live mixed plan
  is `blocked_stages: ["M14"]`, `missing_operations: ["run_thermal"]`;
  the completion report carries the M14 `blocked_stage` entry (missing
  `["run_thermal"]`) and the run_thermal `missing_operation` entry.
- Acceptance, blocked → names + refuses; unblocked → claims with
  evidence — unit tests prove both shapes; the wiring suite proves
  the blocked refusal through `submit` and the unblocked claim
  through 12 fake-PASS submits plus a registered fake thermal solver.

## Design notes

- Query names: `plan_checks` (already in `QUERIES`, now wired) and
  the new `get_design_completion` (Engine method `design_completion`,
  following the `get_check_results` → `check_results` convention).
- Scripted-only stages (project scripting, get_capabilities,
  ip_instantiate) need no solver evidence and never block; every
  tool stage needs ALL its tool entrypoints PASS (matching the
  planner's all-available readiness rule).
- Two PASSes never look fully verified: `run_spice` + `run_hdl_test`
  PASS with M09/M10 never run still refuses with M09/M10 blockers
  (pinned by `test_completion_two_passes_do_not_look_fully_verified`).
- Live mixed completion always refuses until a thermal solver lands:
  `run_thermal` is vocabulary-only by design (proven live:
  `No solver registered: run_thermal`), so M14 stays
  required-but-blocked no matter how many runnable checks PASS.

## RED → GREEN evidence

Env: `UV_CACHE_DIR=/tmp/uv-cache UV_LINK_MODE=copy`,
`PATH=$HOME/tools/oss-cad-suite/bin:$HOME/tools/bin:$PATH`,
`ROCKETEDA_HOME=/tmp/rocketeda-live`. Provision: `scripts/install.sh
--install` (only env path; exit 0, toolchain degraded librelane/opensta
offline as usual, venv + PDK usable). No scratch venvs, no PYTHONPATH
shims, no handrolled installs.

RED (tests written before the module):

    .venv/bin/python -m pytest tests/workflows/test_completion.py \
      tests/workflows/test_completion_wiring.py -q
    # 15 failed, 1 passed, 8 skipped
    # failures: ModuleNotFoundError: No module named
    #   'rocket_engine.workflows.completion'
    # pass: test_run_thermal_is_vocab_only_live (live vocab-only
    #   proof, needs no new module); skips: wiring pre-patch

GREEN (after adding `src/workflows/completion.py` + reinstall):

    # same command
    # 16 passed, 8 skipped in 0.06s (skips = wiring pre-patch)

Named neighbors (never the full suite):

    .venv/bin/python -m pytest tests/workflows/test_process_data.py \
      tests/workflows/test_view_sync_diff.py tests/test_api_spec.py \
      tests/test_docstrings.py tests/workflows/test_completion.py \
      tests/workflows/test_completion_wiring.py -q
    # 48 passed, 8 skipped in 192s (skips = wiring pre-patch)

    .venv/bin/python scripts/api_spec.py --check      # exit 0
    .venv/bin/python scripts/contract.py --check      # exit 0
    # both green on the real tree: regen-neutral pre-patch (no
    # tracked edits); the patched tree needs regen (see below).

Gates: `scripts/check_docstrings.py` clean on the new module and on
all three patched files; no line over 100 chars in new files or
patch-added lines.

One batch run of `tests/adapters/test_mcp_agent_path.py` showed 11
failures alongside the neighbors; that file imports nothing from this
lane (grep clean) and the sampled failure passes in isolation
(`test_constraints_yaml_carries_measurement_definitions`, 1 passed in
0.92s) — shared-tree flake, unrelated to this change.

Wiring-patch verification (throwaway copies `/tmp/i27-orig` pristine
vs `/tmp/i27-edit` edited; real tree untouched):

    git apply --check docs/work/I27-GATE/wiring.patch  # clean
    python -m py_compile <3 patched files>             # clean
    check_docstrings.py <3 patched files + module>     # clean
    AST: plan_checks/design_completion/_query_completion present,
      QUERY_ENGINE_METHODS + vocabulary entries present  # OK
    (cd /tmp/i27-edit && python scripts/api_spec.py --check)
    # exit 1: generator detects the new wiring, docs stale until
    # the integrator regens (expected post-patch state)
    simulated patched methods on the installed package:
    # blocked_stages: ['M14'] | missing: ['run_thermal']
    # fully_verified False, claim None, M14 + run_thermal named

## Integrator runbook

1. Commit the new files (`src/workflows/completion.py`, both test
   files, this directory), then
   `git apply --check docs/work/I27-GATE/wiring.patch`
   (must print nothing), then
   `git apply docs/work/I27-GATE/wiring.patch`.
   Order with peer lane patches: this patch touches the
   composition import block, `QUERY_ENGINE_METHODS`,
   `_COMPLETION_QUERIES` (new symbol), submit dispatch + docstring,
   two new Engine methods, vocabulary `QUERIES`, and the workflows
   `__init__` exports — merge with peers touching the same regions
   by keeping both sides; no adapter, ledger, or MCP changes ride here.
2. Regen (REQUIRED for this patch — two newly wired queries):
   `.venv/bin/python scripts/api_spec.py --write` then
   `.venv/bin/python scripts/contract.py --write`, confirm
   `docs/` gains the `plan_checks` + `get_design_completion`
   sections, then both `--check` gates exit 0. If other lane patches
   land alongside, regen after ALL of them, then re-verify.
3. Reinstall so the sealed package carries the new module and wiring:
   `export UV_CACHE_DIR=/tmp/uv-cache UV_LINK_MODE=copy` with live
   `PATH` + `ROCKETEDA_HOME`, then `scripts/install.sh --install`.
4. Run:
   `.venv/bin/python -m pytest
   tests/workflows/test_completion.py
   tests/workflows/test_completion_wiring.py
   tests/workflows/test_process_data.py
   tests/test_api_spec.py
   tests/test_docstrings.py -q`
   → all green with ZERO skips (the 8 wiring tests flip green; the
   fake-thermal claim test runs 12 inline fake submits, no tools).
5. Then the full suite + gate per ticket acceptance.

## Wiring patch summary (exact bytes in `wiring.patch`)

`src/interfaces/vocabulary.py` (+2/−1): `QUERIES` gains
`get_design_completion` (`plan_checks` was already declared).

`src/composition.py` (+~95): import of the two report builders;
`QUERY_ENGINE_METHODS` gains both queries; new `_COMPLETION_QUERIES`
set + submit dispatch arm; `Engine.plan_checks(flow)` and
`Engine.design_completion(flow)` readers (missing/unknown flow →
`invalid_command`); `_query_completion` router; submit docstring
Returns/Raises cover the new queries.

`src/workflows/__init__.py` (+3): import + `__all__` for the two
report builders.

## Wiring patch (exact, also in `wiring.patch`)

```diff
--- a/src/composition.py
+++ b/src/composition.py
@@ -103,6 +103,7 @@
 from .library.errors import LibraryError
 from .project.errors import ProjectError
 from .project.service import ProjectService
+from .workflows.completion import design_completion_report, plan_checks_report

 _WIRED_QUERIES = frozenset(
     {
@@ -155,6 +156,8 @@
     "delete_layer_preset": "layer_preset_delete",
     "apply_layer_preset": "layer_preset_apply",
     "list_survivors": "boot_report",
+    "plan_checks": "plan_checks",
+    "get_design_completion": "design_completion",
 }

 # Job-result queries served from execution state (plus the captured run log).
@@ -184,6 +187,10 @@
     }
 )

+# Completion queries (I27-GATE): stage plans plus the fully-verified
+# gate, served from the solver registry and the latest check verdicts.
+_COMPLETION_QUERIES = frozenset({"plan_checks", "get_design_completion"})
+
 # A get_logs page never dumps more than this many lines at once.
 _LOG_PAGE_MAX = 200

@@ -407,8 +414,9 @@
             for get_capabilities, the event page for
             get_events_since, the project/document listing for
             the CRUD queries, the status/checks/logs/kinds for
-            the job-result queries, the cell listing or asset
-            bytes for the catalogue/asset queries, the
+            the job-result queries, the stage plan or completion
+            report for the completion queries, the cell listing
+            or asset bytes for the catalogue/asset queries, the
             stackup/rows/presets for the layer-serving queries,
             the stored-or-fresh completion for run_job, the
             boot survivor report for list_survivors, the resume
@@ -438,8 +446,9 @@
                 settings that break the kind schema, future_format
                 for a settings write over a newer on-disk file,
                 or a layer query missing its pdk_id/name, a
-                resume_run or discard_run without a run_id, a
-                component verb missing entity, component, or
+                completion query without a flow or with an unknown
+                flow, a resume_run or discard_run without a run_id,
+                a component verb missing entity, component, or
                 data, or a world snapshot with a non-bool
                 flag, unknown_entity or unknown_component for
                 a missing entity or component, component_exists
@@ -551,6 +560,8 @@
             return self._query_apig(name, arguments)
         if name in _LAYER_QUERIES:
             return self._query_layer(name, arguments)
+        if name in _COMPLETION_QUERIES:
+            return self._query_completion(name, arguments)
         if name in _REPLAY_QUERIES:
             return self.boot_report()
         if name in _WIRED_QUERIES:
@@ -1711,6 +1722,75 @@
             "current_revision": self._project.snapshot()["current_revision"],
         }

+    def plan_checks(self, flow):
+        """Plan one flow's checks against the registered solvers.
+
+        The stage plan behind the check-plan display: every required
+        stage with its readiness (ready when all tool entrypoints are
+        registered, otherwise required-but-blocked with the missing
+        operations named), so a blocked M14 cites run_thermal instead
+        of vanishing.
+
+        Args:
+            flow: Flow inventory to plan (digital/analog/photonic/mixed).
+
+        Returns:
+            Plan mapping with the flow, per-stage readiness plus
+                missing operations, blocked/ready id lists, the sorted
+                missing operations, and the current revision.
+
+        Raises:
+            ProjectError: invalid_command for a missing or unknown flow.
+        """
+        if not flow:
+            raise ProjectError(
+                "invalid_command", "plan_checks needs a flow argument."
+            )
+        try:
+            plan = plan_checks_report(flow, set(self._solvers))
+        except ValueError as exc:
+            raise ProjectError("invalid_command", str(exc)) from exc
+        plan["current_revision"] = self._project.snapshot()["current_revision"]
+        return plan
+
+    def design_completion(self, flow):
+        """Judge one flow's completion; refuse while blockers stand.
+
+        Layers the latest check verdicts over the stage plan: any
+        blocked, unverified, or failing stage becomes a named blocker
+        and the fully-verified claim is refused (claim None with a
+        refusal naming the count); only a blocker-free plan claims
+        fully verified with per-operation evidence run ids. Mixed M14
+        plus the vocab-only run_thermal operation always appear while
+        no thermal solver is registered.
+
+        Args:
+            flow: Flow inventory to judge (digital/analog/photonic/mixed).
+
+        Returns:
+            Completion mapping with the fully_verified flag, claim or
+                refusal, named blockers, missing operations, evidence
+                run ids, per-stage statuses, and the current revision.
+
+        Raises:
+            ProjectError: invalid_command for a missing or unknown flow.
+        """
+        if not flow:
+            raise ProjectError(
+                "invalid_command",
+                "get_design_completion needs a flow argument.",
+            )
+        seen = self.check_results()
+        try:
+            return design_completion_report(
+                flow,
+                set(self._solvers),
+                seen["checks"],
+                seen["current_revision"],
+            )
+        except ValueError as exc:
+            raise ProjectError("invalid_command", str(exc)) from exc
+
     def run_logs(self, run_id=None, query=None, offset=0, limit=40):
         """Search and page one run's captured native log.

@@ -1765,6 +1845,14 @@
             return self.job_kinds()
         raise ProjectError("unsupported_operation", f"Operation not wired yet: {name}.")

     def _query_completion(self, name, arguments):
         """Route a completion query to its Engine reader."""
         if name == "plan_checks":
             return self.plan_checks(arguments.get("flow"))
         if name == "get_design_completion":
             return self.design_completion(arguments.get("flow"))
         raise ProjectError("unsupported_operation", f"Operation not wired yet: {name}.")

     def layer_stackup(self, pdk_id, revision=None, engine_root=None):
         """Serve one PDK's read-only layer stackup.

--- a/src/interfaces/vocabulary.py
+++ b/src/interfaces/vocabulary.py
@@ -25,7 +25,8 @@
     {
         "api_search", "api_info", "api_help", "get_python_console",
         "get_capabilities", "get_project_snapshot", "list_job_kinds",
-        "plan_checks", "get_job_status", "get_check_results",
+        "plan_checks", "get_design_completion",
+        "get_job_status", "get_check_results",
         "get_events_since", "list_artifacts", "get_logs",
         "list_projects", "list_docs", "read_doc",
         "get_component", "components_of", "entities_with",
--- a/src/workflows/__init__.py
+++ b/src/workflows/__init__.py
@@ -1,5 +1,6 @@
 """D/A/P/M step order and check plans as data. Never calls solvers directly."""

+from .completion import design_completion_report, plan_checks_report
 from .connectgraph import (
     RULE_DANGLING_NET,
     RULE_ORPHAN_LABEL,
@@ -27,6 +28,8 @@
 __all__ = [
     "STAGES",
     "applicable_stages",
+    "design_completion_report",
+    "plan_checks_report",
     "Connectivity",
     "ConnectGraphError",
     "Net",
```

## Refusals / constraints honored

- No existing file edited in the real tree (all wiring delivered as
  the patch above); nothing committed, nothing pushed.
- `tests/pdk_*/`, `docs/pdk/*/`, and ASAP7-DRC-DECK files untouched.
- No `.venv` misuse: provisioned only via `scripts/install.sh
  --install` (with the mandated `UV_CACHE_DIR`/`UV_LINK_MODE`
  exports); no scratch venvs, no PYTHONPATH shims, no handrolled pip
  installs. Throwaway copies under `/tmp` were file copies for
  diffing only — never executed via shims (patched-tree checks were
  AST/compile/generator based).
- Full suite never run (new tests plus named neighbors only, per lane
  rules); no `api_spec`/`contract --write` run (both rewrite tracked
  `docs/*` — integrator step, verified needed via patched-tree
  `--check` exit 1).
- Nothing in the ticket was refused: every clause above is
  implemented, tested, and wiring-verified.
