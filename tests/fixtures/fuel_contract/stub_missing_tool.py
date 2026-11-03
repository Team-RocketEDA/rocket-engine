"""Fixture stub with a mapped tool deleted (AST-only, never imported).

get_job_status is gone: the drift check must fail naming the tool.
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
