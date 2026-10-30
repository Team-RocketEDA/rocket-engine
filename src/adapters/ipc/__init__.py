"""Electron stdio transport (duplex): framed envelopes in, events out.

Framing (length-prefix) arrives with the Electron integration; this
slice speaks bare JSON envelopes with the same command shape.
"""

import uuid

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
        return self._engine.submit(
            {
                "project_id": frame["project_id"],
                "operation": frame["operation"],
                "arguments": frame.get("arguments", {}),
                "request_id": str(frame.get("request_id") or uuid.uuid4().hex),
            }
        )
