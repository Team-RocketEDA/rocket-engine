"""CONSOLE-ROUTE — console tier-2 mutations route through admission.

This suite imports the canonical routing homes (one word per
module level) directly: the old `console.route` re-export shim is
gone, and the contract below pins the canonical paths. Valid GREEN
= every test below passes against the canonical modules.

The contract under test: console tier-2 effectful mutations (cell
add/place, wire ops, doc writes, plus the sibling project
mutations) route through ProjectService admission — expected_revision
gating, ledger events with actor + revision, idempotent request ids —
using the identical verbs and the shared ENGINE-ECS / WIRE-PLACE
addressing the CRUD/MCP paths use. The console namespace exposes
those verbs by name (host-side admission router plus worker-side
recorder); tier-2 paths never touch the doc store directly; effects
report with run_ids and never re-execute.
"""

import uuid
from pathlib import Path

import pytest
from ruamel.yaml import YAML

from rocket_engine.execution.routing.calls import (
    CELL_VERBS,
    CONSOLE_TOOL_VERBS,
    DOC_VERBS,
    ECS_VERBS,
    PROJECT_VERBS,
    TIER_2_OPERATIONS,
    WIRE_VERBS,
    admission_envelope,
    build_effects_report,
    collect_run_ids,
    entity_doc_path,
    format_address,
    is_tier2,
    parse_address,
    report_completions,
    stamp_tier2_call,
    tier_for,
    tool_call,
)
from rocket_engine.execution.routing.namespace import ConsoleNamespace
from rocket_engine.execution.routing.tools import ConsoleTools
from rocket_engine.execution.errors import ExecutionError
from rocket_engine.stores import ecs
from rocket_engine.library.apig_catalog import ApigCatalog, static_provider
from rocket_engine.library.errors import LibraryError
from rocket_engine.project.errors import ProjectError
from rocket_engine.project.service import ProjectService

_yaml = YAML(typ="safe")

NAND2 = {
    "cell": "nand2",
    "pdk": "demo",
    "pdk_revision": "r1",
    "ports": ["A", "B", "Y"],
    "default_params": {"w": 1.0},
}


def _code(excinfo):
    return getattr(excinfo.value, "code", None)


def _project(actor="console-agent", engine_root=None):
    return ProjectService(
        "console-demo", actor=actor, engine_root=engine_root
    )


def _catalog():
    return ApigCatalog(".", providers=[static_provider([NAND2])])


def _namespace(project, catalog=True):
    if catalog is True:
        catalog = _catalog()
    elif catalog is False:
        catalog = None
    return ConsoleNamespace(project, catalog=catalog)


# Tier classification.


def test_tier2_families_are_the_ticket_verbs():
    assert set(DOC_VERBS) == {"write_doc", "delete_doc", "apply_mutations"}
    assert set(CELL_VERBS) == {"place_cell"}
    assert set(ECS_VERBS) == {
        "create_entity", "set_component", "attach_component",
        "detach_component", "delete_entity",
    }
    assert set(WIRE_VERBS) == {
        "place_wire", "place_junction", "connect_endpoint", "move_wire",
        "split_wire", "delete_wire", "delete_junction", "materialize_nets",
    }
    assert set(PROJECT_VERBS) == {
        "create_project", "rewind", "write_settings",
    }
    assert TIER_2_OPERATIONS == frozenset(
        list(DOC_VERBS) + list(CELL_VERBS) + list(ECS_VERBS)
        + list(WIRE_VERBS) + list(PROJECT_VERBS)
    )
    assert len(TIER_2_OPERATIONS) == 20


@pytest.mark.parametrize("operation", sorted(TIER_2_OPERATIONS))
def test_tier_for_marks_every_mutation_tier2(operation):
    assert tier_for(operation) == 2
    assert is_tier2(operation) is True


@pytest.mark.parametrize(
    "operation",
    ["read_doc", "list_docs", "get_project_snapshot", "get_events_since",
     "list_projects", "run_drc", "run_spice", "run_job", "python_execute",
     "get_python_console", "get_component", "no_such_op", "", None, 123,
     ["write_doc"], ("write_doc",)],
)
def test_tier_for_leaves_reads_runs_and_unknown_at_tier1(operation):
    assert tier_for(operation) == 1
    assert is_tier2(operation) is False


def test_console_tool_verbs_cover_tier2_sorted():
    assert CONSOLE_TOOL_VERBS == tuple(sorted(TIER_2_OPERATIONS))


# Admission envelopes.


def test_admission_envelope_round_trips_operation_and_arguments():
    arguments = {"path": "notes/a.txt", "content": "hi",
                 "expected_revision": "p12"}
    text = admission_envelope("write_doc", arguments)
    assert _yaml.load(text) == {"operation": "write_doc",
                                "arguments": arguments}


def test_admission_envelope_matches_engine_command_bytes():
    import io

    arguments = {"path": "a.txt", "content": "b", "expected_revision": "p12"}
    buf = io.StringIO()
    _yaml.dump({"operation": "write_doc", "arguments": arguments}, buf)
    assert admission_envelope("write_doc", arguments) == buf.getvalue()


@pytest.mark.parametrize(
    "operation,arguments",
    [("", {"path": "a"}), (None, {"path": "a"}), (123, {"path": "a"}),
     ("write_doc", None), ("write_doc", []), ("write_doc", "x"),
     ("write_doc", {"value": object()})],
)
def test_admission_envelope_rejects_bad_shapes(operation, arguments):
    with pytest.raises(ExecutionError) as excinfo:
        admission_envelope(operation, arguments)
    assert _code(excinfo) == "invalid_command"


# Tier-2 stamping for console replay.


def test_failed_envelope_does_not_poison_later_envelopes():
    with pytest.raises(ExecutionError) as excinfo:
        admission_envelope("write_doc", {"value": object()})
    assert _code(excinfo) == "invalid_command"
    first = admission_envelope("write_doc", {"path": "a"})
    second = admission_envelope("write_doc", {"path": "b"})
    assert first != second
    assert _yaml.load(first) == {
        "operation": "write_doc", "arguments": {"path": "a"},
    }


def test_stamp_leaves_tier1_calls_untouched():
    arguments = {"path": "notes/a.txt"}
    stamped, request_id = stamp_tier2_call("read_doc", arguments, "p99")
    assert stamped == arguments
    assert stamped is not arguments
    assert request_id is None
    stamped, request_id = stamp_tier2_call(
        "run_drc", {"target": "t"}, "p99", request_id="rid-kept"
    )
    assert stamped == {"target": "t"}
    assert request_id == "rid-kept"


def test_stamp_binds_head_and_mints_request_for_tier2():
    stamped, request_id = stamp_tier2_call(
        "write_doc", {"path": "a", "content": "b"}, "p99"
    )
    assert stamped == {"path": "a", "content": "b",
                       "expected_revision": "p99"}
    assert isinstance(request_id, str) and request_id
    _second, other = stamp_tier2_call(
        "place_cell", {"cell": "nand2"}, "p99"
    )
    assert other != request_id


def test_stamp_preserves_caller_binding_and_request():
    stamped, request_id = stamp_tier2_call(
        "write_doc",
        {"path": "a", "content": "b", "expected_revision": "p5"},
        "p99", request_id="rid-caller",
    )
    assert stamped["expected_revision"] == "p5"
    assert request_id == "rid-caller"


@pytest.mark.parametrize("arguments", [None, [], "write_doc", 42])
def test_stamp_rejects_non_mapping_arguments(arguments):
    with pytest.raises(ExecutionError) as excinfo:
        stamp_tier2_call("write_doc", arguments, "p99")
    assert _code(excinfo) == "invalid_command"


# Namespace: doc writes through real admission.


def test_write_doc_routes_through_admission():
    project = _project()
    namespace = _namespace(project)
    response = namespace.write_doc(
        "notes/a.txt", "hi\n", request_id="rid-doc-1",
        expected_revision="p12",
    )
    assert response["current_revision"] == "p13"
    assert response["previous_revision"] == "p12"
    assert response["actor"] == "console-agent"
    assert response["revision_transition"] == {"from": "p12", "to": "p13"}
    assert response["rewind_handle"]["revision"] == "p12"
    assert response["diff_summary"].startswith("created notes/a.txt")
    (record,) = response["events"]
    assert record["event"] == "doc_written"
    assert record["actor"] == "console-agent"
    assert record["data"]["revision"] == "p13"
    assert project.snapshot()["current_revision"] == "p13"
    assert project.read_doc("notes/a.txt")["content"] == "hi\n"


def test_write_doc_replay_returns_identical_without_advancing():
    project = _project()
    namespace = _namespace(project)
    first = namespace.write_doc(
        "notes/a.txt", "hi\n", request_id="rid-doc-replay",
        expected_revision="p12",
    )
    second = namespace.write_doc(
        "notes/a.txt", "hi\n", request_id="rid-doc-replay",
        expected_revision="p12",
    )
    assert second == first
    assert project.snapshot()["current_revision"] == "p13"
    assert len(project.events_since(0)) == 1


def test_write_doc_stale_revision_conflicts_cleanly():
    project = _project()
    namespace = _namespace(project)
    with pytest.raises(ProjectError) as excinfo:
        namespace.write_doc(
            "notes/a.txt", "hi\n", request_id="rid-doc-stale",
            expected_revision="p999",
        )
    assert _code(excinfo) == "revision_conflict"
    assert project.snapshot()["current_revision"] == "p12"
    assert project.events_since(0) == []


def test_write_doc_request_conflict_on_reused_id():
    project = _project()
    namespace = _namespace(project)
    namespace.write_doc(
        "notes/a.txt", "hi\n", request_id="rid-doc-clash",
        expected_revision="p12",
    )
    with pytest.raises(ProjectError) as excinfo:
        namespace.write_doc(
            "notes/b.txt", "other\n", request_id="rid-doc-clash",
            expected_revision="p13",
        )
    assert _code(excinfo) == "request_conflict"


def test_delete_doc_routes_and_replays():
    project = _project()
    namespace = _namespace(project)
    namespace.write_doc(
        "notes/gone.txt", "bye\n", request_id="rid-del-setup",
        expected_revision="p12",
    )
    response = namespace.delete_doc(
        "notes/gone.txt", request_id="rid-del-1",
        expected_revision="p13",
    )
    assert response["current_revision"] == "p14"
    assert response["events"][0]["event"] == "doc_deleted"
    replay = namespace.delete_doc(
        "notes/gone.txt", request_id="rid-del-1",
        expected_revision="p13",
    )
    assert replay == response
    with pytest.raises(ProjectError) as excinfo:
        namespace.delete_doc(
            "notes/missing.txt", request_id="rid-del-unknown",
            expected_revision="p14",
        )
    assert _code(excinfo) == "unknown_document"


def test_apply_mutations_atomic_single_revision():
    project = _project()
    namespace = _namespace(project)
    mutations = [
        {"op": "write", "path": "a.txt", "content": "a\n"},
        {"op": "write", "path": "b.txt", "content": "b\n"},
    ]
    response = namespace.apply_mutations(
        mutations, request_id="rid-batch-1", expected_revision="p12"
    )
    assert response["current_revision"] == "p13"
    assert len(response["events"]) == 1
    assert response["events"][0]["event"] == "mutations_applied"
    replay = namespace.apply_mutations(
        mutations, request_id="rid-batch-1", expected_revision="p12"
    )
    assert replay == response
    assert project.snapshot()["current_revision"] == "p13"


def test_create_project_routes(tmp_path):
    project = _project(engine_root=str(tmp_path))
    namespace = _namespace(project)
    response = namespace.create_project(
        "console-child", request_id="rid-create-1"
    )
    assert response["project_id"] == "console-child"
    assert response["current_revision"] == "p12"
    assert response["actor"] == "console-agent"
    replay = namespace.create_project(
        "console-child", request_id="rid-create-1"
    )
    assert replay == response


def test_rewind_covers_console_writes():
    project = _project()
    namespace = _namespace(project)
    namespace.write_doc(
        "notes/a.txt", "v1\n", request_id="rid-rw-1",
        expected_revision="p12",
    )
    namespace.write_doc(
        "notes/a.txt", "v2\n", request_id="rid-rw-2",
        expected_revision="p13",
    )
    response = namespace.rewind(
        "p13", request_id="rid-rw-3", expected_revision="p14"
    )
    assert response["current_revision"] == "p15"
    assert response["events"][0]["event"] == "project_rewound"
    assert response["events"][0]["actor"] == "console-agent"
    assert project.read_doc("notes/a.txt")["content"] == "v1\n"


def test_write_settings_routes_and_skips_unchanged():
    from rocket_engine.stores.settings import default_settings

    project = _project()
    namespace = _namespace(project)
    settings = default_settings("text.vars")
    response = namespace.write_settings(
        "text.vars", settings, request_id="rid-set-1",
        expected_revision="p12",
    )
    assert response["written"] is True
    assert response["current_revision"] == "p13"
    replay = namespace.write_settings(
        "text.vars", settings, request_id="rid-set-2",
        expected_revision="p13",
    )
    assert replay["written"] is False
    assert replay["current_revision"] == "p13"


# Namespace: cell placement.


def test_place_cell_routes_through_batch_admission():
    project = _project()
    namespace = _namespace(project)
    response = namespace.place_cell(
        "nand2", request_id="rid-cell-1", expected_revision="p12",
        instance_id="top_nand",
    )
    assert response["current_revision"] == "p13"
    assert response["actor"] == "console-agent"
    stored = project.read_doc("components/top_nand.yaml")["content"]
    assert "nand2" in stored
    replay = namespace.place_cell(
        "nand2", request_id="rid-cell-1", expected_revision="p12",
        instance_id="top_nand",
    )
    assert replay == response
    assert project.snapshot()["current_revision"] == "p13"


def test_place_cell_maps_library_errors_to_project_errors():
    project = _project()
    namespace = _namespace(project)
    with pytest.raises(ProjectError) as excinfo:
        namespace.place_cell(
            "no_such_cell", request_id="rid-cell-unknown",
            expected_revision="p12",
        )
    assert _code(excinfo) == "unknown_cell"


def test_place_cell_without_catalog_refuses():
    project = _project()
    namespace = _namespace(project, catalog=False)
    with pytest.raises(ProjectError) as excinfo:
        namespace.place_cell(
            "nand2", request_id="rid-cell-nocat",
            expected_revision="p12",
        )
    assert _code(excinfo) == "unsupported_operation"


# Zero direct doc-store writes from tier-2 paths.


def test_tier2_module_names_no_private_doc_store_writers():
    from rocket_engine.execution.routing import calls as module

    files = sorted(
        (Path(module.__file__).parent).glob("*.py")
    )
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in files
    )
    forbidden = [
        "_write_doc_text", "_delete_doc_path", "_write_bytes_map",
        "._doc_path(", "_read_doc_text", "_capture_snapshot",
        "_ensure_snapshot", "_append_event", "_persist_after_mutation",
        "_persist", "_refresh_durable", "_gate_revision", "_check_replay",
        "_current_revision", "_requests", "_events", "_docs", "_snapshots",
        "open(", "write_text", "write_bytes", ".unlink(", "os.replace",
        "os.remove", "shutil", "subprocess", "setattr", "__dict__",
    ]
    hits = [token for token in forbidden if token in source]
    assert hits == []


class _RecordingProject:
    """Public-verbs-only stand-in proving delegation shape."""

    VERBS = (
        "write_doc", "delete_doc", "apply_mutations", "create_entity",
        "set_component", "attach_component", "detach_component",
        "delete_entity", "place_wire", "place_junction",
        "connect_endpoint", "move_wire", "split_wire", "delete_wire",
        "delete_junction", "materialize_nets", "create_project",
        "rewind", "write_settings",
    )

    def __init__(self):
        self.calls = []
        for verb in self.VERBS:
            setattr(self, verb, self._recorder(verb))

    def _recorder(self, verb):
        def record(*args, **kwargs):
            self.calls.append((verb, args, kwargs))
            return {"ok": True, "verb": verb}

        return record


def _namespace_calls():
    pin = {"entity": "ent-pin", "instance": "i0", "pin": "A", "xy": [0, 0]}
    endpoints = [
        {"ref": None, "xy": [0, 0]}, {"ref": None, "xy": [1, 0]},
    ]
    return {
        "write_doc": {"path": "a.txt", "content": "a\n"},
        "delete_doc": {"path": "a.txt"},
        "apply_mutations": {
            "mutations": [{"op": "write", "path": "a", "content": "b"}]
        },
        "create_entity": {"kind": "block", "components": {"a": 1}},
        "set_component": {
            "entity": "ent-abc", "component": "C", "data": {"x": 1}
        },
        "attach_component": {
            "entity": "ent-abc", "component": "C", "data": {"x": 1}
        },
        "detach_component": {"entity": "ent-abc", "component": "C"},
        "delete_entity": {"entity": "ent-abc"},
        "place_wire": {
            "segments": [[[0, 0], [1, 0]]], "layer": "m1",
            "endpoints": endpoints,
        },
        "place_junction": {"xy": [0, 0], "layer": "m1"},
        "connect_endpoint": {
            "wire_id": "ent-wire", "end": "a", "ref": "ent-pin"
        },
        "move_wire": {"wire_id": "ent-wire", "dx": 1, "dy": 2},
        "split_wire": {"wire_id": "ent-wire", "at": [0, 0]},
        "delete_wire": {"wire_id": "ent-wire"},
        "delete_junction": {"junction_id": "ent-junc"},
        "materialize_nets": {"pins": [pin]},
        "create_project": {"new_project_id": "proj-child"},
        "rewind": {"target_revision": "p12"},
        "write_settings": {"kind": "text.vars", "settings": {"a": 1}},
    }


@pytest.mark.parametrize("verb", sorted(_namespace_calls()))
def test_namespace_delegates_once_to_same_named_public_verb(verb):
    project = _RecordingProject()
    namespace = ConsoleNamespace(project, catalog=_catalog())
    kwargs = dict(_namespace_calls()[verb])
    if verb == "create_project":
        getattr(namespace, verb)(**kwargs, request_id="rid-delegate")
    else:
        getattr(namespace, verb)(
            **kwargs, request_id="rid-delegate", expected_revision="p12"
        )
    assert len(project.calls) == 1
    seen, seen_args, seen_kwargs = project.calls[0]
    assert seen == verb
    # Engine call shape: verb arguments, then the envelope id plus
    # identity text positionally, revision bound by keyword.
    rid_at = list(seen_args).index("rid-delegate")
    command_text = seen_args[rid_at + 1]
    envelope = _yaml.load(command_text)
    assert envelope["operation"] == verb
    for key, value in kwargs.items():
        assert envelope["arguments"][key] == value
    if verb == "create_project":
        assert "expected_revision" not in seen_kwargs
        assert "expected_revision" not in envelope["arguments"]
    else:
        assert seen_kwargs["expected_revision"] == "p12"
        assert envelope["arguments"]["expected_revision"] == "p12"


def test_place_cell_delegates_to_catalog_place_cell():
    seen = {}

    class _Catalog:
        def place_cell(self, project, cell, request_id,
                       expected_revision=None, pdk=None, instance_id=None,
                       params=None, connections=None):
            seen.update(
                project=project, cell=cell, request_id=request_id,
                expected_revision=expected_revision, pdk=pdk,
                instance_id=instance_id, params=params,
                connections=connections,
            )
            return {"ok": True, "verb": "place_cell"}

    project = _RecordingProject()
    namespace = ConsoleNamespace(project, catalog=_Catalog())
    response = namespace.place_cell(
        "nand2", request_id="rid-cat", expected_revision="p12",
        instance_id="i1",
    )
    assert response == {"ok": True, "verb": "place_cell"}
    assert seen["project"] is project
    assert seen["cell"] == "nand2"
    assert seen["request_id"] == "rid-cat"
    assert seen["expected_revision"] == "p12"
    assert seen["instance_id"] == "i1"
    assert project.calls == []


def test_place_cell_maps_catalog_library_errors():
    class _FailingCatalog:
        def place_cell(self, *args, **kwargs):
            raise LibraryError("unknown_cell", "Unknown cell: 'x'.")

    namespace = ConsoleNamespace(
        _RecordingProject(), catalog=_FailingCatalog()
    )
    with pytest.raises(ProjectError) as excinfo:
        namespace.place_cell("x", request_id="rid-cat-fail")
    assert _code(excinfo) == "unknown_cell"


# Namespace: ECS/wire verbs and shared addressing.


def test_namespace_exposes_every_ecs_and_wire_verb():
    namespace = _namespace(_project())
    tools = ConsoleTools()
    for verb in list(ECS_VERBS) + list(WIRE_VERBS):
        assert callable(getattr(namespace, verb)), verb
        assert callable(getattr(tools, verb)), verb
        assert verb in CONSOLE_TOOL_VERBS


_WIRE_CALLS = {
    "place_wire": {
        "segments": [[[0, 0], [1, 0]]], "layer": "m1",
        "endpoints": [
            {"ref": None, "xy": [0, 0]}, {"ref": None, "xy": [1, 0]}
        ],
    },
    "place_junction": {"xy": [0, 0], "layer": "m1"},
    "connect_endpoint": {"wire_id": "w", "end": "a", "ref": "p"},
    "move_wire": {"wire_id": "w", "dx": 1, "dy": 0},
    "split_wire": {"wire_id": "w", "at": [0, 0]},
    "delete_wire": {"wire_id": "w"},
    "delete_junction": {"junction_id": "j"},
    "materialize_nets": {
        "pins": [{"entity": "e", "instance": "i", "pin": "A",
                  "xy": [0, 0]}]
    },
}

_ECS_CALLS = {
    "create_entity": {"kind": "block"},
    "set_component": {"entity": "e", "component": "C", "data": {}},
    "attach_component": {"entity": "e", "component": "C", "data": {}},
    "detach_component": {"entity": "e", "component": "C"},
    "delete_entity": {"entity": "e"},
}


@pytest.mark.parametrize(
    "verb", sorted(list(_ECS_CALLS) + list(_WIRE_CALLS))
)
def test_unwired_ecs_wire_verbs_refuse_without_side_effects(verb):
    if hasattr(ProjectService, verb):
        pytest.skip(f"peer patch landed for {verb}")
    project = _project()
    namespace = _namespace(project)
    kwargs = dict((_ECS_CALLS | _WIRE_CALLS)[verb])
    with pytest.raises(ProjectError) as excinfo:
        getattr(namespace, verb)(
            **kwargs, request_id=f"rid-{verb}",
            expected_revision="p12",
        )
    assert _code(excinfo) == "unsupported_operation"
    assert verb in str(excinfo.value)
    assert project.snapshot()["current_revision"] == "p12"
    assert project.events_since(0) == []


def test_addressing_delegates_to_shared_substrate():
    assert entity_doc_path("ent-abc") == (
        ecs.entity_doc_path("ent-abc")
    )
    assert parse_address("ent-abc.C") == (
        ecs.parse_address("ent-abc.C")
    )
    assert format_address("ent-abc", "C") == (
        ecs.format_address("ent-abc", "C")
    )
    try:
        ecs.validate_entity_id("not an id!")
    except Exception as exc:  # noqa: BLE001 - parity probe
        want = getattr(exc, "code", None)
    with pytest.raises(Exception) as excinfo:  # noqa: BLE001 - parity
        entity_doc_path("not an id!")
    assert _code(excinfo) == want


# Worker-side recorder namespace.


def test_named_wrappers_record_prelude_identical_entries():
    tools = ConsoleTools()
    for index, verb in enumerate(CONSOLE_TOOL_VERBS, start=1):
        kwargs = {"alpha": 1, "beta": "two"}
        receipt = getattr(tools, verb)(**kwargs)
        assert receipt == {"state": "recorded", "operation": verb,
                           "index": index}
    assert [entry["operation"] for entry in tools.calls] == (
        list(CONSOLE_TOOL_VERBS)
    )
    assert tools.calls[0]["arguments"] == {"alpha": 1, "beta": "two"}


def test_generic_fallback_records_uncataloged_ops():
    tools = ConsoleTools()
    receipt = tools.run_drc(target="amplifier")
    assert receipt["operation"] == "run_drc"
    assert tools.calls == [{
        "operation": "run_drc", "arguments": {"target": "amplifier"},
    }]


def test_positional_args_rejected_like_prelude():
    tools = ConsoleTools()
    with pytest.raises(TypeError) as excinfo:
        tools.write_doc("a.txt", "b")
    assert str(excinfo.value) == (
        "op calls take keyword arguments only: write_doc."
    )
    with pytest.raises(TypeError) as excinfo:
        tools.run_drc("amplifier")
    assert str(excinfo.value) == (
        "op calls take keyword arguments only: run_drc."
    )
    assert tools.calls == []


def test_sink_and_calls_accumulate_every_entry():
    sunk = []
    tools = ConsoleTools(sink=sunk.append)
    tools.write_doc(path="a", content="b")
    tools.read_doc(path="a")
    assert len(tools.calls) == 2
    assert sunk == tools.calls


def test_tool_call_validates_and_copies():
    arguments = {"path": "a"}
    entry = tool_call("write_doc", arguments)
    assert entry == {"operation": "write_doc", "arguments": {"path": "a"}}
    arguments["path"] = "mutated"
    assert entry["arguments"] == {"path": "a"}
    for operation, bad in [("", {}), (None, {}), ("write_doc", None),
                           ("write_doc", [])]:
        with pytest.raises(ExecutionError) as excinfo:
            tool_call(operation, bad)
        assert _code(excinfo) == "invalid_command"


# Effects reporting: report with run_ids, never re-execute.


def test_collect_run_ids_rule():
    op_results = [
        {"operation": "run_drc", "ok": True,
         "result": {"run_id": "run-1"}},
        {"operation": "run_drc", "ok": False,
         "error": {"code": "x", "message": "y"}},
        {"operation": "write_doc", "ok": True,
         "result": {"current_revision": "p13"}},
        {"operation": "run_spice", "ok": True,
         "result": {"run_id": 42}},
        {"operation": "run_spice", "ok": True, "result": None},
        {"not": "a result"},
    ]
    assert collect_run_ids(op_results) == ["run-1"]
    assert collect_run_ids([]) == []
    assert collect_run_ids(None) == []


def test_build_effects_report_shape():
    ops = [{"operation": "write_doc", "arguments": {"path": "a"}}]
    op_results = [{"operation": "write_doc", "ok": True,
                   "result": {"run_id": "run-9"}}]
    effects = build_effects_report(ops, op_results, 2)
    assert effects == {
        "ops": ops, "op_results": op_results, "ops_ok": True,
        "ops_skipped": 2, "run_ids": ["run-9"], "replayed": True,
    }
    failed = [{"operation": "write_doc", "ok": False,
               "error": {"code": "c", "message": "m"}}]
    assert build_effects_report(ops, failed, 0)["ops_ok"] is False
    assert build_effects_report([], [], 0, replayed=False) == {
        "ops": [], "op_results": [], "ops_ok": True, "ops_skipped": 0,
        "run_ids": [], "replayed": False,
    }


def test_report_completions_reports_without_executing():
    project = _project()
    namespace = _namespace(project)
    namespace.write_doc(
        "notes/a.txt", "v\n", request_id="rid-rep-1",
        expected_revision="p12",
    )
    calls = []

    def fetch(run_id):
        calls.append(run_id)
        if run_id == "run-missing":
            raise ExecutionError("unknown_run", "Unknown run: run-missing.")
        return {"run_id": run_id, "state": "completed"}

    report = report_completions(["run-a", "run-missing", "run-a"], fetch)
    assert report["run_ids"] == ["run-a", "run-missing", "run-a"]
    assert report["completions"] == [
        {"run_id": "run-a", "state": "completed"}
    ]
    assert [entry["run_id"] for entry in report["refused"]] == [
        "run-missing", "run-a",
    ]
    assert report["refused"][0]["code"] == "unknown_run"
    assert report["refused"][1]["code"] == "duplicate_in_batch"
    again = report_completions(["run-a"], fetch)
    assert again["completions"] == report["completions"]
    assert calls == ["run-a", "run-missing", "run-a"]
    assert project.snapshot()["current_revision"] == "p13"
    assert len(project.events_since(0)) == 1


@pytest.mark.parametrize(
    "run_ids,fetch",
    [([], lambda rid: {}), (None, lambda rid: {}),
     ("run-a", lambda rid: {}), ([42], lambda rid: {}),
     ([""], lambda rid: {}), (["run-a"], None), (["run-a"], 42)],
)
def test_report_completions_rejects_bad_inputs(run_ids, fetch):
    with pytest.raises(ExecutionError) as excinfo:
        report_completions(run_ids, fetch)
    assert _code(excinfo) == "invalid_command"


# Acceptance flow.


def test_terminal_session_rewind_and_reload(tmp_path):
    root = str(tmp_path / "engine")
    project = _project(engine_root=root)
    namespace = _namespace(project)
    placed = namespace.place_cell(
        "nand2", request_id="rid-acc-cell", expected_revision="p12",
        instance_id="top_nand",
    )
    written = namespace.write_doc(
        "notes/net.txt", "net N1\n", request_id="rid-acc-doc",
        expected_revision=placed["current_revision"],
    )
    assert written["current_revision"] == "p14"
    events = project.events_since(0)
    assert [event["actor"] for event in events] == [
        "console-agent", "console-agent",
    ]
    assert [event["data"]["revision"] for event in events] == [
        "p13", "p14",
    ]
    rewound = namespace.rewind(
        "p12", request_id="rid-acc-rewind", expected_revision="p14"
    )
    assert rewound["current_revision"] == "p15"
    assert project.list_docs()["documents"] == []
    fresh = ProjectService(
        "console-demo", actor="console-agent", engine_root=root
    )
    assert fresh.snapshot()["current_revision"] == "p15"
    assert fresh.list_docs() == project.list_docs()
    assert [event["seq"] for event in fresh.events_since(0)] == (
        [event["seq"] for event in project.events_since(0)]
    )


def test_effects_carry_run_ids_and_rereport_is_stable():
    op_results = [
        {"operation": "run_drc", "ok": True,
         "result": {"run_id": "run-1", "state": "completed"}},
        {"operation": "write_doc", "ok": True,
         "result": {"current_revision": "p13"}},
    ]
    effects = build_effects_report([], op_results, 0)
    assert effects["run_ids"] == ["run-1"]
    stored = {"run-1": {"run_id": "run-1", "state": "completed"}}
    fetch = lambda run_id: dict(stored[run_id])  # noqa: E731 - test fetch
    first = report_completions(effects["run_ids"], fetch)
    second = report_completions(effects["run_ids"], fetch)
    assert first == second
    assert first["refused"] == []


def test_request_ids_mint_unique_when_omitted():
    project = _project()
    namespace = _namespace(project)
    first = namespace.write_doc("a.txt", "a\n", expected_revision="p12")
    second = namespace.write_doc(
        "b.txt", "b\n", expected_revision=first["current_revision"]
    )
    assert first["request_id"] != second["request_id"]
    assert uuid.UUID(first["request_id"], version=4)
    assert second["current_revision"] == "p14"
