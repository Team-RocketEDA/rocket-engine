"""Connectable MCP stdio server: initialize/tools/list/tools/call.

One tool per cataloged operation/query; handlers route through
McpTransport so validation stays single-sourced. Tool descriptions
and input schemas read from the serving handler docstrings via the
api_spec generator — the same text the generated reference serves
(ADR-003 double-use). build_server() is transport-free; only main()
touches stdio.

Bound to a project (`--project`), the server fills project_id and the
current expected_revision itself; submit runs inline (same run_id ack
shape plus the verdict), run_job stays for deferred/batch pumping
plus idempotent fetch, and run_spice targets come from the
project's constraints.yaml (`--project-dir`): the agent never sets
them. Finished runs are recorded under results/engine-runs for IDE
and agent alike.
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
from ...execution.python_exec import MCP_INPUT_SCHEMA
from ...interfaces.vocabulary import OPERATIONS, QUERIES
from ...project.errors import ProjectError
from ..errors import AdapterError
from . import McpTransport

_ENGINE_ERRORS = (AdapterError, ProjectError, ExecutionError)


# Grandfathered override: python_execute keeps its richer hand
# validation schema (types, bounds, mode oneOf) until API-V1-CLIENTS
# retires this wire. Every other tool derives its schema from the
# api_spec generator — never add a second entry here.
_TOOL_SCHEMAS = {
    "python_execute": MCP_INPUT_SCHEMA,
}


_API_SCHEMAS = None


_HELP_ENGINE = None


def _help_engine():
    """Docs-only Engine for solver introspection (never submits).

    Returns:
        Shared in-memory Engine whose solver map describes each
            operation's serving adapters.
    """
    global _HELP_ENGINE
    if _HELP_ENGINE is None:
        from ...composition import Engine

        _HELP_ENGINE = Engine("mcp-help", actor="mcp")
    return _HELP_ENGINE


def _summary_of(target):
    """First docstring line of one handler (help-text source).

    Args:
        target: Handler class, method, or function to summarize.

    Returns:
        Summary line, or "" when the handler is undocumented.
    """
    doc = target.__doc__ or ""
    return doc.splitlines()[0].strip() if doc.splitlines() else ""


def describe_tool(name):
    """Describe one tool from its serving handler docstring.

    Wired solver operations read the primary adapter's class
    summary; CRUD operations and wired queries read their
    ProjectService method summary; Engine-served queries read
    their Engine method summary; run_job reads the phase-2
    runner summary; unwired names honestly say so. The generated
    reference reads the same docstrings, so docs and agent help
    cannot drift apart.

    Args:
        name: Cataloged operation or query name.

    Returns:
        Tool description text for the name.
    """
    from ...composition import QUERY_ENGINE_METHODS, QUERY_METHODS, Engine
    from ...project.service import ProjectService

    solvers = _help_engine().solvers_for(name)
    if solvers:
        return _summary_of(next(iter(solvers.values())))
    if name == "run_job":
        # run_job's contract doc lives on the phase-2 runner
        # (introspection only; never called for help).
        return _summary_of(Engine._run_queued)
    if name == "python_execute":
        # python_execute's contract doc lives on the approval
        # request (introspection only; never called for help).
        from ...execution.python_exec import PythonExecService

        return _summary_of(PythonExecService.request_execution)
    if name in OPERATIONS and hasattr(ProjectService, name):
        return _summary_of(getattr(ProjectService, name))
    method = QUERY_METHODS.get(name)
    if method is not None:
        return _summary_of(getattr(ProjectService, method))
    emethod = QUERY_ENGINE_METHODS.get(name)
    if emethod is not None:
        return _summary_of(getattr(Engine, emethod))
    kind = "operation" if name in OPERATIONS else "query"
    return f"Declared {kind} `{name}`; no handler wired yet."


def _engine_root():
    """Repo root holding docs/ for the generated-schema fallback.

    Returns:
        Path three levels above this file
            (src/adapters/mcp/server.py).
    """
    return Path(__file__).resolve().parents[3]


def _load_generated_schemas():
    """Load the api_spec generator output (package data or repo docs).

    The wheel ships docs/api-schema.json as adapter package data;
    a repo checkout falls back to docs/api-schema.json on disk.

    Returns:
        {"operations": {...}, "queries": {...}} mapping, or {} when
            neither source is readable.
    """
    try:
        from importlib.resources import files

        text = (files(__package__) / "api-schema.json").read_text(
            encoding="utf-8"
        )
        return json.loads(text)
    except Exception:
        pass
    try:
        return json.loads(
            (_engine_root() / "docs" / "api-schema.json").read_text(
                encoding="utf-8"
            )
        )
    except Exception:
        return {}


def _generated_schemas():
    """Per-op schemas from the api_spec generator output, cached.

    Returns:
        {"operations": {...}, "queries": {...}} mapping, or {} when
            no generator output is readable.
    """
    global _API_SCHEMAS
    if _API_SCHEMAS is None:
        _API_SCHEMAS = _load_generated_schemas()
    return _API_SCHEMAS


def input_schema_for(name):
    """Wire inputSchema for one cataloged tool, from the generator.

    Wired tools carry their generated properties/required verbatim;
    unwired names keep the generic object with a loud marker naming
    the tool. python_execute keeps its richer hand validation
    schema (pinned by test_python_exec_wiring.py) until
    API-V1-CLIENTS retires this wire.

    Args:
        name: Cataloged operation or query name.

    Returns:
        JSON Schema dict for the tool's inputSchema.
    """
    if name in _TOOL_SCHEMAS:
        return _TOOL_SCHEMAS[name]
    if name in OPERATIONS:
        section = "operations"
    elif name in QUERIES:
        section = "queries"
    else:
        section = None
    entry = None
    if section is not None:
        entry = _generated_schemas().get(section, {}).get(name)
    if entry and entry.get("wired"):
        return {
            "type": "object",
            "properties": entry.get("properties", {}),
            "required": entry.get("required", []),
        }
    kind = "operation" if name in OPERATIONS else "query"
    return {
        "type": "object",
        "description": (
            f"No generated schema for {kind} `{name}` yet — no "
            "handler wired; see docs/engine-api.md."
        ),
    }


def tool_definitions():
    """Build one MCP tool per cataloged operation/query.

    Descriptions come from the serving handler docstrings and input
    schemas come from the api_spec generator over those same
    docstrings — the same text the generated reference serves
    (ADR-003 double-use). A new documented op gains its wire schema
    with no server edit.

    Returns:
        Tool list with per-operation descriptions and generated
            input schemas, sorted by name.
    """
    tools = []
    for name in sorted(OPERATIONS | QUERIES):
        tools.append(Tool(
            name=name,
            description=describe_tool(name),
            inputSchema=input_schema_for(name),
        ))
    return tools


def _error(code, message, fields=None):
    payload = {"ok": False, "code": code, "message": message}
    if fields:
        payload["fields"] = list(fields)
    return CallToolResult(
        content=[TextContent(
            type="text",
            text=json.dumps(payload),
        )],
        isError=True,
    )


def _confine_files(arguments, project_dir):
    """Resolve run_spice sources inside the project and fix the workdir."""
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
    """(short commit, dirty) of the git working tree, or (None, None)."""
    git = ["git", "-C", str(root)]
    head = subprocess.run([*git, "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
    if head.returncode != 0:
        return None, None
    status = subprocess.run(
        [*git, "status", "--porcelain", "--", "design", "tests", "constraints.yaml"],
        capture_output=True, text=True,
    )
    return head.stdout.strip(), bool(status.stdout.strip())


def write_evidence(project_dir, engine, outcomes, arguments):
    """Persist finished runs under results/engine-runs/<run_id>.json.

    Args:
        project_dir: Project folder the evidence is written into.
        engine: Engine the runs executed on (for the native log).
        outcomes: Completion mappings with run_id, operation, verdict.
        arguments: Submitted arguments (for the run's source list).

    Note:
        Only the engine runs jobs; this only records them, so IDE
        buttons and agent calls share one evidence trail.
    """
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
        (folder / f"{outcome['run_id']}.json").write_text(
            json.dumps(record, indent=2), encoding="utf-8"
        )


def make_handlers(engine_factory, project_scope=None, project_dir=None):
    """Build transport-free list/call handlers over McpTransport.

    Handlers route through McpTransport so validation stays
    single-sourced; engines are cached per project id. Submit runs
    inline (ack plus verdict); run_job stays the deferred/batch
    pump and idempotent fetch.

    Args:
        engine_factory: Callable turning a project id into an
            engine.
        project_scope: Optional scope enforced on every call; fills
            project_id and the current expected_revision.
        project_dir: Optional project folder; run_spice sources are
            confined inside it, targets load from its
            constraints.yaml, and finished runs are recorded under
            its results/engine-runs.

    Returns:
        (list_tools, call_tool) async handler pair. Call failures
            become error results, never exceptions.
    """
    engines = {}
    submitted_arguments = {}

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
                    and params.name != "run_job"
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
            if (
                project_dir is not None
                and params.name in OPERATIONS
                and params.name != "run_job"
                and isinstance(result, dict)
                and "run_id" in result
            ):
                submitted_arguments[result["run_id"]] = arguments
            if (
                project_dir is not None
                and params.name == "run_job"
                and isinstance(result, dict)
                and result.get("state") == "completed"
                and "run_id" in result
            ):
                write_evidence(
                    project_dir, engine, [result],
                    submitted_arguments.pop(result["run_id"], {}),
                )
        except _ENGINE_ERRORS as exc:
            return _error(exc.code, str(exc),
                           getattr(exc, "fields", None))
        return CallToolResult(content=[TextContent(
            type="text", text=json.dumps(result))])

    return _list_tools, _call_tool


def build_server(engine_factory, project_scope=None, project_dir=None):
    """Build the MCP server with list/call handlers attached.

    Args:
        engine_factory: Callable turning a project id into an
            engine.
        project_scope: Optional scope enforced on every call.
        project_dir: Optional project folder for source
            confinement and run evidence.

    Returns:
        Configured MCP server (stdio wiring stays in main).
    """
    list_handler, call_handler = make_handlers(engine_factory,
                                               project_scope, project_dir)
    return Server("rocket-engine",
                  on_list_tools=list_handler,
                  on_call_tool=call_handler)


def load_constraints(project_dir):
    """Read run_spice targets from the project's constraints.yaml.

    Args:
        project_dir: Project folder holding constraints.yaml.

    Returns:
        {metric: {min|max, unit[, expr, control]}} mapping (`>=`
        is min, `<=` is max, `==` carries no bound), or None when
        the file is missing.
    """
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
    from mcp.types import CallToolRequestParams

    created = {}

    def factory(pid):
        if pid not in created:
            created[pid] = engine_factory(pid)
        return created[pid]

    _, call = make_handlers(factory, args.project, args.project_dir)

    def invoke(name, arguments):
        result = asyncio.run(call(None, CallToolRequestParams(name=name, arguments=arguments)))
        return result.is_error, json.loads(result.content[0].text)

    failed, body = invoke(args.call, json.loads(args.args))
    if (
        not failed
        and args.call in OPERATIONS
        and "run_id" in body
        and "verdict" not in body
    ):
        failed, body = invoke("run_job", {"run_id": body["run_id"]})
        if not failed and "run_id" in body:
            failed, body = invoke("get_job_status", {"run_id": body["run_id"]})
    if (
        not failed
        and args.call in OPERATIONS
        and args.project_dir is not None
        and "run_id" in body
        and body.get("state") == "completed"
    ):
        engine = created.get(args.project)
        if engine is not None:
            write_evidence(args.project_dir, engine, [body], json.loads(args.args))
    print(json.dumps(body))
    return 1 if failed else 0


def main(argv=None):
    """Serve the MCP stdio server until stdin closes.

    Args:
        argv: CLI vector: --project binds the project id (fills
            project_id/expected_revision), --project-dir confines
            run_spice sources and records evidence,
            --call/--args run one operation through the same
            handlers, then its run_job and status, and exit.

    Returns:
        Process exit code (0 on a clean stdio shutdown, or a
        successful one-shot call).
    """
    from ...composition import Engine

    parser = argparse.ArgumentParser(prog="rocket-engine-mcp")
    parser.add_argument(
        "--project", help="bind to this project id (fills project_id/expected_revision)"
    )
    parser.add_argument(
        "--project-dir", help="project folder; run_spice targets come from its constraints.yaml"
    )
    parser.add_argument(
        "--call", help="run one operation through the same handlers, print its job status, exit"
    )
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
