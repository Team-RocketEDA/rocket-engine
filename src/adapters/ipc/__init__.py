"""Electron stdio transport (request/response + get_events_since polling, NOT push — see PUSH-EVENTS): envelopes in, replies out.

Framing (length-prefix) arrives with the Electron integration; this
slice speaks bare JSON envelopes with the same command shape.
"""

import uuid

from .. import api
from ..base import enforce_scope, parse_json
from ..errors import AdapterError


class IpcTransport:
    """Electron stdio transport over an engine: envelopes in, events out.

    Args:
        engine: Engine the envelopes submit against.
        project_id: Optional scope; frames for another project are
            denied, never routed.
    """

    def __init__(self, engine, project_id=None):
        self._engine = engine
        self._project_id = project_id

    def handle(self, text):
        """Route one JSON envelope through the engine.

        Args:
            text: Raw JSON frame with project_id, operation,
                arguments, and an optional request_id.

        Returns:
            Engine admission ack or query result for the frame.

        Raises:
            AdapterError: invalid_command for a missing
                project_id, cross_project_denied for a frame
                outside the bound scope.
        """
        frame = parse_json(text)
        if frame.get("project_id") is None:
            raise AdapterError("invalid_command", "Missing project_id in frame.")
        enforce_scope(frame.get("project_id"), self._project_id)
        return api.submit(
            self._engine,
            frame["project_id"],
            frame["operation"],
            frame.get("arguments", {}),
            request_id=str(frame.get("request_id") or uuid.uuid4().hex),
        )


class EventStream:
    """Push event stream over a runtime (PUSH-EVENTS addition).

    Addition-only seam: IpcTransport is untouched — this wraps
    the same lifecycle log the MCP notifier pushes, so framed
    stdio clients can subscribe instead of polling
    get_events_since.

    Args:
        runtime: EngineRuntime emitting lifecycle events.
    """

    def __init__(self, runtime):
        self._runtime = runtime

    def since(self, cursor):
        """Read ordered lifecycle events after a cursor.

        Args:
            cursor: Opaque position from a previous read; 0
                replays the retained log.

        Returns:
            Events appended after the cursor, oldest first,
                plus the current cursor.

        Raises:
            ExecutionError: cursor_expired when the cursor is
                behind the retained floor or past the head.
        """
        return self._runtime.watch(cursor)

    def subscribe(self, send):
        """Push every lifecycle event to one subscriber.

        Args:
            send: Called synchronously with each emitted
                event mapping.

        Returns:
            Unsubscribe callable removing the listener.
        """
        return self._runtime.add_listener(send)
