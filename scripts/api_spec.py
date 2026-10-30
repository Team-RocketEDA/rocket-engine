"""API contract generator: docstrings in, reference + schemas + help out.

ADR-003 makes handler docstrings the contract source: one text feeds
the human API reference, per-operation JSON Schemas (IDE types, fuel
stubs), and MCP tool descriptions plus help. This script derives all
three from code with stdlib-only AST parsing (no imports, no install):

- docs/engine-api.md — human reference (generated output + pointer,
  never hand-edited; freshness-pinned by tests/test_api_spec.py),
- docs/api-schema.json — JSON Schema per operation/query,
- docs/api-help.json — MCP help text (identical to the reference
  section bodies: docs == agent help text, the double-use).

Contract sources read (all AST, all code):
- interfaces/vocabulary.py — OPERATIONS/QUERIES names,
- composition.py — _solvers map (op -> tool -> adapter),
  QUERY_METHODS (query -> ProjectService method), _CRUD_OPERATIONS,
- adapter class docstrings — per-tool summary, prose, `Job keys:`,
  Caution (migrated docs/engine-api.md endpoint prose),
- adapter preflight/execute/parse docstrings — Returns/Raises,
- ProjectService method docstrings — CRUD/query Args/Returns/Raises,
- Engine._run_queued docstring — run_job contract.

Conventions honored: `Job keys:` / `Request keys:` sections list
`name:` or `name (required):` items; envelope plumbing
(request_id/command_text) is excluded from CRUD/query schemas;
expected_revision is injected into solver-op schemas from
ProjectService.submit's own arg text.

Usage: python scripts/api_spec.py [--write|--check] (default --check).
"""

import argparse
import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"

# Method params that are envelope plumbing, never operation arguments.
_PLUMBING = frozenset({"request_id", "command_text"})

# Query args the Engine dispatch layer defaults (Engine.submit path),
# so they are optional even though the ProjectService signature
# requires them. Cites Engine._query_events_since (cursor defaults 0).
_QUERY_DEFAULTS = {"get_events_since": {"cursor"}}

_SECTION_HEADERS = frozenset(
    {"Args:", "Returns:", "Raises:", "Job keys:", "Request keys:"}
)

_UNWIRED_TEMPLATE = "Declared {kind} `{name}`; no handler wired yet."


def _tree(rel):
    return ast.parse((SRC / rel).read_text(encoding="utf-8"))


def _str_set(node):
    if isinstance(node, ast.Call) and node.args:
        items = node.args[0]
    else:
        items = node
    if isinstance(items, (ast.Set, ast.List, ast.Tuple)):
        return {e.value for e in items.elts if isinstance(e, ast.Constant)}
    return set()


def _str_dict(node):
    if not isinstance(node, ast.Dict):
        return {}
    return {
        k.value: v.value
        for k, v in zip(node.keys, node.values)
        if isinstance(k, ast.Constant) and isinstance(v, ast.Constant)
    }


def _module_assign(tree, name):
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = [
                t.id for t in node.targets if isinstance(t, ast.Name)
            ]
            if name in targets:
                return node.value
    return None


def load_vocabulary(root=None):
    """(OPERATIONS, QUERIES) name sets from vocabulary.py."""
    root = Path(root) if root is not None else SRC
    tree = ast.parse((root / "interfaces" / "vocabulary.py").read_text())
    operations, queries = set(), set()
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if "OPERATIONS" in targets:
            operations = _str_set(node.value)
        if "QUERIES" in targets:
            queries = _str_set(node.value)
    return operations, queries


def crud_operations(root=None):
    """CRUD-immediate op names from composition._CRUD_OPERATIONS."""
    root = Path(root) if root is not None else SRC
    tree = ast.parse((root / "composition.py").read_text())
    return _str_set(_module_assign(tree, "_CRUD_OPERATIONS"))


def query_methods(root=None):
    """Wired query -> ProjectService method from QUERY_METHODS."""
    root = Path(root) if root is not None else SRC
    tree = ast.parse((root / "composition.py").read_text())
    return _str_dict(_module_assign(tree, "QUERY_METHODS"))


def solver_map(root=None):
    """{op: [(tool, adapter_class, module_rel)]} from Engine._solvers.

    Tool order is registration order (first = deck.tool default);
    adapter modules resolve through composition's from-imports.
    """
    root = Path(root) if root is not None else SRC
    tree = ast.parse((root / "composition.py").read_text())
    locations = {}
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom) or node.level != 1:
            continue
        parts = (node.module or "").split(".")
        if len(parts) == 2 and parts[0] == "adapters":
            rel = f"adapters/{parts[1]}/__init__.py"
            for alias in node.names:
                locations[alias.asname or alias.name] = rel
    solvers = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != "Engine":
            continue
        for child in node.body:
            if not isinstance(child, ast.FunctionDef):
                continue
            for sub in ast.walk(child):
                if not isinstance(sub, ast.Assign):
                    continue
                targets = [
                    t.attr for t in sub.targets
                    if isinstance(t, ast.Attribute)
                ]
                if "_solvers" not in targets or not isinstance(
                    sub.value, ast.Dict
                ):
                    continue
                for op_key, tools_node in zip(sub.value.keys, sub.value.values):
                    if not isinstance(op_key, ast.Constant):
                        continue
                    entries = []
                    if isinstance(tools_node, ast.Dict):
                        for tool_key, adapter in zip(
                            tools_node.keys, tools_node.values
                        ):
                            if (
                                isinstance(tool_key, ast.Constant)
                                and isinstance(adapter, ast.Call)
                                and isinstance(adapter.func, ast.Name)
                            ):
                                cls = adapter.func.id
                                entries.append(
                                    (tool_key.value, cls, locations.get(cls))
                                )
                    solvers[op_key.value] = entries
    return solvers


def _find_node(tree, qualname):
    node = None
    for part in qualname.split("."):
        body = tree.body if node is None else node.body
        node = next(
            (
                c for c in body
                if isinstance(c, (ast.ClassDef, ast.FunctionDef,
                                  ast.AsyncFunctionDef))
                and c.name == part
            ),
            None,
        )
        if node is None:
            return None
    return node


def doc_of(rel, qualname, root=None):
    """Raw docstring for module relpath + qualname (None when absent)."""
    root = Path(root) if root is not None else SRC
    tree = ast.parse((root / rel).read_text(encoding="utf-8"))
    node = _find_node(tree, qualname)
    return ast.get_docstring(node) if node is not None else None


def signature_required(rel, qualname, root=None):
    """Params without defaults (minus self/plumbing) from the AST."""
    root = Path(root) if root is not None else SRC
    tree = ast.parse((root / rel).read_text(encoding="utf-8"))
    node = _find_node(tree, qualname)
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return []
    args = node.args
    positional = list(args.posonlyargs) + list(args.args)
    skip = len(positional) - len(args.defaults)
    required = [a.arg for i, a in enumerate(positional) if i < skip]
    for arg, default in zip(args.kwonlyargs, args.kw_defaults):
        if default is None:
            required.append(arg.arg)
    return [n for n in required if n not in _PLUMBING and n != "self"]


def _section_block(lines, header):
    try:
        start = next(
            i for i, line in enumerate(lines) if line.strip() == header
        )
    except StopIteration:
        return []
    block = []
    for line in lines[start + 1:]:
        stripped = line.strip()
        if stripped in _SECTION_HEADERS or stripped.startswith("Caution:"):
            break
        if stripped and not line.startswith((" ", "\t")):
            break
        block.append(line)
    return block


def _parse_items(block, required_marker=False):
    """[(name, required, description)] from an Args/keys block."""
    items = []
    current = None
    for line in block:
        stripped = line.strip()
        if not stripped:
            continue
        name, sep, desc = stripped.partition(":")
        is_item = (
            bool(sep)
            and line.startswith("    ")
            and not line.startswith("        ")
            and " " not in name.strip().replace(" (required)", "")
            and name.strip() != ""
        )
        if is_item:
            tokens = name.strip().split()
            item_name = tokens[0]
            if not item_name.replace("_", "").isalnum():
                is_item = False
        if is_item:
            required = required_marker and "(required)" in name
            current = [item_name, required, desc.strip()]
            items.append(current)
        elif current is not None:
            current[2] = (current[2] + " " + stripped).strip()
    return [(n, r, d) for n, r, d in items]


def parse_docstring(doc):
    """Split a Google docstring into summary/prose/sections."""
    if not doc:
        return {
            "summary": "", "prose": "", "args": [], "returns": "",
            "raises": "", "cautions": [], "job_keys": [],
        }
    lines = doc.splitlines()
    summary = lines[0].strip() if lines else ""
    prose_lines = []
    for line in lines[1:]:
        stripped = line.strip()
        if stripped in _SECTION_HEADERS or stripped.startswith("Caution:"):
            break
        prose_lines.append(line)
    prose = "\n".join(prose_lines).strip()
    cautions = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("Caution:"):
            text = stripped[len("Caution:"):].strip()
            for cont in lines[i + 1:]:
                if cont.strip() and cont.startswith((" ", "\t")):
                    text += " " + cont.strip()
                else:
                    break
            cautions.append(text)
    keys = _parse_items(
        _section_block(lines, "Job keys:") or
        _section_block(lines, "Request keys:"),
        required_marker=True,
    )
    return {
        "summary": summary,
        "prose": prose,
        "args": _parse_items(_section_block(lines, "Args:")),
        "returns": " ".join(
            ln.strip() for ln in _section_block(lines, "Returns:")
            if ln.strip()
        ),
        "raises": " ".join(
            ln.strip() for ln in _section_block(lines, "Raises:")
            if ln.strip()
        ),
        "cautions": cautions,
        "job_keys": keys,
    }


def _handler_ref(rel, qualname):
    return "rocket_engine." + rel[:-len("/__init__.py")].replace(
        "/", "."
    ) + "." + qualname if rel.endswith("/__init__.py") else (
        "rocket_engine." + rel[:-3].replace("/", ".") + "." + qualname
    )


def _expected_revision_text(root):
    parsed = parse_docstring(doc_of(
        "project/service.py", "ProjectService.submit", root=root
    ))
    for name, _required, desc in parsed["args"]:
        if name == "expected_revision":
            return desc
    return "Revision the writer read."


def endpoint_spec(name, root=None):
    """Contract record for one cataloged operation/query name."""
    root = root if root is not None else SRC
    operations, queries = load_vocabulary(root)
    kind = (
        "operation" if name in operations
        else "query" if name in queries
        else "unknown"
    )
    solvers = solver_map(root)
    crud = crud_operations(root)
    qmethods = query_methods(root)
    spec = {"name": name, "kind": kind, "wired": False, "handlers": []}
    if name in solvers:
        spec["wired"] = True
        spec["tools"] = [
            {"tool": tool, "adapter": cls, "default": i == 0}
            for i, (tool, cls, _rel) in enumerate(solvers[name])
        ]
        for _tool, cls, rel in solvers[name]:
            spec["handlers"].append(_handler_ref(rel, cls))
        first = solvers[name][0]
        spec["summary"] = parse_docstring(
            doc_of(first[2], first[1], root=root)
        )["summary"]
    elif name in crud:
        spec["wired"] = True
        spec["handlers"] = [
            "rocket_engine.project.service.ProjectService." + name
        ]
        spec["summary"] = parse_docstring(doc_of(
            "project/service.py", "ProjectService." + name, root=root
        ))["summary"]
    elif name == "run_job":
        spec["wired"] = True
        spec["handlers"] = [
            "rocket_engine.composition.Engine.run",
            "rocket_engine.composition.Engine._run_queued",
        ]
        spec["summary"] = parse_docstring(doc_of(
            "composition.py", "Engine._run_queued", root=root
        ))["summary"]
    elif name in qmethods:
        spec["wired"] = True
        spec["handlers"] = [
            "rocket_engine.project.service.ProjectService."
            + qmethods[name]
        ]
        spec["summary"] = parse_docstring(doc_of(
            "project/service.py", "ProjectService." + qmethods[name],
            root=root,
        ))["summary"]
    else:
        spec["summary"] = _UNWIRED_TEMPLATE.format(kind=kind, name=name)
    return spec


def _arguments_block(items):
    if not items:
        return "Arguments:\n\n- _(none)_"
    rendered = ["Arguments:", ""]
    for name, required, desc in items:
        marker = " (required)" if required else ""
        rendered.append(f"- `{name}`{marker}: {desc}")
    return "\n".join(rendered)


def _optional_block(title, text):
    if not text:
        return ""
    return f"{title}:\n\n{text}"


def _join_blocks(blocks):
    return "\n\n".join(b for b in blocks if b) + "\n"


def section_body(name, root=None):
    """Reference section body for one name (help text source)."""
    root = root if root is not None else SRC
    spec = endpoint_spec(name, root=root)
    solvers = solver_map(root)
    crud = crud_operations(root)
    qmethods = query_methods(root)
    if name in solvers:
        return _solver_section(name, solvers[name], root)
    if name in crud or name in qmethods:
        method = name if name in crud else qmethods[name]
        return _method_section(name, method, root)
    if name == "run_job":
        parsed = parse_docstring(doc_of(
            "composition.py", "Engine._run_queued", root=root
        ))
        return _join_blocks([
            spec["summary"],
            "Handler: `rocket_engine.composition.Engine.run` (phase 2 "
            "executes an admitted request; submit admits first).",
            _arguments_block(parsed["job_keys"]),
            _optional_block("Returns", parsed["returns"]),
            _optional_block("Raises", parsed["raises"]),
        ])
    return (
        spec["summary"]
        + "\n\n`Engine.submit` raises `unsupported_operation` for this "
        "name; it becomes callable when a solver registers or a query "
        "path wires it.\n"
    )


def _solver_section(name, entries, root):
    first = entries[0]
    summary = parse_docstring(
        doc_of(first[2], first[1], root=root)
    )["summary"]
    tools = ", ".join(
        f"`{tool}`" + (" (default)" if i == 0 else "")
        for i, (tool, _cls, _rel) in enumerate(entries)
    )
    handlers = ", ".join(
        f"`{_handler_ref(rel, cls)}`" for _t, cls, rel in entries
    )
    parts = [
        summary,
        f"Tools: {tools} — `deck.tool` selects; a missing tool falls "
        "back to the default, an unknown tool fails "
        "`unsupported_operation` before anything runs.",
        f"Handlers: {handlers}.",
    ]
    revision_text = _expected_revision_text(root)
    for tool, cls, rel in entries:
        parsed = parse_docstring(doc_of(rel, cls, root=root))
        preflight = parse_docstring(doc_of(
            rel, f"{cls}.preflight", root=root
        ))
        execute = parse_docstring(doc_of(
            rel, f"{cls}.execute", root=root
        ))
        parse = parse_docstring(doc_of(rel, f"{cls}.parse", root=root))
        args = list(parsed["job_keys"]) + [
            ("expected_revision", False, revision_text)
        ]
        raises = "\n\n".join(
            t for t in (
                f"(preflight) {preflight['raises']}" if preflight["raises"] else "",
                f"(execute) {execute['raises']}" if execute["raises"] else "",
                f"(parse) {parse['raises']}" if parse["raises"] else "",
            ) if t
        )
        parts.extend([
            f"#### Tool `{tool}`",
            parsed["summary"],
            parsed["prose"],
            _arguments_block(args),
            _optional_block("Returns", parse["returns"]),
            _optional_block("Raises", raises),
            "\n".join(f"Caution: {c}" for c in parsed["cautions"]),
        ])
    return _join_blocks(parts)


def _method_section(name, method, root):
    parsed = parse_docstring(doc_of(
        "project/service.py", "ProjectService." + method, root=root
    ))
    required = set(signature_required(
        "project/service.py", "ProjectService." + method, root=root
    ))
    required -= _QUERY_DEFAULTS.get(name, set())
    args = [
        (n, n in required, d) for n, _r, d in parsed["args"]
        if n not in _PLUMBING
    ]
    return _join_blocks([
        parsed["summary"],
        "Handler: `rocket_engine.project.service.ProjectService."
        + method + "`.",
        parsed["prose"],
        _arguments_block(args),
        _optional_block("Returns", parsed["returns"]),
        _optional_block("Raises", parsed["raises"]),
        "\n".join(f"Caution: {c}" for c in parsed["cautions"]),
    ])


def build_help(root=None):
    """{name: {kind, wired, summary, text}} for MCP help."""
    root = root if root is not None else SRC
    operations, queries = load_vocabulary(root)
    help_texts = {}
    for name in sorted(operations | queries):
        spec = endpoint_spec(name, root=root)
        help_texts[name] = {
            "kind": spec["kind"],
            "wired": spec["wired"],
            "summary": spec["summary"],
            "text": section_body(name, root=root),
        }
    return help_texts


def build_schemas(root=None):
    """{"$schema", operations, queries} with a schema per name."""
    root = root if root is not None else SRC
    operations, queries = load_vocabulary(root)
    solvers = solver_map(root)
    crud = crud_operations(root)
    qmethods = query_methods(root)
    revision_text = _expected_revision_text(root)
    schemas = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "operations": {},
        "queries": {},
    }
    for name in sorted(operations):
        schemas["operations"][name] = _schema_for(
            name, "operation", solvers, crud, qmethods, revision_text, root
        )
    for name in sorted(queries):
        schemas["queries"][name] = _schema_for(
            name, "query", solvers, crud, qmethods, revision_text, root
        )
    return schemas


def _schema_for(name, kind, solvers, crud, qmethods, revision_text, root):
    spec = endpoint_spec(name, root=root)
    schema = {
        "name": name,
        "kind": kind,
        "wired": spec["wired"],
        "description": spec["summary"],
        "type": "object",
        "properties": {},
        "required": [],
        "handlers": spec["handlers"],
    }
    if name in solvers:
        tools = {}
        for tool, cls, rel in solvers[name]:
            parsed = parse_docstring(doc_of(rel, cls, root=root))
            props = {
                n: {"description": d} for n, _r, d in parsed["job_keys"]
            }
            props["expected_revision"] = {"description": revision_text}
            tools[tool] = {
                "adapter": _handler_ref(rel, cls),
                "properties": props,
                "required": [
                    n for n, r, _d in parsed["job_keys"] if r
                ],
            }
        schema["tools"] = tools
        primary = tools[solvers[name][0][0]]
        schema["properties"] = primary["properties"]
        schema["required"] = primary["required"]
        parse = parse_docstring(doc_of(
            solvers[name][0][2], solvers[name][0][1] + ".parse", root=root
        ))
        schema["returns"] = parse["returns"]
        return schema
    if name in crud or name in qmethods:
        method = name if name in crud else qmethods[name]
        parsed = parse_docstring(doc_of(
            "project/service.py", "ProjectService." + method, root=root
        ))
        required = set(signature_required(
            "project/service.py", "ProjectService." + method, root=root
        ))
        required -= _QUERY_DEFAULTS.get(name, set())
        schema["properties"] = {
            n: {"description": d} for n, _r, d in parsed["args"]
            if n not in _PLUMBING
        }
        schema["required"] = [
            n for n, _r, _d in parsed["args"]
            if n in required and n not in _PLUMBING
        ]
        schema["returns"] = parsed["returns"]
        schema["raises"] = parsed["raises"]
        return schema
    if name == "run_job":
        parsed = parse_docstring(doc_of(
            "composition.py", "Engine._run_queued", root=root
        ))
        schema["properties"] = {
            n: {"description": d} for n, _r, d in parsed["job_keys"]
        }
        schema["required"] = [n for n, r, _d in parsed["job_keys"] if r]
        schema["returns"] = parsed["returns"]
        schema["raises"] = parsed["raises"]
        return schema
    schema["returns"] = ""
    return schema


_PREAMBLE = """\
# Engine API (generated — do not hand-edit)

> Generated by `scripts/api_spec.py` from handler docstrings
> ([ADR-003](adr/003-docstring-generated-api-contract.md)). Endpoint
> prose lives in docstrings (see `AGENTS.md`); regenerate with
> `python scripts/api_spec.py --write`. Freshness-pinned by
> `tests/test_api_spec.py` — a hand edit fails the gate.

The engine is headless. This document is the complete data contract:
every operation, query, event, state, and result shape the UI can
depend on. No UI field may exist without a typed engine output defined
here or in `src/interfaces/`. Transports (`http`, `ipc`, `mcp`, `cli`)
carry identical commands — the shapes below never vary by caller.

Conventions: `ref` = `{scope, id, revision}` (scope `project` or
`global`). All lists are paginated with opaque `next_cursor`.
`artifact` = `{id, kind, relpath, mime, bytes, digest}`.
Items marked (proposed) extend the PRD and need its sign-off.

Machine companions (same generator run): `api-schema.json` carries a
JSON Schema per operation/query; `api-help.json` carries the MCP help
text, identical to the section bodies below.
"""

_APPENDIX = """\
## Appendix: envelopes, states, shapes, errors, transports

Generator-owned static text (transport and payload rules, not endpoint
prose — endpoint prose lives in the docstrings above).

### States and lifecycles

Readiness (per project × operation, from `get_capabilities`):
`ready` → executes; `blocked` (fixable, reason + missing items);
`unavailable` (env/tool down, retryable); `unsupported` (no backend
or deck — terminal for this config); `unknown` (never shipped).

Run lifecycle: `queued` → `running` → `completed` | `error` |
`cancelled`. Cancel is racy: cancelling a finished run truthfully
returns its terminal state, never a fake `cancelled`.

Check verdicts: `PASS` (all acceptance met) / `FAIL` (violations or
missed targets) / `NOT_RUN` (missing input, cancelled, unparsable, or
unsupported-required — always with `reason`) / `UNSUPPORTED`
(terminal for this config). Exit zero never implies PASS.

Freshness: evidence pins `snapshot_id`; later source edits mark it
`stale` (kept, flagged) rather than deleting it.

Events (SSE / stdio / MCP streams, ordered, cursor-resyncable):
`job_queued`, `job_finished`, `check_updated` carry
`{run_id, check_id, status, revision}`. `artifact_ready` (proposed)
carries artifact descriptors as files land. Console streams emit
`console_output` chunks plus `approval_requested` / `approval_resolved`
(proposed) for the trusted approval UI.

Ledger (LEDGER-DURABLE/I30, implemented): every accepted mutation
advances the project revision (`p12` → `p13` → …) and appends a
seq-ordered actor-attributed event to the durable log at
`projects/<id>/events.yaml` (`job_queued`, `run_completed`,
`run_failed` — `run_failed` means NOT_RUN; a FAIL verdict is a
completed run). Stale `expected_revision` fails `revision_conflict`
instead of merging. The ack carries the advanced `current_revision`
so writers follow the head. Read back via the `get_events_since`
query (`{cursor, require_contiguous_from?}` → `{project_id,
events, cursor}`); `resync_required` means the contiguity demand
fell outside retained history — re-read the snapshot plus the full
log and reset the cursor. Retention keeps the newest 10,000 events
per project, oldest-first trim; see `docs/storage-policy.md`.

CRUD (CRUD-API/I31, implemented): uniform document ops over
`(project, path)` — queries `list_projects` / `list_docs` /
`read_doc`, immediate mutations `create_project` / `write_doc` /
`delete_doc` / `apply_mutations` (no queue, no solver; the CLI
`run` spelling delegates to the same path). Writes gate on
`expected_revision` and return the new revision plus the appended
event (`doc_written`, `doc_deleted`, `mutations_applied`);
`apply_mutations` lands every mutation under one new revision or
lands none, naming the failed document. Components and scripts are
conventional paths (`components/…`, `scripts/…`) — no per-content
verbs. Every mutation response carries `actor`, `diff_summary`,
`revision_transition {from, to}`, and `rewind_handle
{project_id, revision, request_id}` for the approval UI.
`create_project` takes `new_project_id` (the envelope keeps the
bound project) and starts the new ledger clean at `p12`.
`delete_project` and `run_script` are explicitly out of scope.
Errors: `unknown_document`, `project_exists`, `invalid_project`,
`invalid_path` / `path_escape` alongside the ledger codes.

Rewind (REWIND, implemented): restorable per-revision snapshots of
managed bytes. Every accepted mutation stores its previous revision
(when missing) and its new revision under
`snapshots/<revision>/` (in-memory map without an engine root);
the immediate `rewind` operation takes `{target_revision,
expected_revision}` and restores the target bytes byte-identically
under a new head revision with a single `project_rewound` event —
history stays append-only, the head never moves backward. `runs/`,
the ledger, and the snapshots themselves are never restored or
deleted. Responses carry the CRUD approval-UI fields plus
`target_revision` and `external_files`; linked projects bind
`linked_root`, and rewind lists caller files outside `.rocket/` as
left untouched without writing to the caller tree. Errors:
`unknown_revision` for a target with no snapshot,
`invalid_command` for a target that equals the live head,
alongside the ledger codes.

Earlier prose named controls (`cancel_run`, `approve_console`,
`submit_revision`) that are not in `interfaces/vocabulary.py` and
have no handler; they are not part of this contract.

### Common result envelope

Every check result carries: `run_id`, `check_id`, `status`,
`project_revision`, `snapshot_id`, `tool` {adapter, version, deck
digest}, `started/finished_at`, `summary` {counts by severity},
`measurements[]`, `findings[]`, `artifacts[]`, `log_excerpt` +
full-log artifact ref, `freshness`. A finding is
`{id, severity, rule, message, location?, actual?, limit?}` where
location may be a file span, a device path, or a bbox whose key names
its units: `bbox_um` for metric decks, `bbox_lambda` for lambda decks.
Never infer units from the operation — read the key. A
measurement is `{name, value, unit, target?, margin?, status}` —
`margin` is always engine-computed, never left to the UI.

### Per-family data shapes

- HDL sim: `{passed, failed_asserts[], coverage_pct, seeds[], cycles,
  wave}` where `wave` is an FST artifact (+VCD on request).
- Formal: `{engine, depth, result: proven|bounded|cex|timeout,
  trace_artifact?}`; mutation quality `{score, killed/total}`.
- Digital flow: `stages[] {name, status, occurrences[],
  disabled_reasons[]}` plus `area_um2, power_mw, wns_ns, tns_ns` and
  GDS/LEF/SDF/SPEF artifacts. Parent completion never implies all
  checks passed — the UI must render per-stage states.
- SPICE: `op {node: {v,i}}`, `ac[] {f, mag_db, phase_deg}`,
  `tran {t[], signals{}}` (downsampled + full artifact),
  `corners[] {name, measurements[]}`, `mc {runs, mean, std, yield}`.
- Photonic: `spectra[] {wavelength_nm[], transmission_db[]}`,
  `s_params {ports[], matrix_ref}`, scalar measurements as above.
- EM/thermal: `{converged, iterations, s_params?, modes[]?,
  hotspots[] {location, value, unit}, peak, mean, margins{}}`.
- DRC: `{total, violations[] {rule, message, location{bbox_um |
  bbox_lambda, area?}}}`; FAIL iff any error-severity violation.
  LVS: `{match, layout_devices, schematic_devices, mismatches[]}`.
  Extraction: `{netlist_artifact, devices, nets, coverage_pct}`.
- Console: `cells[] {seq, code_ref, stdout, stderr, state}`,
  `effects[]` (runs spawned, files staged — never silent writes),
  approvals `{approval_id, state, binding_hash}`. A live approval
  binds code + history cursor + env digest + revision: any drift at
  admit time fails `approval_invalid`, and console reset kills every
  outstanding approval.
- Library: `pdks[] {id, revision, domains, readiness{}}`,
  `components[] {ref, status}` where `status` includes `UNVERIFIED`
  for unproven reuse; `dependency_closure[]`.

### Artifact kinds

`wave` (FST/VCD), `layout` (GDS/OAS + preview PNG), `schematic`
(SVG/PNG render), `netlist` (SPICE/CDL/Verilog), `report`
(TXT/JSON), `plot` (PNG + source CSV), `dataset` (CSV/NPY),
`trace` (formal/VCD), `log` (bounded excerpt inline, full file).
The engine serves bytes by `relpath`; RocketIDE renders and caches.

Dual-representation rule: anything a human would read as a graph
MUST ship as a full-fidelity `dataset` the agent can script against
(columnar, units in metadata, no silent downsampling) plus an
optionally generated `plot` image for visual intuition. Every `plot`
links its source `dataset`. Inline previews MUST declare `n_total`
vs `n_shown` and the downsampling method.

### Errors

Stable `code` + human `message` + `fields[]` when itemized:
`invalid_yaml`, `invalid_reference`, `missing_dependency`,
`incompatible_port`, `unsupported_operation`, `unsupported_check`,
`revision_conflict`, `request_conflict`, `resync_required`,
`approval_invalid`, `runner_unavailable`, plus adapter-layer
`cross_project_denied` and `invalid_command`. Unknown enum values
and fields are rejected, never ignored.

### Transports and versioning

Same command over HTTPS+SSE, framed stdio, MCP `tools/call`, and
the CLI mirror. Envelope: `{schema, request_id, project_id,
expected_revision, operation, target?, arguments}` → ack
`{run_id, snapshot_id, state}` → events → result. Resubmitting the
same envelope id returns the identical ack (MCP passes the JSON-RPC
id as `request_id`). Contract changes are additive and versioned
(`rocketeda/tooling/vX.Y`);
renames are breaking and need a major bump plus migration notes.

### Agent analytical access

The harness is an LLM: sequential data is for scripts first, eyes
second. Datasets are analysis-ready (see above); the design profile
guarantees numpy/scipy/pandas/matplotlib so agents can fit, FFT,
and diff against models — e.g. fit a SPICE transient to the target
s-domain step response and report stray as margins.

Console permission is two-tier (proposed, needs PRD sign-off):
standing user permission covers the analysis sandbox only
(read-only project data + scratch, no host/network/evidence
writes); anything effectful keeps per-action approval binding.
Reference workflow: the analog s-domain loop in
`docs/prd-feedforward.md` F7.
"""


def render_reference(root=None):
    """Full docs/engine-api.md content, derived from docstrings."""
    root = root if root is not None else SRC
    operations, queries = load_vocabulary(root)
    solvers = solver_map(root)
    qmethods = query_methods(root)
    lines = [_PREAMBLE.rstrip(), "", "## Operations", ""]
    lines.append("| Operation | Wired | Tools | Summary |")
    lines.append("|---|---|---|---|")
    for name in sorted(operations):
        spec = endpoint_spec(name, root=root)
        wired = "yes" if spec["wired"] else "no"
        if name in solvers:
            tools = ", ".join(
                f"`{tool}`" + (" (default)" if i == 0 else "")
                for i, (tool, _c, _r) in enumerate(solvers[name])
            )
        else:
            tools = "—"
        lines.append(f"| `{name}` | {wired} | {tools} | {spec['summary']} |")
    lines.extend(["", "## Queries", ""])
    lines.append("| Query | Wired | Handler | Summary |")
    lines.append("|---|---|---|---|")
    for name in sorted(queries):
        spec = endpoint_spec(name, root=root)
        wired = "yes" if spec["wired"] else "no"
        handler = f"`{spec['handlers'][0]}`" if spec["handlers"] else "—"
        lines.append(f"| `{name}` | {wired} | {handler} | {spec['summary']} |")
    lines.extend(["", "## Operation reference", ""])
    for name in sorted(operations):
        lines.append(f"### {name}")
        lines.append("")
        lines.append(section_body(name, root=root).rstrip())
        lines.append("")
    lines.extend(["## Query reference", ""])
    for name in sorted(queries):
        lines.append(f"### {name}")
        lines.append("")
        lines.append(section_body(name, root=root).rstrip())
        lines.append("")
    lines.append(_APPENDIX.rstrip())
    lines.append("")
    return "\n".join(lines)


def _dumps(payload):
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def main(argv):
    """Regenerate (--write) or freshness-check (--check, default) outputs."""
    parser = argparse.ArgumentParser(description="API contract generator.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--write", action="store_true")
    group.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    outputs = {
        ROOT / "docs" / "engine-api.md": render_reference(),
        ROOT / "docs" / "api-schema.json": _dumps(build_schemas()),
        ROOT / "docs" / "api-help.json": _dumps(build_help()),
    }
    if args.write:
        for path, text in outputs.items():
            path.write_text(text, encoding="utf-8")
        return 0
    failures = [
        str(path) for path, text in outputs.items()
        if not path.is_file() or path.read_text(encoding="utf-8") != text
    ]
    for path in failures:
        print(f"stale generated output: {path} (run --write)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
