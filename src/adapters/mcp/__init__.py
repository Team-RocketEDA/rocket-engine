"""MCP stdio bridge (request/response + get_events_since polling, NOT push — see PUSH-EVENTS): tool calls in, bounded replies out.

Only cataloged operations and read queries are exposed. Anything else
— host shells first among them — is rejected, never routed.
"""

import uuid

from ...interfaces.vocabulary import OPERATIONS, QUERIES
from ..base import enforce_scope, parse_json
from ..errors import AdapterError


class McpTransport:
    """MCP transport over an engine: tool calls in, bounded replies out.

    Args:
        engine: Engine the tool calls submit against.
        project_id: Optional scope; calls for another project are
            denied, never routed.
    """

    host_execution_enabled = False

    def __init__(self, engine, project_id=None):
        self._engine = engine
        self._project_id = project_id

    def handle(self, text):
        """Route one tools/call message through the engine.

        Args:
            text: Raw JSON-RPC message with method tools/call and
                params holding the tool name plus arguments
                (project_id required).

        Returns:
            Engine admission ack or query result for the tool call.

        Raises:
            AdapterError: unsupported_operation for a foreign
                method or an uncataloged tool, invalid_command for
                a missing project_id, cross_project_denied for a
                call outside the bound scope.

        Caution: Only cataloged operations and read queries are
            exposed — anything else, host shells first among them,
            is rejected, never routed.
        """
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
