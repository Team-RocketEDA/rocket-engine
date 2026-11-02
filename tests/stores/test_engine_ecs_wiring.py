"""ENGINE-ECS wiring tests — Engine/MCP exposure (integrator-run).

Run AFTER the integrator applies docs/work/ENGINE-ECS/wiring.patch
and reinstalls the package. Before that the whole module skips: the
names are unwired and the installed package lacks the store.

Wired surface under test:
  - OPERATIONS carries create_entity, set_component,
    attach_component, detach_component, delete_entity (immediate,
    CRUD precedent: revision gate + idempotent request ids +
    ledger event, persisted as entities/<id>.json documents).
  - QUERIES carries get_component, components_of, entities_with,
    get_world_snapshot (reads, revision untouched).
  - Every component write appends component_changed with
    {entity, component, revision}; the world snapshot mirrors
    every entity plus read-only backfilled docs.
"""

import importlib.util
import uuid

import pytest

PROJECT = "ecs_wiring_demo"

try:
    from rocket_engine.composition import Engine
    from rocket_engine.project.errors import ProjectError

    _HAVE_ENGINE = True
except ImportError:
    _HAVE_ENGINE = False


def _wiring_present():
    if not _HAVE_ENGINE:
        return False
    if (
        importlib.util.find_spec(
            "rocket_engine.stores.ecs"
        )
        is None
    ):
        return False
    try:
        from rocket_engine.interfaces.vocabulary import OPERATIONS
    except ImportError:
        return False
    if "create_entity" not in OPERATIONS:
        return False
    probe = Engine(f"ecs-probe-{uuid.uuid4().hex[:8]}", actor="test")
    try:
        probe.submit(
            {
                "project_id": probe.snapshot()["project_id"],
                "operation": "create_entity",
                "arguments": {
                    "expected_revision": probe.snapshot()[
                        "current_revision"
                    ]
                },
                "request_id": uuid.uuid4().hex,
            }
        )
    except Exception as exc:
        return getattr(exc, "code", None) != "unsupported_operation"
    return True


pytestmark = pytest.mark.skipif(
    not _wiring_present(), reason="needs ENGINE-ECS wiring patch"
)


def _engine():
    return Engine(f"{PROJECT}-{uuid.uuid4().hex[:8]}", actor="human")


def _submit(engine, operation, arguments, request_id=None):
    return engine.submit(
        {
            "project_id": engine.snapshot()["project_id"],
            "operation": operation,
            "arguments": arguments,
            "request_id": request_id or uuid.uuid4().hex,
        }
    )


def _head(engine):
    return engine.snapshot()["current_revision"]


def _mutate(engine, operation, arguments, request_id=None):
    arguments = dict(arguments)
    arguments.setdefault("expected_revision", _head(engine))
    return _submit(engine, operation, arguments, request_id)


def _code(excinfo):
    return getattr(excinfo.value, "code", None)


def test_vocabulary_contains_ecs_names():
    from rocket_engine.interfaces.vocabulary import OPERATIONS, QUERIES

    assert {
        "create_entity",
        "set_component",
        "attach_component",
        "detach_component",
        "delete_entity",
    } <= set(OPERATIONS)
    assert {
        "get_component",
        "components_of",
        "entities_with",
        "get_world_snapshot",
    } <= set(QUERIES)


def test_create_attach_wire_events_world_via_engine():
    engine = _engine()
    block = _mutate(engine, "create_entity", {"kind": "block"})["entity"]
    pin = _mutate(engine, "create_entity", {"kind": "pin"})["entity"]
    assert block != pin

    attached = _mutate(
        engine,
        "attach_component",
        {"entity": block, "component": "sources",
         "data": ["design/top.yaml"]},
    )
    assert attached["address"] == f"{block}.sources"

    wired = _mutate(
        engine,
        "set_component",
        {"entity": block, "component": "wires",
         "data": {"w1": {"to": f"{pin}.pad"}}},
    )
    fetched = _submit(
        engine, "get_component",
        {"entity": block, "component": "wires"},
    )
    assert fetched["data"] == {"w1": {"to": f"{pin}.pad"}}
    assert fetched["address"] == f"{block}.wires"

    events = _submit(engine, "get_events_since", {"cursor": 0})["events"]
    kinds = [e["event"] for e in events]
    assert kinds == [
        "entity_created", "entity_created",
        "component_changed", "component_changed",
    ]
    assert events[2]["data"] == {
        "entity": block, "component": "sources",
        "revision": attached["current_revision"],
    }

    world = _submit(engine, "get_world_snapshot", {})
    by_id = {e["id"]: e for e in world["entities"]}
    assert by_id[block]["components"]["sources"] == ["design/top.yaml"]
    assert by_id[block]["components"]["wires"] == {"w1": {"to": f"{pin}.pad"}}
    assert world["current_revision"] == wired["current_revision"]


def test_no_path_entity_drift_through_engine():
    engine = _engine()
    created = _mutate(engine, "create_entity", {"kind": "block"})
    entity = created["entity"]
    path = created["path"]
    assert path == f"entities/{entity}.json"

    _mutate(
        engine, "set_component",
        {"entity": entity, "component": "sources", "data": ["a"]},
    )
    raw = _submit(engine, "read_doc", {"path": path})["content"]
    import json

    assert json.loads(raw)["components"] == {"sources": ["a"]}
    listing = _submit(engine, "list_docs", {"prefix": "entities"})
    assert path in [d["path"] for d in listing["documents"]]
    assert _submit(
        engine, "components_of", {"entity": entity}
    )["components"] == ["sources"]
    holders = _submit(engine, "entities_with", {"component": "sources"})
    assert entity in holders["entities"]


def test_attach_duplicate_and_detach_missing_name_reasons():
    engine = _engine()
    entity = _mutate(engine, "create_entity", {})["entity"]
    _mutate(
        engine, "attach_component",
        {"entity": entity, "component": "sources", "data": []},
    )
    with pytest.raises(Exception) as excinfo:
        _mutate(
            engine, "attach_component",
            {"entity": entity, "component": "sources", "data": []},
        )
    assert _code(excinfo) == "component_exists"
    with pytest.raises(Exception) as excinfo:
        _mutate(
            engine, "detach_component",
            {"entity": entity, "component": "missing"},
        )
    assert _code(excinfo) == "unknown_component"
    with pytest.raises(Exception) as excinfo:
        _submit(
            engine, "get_component",
            {"entity": entity, "component": "missing"},
        )
    assert _code(excinfo) == "unknown_component"


def test_detach_and_delete_flow_through_engine():
    engine = _engine()
    entity = _mutate(engine, "create_entity", {})["entity"]
    _mutate(
        engine, "attach_component",
        {"entity": entity, "component": "sources", "data": ["a"]},
    )
    detached = _mutate(
        engine, "detach_component",
        {"entity": entity, "component": "sources"},
    )
    assert detached["events"][0]["data"]["detached"] is True
    assert _submit(
        engine, "components_of", {"entity": entity}
    )["components"] == []
    deleted = _mutate(engine, "delete_entity", {"entity": entity})
    assert deleted["events"][0]["event"] == "entity_deleted"
    with pytest.raises(Exception) as excinfo:
        _submit(
            engine, "get_component",
            {"entity": entity, "component": "sources"},
        )
    assert _code(excinfo) == "unknown_entity"


def test_entities_with_predicate_filters_through_engine():
    engine = _engine()
    on_vdd = _mutate(engine, "create_entity", {"kind": "pin"})["entity"]
    on_gnd = _mutate(engine, "create_entity", {"kind": "pin"})["entity"]
    _mutate(
        engine, "set_component",
        {"entity": on_vdd, "component": "net",
         "data": {"name": "VDD", "class": "power"}},
    )
    _mutate(
        engine, "set_component",
        {"entity": on_gnd, "component": "net",
         "data": {"name": "VSS", "class": "power"}},
    )
    holders = _submit(engine, "entities_with", {"component": "net"})
    assert holders["entities"] == sorted([on_vdd, on_gnd])
    only_vdd = _submit(
        engine, "entities_with",
        {"component": "net", "predicate": {"name": "VDD"}},
    )
    assert only_vdd["entities"] == [on_vdd]


def test_backfill_world_snapshot_without_revision_bump():
    engine = _engine()
    _mutate(
        engine, "write_doc",
        {"path": "design/top.yaml", "content": "top: true\n"},
    )
    before = _head(engine)
    world = _submit(engine, "get_world_snapshot", {})
    assert _head(engine) == before
    backfilled = [e for e in world["entities"] if e["id"].startswith("doc-")]
    assert len(backfilled) == 1
    assert backfilled[0]["components"]["doc"]["path"] == "design/top.yaml"
    lean = _submit(
        engine, "get_world_snapshot", {"include_backfill": False}
    )
    assert [e for e in lean["entities"] if e["id"].startswith("doc-")] == []
    assert _head(engine) == before


def test_backfill_mutations_are_refused_through_engine():
    from rocket_engine.stores import ecs

    engine = _engine()
    _mutate(
        engine, "write_doc",
        {"path": "design/top.yaml", "content": "top: true\n"},
    )
    virtual = ecs.backfill_id_for_doc("design/top.yaml")
    with pytest.raises(Exception) as excinfo:
        _mutate(
            engine, "set_component",
            {"entity": virtual, "component": "doc", "data": {}},
        )
    assert _code(excinfo) == "backfill_readonly"
    with pytest.raises(Exception) as excinfo:
        _mutate(engine, "delete_entity", {"entity": virtual})
    assert _code(excinfo) == "backfill_readonly"


def test_revision_gate_and_idempotent_replay_through_engine():
    engine = _engine()
    head = _head(engine)
    # A replay resubmits the identical envelope (same revision text).
    first = _submit(
        engine, "create_entity",
        {"kind": "a", "expected_revision": head}, "req-ecs-w1",
    )
    replayed = _submit(
        engine, "create_entity",
        {"kind": "a", "expected_revision": head}, "req-ecs-w1",
    )
    assert replayed == first
    with pytest.raises(Exception) as excinfo:
        _submit(
            engine, "create_entity",
            {"kind": "b", "expected_revision": head},
            "req-ecs-w2",
        )
    assert _code(excinfo) == "revision_conflict"


def test_unknown_entity_codes_through_engine():
    engine = _engine()
    ghost = "ent-000000000000"
    with pytest.raises(Exception) as excinfo:
        _submit(
            engine, "get_component",
            {"entity": ghost, "component": "sources"},
        )
    assert _code(excinfo) == "unknown_entity"
    with pytest.raises(Exception) as excinfo:
        _mutate(engine, "delete_entity", {"entity": ghost})
    assert _code(excinfo) == "unknown_entity"


def test_mcp_tool_definitions_cover_ecs_names():
    from rocket_engine.adapters.mcp.server import (
        describe_tool,
        tool_definitions,
    )

    names = {tool.name for tool in tool_definitions()}
    for name in (
        "create_entity", "set_component", "attach_component",
        "detach_component", "delete_entity", "get_component",
        "components_of", "entities_with", "get_world_snapshot",
    ):
        assert name in names
        assert "no handler wired yet" not in describe_tool(name)
