"""Run admission gates and run-event recording."""

from ..errors import ProjectError

from .shared import _REPLAY_EVENTS, _RUN_OUTCOMES

#: Verdict detail kept on the completion event: the ledger answers
#: findings() and run_logs() after a reboot, when the in-memory
#: execution record is gone. Lists cap here; the verdict keeps
#: the full counts and the event keeps the truncated remainder.
_DURABLE_FINDINGS_MAX = 100

#: Native-log tail kept on the completion event: triage reads the
#: tail, and the ledger never carries bulk vectors.
_DURABLE_LOG_CHARS = 4096


class _RunMixin:
    """Run admission helpers for ProjectService."""

    def append_run_event(self, outcome, run_id, operation, verdict,
                         request_id=None, findings=(), log=""):
        """Append a run completion event with its verdict link.

        Findings and the native-log tail ride the event so the
        ledger answers findings() and run_logs() after a reboot.
        Both cap: the first findings plus the truncated remainder
        count, and the last log characters plus the full line
        count.

        Args:
            outcome: run_completed for a judged run (PASS or FAIL),
                run_failed when no verdict exists (NOT_RUN).
            run_id: Run the verdict belongs to; findings read back
                through it.
            operation: Operation that ran.
            verdict: Full verdict mapping stored on the event.
            request_id: Queued request this run discharges, if any
                (run_job); direct runs carry None.
            findings: Finding mappings stored first-N with the
                truncated remainder count.
            log: Native log text; the tail is stored with the
                full line count.

        Returns:
            The appended event record with its seq.

        Raises:
            ProjectError: invalid_command for an unknown outcome.

        Caution: Appends to the ordered log (and the cursor) but
            never advances the project revision — running judges,
            only submitting mutates.
        """
        if outcome not in _RUN_OUTCOMES:
            raise ProjectError(
                "invalid_command", f"Unknown run outcome: {outcome}."
            )
        kept = list(findings)[:_DURABLE_FINDINGS_MAX]
        dropped = max(0, len(list(findings)) - len(kept))
        excerpt = log[-_DURABLE_LOG_CHARS:] if log else ""
        with self._ledger_lock:
            self._refresh_durable()
            record = self._append_event(
                outcome,
                request_id,
                {
                    "run_id": run_id,
                    "operation": operation,
                    "verdict": verdict,
                    "findings": kept,
                    "findings_truncated": dropped,
                    "log_excerpt": excerpt,
                    "log_lines": len(log.splitlines()) if log else 0,
                },
            )
            self._persist_after_mutation()
        return record

    def append_replay_event(self, event, request_id, data):
        """Append a replay-lifecycle event for one run.

        `run_started` marks execution begin (a kill after it reads as
        an interruption at the next boot); `run_interrupted` records
        one admitted->interrupted transition for its content key (two
        quarantines the key); `run_discarded` retires a survivor the
        user chose not to resume.

        Args:
            event: Replay event name (run_started, run_interrupted,
                or run_discarded).
            request_id: Queued request the run belongs to.
            data: Event data carrying the run_id (plus content_key
                for started/interrupted marks).

        Returns:
            The appended event record with its seq.

        Raises:
            ProjectError: invalid_command for an unknown replay
                event or data without a run_id.

        Caution: Appends to the ordered log (and the cursor) but
            never advances the project revision — replay
            bookkeeping judges nothing and mutates nothing.
        """
        if event not in _REPLAY_EVENTS:
            raise ProjectError(
                "invalid_command", f"Unknown replay event: {event}."
            )
        if not isinstance(data, dict) or data.get("run_id") is None:
            raise ProjectError(
                "invalid_command", "Replay event needs a data.run_id."
            )
        with self._ledger_lock:
            self._refresh_durable()
            record = self._append_event(event, request_id, dict(data))
            self._persist_after_mutation()
        return record

    def log_coalesced_request(self, command_text, request_id, run_id,
                              snapshot_id):
        """Log a coalesced envelope against its shared run (COALESCE-I33).

        A duplicate submit that joins a live run records its envelope
        here instead of admitting: the request_id maps to the shared
        run_id in the request map (so replays and run_job resolve it)
        and a `request_coalesced` event lands in the log — but the
        revision never advances, no snapshot is captured, and the
        project never mutates. Joining callers are readers of a
        shared verdict, not writers.

        Args:
            command_text: YAML command mapping with an operation.
            request_id: Joining envelope id; resubmitting the
                identical text returns the identical ack.
            run_id: Shared live run the envelope joins.
            snapshot_id: Shared run's snapshot (one revision pins
                one snapshot).

        Returns:
            Coalesced ack with the caller's request_id, the shared
                run_id and snapshot_id, queued state, the current
                (unadvanced) revision, the event cursor, and a
                coalesced marker.

        Raises:
            ProjectError: invalid_yaml for an unparsable command or
                one without an operation, request_conflict for a
                reused id with new text.

        Caution: Never advances the revision — a coalesced envelope
            must not break the pin later duplicates join under.
        """
        self._refresh_durable()
        replay = self._check_replay(request_id, command_text)
        if replay is not None:
            return replay
        try:
            command = self._yaml.load(command_text)
        except Exception as exc:
            raise ProjectError(
                "invalid_yaml", f"Cannot parse command: {exc}"
            ) from exc
        if not isinstance(command, dict) or "operation" not in command:
            raise ProjectError(
                "invalid_yaml",
                "Command must be a mapping with an operation.",
            )
        ack = {
            "request_id": request_id,
            "project_id": self._project_id,
            "run_id": run_id,
            "snapshot_id": snapshot_id,
            "state": "queued",
            "current_revision": self._current_revision,
            "coalesced": True,
        }
        self._requests[request_id] = (command_text, ack)
        self._append_event(
            "request_coalesced",
            request_id,
            {
                "run_id": run_id,
                "revision": self._current_revision,
                "operation": command.get("operation"),
            },
        )
        ack["event_cursor"] = self._cursor()
        self._persist_after_mutation()
        return ack

    def command_for(self, request_id):
        """Return the admitted (command, ack) for a queued request.

        Phase 2 of submit-then-run: unknown ids raise
        `unknown_request` instead of running a stranger's job.

        Args:
            request_id: Envelope id admitted by an earlier submit.

        Returns:
            (command, ack) pair stored at admission time.

        Raises:
            ProjectError: unknown_request for an id never admitted.
        """
        self._refresh_durable()
        try:
            command_text, ack = self._requests[str(request_id)]
        except KeyError:
            raise ProjectError(
                "unknown_request", f"No queued request: {request_id}."
            ) from None
        return self._yaml.load(command_text), ack

    def _check_replay(self, request_id, command_text):
        """Return the stored response for an idempotent replay, if any.

        Args:
            request_id: Client envelope id.
            command_text: YAML command text for identity comparison.

        Returns:
            Stored response when the id was seen with identical
            text, else None.

        Raises:
            ProjectError: request_conflict for a reused id with
                new text.
        """
        prev = self._requests.get(request_id)
        if prev is None:
            return None
        prev_text, prev_ack = prev
        if prev_text != command_text:
            raise ProjectError(
                "request_conflict",
                f"Request id reused with different input: {request_id}.",
            )
        return prev_ack

    def _gate_revision(self, expected_revision):
        """Fail stale writers before any effect lands.

        Args:
            expected_revision: Revision the writer read.

        Raises:
            ProjectError: revision_conflict for a stale head.
        """
        if expected_revision != self._current_revision:
            raise ProjectError(
                "revision_conflict",
                f"Expected revision {self._current_revision}, "
                f"got {expected_revision}.",
            )
