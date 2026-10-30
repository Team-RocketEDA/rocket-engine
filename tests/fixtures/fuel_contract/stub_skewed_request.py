"""Fixture stub with a skewed REQUEST field (AST-only, never imported).

get_logs takes run_ref instead of run_id: the drift check must fail
naming run_id and get_logs. All other mapped shapes match stub_ok.py.
"""

from mcp.server.mcpserver import MCPServer

mcp = MCPServer("rocket")


@mcp.tool()
def run_job(kind: str, hypothesis: str = "", rocket_session: str = "") -> dict:
    """Run a registered job on the current design and evaluate checks."""
    return {
        "run_id": "stub-1",
        "iteration": 0,
        "checks": {},
    }


@mcp.tool()
def get_job_status(run_id: str) -> dict:
    """State of a run: queued, running, completed, error or cancelled."""
    return {"run_id": run_id, "state": "completed"}


@mcp.tool()
def get_logs(run_ref: str, query: str = "", offset: int = 0, limit: int = 40) -> dict:
    """Search or page through a run's full log."""
    return {
        "run_id": run_ref,
        "total_lines": 120,
        "matched": 1,
        "offset": offset,
        "lines": [],
        "more": False,
    }
