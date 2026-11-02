"""API spec generator: docstrings are the contract source (ADR-003).

scripts/api_spec.py derives the human reference, per-operation JSON
Schemas, and MCP help text from handler docstrings — one text, three
consumers. docs/engine-api.md is generated output (freshness-pinned
here, never hand-edited); MCP tool descriptions serve the same text
as the docs for every wired endpoint.
"""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_spec():
    # RED: scripts/api_spec.py does not exist yet.
    spec = importlib.util.spec_from_file_location(
        "api_spec", ROOT / "scripts" / "api_spec.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _wired_names():
    """Names Engine.submit serves, probed behaviorally (oracle).

    Wired = submit does anything other than raise
    unsupported_operation: an ack, data, or a different error
    (invalid_command for missing args still proves a handler).
    In-memory engine: queueing mutates nothing on disk.
    """
    from rocket_engine.composition import Engine
    from rocket_engine.execution.errors import ExecutionError
    from rocket_engine.interfaces.vocabulary import OPERATIONS, QUERIES
    from rocket_engine.project.errors import ProjectError

    engine = Engine("probe", actor="probe")
    wired = set()
    for name in sorted(OPERATIONS | QUERIES):
        try:
            engine.submit(
                {
                    "project_id": "probe",
                    "operation": name,
                    "arguments": {},
                    "request_id": f"probe-{name}",
                }
            )
        except ProjectError as exc:
            if exc.code != "unsupported_operation":
                wired.add(name)
        except ExecutionError:
            # A wired execution-backed query proving its handler.
            wired.add(name)
        else:
            wired.add(name)
    return wired


def _handler_summary(module_name, qualname):
    """First docstring line of a live handler (independent oracle)."""
    import importlib

    module = importlib.import_module(module_name)
    target = module
    for part in qualname.split("."):
        target = getattr(target, part)
    doc = target.__doc__
    assert doc, f"{module_name}.{qualname} carries no docstring"
    return doc.splitlines()[0].strip()


def _reference_section(reference, name):
    """Extract the `### name` section body from rendered reference."""
    marker = f"### {name}\n"
    start = reference.index(marker) + len(marker)
    hits = [
        c for c in (
            reference.find("\n### ", start),
            reference.find("\n## ", start),
        )
        if c != -1
    ]
    end = min(hits) + 1 if hits else len(reference)
    return reference[start:end].strip() + "\n"


def test_reference_covers_every_wired_operation_and_query():
    api_spec = _load_spec()
    reference = api_spec.render_reference()
    for name in sorted(_wired_names()):
        assert f"### {name}\n" in reference, name


def test_schemas_cover_every_wired_operation():
    from rocket_engine.interfaces.vocabulary import OPERATIONS

    api_spec = _load_spec()
    schemas = api_spec.build_schemas()
    wired_ops = sorted(set(OPERATIONS) & _wired_names())
    assert wired_ops != []
    for name in wired_ops:
        schema = schemas["operations"][name]
        assert schema["type"] == "object", name
        assert schema["description"], name
        assert isinstance(schema["properties"], dict), name


def test_help_text_matches_reference_section():
    api_spec = _load_spec()
    reference = api_spec.render_reference()
    help_texts = api_spec.build_help()
    for name in (
        "run_drc", "run_spice", "read_doc", "get_project_snapshot",
        "write_doc", "run_job", "get_capabilities",
    ):
        assert name in _wired_names(), name
        assert help_texts[name]["text"] == _reference_section(reference, name)


def test_help_summary_comes_from_handler_docstring():
    api_spec = _load_spec()
    help_texts = api_spec.build_help()
    assert help_texts["run_drc"]["summary"] == _handler_summary(
        "rocket_engine.adapters.drc.magic", "MagicDrcAdapter"
    )
    assert help_texts["read_doc"]["summary"] == _handler_summary(
        "rocket_engine.project.service", "ProjectService.read_doc"
    )
    assert help_texts["write_doc"]["summary"] == _handler_summary(
        "rocket_engine.project.service", "ProjectService.write_doc"
    )
    assert help_texts["run_job"]["summary"] == _handler_summary(
        "rocket_engine.composition", "Engine._run_queued"
    )
    assert help_texts["get_capabilities"]["summary"] == _handler_summary(
        "rocket_engine.composition", "Engine.capabilities"
    )


def test_mcp_description_matches_docs_summary():
    from rocket_engine.adapters.mcp.server import tool_definitions

    api_spec = _load_spec()
    help_texts = api_spec.build_help()
    by_name = {tool.name: tool.description for tool in tool_definitions()}
    for name in (
        "run_drc", "run_spice", "read_doc", "get_project_snapshot",
        "write_doc", "run_job", "run_formal", "api_search",
        "get_capabilities",
    ):
        assert by_name[name] == help_texts[name]["summary"], name


def test_engine_job_control_ops_render_wired():
    """APISPEC-DISCOVERY RED: submit-branch job-control ops render wired.

    resume_run, discard_run, resume_all_retryable, and cancel_job are
    served by Engine methods through submit, so the generated spec
    must render them wired with handler docstring text — never the
    "no handler wired yet" template.
    """
    from rocket_engine.composition import ENGINE_OP_METHODS

    api_spec = _load_spec()
    assert set(ENGINE_OP_METHODS) == {
        "resume_run", "discard_run", "resume_all_retryable", "cancel_job",
    }
    schemas = api_spec.build_schemas()
    help_texts = api_spec.build_help()
    expected_required = {
        "resume_run": ["run_id"],
        "discard_run": ["run_id"],
        "resume_all_retryable": [],
        # cancel_job's signature defaults run_id to None, but submit
        # raises invalid_command without it — the schema pins the
        # behavioral contract, not the default.
        "cancel_job": ["run_id"],
    }
    for name, method in ENGINE_OP_METHODS.items():
        spec = api_spec.endpoint_spec(name)
        assert spec["wired"] is True, name
        assert spec["handlers"] == [
            f"rocket_engine.composition.Engine.{method}"
        ], name
        assert spec["summary"] == _handler_summary(
            "rocket_engine.composition", f"Engine.{method}"
        ), name
        assert "no handler wired yet" not in help_texts[name]["text"], name
        assert help_texts[name]["wired"] is True, name
        schema = schemas["operations"][name]
        assert schema["wired"] is True, name
        assert schema["description"] == spec["summary"], name
        assert schema["handlers"] == spec["handlers"], name
        assert schema["required"] == expected_required[name], name


def test_spec_wired_matches_oracle_wired_with_named_gaps():
    """Contract-sync RED: generated wired flags equal submit behavior.

    Every name submit serves (anything but unsupported_operation)
    renders wired; every wired render is served by submit. place_cell
    is the one named residual: its handler docstring carries no Args
    (owner: ops/submit.py) and ADR-003 forbids generator prose, so
    the spec stays honest-unwired until that docstring lands.
    """
    from rocket_engine.interfaces.vocabulary import OPERATIONS, QUERIES

    api_spec = _load_spec()
    schemas = api_spec.build_schemas()
    oracle = _wired_names()
    known_gaps = {"place_cell"}
    for name in sorted(OPERATIONS | QUERIES):
        section = "operations" if name in OPERATIONS else "queries"
        rendered = schemas[section][name]
        if name in known_gaps:
            assert name in oracle, name
            assert rendered["wired"] is False, name
            continue
        assert rendered["wired"] == (name in oracle), name
        if name in oracle:
            assert rendered["description"], name
            assert rendered["handlers"] != [], name


def test_mcp_definitions_match_generated_spec_for_every_name():
    """Contract-sync RED: MCP wire equals the generated spec, all names.

    Descriptions come from the same handler docstrings as the docs
    summary; wired tools carry the generated properties/required
    verbatim. python_execute keeps its grandfathered richer schema.
    """
    from rocket_engine.adapters.mcp.server import tool_definitions
    from rocket_engine.interfaces.vocabulary import OPERATIONS, QUERIES

    api_spec = _load_spec()
    help_texts = api_spec.build_help()
    schemas = api_spec.build_schemas()
    by_name = {tool.name: tool for tool in tool_definitions()}
    assert set(by_name) == set(OPERATIONS | QUERIES)
    for name in sorted(OPERATIONS | QUERIES):
        assert by_name[name].description == help_texts[name]["summary"], name
        if name == "python_execute":
            continue
        section = "operations" if name in OPERATIONS else "queries"
        entry = schemas[section][name]
        schema = by_name[name].input_schema
        assert schema["type"] == "object", name
        if entry["wired"]:
            assert schema["properties"] == entry["properties"], name
            assert schema["required"] == entry["required"], name
        else:
            assert "No generated schema" in schema.get("description", ""), name


def test_cataloged_names_resolve_identically_across_transports():
    """Contract-sync RED: HTTP/IPC/MCP/CLI deliver the same command.

    Every transport is a thin frame over engine.submit: the same
    logical call must arrive as the identical engine command, with
    no per-transport name table to drift.
    """
    import json as jsonlib

    from rocket_engine.adapters.http import HttpTransport
    from rocket_engine.adapters.ipc import IpcTransport
    from rocket_engine.adapters.mcp import McpTransport
    from rocket_engine.execution.dispatch import OpDispatcher
    from rocket_engine.interfaces.vocabulary import OPERATIONS, QUERIES

    for name in sorted(OPERATIONS | QUERIES):
        received = []

        class RecordingEngine:
            def submit(self, command):
                received.append(command)
                return {"ok": True}

        engine = RecordingEngine()
        McpTransport(engine).handle(jsonlib.dumps({
            "method": "tools/call",
            "params": {"name": name,
                       "arguments": {"project_id": "p-sync"}},
            "id": "r-sync",
        }))
        HttpTransport(engine).handle(jsonlib.dumps({
            "project_id": "p-sync", "operation": name,
            "arguments": {}, "request_id": "r-sync",
        }))
        IpcTransport(engine).handle(jsonlib.dumps({
            "project_id": "p-sync", "operation": name,
            "arguments": {}, "request_id": "r-sync",
        }))
        OpDispatcher(engine, project_id="p-sync").execute(
            name, {}, request_id="r-sync")
        assert len(received) == 4, name
        first, rest = received[0], received[1:]
        assert first == {"project_id": "p-sync", "operation": name,
                         "arguments": {}, "request_id": "r-sync"}, name
        assert all(command == first for command in rest), name


def test_api_discovery_queries_serve_live_contract():
    """REVIEW-TAILS I18 RED: api_search/api_info/api_help answer.

    The discovery queries serve the live contract (names, summaries,
    handlers) instead of raising unsupported_operation. api_info
    without a name refuses with invalid_command — a denial that
    still proves the handler is wired.
    """
    import pytest

    from rocket_engine.composition import Engine
    from rocket_engine.project.errors import ProjectError

    engine = Engine("probe-discovery", actor="probe")
    found = engine.submit({
        "project_id": "probe-discovery", "operation": "api_search",
        "arguments": {"query": "spice"}, "request_id": "probe-search",
    })
    assert any(m["name"] == "run_spice" for m in found["matches"])
    info = engine.submit({
        "project_id": "probe-discovery", "operation": "api_info",
        "arguments": {"name": "run_spice"}, "request_id": "probe-info",
    })
    assert info["name"] == "run_spice" and info["wired"] is True
    assert info["handlers"] != [] and info["summary"]
    helped = engine.submit({
        "project_id": "probe-discovery", "operation": "api_help",
        "arguments": {"name": "run_spice"}, "request_id": "probe-help",
    })
    assert helped["name"] == "run_spice" and helped["summary"]
    assert helped["text"]
    with pytest.raises(ProjectError) as excinfo:
        engine.submit({
            "project_id": "probe-discovery", "operation": "api_info",
            "arguments": {}, "request_id": "probe-info-missing",
        })
    assert excinfo.value.code == "invalid_command"


def test_engine_api_md_is_current():
    api_spec = _load_spec()
    rendered = api_spec.render_reference()
    assert (ROOT / "docs" / "engine-api.md").read_text() == rendered


def test_schema_and_help_json_are_current():
    api_spec = _load_spec()
    schemas = api_spec.build_schemas()
    help_texts = api_spec.build_help()
    assert json.loads((ROOT / "docs" / "api-schema.json").read_text()) == schemas
    assert json.loads((ROOT / "docs" / "api-help.json").read_text()) == help_texts
