"""Engine ops mixin: Run pumping, batching, replay and solver execution."""

from ..adapters.errors import AdapterError
from ..execution.apig.pool import request_for_run
from ..execution.apig.submit import merge_ack_completion
from ..execution.block_runs_scope import (build_scope_record, narrow_job_for_block, stamp_verdict)
from ..execution.errors import ExecutionError
from ..execution.replay_safe import content_key_for
from ..interfaces.yaml_dump import dump_yaml_text
from ..project.errors import ProjectError
from .gates import check_submit_gates

#: Per-item state rank for the batch worst-state-wins summary —
#: a failed run outranks a cancelled one, which outranks a refused
#: (never attempted) one, which outranks a clean completion.
_STATE_RANK = {"failed": 3, "cancelled": 2, "refused": 1, "completed": 0}


def refuse_smuggled_budget(arguments):
    """Refuse a root-level budget smuggled past the frozen request.

    The budget travels in the frozen `run.request` only, the way
    caller min/max targets never ride the call. Admission
    refuses it fail-fast; execution stamps the frozen value
    itself, so the stored command never carries a root budget.

    Args:
        arguments: Solver arguments to inspect.

    Raises:
        ProjectError: invalid_command for a root-level
            `timeout_s`.
    """
    if "timeout_s" in arguments:
        raise ProjectError(
            "invalid_command",
            "Budget comes from the frozen run.request timeout_s, "
            "not the job root: remove timeout_s.",
        )


def stamp_solver_budget(arguments):
    """Refuse a smuggled root budget; stamp the frozen one.

    The budget travels in the frozen `run.request` (None means
    "adapter default": a spice sim keeps 120s, a LibreLane flow
    keeps its hour). Called at execution: admission already
    refused smuggling, so the stored command carries none and
    the stamp lands exactly once.

    Args:
        arguments: Solver arguments with a normalized `request`.

    Returns:
        Arguments with the frozen budget stamped as the job
            `timeout_s`, or untouched when the request keeps
            the adapter default.

    Raises:
        ProjectError: invalid_command for a root-level
            `timeout_s`.
    """
    refuse_smuggled_budget(arguments)
    budget = (arguments.get("request") or {}).get("timeout_s")
    if budget is None:
        return arguments
    return {**arguments, "timeout_s": budget}


def _item_state(completion):
    """Batch state for one completion: verdict FAIL reads failed."""
    verdict = (completion or {}).get("verdict") or {}
    if verdict.get("status") == "FAIL":
        return "failed"
    return completion.get("state", "completed")


class _RunMixin:
    """Run pumping, batching, replay and solver execution."""

    def _await_shared(self, ack, run_id, waiter):
        """Resolve a coalesced envelope to the shared completion.

        The waiter delivers the owner's completion; a run evicted
        just before attach (or discarded when its drain raised)
        falls back to the stored completion — the run event
        precedes eviction, so fetch cannot miss a finished run.
        """
        completion = None
        if waiter is not None:
            completion = self._coalescer.await_completion(waiter)
        if completion is None:
            completion = self._stored_completion(run_id)
        if completion is None:
            raise ExecutionError(
                "coalesced_run_lost",
                f"Shared run finished with no completion: {run_id}.",
            )
        return merge_ack_completion(ack, completion)

    def _resolve_pending(self, request_id):
        """Admitted (command, ack) for a queued request, registered.

        Reboot path: unknown execution records are registered and
        the run job stashed, so the pool runner finds both.
        """
        stored_command, ack = self._project.command_for(request_id)
        run_id = ack.get("run_id")
        if not self._execution.known(run_id):
            self._execution.dispatch(
                stored_command.get("operation"),
                {"cell": (stored_command.get("arguments") or {}).get("cell")},
                ack.get("snapshot_id", ""),
                run_id=run_id,
            )
        self._run_jobs.setdefault(
            run_id,
            {
                "operation": stored_command.get("operation"),
                "arguments": dict(stored_command.get("arguments") or {}),
                "snapshot_id": ack.get("snapshot_id", ""),
                "request_id": str(request_id),
            },
        )
        return stored_command, ack

    def _pool_execute(self, operation, arguments, snapshot_id, request_id,
                      run_id):
        """Execute one pooled run through its solver, contained."""
        try:
            cancelled = (
                self._execution.status(run_id)["state"] == "cancelled"
            )
        except ExecutionError:
            cancelled = False
        if cancelled:
            verdict = {
                "status": "NOT_RUN",
                "reason": "cancelled before dispatch",
            }
            self._project.append_run_event(
                "run_failed", run_id, operation, verdict, request_id
            )
            return {
                "run_id": run_id,
                "state": "cancelled",
                "operation": operation,
                "reason": "cancelled before dispatch",
                "verdict": verdict,
            }
        if not self._solvers.get(operation):
            self._latest[operation] = run_id
            self._logs[run_id] = (
                f"unsupported_operation: No solver registered: {operation}."
            )
            verdict = self._execution.record_not_run(
                run_id, self._logs[run_id]
            )
            self._project.append_run_event(
                "run_failed", run_id, operation, verdict, request_id
            )
            return {
                "run_id": run_id,
                "state": "completed",
                "verdict": verdict,
                "operation": operation,
            }
        run_arguments = dict(arguments)
        run_arguments.pop("expected_revision", None)
        # REPLAY-SAFE: a kill after this mark reads as an
        # interruption at the next boot (AMBIGUOUS, counted toward
        # poison); a kill before it stays RETRYABLE.
        self._project.append_replay_event(
            "run_started",
            request_id,
            {
                "run_id": run_id,
                "content_key": content_key_for(operation, run_arguments),
                "operation": operation,
            },
        )
        return self._run_operation(
            operation,
            run_arguments,
            snapshot_id,
            request_id,
            run_id=run_id,
            contain=True,
        )

    def _run_batch(self, run_ids, force=False):
        """Pump a batch of admitted runs oldest-listed first.

        Finished runs contribute their stored completion without
        re-executing; runs cancelled before drain contribute a
        cancelled completion without running; the rest are
        admitted to the pool (pool_full refuses loudly past the
        bound), gate-rechecked at drain time (a verdict that moved
        since submit refuses loud), and drained — concurrently
        when the pool fans out. Every listed id lands in exactly
        one of completions/refused, and states/summary roll the
        per-item outcomes up worst-first.

        Args:
            run_ids: Admitted run ids to pump, in order.
            force: Bypass drain-time verdict gates only (hard deps
                still refuse).
        """
        if not isinstance(run_ids, list) or not run_ids:
            raise ProjectError(
                "invalid_command",
                "run_job batch needs a non-empty run_ids list.",
            )
        completions = []
        refused = []
        seen = set()
        admitted = []
        for run_id in run_ids:
            if run_id in seen:
                refused.append({
                    "run_id": run_id,
                    "code": "duplicate_in_batch",
                    "message": f"Run listed twice in one batch: {run_id}.",
                })
                continue
            seen.add(run_id)
            stored = self._stored_completion(run_id)
            if stored is not None:
                completions.append(stored)
                continue
            pending = self._run_jobs.get(run_id)
            if pending is not None:
                request_id = pending["request_id"]
            else:
                request_id = request_for_run(
                    self._project.events_since(0), run_id
                )
            if request_id is None:
                refused.append({
                    "run_id": run_id,
                    "code": "unknown_request",
                    "message": f"No queued request: {run_id}.",
                })
                continue
            stored_command, ack = self._project.command_for(request_id)
            operation = stored_command.get("operation")
            if not self._solvers.get(operation):
                refused.append({
                    "run_id": run_id,
                    "code": "unsupported_operation",
                    "message": f"No solver registered: {operation}.",
                })
                continue
            if self._is_cancelled(run_id):
                completions.append(
                    self._record_cancelled_skip(
                        run_id, operation, stored_command, request_id
                    )
                )
                continue
            try:
                check_submit_gates(
                    operation,
                    stored_command.get("arguments") or {},
                    self._project,
                    force=force,
                )
            except ProjectError as exc:
                refused.append({
                    "run_id": run_id,
                    "code": exc.code,
                    "message": str(exc),
                })
                continue
            self._resolve_pending(request_id)
            try:
                adopted = self._pool.adopt(
                    request_id, run_id, stored_command,
                    ack.get("snapshot_id", ""),
                )
            except ExecutionError as exc:
                refused.append({
                    "run_id": run_id,
                    "code": exc.code,
                    "message": str(exc),
                })
                continue
            if not adopted:
                stored = self._stored_completion(run_id)
                if stored is not None:
                    completions.append(stored)
                    continue
            admitted.append(run_id)
        if admitted:
            completions.extend(self._pool.drain_ids(admitted))
        states = {}
        for completion in completions:
            states[completion.get("run_id")] = _item_state(completion)
        for entry in refused:
            states[entry.get("run_id")] = "refused"
        summary = "completed"
        for state in states.values():
            if _STATE_RANK.get(state, 0) > _STATE_RANK.get(summary, 0):
                summary = state
        return {
            "run_ids": list(run_ids),
            "completions": completions,
            "refused": refused,
            "states": states,
            "summary": summary,
        }

    def _is_cancelled(self, run_id):
        """True when the run was cancelled before this drain."""
        try:
            return self._execution.status(run_id)["state"] == "cancelled"
        except ExecutionError:
            return False

    def _record_cancelled_skip(self, run_id, operation, stored_command,
                               request_id):
        """Record a cancel-before-drain skip as a terminal NOT_RUN."""
        verdict = {
            "status": "NOT_RUN",
            "reason": "cancelled before dispatch",
        }
        self._project.append_run_event(
            "run_failed", run_id, operation, verdict, request_id
        )
        return {
            "run_id": run_id,
            "state": "cancelled",
            "operation": operation,
            "reason": "cancelled before dispatch",
            "verdict": verdict,
        }

    def _replay_once(self):
        """Build the crash-survivor boot report once per Engine."""
        if self._replayed:
            return None
        self._replayed = True
        return self.boot_report()

    def _replay_execute(self, operation, arguments, snapshot_id, request_id,
                        run_id):
        """Registered pool execution for one explicit resume."""
        self._resolve_pending(request_id)
        return self._pool_execute(
            operation, arguments, snapshot_id, request_id, run_id
        )

    def _run_pyexec(self, run_id, request_id):
        """Execute an admitted python_execute run (phase 2).

        Approval lapses propagate as approval errors — approval
        state is never folded into a verdict. Completion carries
        the NOT_RUN verdict (zero exit is never check PASS) and
        appends the run_failed ledger event the NOT_RUN shape
        owns; cancellation returns the cancelled state with no
        ledger event, like every cancelled job.

        Args:
            run_id: Admitted execution id (the submit ack id).
            request_id: Queued request this run discharges.

        Returns:
            Completion mapping with run_id, state, verdict, and
                operation.

        Raises:
            ExecutionError: unknown_run for an id never admitted,
                approval_pending/approval_denied/approval_expired
                when the approval lapses, approval_invalid for
                binding drift.

        Caution: Runs the approved worker now — read the verdict
            (always NOT_RUN) plus the execution record, never the
            exit path.
        """
        record = self._pyexec.run_job(run_id)
        self._latest["python_execute"] = run_id
        log = record.get("stdout", "")
        if record.get("stderr"):
            log += "\n--- stderr ---\n" + record["stderr"]
        self._logs[run_id] = log
        if record["state"] == "cancelled":
            return {
                "run_id": run_id,
                "state": "cancelled",
                "verdict": record["verdict"],
                "operation": "python_execute",
            }
        self._project.append_run_event(
            "run_failed", run_id, "python_execute", record["verdict"],
            request_id,
        )
        return {
            "run_id": run_id,
            "state": "completed",
            "verdict": record["verdict"],
            "operation": "python_execute",
        }

    def _run_operation(self, name, arguments, snapshot_id, request_id, run_id=None,
                       contain=False, block_scope=None):
        """Select the solver, run it, judge the verdict, log completion."""
        from ..composition import _LOCATION_KEYS  # deferred: breaks the ops<->composition cycle
        solvers = self._solvers.get(name) or {}
        if not solvers:
            raise ProjectError(
                "unsupported_operation", f"No solver registered: {name}."
            )
        arguments = stamp_solver_budget(dict(arguments))
        try:
            adapter = self._select_solver(name, arguments)
        except ProjectError as exc:
            if not contain:
                raise
            self._latest[name] = run_id
            self._logs[run_id] = f"{exc.code}: {exc}"
            verdict = self._execution.record_not_run(run_id, f"{exc.code}: {exc}")
            stored_scope = self._run_jobs.get(run_id, {}).get("block_scope")
            if stored_scope is not None:
                verdict = stamp_verdict(verdict, stored_scope["provenance"])
                self._execution.mark_completed(run_id, verdict)
            self._project.append_run_event(
                "run_failed", run_id, name, verdict, request_id
            )
            return {
                "run_id": run_id,
                "state": "completed",
                "verdict": verdict,
                "operation": name,
            }
        if run_id is None:
            issued = self._execution.dispatch(
                name, {"cell": arguments.get("cell")}, snapshot_id
            )
            run_id = issued["run_id"]
        else:
            # Reuses the submit-time record: unknown ids fail as unknown_run.
            self._execution.status(run_id)
        self._execution.mark_running(run_id)
        self._latest[name] = run_id
        scope_record = block_scope
        if scope_record is None:
            scope_record = self._run_jobs.get(run_id, {}).get("block_scope")
        elif "provenance" not in scope_record:
            # Direct runs admit the closure without a run_id; bind it now.
            scope_record = build_scope_record(
                run_id=run_id,
                revision=self._project.snapshot()["current_revision"],
                block_id=scope_record["block_id"],
                deck=arguments.get("deck"),
                closure=scope_record["closure"],
            )
        if scope_record is not None:
            arguments = narrow_job_for_block(arguments, scope_record["closure"])
        try:
            adapter.preflight({"operation": name, **arguments})
            native = adapter.execute({"operation": name, **arguments})
            result = adapter.parse(native)
        except AdapterError as exc:
            self._logs[run_id] = f"{exc.code}: {exc}"
            verdict = self._execution.record_not_run(run_id, f"{exc.code}: {exc}")
            if scope_record is not None:
                verdict = stamp_verdict(verdict, scope_record["provenance"])
                self._execution.mark_completed(run_id, verdict)
            self._project.append_run_event(
                "run_failed", run_id, name, verdict, request_id
            )
            return {
                "run_id": run_id,
                "state": "completed",
                "verdict": verdict,
                "operation": name,
            }
        except Exception as exc:
            # A solver bug in a queued job is NOT_RUN with a reason,
            # never a crash and never a verdict. Direct runs re-raise.
            if not contain:
                raise
            self._logs[run_id] = f"internal_error: {exc!r}"
            verdict = self._execution.record_not_run(run_id, f"internal_error: {exc}")
            if scope_record is not None:
                verdict = stamp_verdict(verdict, scope_record["provenance"])
                self._execution.mark_completed(run_id, verdict)
            self._project.append_run_event(
                "run_failed", run_id, name, verdict, request_id
            )
            return {
                "run_id": run_id,
                "state": "completed",
                "verdict": verdict,
                "operation": name,
            }
        self._logs[run_id] = native.get("log") or "\n".join(
            part for part in (native.get("stdout"), native.get("stderr")) if part
        )
        self._datasets[run_id] = list(native.get("waveforms") or [])
        self._spectra[run_id] = list(result.get("spectra") or [])
        # Solver convention (see ToolAdapter.parse): violations carry
        # rule/severity/message plus flat location keys, nested here.
        findings = []
        for violation in result.get("violations", []):
            location = {}
            for source, dest in _LOCATION_KEYS:
                if violation.get(source) is not None:
                    location[dest] = violation[source]
            findings.append(
                {
                    "severity": violation.get("severity", "error"),
                    "rule": violation["rule"],
                    "message": violation.get("message", violation["rule"]),
                    "location": location,
                }
            )
        findings_text = dump_yaml_text({"findings": findings})
        verdict = self._execution.evaluate(
            run_id, native.get("exit_code", 0), findings_text
        )
        # Keep measured values on PASS too: a verdict without numbers can't be reviewed.
        if result.get("measurements") is not None:
            verdict = dict(verdict, measurements=result["measurements"])
            self._execution.mark_completed(run_id, verdict)
        # Post-layout evidence rides the same way: the pre/post delta
        # table plus the extraction/schematic provenance are small and
        # reviewable (raw waveform samples stay adapter-level so the
        # ledger never carries bulk vectors).
        if result.get("comparison") is not None:
            verdict = dict(verdict, comparison=result["comparison"])
            self._execution.mark_completed(run_id, verdict)
        if result.get("provenance") is not None:
            verdict = dict(verdict, provenance=result["provenance"])
            self._execution.mark_completed(run_id, verdict)
        if scope_record is not None:
            verdict = stamp_verdict(verdict, scope_record["provenance"])
            self._execution.mark_completed(run_id, verdict)
        if (verdict or {}).get("status") == "NOT_RUN":
            outcome = "run_failed"
        else:
            outcome = "run_completed"
        self._project.append_run_event(
            outcome, run_id, name, verdict, request_id,
            findings=findings, log=self._logs.get(run_id, ""),
        )
        return {
            "run_id": run_id,
            "state": "completed",
            "verdict": verdict,
            "operation": name,
        }
