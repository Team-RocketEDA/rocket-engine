"""MCP stdio bridge (duplex): tool calls in, bounded replies out.

Only cataloged operations and read queries are exposed. Anything else
— host shells first among them — is rejected, never routed.
"""

from ..base import enforce_scope, parse_json
from ..errors import AdapterError

OPERATIONS = frozenset(
    {
        "generate_views", "run_hdl_test", "run_formal", "run_syntax",
        "run_connectivity", "run_drc", "run_lvs", "run_erc", "run_spice",
        "run_optical", "run_digital_flow", "run_timing", "run_extraction",
        "run_post_layout", "run_em", "run_thermal", "python_execute",
        "run_view_sync",
    }
)
QUERIES = frozenset(
    {
        "api_search", "api_info", "api_help", "get_python_console",
        "get_capabilities", "get_project_snapshot", "list_job_kinds",
        "plan_checks", "get_job_status", "get_check_results",
        "list_artifacts", "get_logs",
    }
)


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
        enforce_scope(arguments.get("project_id"), self._project_id)
        return self._engine.submit(
            {
                "project_id": arguments.pop("project_id"),
                "operation": name,
                "arguments": arguments,
            }
        )
