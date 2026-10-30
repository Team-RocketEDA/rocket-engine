"""Connectable MCP stdio server: initialize/tools/list/tools/call.

One tool per cataloged operation/query; handlers route through
McpTransport so validation stays single-sourced. build_server()
is transport-free; only main() touches stdio.

Bound to a project (`--project`), the server fills project_id and the
current expected_revision itself, runs queued jobs before replying so
get_job_status has a result, and reads run_spice targets from the
project's constraints.yaml (`--project-dir`): the agent never sets them.
"""

import argparse
import asyncio
import json
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool
from ruamel.yaml import YAML

from ...execution.errors import ExecutionError
from ...interfaces.vocabulary import OPERATIONS, QUERIES
from ...project.errors import ProjectError
from ..errors import AdapterError
from . import McpTransport

_ENGINE_ERRORS = (AdapterError, ProjectError, ExecutionError)

_RUN_ID = {"type": "string", "description": "run_id from the queued acknowledgement."}

# Argument schemas for the tools an agent uses in the repair loop. Targets are
# deliberately absent from run_spice: they come from the project's constraints.
_SCHEMAS = {
    "run_spice": (
        "Run an ngspice simulation and judge each measurement against the project's targets. "
        "Returns a queued acknowledgement with run_id; read the verdict with get_job_status.",
        {
            "sources": {"type": "array", "items": {"type": "string"},
                        "description": "Netlist files to include, e.g. [\"design/opamp.cir\"]."},
            "measurements": {
                "type": "array",
                "description": "What to measure. Names must match metrics in constraints.yaml; "
                               "targets (and the measurement formula, when the project defines it) "
                               "are filled in from there.",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Metric name, e.g. dc_gain_db."},
                        "expr": {"type": "string", "description": "ngspice expression, e.g. vdb(out)[0]. "
                                 "Omit when constraints.yaml defines it."},
                        "unit": {"type": "string"},
                    },
                    "required": ["name"],
                },
            },
            "analyses": {"type": "array", "items": {"type": "string"},
                         "description": "ngspice analysis lines, e.g. [\"ac dec 20 1 1e9\"]."},
            "params": {"type": "object", "description": "Extra .param values."},
            "corner": {"type": "string", "description": "Process corner, default tt."},
            "temp_c": {"type": "number", "description": "Temperature in C, default 27."},
        },
        ["sources", "measurements"],
    ),
    "get_job_status": ("State and verdict of a run, with measured values and margins.", {"run_id": _RUN_ID}, ["run_id"]),
    "get_check_results": (
        "Latest verdict per operation for this project.",
        {"operation": {"type": "string", "description": "Only this operation, e.g. run_spice."}},
        [],
    ),
    "get_logs": (
        "Search or page through a run's full log. Use query (e.g. \"error\") rather than paging everything.",
        {
            "run_id": _RUN_ID,
            "query": {"type": "string", "description": "Case-insensitive text to match."},
            "offset": {"type": "integer", "minimum": 0},
            "limit": {"type": "integer", "minimum": 1, "maximum": 200},
        },
        ["run_id"],
    ),
    "list_job_kinds": ("Operations this engine can run and the tools behind each.", {}, []),
    "get_project_snapshot": ("Current revision and event cursor of the project.", {}, []),
}

_ENVELOPE = {
    "project_id": {"type": "string", "description": "Filled in by a project-bound server."},
    "expected_revision": {"type": "string", "description": "Filled in by a project-bound server."},
}


def tool_definitions():
    tools = []
    for name in sorted(OPERATIONS | QUERIES):
        kind = "operation" if name in OPERATIONS else "query"
        description, properties, required = _SCHEMAS.get(
            name,
            (f"Rocket-engine {kind} {name}. Arguments: project_id plus operation arguments.", {}, []),
        )
        schema = {"type": "object", "properties": {**_ENVELOPE, **properties}}
        if required:
            schema["required"] = required
        tools.append(Tool(name=name, description=description, inputSchema=schema))
    return tools


def _error(code, message):
    return CallToolResult(
        content=[TextContent(
            type="text",
            text=json.dumps({"ok": False, "code": code, "message": message}),
        )],
        isError=True,
    )


def _confine_files(arguments, project_dir):
    """Resolve run_spice sources inside the project and give ngspice a workdir under results/."""
    root = Path(project_dir).resolve()
    sources = arguments.get("sources")
    if isinstance(sources, list):
        resolved = []
        for source in sources:
            path = (root / str(source)).resolve()
            if not path.is_relative_to(root):
                raise AdapterError("invalid_reference", f"Source outside the project: {source}.")
            resolved.append(str(path))
        arguments["sources"] = resolved
    if "workdir" in arguments:
        raise AdapterError("invalid_command", "workdir is chosen by the engine, not the caller.")
    workdir = root / "results" / "engine-runs"
    workdir.mkdir(parents=True, exist_ok=True)
    arguments["workdir"] = str(workdir)


def _source_state(root):
    """(short commit, dirty) of the project's git working tree, or (None, None) outside git."""
    git = ["git", "-C", str(root)]
    head = subprocess.run([*git, "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
    if head.returncode != 0:
        return None, None
    status = subprocess.run([*git, "status", "--porcelain", "--", "design", "tests", "constraints.yaml"],
                            capture_output=True, text=True)
    return head.stdout.strip(), bool(status.stdout.strip())


def write_evidence(project_dir, engine, outcomes, arguments):
    """Persist each finished run under results/engine-runs/<run_id>.json, so the IDE
    sees agent and manual runs alike. Only the engine writes here."""
    root = Path(project_dir).resolve()
    folder = root / "results" / "engine-runs"
    folder.mkdir(parents=True, exist_ok=True)
    commit, dirty = _source_state(root)
    finished = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for outcome in outcomes:
        record = {
            "producer": "rocket-engine",
            "run_id": outcome["run_id"],
            "operation": outcome["operation"],
            "verdict": outcome["verdict"],
            "finished_at": finished,
            "source_commit": commit,
            "source_dirty": dirty,
            "sources": [str(Path(s).relative_to(root)) if Path(s).is_relative_to(root) else s
                        for s in arguments.get("sources") or []],
            "log": engine.log_text(outcome["run_id"]) if hasattr(engine, "log_text") else "",
        }
        (folder / f"{outcome['run_id']}.json").write_text(json.dumps(record, indent=2), encoding="utf-8")


def make_handlers(engine_factory, project_scope=None, project_dir=None):
    engines = {}

    def _engine_for(project_id):
        if project_id not in engines:
            engines[project_id] = engine_factory(project_id)
        return engines[project_id]

    async def _list_tools(ctx, params):
        return ListToolsResult(tools=tool_definitions())

    async def _call_tool(ctx, params):
        arguments = dict(params.arguments or {})
        if project_scope is not None:
            arguments.setdefault("project_id", project_scope)
        project_id = arguments.get("project_id")
        if project_id is None:
            return _error("invalid_command",
                           "Missing project_id in arguments.")
        try:
            engine = _engine_for(project_id)
            transport = McpTransport(engine, project_id=project_scope)
            if (project_scope is not None and params.name in OPERATIONS
                    and "expected_revision" not in arguments
                    and hasattr(engine, "snapshot")):
                arguments["expected_revision"] = engine.snapshot()["current_revision"]
            if project_dir is not None and params.name == "run_spice":
                _confine_files(arguments, project_dir)
            result = transport.handle(json.dumps({
                "method": "tools/call",
                "params": {"name": params.name, "arguments": arguments},
                "id": uuid.uuid4().hex,
            }))
            # Run what was just queued, so the agent's next get_job_status has a verdict.
            if params.name in OPERATIONS and hasattr(engine, "drain"):
                outcomes = engine.drain()
                if project_dir is not None:
                    write_evidence(project_dir, engine, outcomes, arguments)
        except _ENGINE_ERRORS as exc:
            return _error(exc.code, str(exc))
        return CallToolResult(content=[TextContent(
            type="text", text=json.dumps(result))])

    return _list_tools, _call_tool


def build_server(engine_factory, project_scope=None, project_dir=None):
    list_handler, call_handler = make_handlers(engine_factory,
                                               project_scope, project_dir)
    return Server("rocket-engine",
                  on_list_tools=list_handler,
                  on_call_tool=call_handler)


def load_constraints(project_dir):
    """constraints.yaml checks -> {metric: {min|max, unit[, expr, control]}} (>= is min, <= is max)."""
    path = Path(project_dir) / "constraints.yaml"
    if not path.is_file():
        return None
    data = YAML(typ="safe").load(path.read_text(encoding="utf-8")) or {}
    targets = {}
    for check in data.get("checks", []):
        bound = {">=": "min", "<=": "max"}.get(check.get("comparison"))
        if bound and check.get("metric"):
            target = targets.setdefault(check["metric"], {"unit": check.get("unit", "")})
            target[bound] = check["value"]
            # Optional: how the metric is measured (ngspice expr plus control lines such as meas).
            if check.get("expr"):
                target["expr"] = check["expr"]
            if check.get("control"):
                target["control"] = list(check["control"])
    return targets


def _call_once(engine_factory, args):
    """One-shot mode for the IDE's own buttons: same validation, targets and evidence as an agent call."""
    from mcp.types import CallToolRequestParams

    _, call = make_handlers(engine_factory, args.project, args.project_dir)

    def invoke(name, arguments):
        result = asyncio.run(call(None, CallToolRequestParams(name=name, arguments=arguments)))
        return result.is_error, json.loads(result.content[0].text)

    failed, body = invoke(args.call, json.loads(args.args))
    if not failed and args.call in OPERATIONS and "run_id" in body:
        failed, body = invoke("get_job_status", {"run_id": body["run_id"]})
    print(json.dumps(body))
    return 1 if failed else 0


def main(argv=None):
    from ...composition import Engine

    parser = argparse.ArgumentParser(prog="rocket-engine-mcp")
    parser.add_argument("--project", help="bind to this project id (fills project_id/expected_revision)")
    parser.add_argument("--project-dir", help="project folder; run_spice targets come from its constraints.yaml")
    parser.add_argument("--call", help="run one operation through the same handlers, print its job status, exit")
    parser.add_argument("--args", default="{}", help="JSON arguments for --call")
    args = parser.parse_args(argv)
    constraints = load_constraints(args.project_dir) if args.project_dir else None
    engine_factory = lambda pid: Engine(pid, actor="mcp", constraints=constraints)  # noqa: E731

    if args.call:
        return _call_once(engine_factory, args)

    server = build_server(
        engine_factory,
        project_scope=args.project,
        project_dir=args.project_dir,
    )

    async def _run():
        async with stdio_server() as (read, write):
            await server.run(
                read, write, server.create_initialization_options())

    asyncio.run(_run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
