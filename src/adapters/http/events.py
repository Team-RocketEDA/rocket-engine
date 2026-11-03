"""HTTP SSE frames over the runtime lifecycle log (PUSH-EVENTS).

Append-only seam: the POST/GET-health path is untouched — this
only translates the same lifecycle log the MCP notifier and the
IPC stream push into Server-Sent Events frames, so browsers and
HTTP clients can subscribe instead of polling get_events_since.
"""

import json


def format_frame(event):
    """Render one lifecycle event as an SSE frame.

    Args:
        event: Lifecycle event with seq, kind, and run_id.

    Returns:
        SSE text with the event id, kind, and JSON data,
            terminated by a blank line.
    """
    seq = event.get("seq", 0)
    kind = event.get("kind", "message")
    return f"id: {seq}\nevent: {kind}\ndata: {json.dumps(dict(event))}\n\n"


class EventSource:
    """SSE source over a runtime (mirrors the IPC EventStream).

    Addition-only seam: wraps the runtime lifecycle log, so HTTP
    clients replay missed events then receive live frames.

    Args:
        runtime: EngineRuntime emitting lifecycle events.
    """

    def __init__(self, runtime):
        self._runtime = runtime

    def since(self, cursor):
        """Replay lifecycle events after a cursor.

        Args:
            cursor: Opaque position from a previous read; 0
                replays the retained log.

        Returns:
            Events appended after the cursor, oldest first,
                plus the current cursor.
        """
        return self._runtime.watch(cursor)

    def subscribe(self, send):
        """Push every lifecycle event to one subscriber as frames.

        Args:
            send: Called synchronously with each SSE frame text.

        Returns:
            Unsubscribe callable removing the listener.
        """
        return self._runtime.add_listener(
            lambda event: send(format_frame(event)))
