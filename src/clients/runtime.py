"""Shared client over one engine's integrated runtime (CLIENTS).

Every transport (MCP, HTTP, IPC, stdio console, Python) serves the
same EngineRuntime through this one client instead of inventing
its own queue. All run control delegates to the engine's public
deferred surface — the client never constructs a second runtime,
never reimplements admission, and never synthesizes verdicts.

Caution: The push-listener handle (`add_listener`) stays behind
the runtime object the servers bind explicitly; the engine
exposes no public listener accessor yet (see the API-V1-CLIENTS
verdict carry). Watch polling and cursor recovery ride the
public `runtime_events` surface instead.
"""

from ..project.errors import ProjectError


class RuntimeClient:
    """One engine's deferred runs, served to every client alike.

    Args:
        engine: Engine whose integrated runtime this client
            serves (submit, deferred submit/pump/wait/fetch,
            cancel, watch, survivors).
    """

    def __init__(self, engine):
        self._engine = engine
        self._paused = False

    @property
    def engine(self):
        """Engine this client serves.

        Returns:
            The bound engine.
        """
        return self._engine

    @property
    def paused(self):
        """Client-side capacity signal from the last refusal.

        True after a deferred admission refused with admitted
        False (retryable saturation); False again once a pump,
        cancel, or admitted submit frees the lane.

        Returns:
            Whether the client believes admission is paused.
        """
        return self._paused

    def submit(self, project_id, operation, arguments, request_id=None):
        """Submit one call inline through the engine.

        Args:
            project_id: Project the call runs against.
            operation: Cataloged operation or query name.
            arguments: Operation arguments mapping.
            request_id: Client envelope id; minted when omitted.

        Returns:
            Engine result for the call (ack, completion, or data).
        """
        command = {
            "project_id": project_id,
            "operation": operation,
            "arguments": dict(arguments),
        }
        if request_id is not None:
            command["request_id"] = request_id
        return self._engine.submit(command)

    def deferred_submit(self, operation, arguments, request_id=None):
        """Admit one deferred run with a prompt acknowledgement.

        Args:
            operation: Cataloged operation name.
            arguments: Operation arguments mapping.
            request_id: Client envelope id; minted when omitted.

        Returns:
            Deferred handle watching the admitted run; the
            receipt carries no verdict. A refused handle carries
            admitted False and marks this client paused.
        """
        handle = self._engine.deferred_submit(
            operation, dict(arguments or {}), request_id=request_id)
        receipt = handle.receipt
        if receipt.get("admitted") is False:
            self._paused = True
        else:
            self._paused = False
        return handle

    def pump(self, limit=None):
        """Dispatch queued deferred runs oldest first.

        Args:
            limit: Maximum entries to drain; the whole backlog
                when omitted.

        Returns:
            Completions in dispatch order. A drained lane clears
                this client's paused signal.
        """
        completions = self._engine.deferred_pump(limit=limit)
        if completions:
            self._paused = False
        return completions

    def wait_for(self, run_id, timeout=None):
        """Block until one deferred run reaches a terminal state.

        Args:
            run_id: Deferred run id to wait for.
            timeout: Maximum seconds to wait; waits with the run
                when omitted.

        Returns:
            Terminal completion for the run.
        """
        return self._engine.deferred_wait(run_id, timeout=timeout)

    def status(self, run_id):
        """Read one deferred run's state, verdict, and operation.

        Args:
            run_id: Deferred run id to inspect.

        Returns:
            Status with run_id, operation, state, and verdict
                once judged.
        """
        return self._engine.deferred_status(run_id)

    def fetch(self, run_id):
        """Fetch one deferred run's merged ack-plus-completion.

        Args:
            run_id: Deferred run id to fetch.

        Returns:
            Merged receipt-plus-completion; verdict present once
                the run finished.
        """
        return self._engine.deferred_fetch(run_id)

    def cancel(self, run_id, actor=None):
        """Cancel one queued or running deferred run.

        Args:
            run_id: Deferred run id to cancel.
            actor: Attribution for the lifecycle event; the
                engine actor when omitted.

        Returns:
            Outcome with run_id, state, actor, and verdict when
                judged. A freed lane clears this client's paused
                signal.
        """
        outcome = self._engine.runtime_cancel(run_id, actor=actor)
        self._paused = False
        return outcome

    def watch(self, cursor=0):
        """Read ordered lifecycle events after a cursor.

        A cursor the retained log no longer covers recovers
        loudly: the page replays from the floor and reports
        resynced True with the current revision instead of
        failing the subscriber.

        Args:
            cursor: Opaque position from a previous read; 0
                replays the retained log.

        Returns:
            Page with events oldest first, the current cursor,
                and resynced True only after a recovery replay.

        Raises:
            ProjectError: any runtime refusal other than
                cursor_expired — expired cursors recover,
                never raise.
        """
        try:
            page = self._engine.runtime_events(cursor)
        except ProjectError as err:
            if err.code != "cursor_expired":
                raise
            snapshot = self._engine.snapshot()
            page = self._engine.runtime_events(0)
            return {
                "events": page["events"],
                "cursor": page["cursor"],
                "resynced": True,
                "current_revision": snapshot["current_revision"],
            }
        return {
            "events": page["events"],
            "cursor": page["cursor"],
            "resynced": False,
        }

    def survivors(self):
        """Report unfinished deferred runs without executing any.

        Returns:
            Boot report with survivors, interrupted, and
                quarantined run ids.
        """
        return self._engine.boot_report()

    def resume(self, run_id, force=False):
        """Resume one crash-surviving deferred run.

        Args:
            run_id: Survivor to execute now.
            force: Required to resume a quarantined run.

        Returns:
            Resume outcome for the run.
        """
        return self._engine.resume_survivor(run_id, force=force)

    def discard(self, run_id):
        """Discard one crash-surviving deferred run.

        Args:
            run_id: Survivor to discard.

        Returns:
            Discard record for the run.
        """
        return self._engine.discard_survivor(run_id)

    def resume_all(self):
        """Resume every retryable crash survivor.

        Returns:
            Gated batch with resumed run ids, their
                completions, and skipped entries.
        """
        return self._engine.resume_all_retryable()

    def replay_pending(self):
        """Resume crash-surviving RETRYABLE admissions, oldest first.

        Returns:
            Report with replayed run ids, their completions, and
                skipped entries.
        """
        return self._engine.replay_pending()
