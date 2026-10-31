"""HTTP transport (duplex): JSON requests in, results and events out."""

import uuid

from ..base import enforce_scope, parse_json
from ..errors import AdapterError


class HttpTransport:
    """HTTP transport over an engine: requests in, results out.

    Args:
        engine: Engine the requests submit against.
        project_id: Optional scope; requests for another project
            are denied, never routed.
    """

    def __init__(self, engine, project_id=None):
        self._engine = engine
        self._project_id = project_id

    def handle(self, text):
        """Route one JSON request through the engine.

        Args:
            text: Raw JSON request with project_id, operation,
                arguments, and an optional request_id.

        Returns:
            Engine admission ack or query result for the request.

        Raises:
            AdapterError: invalid_command for a missing
                project_id, cross_project_denied for a request
                outside the bound scope.
        """
        request = parse_json(text)
        if request.get("project_id") is None:
            raise AdapterError("invalid_command", "Missing project_id in request.")
        enforce_scope(request.get("project_id"), self._project_id)
        return self._engine.submit(
            {
                "project_id": request["project_id"],
                "operation": request["operation"],
                "arguments": request.get("arguments", {}),
                "request_id": str(request.get("request_id") or uuid.uuid4().hex),
            }
        )
