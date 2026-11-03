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
them. The same file names the PDK (`pdk:`); every run_spice the bound
server admits carries that pin. Finished runs are recorded under
results/engine-runs for IDE and agent alike.
"""

import argparse
import asyncio
import json
import math
import shutil
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
from ...interfaces.errors import ContractError
from ...interfaces.paths import slugify
from ...interfaces.pdks import list_pdks, resolve_engine_root
from ...interfaces.vocabulary import OPERATIONS, QUERIES
from ...project.errors import ProjectError
from ..errors import AdapterError
from . import McpTransport

_ENGINE_ERRORS = (AdapterError, ProjectError, ExecutionError)

TRUST_NOTE = (
    "Local-only trust: this MCP server speaks stdio to the local "
    "harness under OS identity, with no auth step because there is "
    "no second party — no tokens, no broker, no listener, no remote "
    "execution, no multi-user. Human Run on the displayed cell is the "
    "approval; the harness edge (rocket-fuel client permissions) owns "
    "ask/deny, never this adapter. localhost-only, no auth, same "
    "caller-blind API as every other transport (ADR-006 applies to "
    "the HTTP adapter; stdio needs no boundary because it cannot "
    "leave the machine)."
)


# Grandfathered override: python_execute keeps its richer hand
# validation schema (types, bounds, mode oneOf) until API-V1-CLIENTS
# retires this wire. Every other tool derives its schema from the
# api_spec generator — never add a second entry here.
_TOOL_SCHEMAS = {
    "python_execute": MCP_INPUT_SCHEMA,
}


#: Arguments that are lists. The generated schemas carry only descriptions, so
#: a model can't tell, and often sends them as text.
_LIST_ARGUMENTS = ("sources", "analyses", "measurements")


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
    from ...composition import (
        ENGINE_OP_METHODS,
        QUERY_ENGINE_METHODS,
        QUERY_METHODS,
        Engine,
    )
    from ...project.service import ProjectService

    solvers = _help_engine().solvers_for(name)
    if solvers:
        return _summary_of(next(iter(solvers.values())))
    op_method = ENGINE_OP_METHODS.get(name)
    if op_method is not None:
        return _summary_of(getattr(Engine, op_method))
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


def _decode_list_arguments(arguments):
    """Accept a list argument sent as JSON text or as one bare string.

    Models often send lists this way, and iterating the string would read
    it one character at a time.

    Args:
        arguments: Tool call arguments.

    Returns:
        The arguments with each known list argument as a list.
    """
    decoded = dict(arguments)
    for key in _LIST_ARGUMENTS:
        value = decoded.get(key)
        if not isinstance(value, str):
            continue
        try:
            parsed = json.loads(value)
        except ValueError:
            parsed = value
        decoded[key] = parsed if isinstance(parsed, list) else [parsed]
    return decoded


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


#: Host-execution opt-in surface (I19): there is none yet.
#:
#: The MCP wire exposes cataloged engine operations and read
#: queries only; host shells first among them are rejected, never
#: routed (McpTransport.host_execution_enabled stays False). Any
#: future host-execution tool MUST arrive behind an explicit,
#: named opt-in surface (engine flag plus project scope) — never
#: as a silent tool. Until that decision lands, this constant pins
#: the default-deny posture against drift.
HOST_EXECUTION_OPT_IN = None


def _confine_files(arguments, project_dir):
    """Resolve run_spice sources inside the project and fix the workdir.

    Thin delegate over the engine-side confinement every transport
    shares (Engine.confine_spice_arguments): identical sources,
    identical workdir, identical refusal shapes on every transport.
    """
    from ...composition import Engine

    confined = Engine.confine_spice_arguments(arguments, project_dir)
    arguments.clear()
    arguments.update(confined)


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


def _finite(value):
    """Replace NaN and infinities with None so a reply is valid JSON.

    A perfect optical null is -inf dB; JSON has no infinity and browsers
    reject Python's `-Infinity`, so it travels as null.

    Args:
        value: Any JSON-shaped value.

    Returns:
        The same value with every non-finite float replaced by None.
    """
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: _finite(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_finite(item) for item in value]
    return value


def _keep_datasets(root, folder, engine, run_id):
    """Keep a run's waveforms and spectra next to its record.

    Args:
        root: Resolved project folder.
        folder: Evidence folder inside the project.
        engine: Engine the run executed on.
        run_id: Run whose datasets to keep.

    Returns:
        List of {analysis, path} mappings relative to the project.
    """
    kept = []
    # Under the run id, so the next run can't overwrite them. A second fetch
    # of the run finds them already moved.
    for dataset in engine.datasets(run_id) if hasattr(engine, "datasets") else []:
        target = folder / f"{run_id}-{dataset['analysis']}.raw"
        source = Path(dataset["path"])
        if source.is_file():
            shutil.move(str(source), target)
        if target.is_file():
            kept.append({"analysis": dataset["analysis"], "path": str(target.relative_to(root))})
    spectra = engine.spectra(run_id) if hasattr(engine, "spectra") else []
    if spectra:
        target = folder / f"{run_id}-optical.json"
        target.write_text(json.dumps(_finite(spectra), allow_nan=False), encoding="utf-8")
        kept.append({"analysis": "optical", "path": str(target.relative_to(root))})
    return kept


def write_evidence(project_dir, engine, outcomes, arguments):
    """Persist finished runs under results/engine-runs/<run_id>.json.

    Waveform datasets (ngspice ASCII rawfiles) are kept as
    <run_id>-<analysis>.raw, optical spectra as <run_id>-optical.json.

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
            "datasets": _keep_datasets(root, folder, engine, outcome["run_id"]),
        }
        (folder / f"{outcome['run_id']}.json").write_text(
            json.dumps(_finite(record), indent=2, allow_nan=False), encoding="utf-8"
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
            confined inside it, targets and the PDK pin load from
            its constraints.yaml, and finished runs are recorded
            under its results/engine-runs.

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
        arguments = _decode_list_arguments(params.arguments or {})
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
                # Read per call so a constraints.yaml edit applies without a restart.
                pin = load_pdk_pin(project_dir)
                if pin is not None:
                    arguments["pdk"] = pin
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
            type="text", text=json.dumps(_finite(result), allow_nan=False))])

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


def load_pdk_pin(project_dir):
    """Resolve the project's PDK pin from its constraints.yaml.

    `pdk: <id>` pins the one revision registered under that id;
    `pdk: {id, revision}` is taken as written (the solver checks it
    against the store when it runs). `none`, an empty value or no
    `pdk` key means generic models.

    Args:
        project_dir: Project folder holding constraints.yaml.

    Returns:
        {"id", "revision"} pin for run_spice, or None when the
        project names no PDK or has no constraints.yaml.

    Raises:
        AdapterError: unknown_pdk when the id is not registered on
            this machine; invalid_command for a malformed value or
            an id with several revisions; a store error's own code
            when the store cannot be read.

    Caution:
        Never falls back to generic models when a named PDK cannot
        be pinned: a silent fallback would score the design against
        the wrong devices.
    """
    path = Path(project_dir) / "constraints.yaml"
    if not path.is_file():
        return None
    data = YAML(typ="safe").load(path.read_text(encoding="utf-8")) or {}
    value = data.get("pdk")
    if value is None or (isinstance(value, str) and value.strip().lower() in ("", "none")):
        return None
    if isinstance(value, dict):
        pin = {key: value.get(key) for key in ("id", "revision")}
        if not all(isinstance(part, str) and part for part in pin.values()):
            raise AdapterError(
                "invalid_command", f"constraints.yaml pdk needs id and revision: {value!r}."
            )
        return pin
    if not isinstance(value, str):
        raise AdapterError(
            "invalid_command",
            f"constraints.yaml pdk must be an id or {{id, revision}}: {value!r}.",
        )
    name = value.strip()
    try:
        slug = slugify(name)
        registered = list_pdks() if resolve_engine_root().is_dir() else []
    except ContractError as exc:
        raise AdapterError(exc.code, str(exc)) from exc
    matches = [entry for entry in registered if slugify(entry["id"]) == slug]
    if len(matches) == 1:
        return {"id": matches[0]["id"], "revision": matches[0]["revision"]}
    if matches:
        revisions = ", ".join(entry["revision"] for entry in matches)
        raise AdapterError(
            "invalid_command",
            f"PDK {name} has several revisions ({revisions}); pin one in "
            f"constraints.yaml as pdk: {{id: {name}, revision: <revision>}}.",
        )
    known = ", ".join(f"{entry['id']} {entry['revision']}" for entry in registered) or "none"
    raise AdapterError(
        "unknown_pdk",
        f"PDK {name} is not registered with Rocket Engine on this machine "
        f"(registered: {known}). Register it with scripts/install.sh --pdk-only.",
    )


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
        "--project-dir",
        help="project folder; run_spice targets and PDK pin come from its constraints.yaml",
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


#: Lifecycle kinds that ride the progress channel instead of a
#: plain message notification.
_PROGRESS_KINDS = frozenset({"job_progress"})


def build_lifecycle_notification(event):
    """Build one MCP push notification for a lifecycle event.

    Append-only PUSH-EVENTS seam: existing list/call handlers
    are untouched — this only translates the runtime event log
    into JSON-RPC notifications agents can subscribe to.

    Args:
        event: Lifecycle event with seq, kind, and run_id.

    Returns:
        JSON-RPC notification with jsonrpc, method
            (notifications/progress for progress, else
            notifications/<kind>), and the event as params.
    """
    kind = event.get("kind", "message")
    if kind in _PROGRESS_KINDS:
        method = "notifications/progress"
    else:
        method = f"notifications/{kind}"
    return {"jsonrpc": "2.0", "method": method,
            "params": dict(event)}


def subscribe_runtime(runtime, send):
    """Push every lifecycle event to one subscriber.

    Append-only PUSH-EVENTS seam: registers a listener on the
    runtime; the list/call path keeps serving polling clients
    unchanged.

    Args:
        runtime: EngineRuntime emitting lifecycle events.
        send: Called synchronously with each built
            notification mapping.

    Returns:
        Unsubscribe callable removing the listener.
    """
    return runtime.add_listener(
        lambda event: send(build_lifecycle_notification(event)))
