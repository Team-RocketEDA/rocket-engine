"""Electron stdio transport (duplex): framed envelopes in, events out.

Framing (length-prefix) arrives with the Electron integration; this
slice speaks bare JSON envelopes with the same command shape.
"""

from ..base import enforce_scope, parse_json


class IpcTransport:
    def __init__(self, engine, project_id=None):
        self._engine = engine
        self._project_id = project_id

    def handle(self, text):
        frame = parse_json(text)
        enforce_scope(frame.get("project_id"), self._project_id)
        return self._engine.submit(
            {
                "project_id": frame["project_id"],
                "operation": frame["operation"],
                "arguments": frame.get("arguments", {}),
            }
        )
