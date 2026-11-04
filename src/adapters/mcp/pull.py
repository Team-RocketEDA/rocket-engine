"""MCP pull path over the cursor event log (ADR-017 D7).

The MCP port is pull-by-default: the client polls the existing
cursor log from a stale cursor and converges, never waiting on a
server push. Push stays a per-port opt-in: subscribing without
the explicit flag is refused, never silently armed.

Position dedupe reuses the bus-owned PositionGuard (the one
shared helper every port applies through): the pull path reads
the shared cursor log through the wired get_events_since query
every transport serves, so there is no second event shape and
no duplicated seam — receiving one page twice re-renders the
same state.
"""

from ...execution.ports import PositionGuard
from .. import api
from ..errors import AdapterError


def poll_events(engine, project_id, cursor, require_contiguous_from=None,
                request_id=None):
    """Poll one page of ledger events after a cursor.

    The poll rides the wired get_events_since query — the same
    cursor log every transport shares — so a stale cursor
    converges with no diff reconstruction and no snapshot
    pinning.

    Args:
        engine: Engine the MCP port reads through.
        project_id: Project the cursor belongs to.
        cursor: Only events with a higher seq are returned; 0
            replays the retained log.
        require_contiguous_from: Assert the reader holds
            contiguous history from this seq; an unmet demand
            fails with resync_required instead of gap-hiding.
        request_id: Envelope id; minted when omitted.

    Returns:
        Page mapping with the events after the cursor, oldest
            first, plus the live cursor.
    """
    arguments = {"cursor": cursor}
    if require_contiguous_from is not None:
        arguments["require_contiguous_from"] = require_contiguous_from
    return api.submit(engine, project_id, "get_events_since",
                      arguments, request_id=request_id)


class McpPullClient:
    """Pull-by-default MCP cursor over one project's event log.

    The client holds its cursor and reuses the bus-owned
    PositionGuard for position-check-then-apply, so
    same-position redelivery applies once through the one
    shared helper every port uses — never a per-client
    reinvention. Bind the port's bus guard (guard_for) and
    port name and the pull path shares one dedupe record
    with the push path. Polling advances the cursor; a
    failed contiguity demand resyncs from the snapshot plus
    the full retained log and resets the position, never
    skipping over a trimmed gap.

    Args:
        engine: Engine the MCP port reads through.
        project_id: Project the cursor belongs to.
        cursor: Last consumed ledger position; 0 replays the
            retained log.
        guard: PositionGuard to check positions against; the
            port's bound bus guard when the MCP port is
            bus-attached, a client-owned guard otherwise.
        port: Port name positions apply under; the attached
            port name for a bus-bound guard, the project id
            otherwise.
    """

    def __init__(self, engine, project_id, cursor=0, guard=None,
                 port=None):
        self._engine = engine
        self._project_id = project_id
        self._cursor = cursor
        self._applied = cursor
        self._guard = guard if guard is not None else PositionGuard()
        self._owns_guard = guard is None
        self._port = port if port is not None else project_id

    @property
    def cursor(self):
        """Last consumed ledger position.

        Returns:
            Cursor the next poll reads after.
        """
        return self._cursor

    @property
    def applied_position(self):
        """Highest ledger position this client handed over.

        The guard stays the dedupe authority (it also records
        positions the push path applied); this is the client's
        own high-water mark for cursor bookkeeping.

        Returns:
            Seq of the last applied event, or the starting
                cursor when nothing applied yet.
        """
        return self._applied

    def poll(self, require_contiguous=False, request_id=None):
        """Poll the next page after the stored cursor.

        A stale cursor converges: the page carries every
        retained event after it, and the stored cursor advances
        to the live head. With require_contiguous, the poll
        asserts the reader holds contiguous history from
        cursor + 1; a fresh cursor (0) skips the demand because
        an empty log cannot be non-contiguous, and an unmet
        demand resyncs instead of gap-hiding.

        Args:
            require_contiguous: Assert contiguous history from
                cursor + 1 and resync when the demand cannot
                be met (a trimmed gap).
            request_id: Envelope id; minted when omitted.

        Returns:
            Page mapping with events, the live cursor, and
                whether a resync served it.

        Raises:
            ProjectError: invalid_command for a malformed
                cursor. An unmet contiguity demand never escapes
                — it resyncs instead.
        """
        demand = self._cursor + 1 if require_contiguous and self._cursor else None
        try:
            page = poll_events(self._engine, self._project_id,
                               self._cursor,
                               require_contiguous_from=demand,
                               request_id=request_id)
        except Exception as exc:
            if getattr(exc, "code", None) != "resync_required":
                raise
            return self.resync(request_id=request_id)
        self._cursor = page["cursor"]
        return {"events": page["events"], "cursor": page["cursor"],
                "resynced": False}

    def apply(self, events, handler):
        """Apply one page idempotently: position check, then apply.

        The check runs through the bus-owned PositionGuard, so
        a position the push path already applied (or this page
        before) applies once per port. Events are offered in
        seq order; events without an integer seq carry no
        ledger position, so the guard cannot admit them and
        they are skipped. A raising handler leaves its
        position unrecorded, so redelivery retries it.

        Args:
            events: Page of ledger events, oldest first.
            handler: Called once per newly positioned event.

        Returns:
            Count of events handed to the handler.
        """
        ordered = sorted(
            (e for e in events if isinstance(e.get("seq"), int)
             and not isinstance(e.get("seq"), bool)),
            key=lambda e: e["seq"],
        )
        applied = 0
        for event in ordered:
            done, _ = self._guard.apply_once(
                self._port, event["seq"], handler, event)
            if not done:
                continue
            if event["seq"] > self._applied:
                self._applied = event["seq"]
            applied += 1
        return applied

    def resync(self, request_id=None):
        """Resync from the snapshot plus the full retained log.

        Drops the stale position, re-reads the live head, and
        replays the retained log from 0 so the caller
        re-renders current state. The applied position resets
        so the replayed page applies in full through apply;
        running the onboarding ritual twice stays safe. A
        client-owned guard is replaced with a fresh one; a
        bus-bound guard is left alone — bus resync rebinds
        through the bus (a new onboarding, per ADR-017), so
        the shared dedupe record is never wiped here.

        Args:
            request_id: Envelope id; minted when omitted.

        Returns:
            Page mapping with the full retained events, the
                live cursor, and resynced True.
        """
        self._cursor = 0
        self._applied = 0
        if self._owns_guard:
            self._guard = PositionGuard()
        page = poll_events(self._engine, self._project_id, 0,
                           request_id=request_id)
        self._cursor = page["cursor"]
        return {"events": page["events"], "cursor": page["cursor"],
                "resynced": True}


def subscribe_push(runtime, send, enable_push=False):
    """Push lifecycle events to one subscriber, opt-in only.

    Pull is the default; this is the per-port push escape hatch
    (ADR-017 D7). Without the explicit flag the call is
    refused and no listener is registered — the AI wakes on
    its own polls, never on UI churn.

    Args:
        runtime: EngineRuntime emitting lifecycle events.
        send: Called synchronously with each built
            notification mapping.
        enable_push: Explicit opt-in; push stays off unless
            this is True.

    Returns:
        Unsubscribe callable removing the listener.

    Raises:
        AdapterError: unsupported_operation when push was not
            explicitly opted into.
    """
    if not enable_push:
        raise AdapterError(
            "unsupported_operation",
            "MCP push is opt-in only (ADR-017 D7): pass "
            "enable_push=True, or keep polling the cursor log.",
        )
    from .server import subscribe_runtime

    return subscribe_runtime(runtime, send)
