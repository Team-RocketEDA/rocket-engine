"""Fixture stub with a skewed RESPONSE field (AST-only, never imported).

run_job's success literal carries execution_id instead of run_id: the
drift check must fail naming run_id and run_job. All else matches.
"""

from mcp.server.mcpserver import MCPServer

mcp = MCPServer("rocket")


@mcp.tool()
def run_job(kind: str, hypothesis: str = "", rocket_session: str = "") -> dict:
    """Run a registered job on the current design and evaluate checks."""
    if kind != "spice_sim":
        return {"error": "unsupported_operation", "message": "unknown job kind"}
    return {
        "execution_id": "stub-1",
        "iteration": 0,
        "checks": {},
    }


@mcp.tool()
def get_job_status(run_id: str) -> dict:
    """State of a run: queued, running, completed, error or cancelled."""
    return {"run_id": run_id, "state": "completed"}


@mcp.tool()
def get_logs(run_id: str, query: str = "", offset: int = 0, limit: int = 40) -> dict:
    """Search or page through a run's full log."""
    return {
        "run_id": run_id,
        "total_lines": 120,
        "matched": 1,
        "offset": offset,
        "lines": [],
        "more": False,
    }
