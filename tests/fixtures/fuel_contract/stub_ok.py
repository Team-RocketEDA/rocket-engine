"""Fixture stub mirroring mcp-stub's mapped shapes (AST-only, never imported).

Tools/args/response keys track rocket_fuel/mcp-stub/src/rocket_stub/server.py
for the drift check's overlap map: run_job, get_job_status, get_logs.
"""

from mcp.server.mcpserver import MCPServer

mcp = MCPServer("rocket")


@mcp.tool()
def run_job(kind: str, hypothesis: str = "", rocket_session: str = "") -> dict:
    """Run a registered job on the current design and evaluate checks."""
    if kind != "spice_sim":
        return {"error": "unsupported_operation", "message": "unknown job kind", "allowed": ["spice_sim"]}
    return {
        "run_id": "stub-1",
        "iteration": 0,
        "iterations_left": 3,
        "checks": {},
        "failing_required": [],
        "changes_since_last_run": [],
        "log_excerpt": [],
        "note": "STUB RESULT",
    }


@mcp.tool()
def get_job_status(run_id: str) -> dict:
    """State of a run: queued, running, completed, error or cancelled."""
    run = {"kind": "spice_sim", "state": "completed"}
    return {"run_id": run_id, **run} if run else {"error": "unknown_run", "message": "no run"}


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
