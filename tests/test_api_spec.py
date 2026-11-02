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
