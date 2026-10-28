"""MCP stdio bridge (duplex): tool calls in, bounded replies out.

Only cataloged operations and read queries are exposed. Anything else
— host shells first among them — is rejected, never routed.
"""

import uuid

from ...interfaces.vocabulary import OPERATIONS, QUERIES
from ..base import enforce_scope, parse_json
from ..errors import AdapterError


class McpTransport:
    host_execution_enabled = False

    def __init__(self, engine, project_id=None):
        self._engine = engine
        self._project_id = project_id

    def handle(self, text):
        message = parse_json(text)
        if message.get("method") != "tools/call":
            raise AdapterError(
                "unsupported_operation",
                f"Unsupported method: {message.get('method')}.",
            )
        params = message.get("params", {})
        name = params.get("name")
        if name not in OPERATIONS and name not in QUERIES:
            raise AdapterError("unsupported_operation", f"Unsupported tool: {name}.")
        arguments = dict(params.get("arguments", {}))
        if arguments.get("project_id") is None:
            raise AdapterError("invalid_command", "Missing project_id in arguments.")
        enforce_scope(arguments.get("project_id"), self._project_id)
        return self._engine.submit(
            {
                "project_id": arguments.pop("project_id"),
                "operation": name,
                "arguments": arguments,
                "request_id": str(message.get("id", uuid.uuid4().hex)),
            }
        )
