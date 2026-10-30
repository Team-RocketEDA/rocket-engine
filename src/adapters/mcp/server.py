"""Connectable MCP stdio server: initialize/tools/list/tools/call.

One tool per cataloged operation/query; handlers route through
McpTransport so validation stays single-sourced. build_server()
is transport-free; only main() touches stdio.
"""

import asyncio
import json
import uuid

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool

from ...interfaces.vocabulary import OPERATIONS, QUERIES
from ...project.errors import ProjectError
from ..errors import AdapterError
from . import McpTransport


def tool_definitions():
    """Build one MCP tool per cataloged operation/query.

    Returns:
        Tool list with per-operation descriptions, sorted by name.
    """
    tools = []
    for name in sorted(OPERATIONS | QUERIES):
        kind = "operation" if name in OPERATIONS else "query"
        tools.append(Tool(
            name=name,
            description=(
                f"Rocket-engine {kind} {name}. "
                "Arguments: project_id (required) plus operation arguments."
            ),
            inputSchema={"type": "object"},
        ))
    return tools


def _error(code, message):
    return CallToolResult(
        content=[TextContent(
            type="text",
            text=json.dumps({"ok": False, "code": code, "message": message}),
        )],
        isError=True,
    )


def make_handlers(engine_factory, project_scope=None):
    """Build transport-free list/call handlers over McpTransport.

    Handlers route through McpTransport so validation stays
    single-sourced; engines are cached per project id.

    Args:
        engine_factory: Callable turning a project id into an
            engine.
        project_scope: Optional scope enforced on every call.

    Returns:
        (list_tools, call_tool) async handler pair. Call failures
            become error results, never exceptions.
    """
    engines = {}

    def _engine_for(project_id):
        if project_id not in engines:
            engines[project_id] = engine_factory(project_id)
        return engines[project_id]

    async def _list_tools(ctx, params):
        return ListToolsResult(tools=tool_definitions())

    async def _call_tool(ctx, params):
        arguments = dict(params.arguments or {})
        project_id = arguments.get("project_id")
        if project_id is None:
            return _error("invalid_command",
                           "Missing project_id in arguments.")
        try:
            transport = McpTransport(_engine_for(project_id),
                                     project_id=project_scope)
            result = transport.handle(json.dumps({
                "method": "tools/call",
                "params": {"name": params.name, "arguments": arguments},
                "id": uuid.uuid4().hex,
            }))
        except (AdapterError, ProjectError) as exc:
            return _error(exc.code, str(exc))
        return CallToolResult(content=[TextContent(
            type="text", text=json.dumps(result))])

    return _list_tools, _call_tool


def build_server(engine_factory, project_scope=None):
    """Build the MCP server with list/call handlers attached.

    Args:
        engine_factory: Callable turning a project id into an
            engine.
        project_scope: Optional scope enforced on every call.

    Returns:
        Configured MCP server (stdio wiring stays in main).
    """
    list_handler, call_handler = make_handlers(engine_factory,
                                               project_scope)
    return Server("rocket-engine",
                  on_list_tools=list_handler,
                  on_call_tool=call_handler)


def main(argv=None):
    """Serve the MCP stdio server until stdin closes.

    Args:
        argv: Unused; accepted for entry-point parity.

    Returns:
        Process exit code (0 on a clean stdio shutdown).
    """
    from ...composition import Engine

    server = build_server(lambda pid: Engine(pid, actor="mcp"))

    async def _run():
        async with stdio_server() as (read, write):
            await server.run(
                read, write, server.create_initialization_options())

    asyncio.run(_run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
