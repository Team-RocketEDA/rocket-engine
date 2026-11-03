"""Wave-3 deferred runtime seam (EngineRuntime integration).

Engine owns one EngineRuntime bound to the solver lane: deferred
submits acknowledge promptly with a run id and no verdict, the
pump executes through the ledger-admitting runner, and the
terminal completion merges back with merge_ack_completion. The
synchronous submit path is untouched — deferred runs correlate
with ledger admissions through the shared request id.
"""

from ..execution.apig.submit import merge_ack_completion
from ..interfaces.yaml_dump import dump_yaml_text
from ..project.errors import ProjectError


class _DeferredMixin:
    """Deferred prompt-ack runtime surface (Wave-3 EngineRuntime)."""

    def _deferred_runner(
            self, operation, arguments, snapshot_id, request_id,
            run_id):
        """Execute one deferred run through ledger admission.

        Admission gates exactly like a synchronous submit
        (targets, request knobs, confinement, budget, verdict
        gates, block scope); the ledger ack run id executes while
        the runtime tracks its own run id. Replay hits return the
        stored completion without re-executing.

        Args:
            operation: Cataloged solver operation name.
            arguments: Operation arguments mapping.
            snapshot_id: Evidence snapshot the run pins.
            request_id: Client envelope id.
            run_id: Runtime run id tracking this run.

        Returns:
            Terminal completion for the run.
        """
        from .gates import check_submit_gates

        args = dict(arguments or {})
        args = self._apply_targets(operation, args)
        args = self._apply_run_request(args)
        if operation == "run_spice":
            args = self.confine_spice_arguments(
                args, self._project_dir)
        from .runs import refuse_smuggled_budget

        refuse_smuggled_budget(args)
        check_submit_gates(operation, args, self._project)
        scope_request = self._admit_block_scope(operation, args)
        command_text = dump_yaml_text(
            {"operation": operation, "arguments": args})
        ack = self._pool.submit_request(
            command_text, str(request_id),
            expected_revision=args.get("expected_revision"),
        )
        self._deferred.apply_edit()
        ledger_id = ack["run_id"]
        stored = self._stored_completion(ledger_id)
        if stored is not None:
            self._pool.discard(ledger_id)
            return {
                "run_id": ledger_id, "state": stored["state"],
                "verdict": stored.get("verdict"),
                "operation": stored.get("operation"),
            }
        self._run_jobs.setdefault(
            ledger_id,
            {
                "operation": operation,
                "arguments": args,
                "snapshot_id": ack["snapshot_id"],
                "request_id": str(request_id),
            },
        )
        if scope_request is not None:
            from ..execution.block_runs_scope import (
                build_scope_record,
            )

            pending = self._run_jobs[ledger_id]
            if "block_scope" not in pending:
                pending["block_scope"] = build_scope_record(
                    run_id=ledger_id,
                    revision=self._project.snapshot()[
                        "current_revision"],
                    block_id=scope_request["block_id"],
                    deck=args.get("deck"),
                    closure=scope_request["closure"],
                )
        if not self._execution.known(ledger_id):
            self._execution.dispatch(
                operation, {"cell": args.get("cell")},
                ack["snapshot_id"], run_id=ledger_id,
            )
        try:
            completion = self._pool_execute(
                operation, args, ack["snapshot_id"],
                str(request_id), ledger_id)
        finally:
            self._pool.discard(ledger_id)
        self._maybe_record_evidence(operation, completion, args)
        return completion

    def deferred_submit(self, operation, arguments, request_id=None):
        """Admit one deferred run with a prompt acknowledgement.

        The receipt carries the run id with no verdict; pump (or
        auto-dispatch) executes, then merge the terminal
        completion back with merge_ack_completion.

        Args:
            operation: Cataloged solver operation name.
            arguments: Operation arguments mapping.
            request_id: Client envelope id; minted when omitted.

        Returns:
            DeferredHandle watching the admitted run.

        Raises:
            ProjectError: unsupported_operation for an unknown
                name; the runtime refusal code otherwise.
        """
        from ..execution.errors import ExecutionError
        from ..interfaces.vocabulary import OPERATIONS

        if operation not in OPERATIONS:
            raise ProjectError(
                "unsupported_operation",
                f"Unsupported operation: {operation}.",
            )
        import uuid as _uuid

        try:
            handle = self._deferred.submit(
                operation, dict(arguments or {}),
                request_id=str(request_id or _uuid.uuid4().hex),
            )
        except ExecutionError as exc:
            raise ProjectError(exc.code, str(exc)) from exc
        self._deferred_receipts[handle.run_id] = dict(
            handle.receipt)
        return handle

    def deferred_pump(self, limit=None):
        """Dispatch deferred runs oldest first through the runner.

        Args:
            limit: Maximum entries to drain; the whole backlog
                when omitted.

        Returns:
            Completions in dispatch order.
        """
        return self._deferred.pump(limit=limit)

    def deferred_status(self, run_id):
        """Read one deferred run's state, verdict, and operation.

        Args:
            run_id: Deferred run id to inspect.

        Returns:
            Status with run_id, operation, state, and verdict
                once judged.
        """
        from ..execution.errors import ExecutionError

        try:
            return self._deferred.status(run_id)
        except ExecutionError as exc:
            raise ProjectError(exc.code, str(exc)) from exc

    def deferred_wait(self, run_id, timeout=None):
        """Block until one deferred run reaches a terminal state.

        Args:
            run_id: Deferred run id to wait for.
            timeout: Maximum seconds to wait; waits with the run
                when omitted.

        Returns:
            Terminal completion for the run.
        """
        from ..execution.errors import ExecutionError

        try:
            return self._deferred.wait_for(
                run_id, timeout=timeout)
        except ExecutionError as exc:
            raise ProjectError(exc.code, str(exc)) from exc

    def runtime_events(self, cursor=0):
        """Read ordered deferred lifecycle events after a cursor.

        Args:
            cursor: Opaque position from a previous read; 0
                replays the retained log.

        Returns:
            Events appended after the cursor, oldest first,
                plus the current cursor.
        """
        from ..execution.errors import ExecutionError

        try:
            return self._deferred.watch(cursor)
        except ExecutionError as exc:
            raise ProjectError(exc.code, str(exc)) from exc

    def runtime_cancel(self, run_id, actor=None):
        """Cancel one queued or running deferred run.

        Args:
            run_id: Deferred run id to cancel.
            actor: Attribution for the lifecycle event.

        Returns:
            Outcome with run_id, state, actor, and verdict
                when judged.
        """
        from ..execution.errors import ExecutionError

        try:
            return self._deferred.cancel(
                run_id,
                actor=actor if actor is not None else self._actor,
            )
        except ExecutionError as exc:
            raise ProjectError(exc.code, str(exc)) from exc

    def replay_pending(self):
        """Resume crash-surviving RETRYABLE admissions, oldest first.

        Explicit-call compat over the gated batch: same survivor
        set as the boot report, but only RETRYABLE runs execute —
        ambiguous and poison survivors are skipped loudly in the
        report instead of re-running.

        Returns:
            Report with replayed run ids (the resumed set, seq
                order), their completions, and skipped entries.
        """
        batch = self._replay.resume_all_retryable()
        return {
            "replayed": batch["resumed"],
            "completions": batch["completions"],
            "skipped": batch["skipped"],
        }

    def deferred_fetch(self, run_id):
        """Fetch one deferred run's merged ack-plus-completion.

        Args:
            run_id: Deferred run id to fetch.

        Returns:
            Merged receipt-plus-completion; verdict present once
                the run finished.

        Raises:
            ProjectError: unknown_run for an untracked id.
        """
        from ..execution.errors import ExecutionError

        try:
            receipt = self._deferred_receipts[run_id]
        except (KeyError, AttributeError):
            raise ProjectError(
                "unknown_run", f"Unknown run: {run_id}.") from None
        try:
            completion = self._deferred.wait_for(run_id, timeout=0)
        except TimeoutError:
            return dict(receipt)
        except ExecutionError as exc:
            raise ProjectError(exc.code, str(exc)) from exc
        return merge_ack_completion(receipt, completion)
