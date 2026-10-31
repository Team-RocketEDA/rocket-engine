"""ENGINE-ECS unit tests — entity store projected over docs + ledger.

Tests assume `src/interfaces/engine_ecs_store.py` with:
  ENTITY_DOC_PREFIX/SUFFIX, EcsError, validate_entity_id,
  validate_component_name, validate_kind, validate_component_data,
  mint_entity_id, entity_doc_path, entity_from_doc_path, is_entity_doc,
  parse_address, format_address, encode_entity_doc, decode_entity_doc,
  backfill_id_for_doc, is_backfill_id, backfill_entity_for_doc,
  backfill_entities, match_predicate, filter_entities,
  build_world_snapshot, component_changed_data, EntityStore.

Valid RED = the load itself fails: the module does not exist yet.

Policy under test (docs/tickets/ENGINE-ECS.md):
  entities + components JSON projected over the doc store + ledger,
  engine-provisioned IDs only, entity.component canonical addressing
  with doc paths as the documented storage projection (no second
  identity system), component_changed(entity, component, revision)
  ledger/event emission, miniplex-shape world snapshot, filter
  queries components_of/entities_with, backfill for current project
  docs without breaking revisions.
"""

import hashlib
import importlib.util
import inspect
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load_store():
    # RED: src/interfaces/engine_ecs_store.py does not exist yet.
    location = ROOT / "src" / "interfaces" / "engine_ecs_store.py"
    spec = importlib.util.spec_from_file_location(
        "engine_ecs_store_under_test", location
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


store = _load_store()


def _code(excinfo):
    return getattr(excinfo.value, "code", None)


def _fresh():
    return store.EntityStore(project_id="ecs_demo", actor="human")


# --- engine-provisioned IDs only -------------------------------------------

def test_create_mints_engine_id_and_takes_no_id_argument():
    params = inspect.signature(store.EntityStore.create_entity).parameters
    assert "entity" not in params
    assert "entity_id" not in params
    assert "id" not in params
    created = _fresh().create_entity()
    assert created["entity"].startswith("ent-")
    store.validate_entity_id(created["entity"])


def test_minted_ids_are_unique_and_well_formed():
    ids = {_fresh().create_entity()["entity"] for _ in range(25)}
    assert len(ids) == 25
    for entity in ids:
        assert entity.startswith("ent-")
        store.validate_entity_id(entity)


def test_mint_entity_id_skips_taken_ids():
    first = store.mint_entity_id(existing=set())
    second = store.mint_entity_id(existing={first})
    assert first != second
    assert first.startswith("ent-")
    assert second.startswith("ent-")


def test_validate_entity_id_rejects_dots_uppercase_and_empties():
    for bad in ("", "ENT-abc", "ent.a", "has space", "ent/a", ".", "-x"):
        with pytest.raises(Exception) as excinfo:
            store.validate_entity_id(bad)
        assert _code(excinfo) == "invalid_entity"


# --- canonical addressing -------------------------------------------------

def test_address_format_parse_round_trip():
    ecs = _fresh()
    entity = ecs.create_entity()["entity"]
    address = store.format_address(entity, "sources")
    assert address == f"{entity}.sources"
    assert store.parse_address(address) == (entity, "sources")


def test_parse_address_rejects_ambiguous_and_empty_parts():
    for bad in ("no-dot-here", "a.b.c", ".sources", "ent-x.", "", "."):
        with pytest.raises(Exception) as excinfo:
            store.parse_address(bad)
        assert _code(excinfo) == "invalid_address"


def test_component_names_reject_dots_so_addresses_stay_unambiguous():
    for bad in ("", "has.dot", "has space", "a/b", ".", "9"):
        if bad == "9":
            store.validate_component_name(bad)  # digits are fine
            continue
        with pytest.raises(Exception) as excinfo:
            store.validate_component_name(bad)
        assert _code(excinfo) == "invalid_component"
    store.validate_component_name("CellLink")
    store.validate_component_name("sources")
    store.validate_component_name("pin-1")


# --- storage projection: doc paths, no second identity --------------------

def test_entity_doc_path_round_trip_is_derived_from_id_only():
    entity = "ent-0123456789ab"
    path = store.entity_doc_path(entity)
    assert path == "entities/ent-0123456789ab.json"
    assert store.entity_from_doc_path(path) == entity
    assert store.is_entity_doc(path) is True
    # Same id in, same path out — the path carries no extra identity.
    assert store.entity_doc_path(entity) == path


def test_non_entity_docs_are_not_entity_docs():
    assert store.is_entity_doc("design/top.yaml") is False
    assert store.is_entity_doc("entities/notes.txt") is False
    assert store.is_entity_doc("entities/sub/x.json") is False
    assert store.entity_from_doc_path("design/top.yaml") is None


def test_entity_doc_encode_decode_round_trip_is_deterministic():
    first = store.encode_entity_doc(
        "ent-0123456789ab", "block", {"sources": ["a"], "pins": {"p1": 1}}
    )
    second = store.encode_entity_doc(
        "ent-0123456789ab", "block", {"pins": {"p1": 1}, "sources": ["a"]}
    )
    assert first == second
    decoded = store.decode_entity_doc(first)
    assert decoded["entity"] == "ent-0123456789ab"
    assert decoded["kind"] == "block"
    assert decoded["components"] == {"sources": ["a"], "pins": {"p1": 1}}


def test_decode_rejects_garbage_and_shape_violations():
    with pytest.raises(Exception) as excinfo:
        store.decode_entity_doc("not json {{{")
    assert _code(excinfo) == "invalid_document"
    with pytest.raises(Exception) as excinfo:
        store.decode_entity_doc(json.dumps({"entity": "x"}))
    assert _code(excinfo) == "invalid_document"


def test_component_data_must_be_json_serializable():
    ecs = _fresh()
    entity = ecs.create_entity()["entity"]
    with pytest.raises(Exception) as excinfo:
        ecs.set_component(entity, "bad", {"nan": float("nan")})
    assert _code(excinfo) == "invalid_data"
    with pytest.raises(Exception) as excinfo:
        ecs.set_component(entity, "bad", {"obj": object()})
    assert _code(excinfo) == "invalid_data"


# --- acceptance flow: block -> sources -> wired pins -> events -> world ---

def test_acceptance_create_attach_wire_events_world():
    ecs = _fresh()
    block = ecs.create_entity(kind="block")["entity"]
    pin = ecs.create_entity(kind="pin")["entity"]

    attached = ecs.attach_component(block, "sources", ["design/top.yaml"])
    assert attached["address"] == f"{block}.sources"
    assert attached["path"] == store.entity_doc_path(block)

    wired = ecs.set_component(
        block, "wires", {"w1": {"from": f"{block}.p1", "to": f"{pin}.pad"}}
    )
    assert wired["address"] == f"{block}.wires"

    fetched = ecs.get_component(block, "wires")
    assert fetched["data"]["w1"]["to"] == f"{pin}.pad"
    assert fetched["address"] == f"{block}.wires"
    assert fetched["path"] == store.entity_doc_path(block)

    events = ecs.events_since(0)
    kinds = [e["event"] for e in events]
    assert kinds == [
        "entity_created", "entity_created",
        "component_changed", "component_changed",
    ]
    changed = events[2]
    assert changed["data"]["entity"] == block
    assert changed["data"]["component"] == "sources"
    assert changed["data"]["revision"] == attached["current_revision"]
    assert changed["actor"] == "human"

    world = ecs.world_snapshot()
    by_id = {e["id"]: e for e in world["entities"]}
    assert by_id[block]["components"]["sources"] == ["design/top.yaml"]
    assert by_id[block]["components"]["wires"]["w1"]["to"] == f"{pin}.pad"
    assert by_id[block]["kind"] == "block"
    assert world["current_revision"] == wired["current_revision"]


def test_no_path_entity_drift_across_crud_events_queries():
    ecs = _fresh()
    created = ecs.create_entity(kind="block")
    entity = created["entity"]
    path = created["path"]
    assert path == store.entity_doc_path(entity)

    ecs.set_component(entity, "sources", ["a"])
    # Plain doc CRUD sees the same bytes under the derived path.
    listing = ecs.list_docs(prefix="entities")
    assert path in [d["path"] for d in listing["documents"]]
    raw = json.loads(ecs.read_doc(path)["content"])
    assert raw["entity"] == entity
    assert raw["components"]["sources"] == ["a"]
    # Events and queries cite the same id.
    changed = [
        e for e in ecs.events_since(0) if e["event"] == "component_changed"
    ]
    assert changed[0]["data"]["entity"] == entity
    assert ecs.components_of(entity)["components"] == ["sources"]
    assert entity in ecs.entities_with("sources")["entities"]
    world_ids = [e["id"] for e in ecs.world_snapshot()["entities"]]
    assert entity in world_ids


# --- component lifecycle errors --------------------------------------------

def test_attach_refuses_duplicates_detach_needs_existing():
    ecs = _fresh()
    entity = ecs.create_entity()["entity"]
    ecs.attach_component(entity, "sources", [])
    with pytest.raises(Exception) as excinfo:
        ecs.attach_component(entity, "sources", [])
    assert _code(excinfo) == "component_exists"
    with pytest.raises(Exception) as excinfo:
        ecs.detach_component(entity, "missing")
    assert _code(excinfo) == "unknown_component"
    with pytest.raises(Exception) as excinfo:
        ecs.get_component(entity, "missing")
    assert _code(excinfo) == "unknown_component"


def test_detach_removes_and_emits_detached_change():
    ecs = _fresh()
    entity = ecs.create_entity()["entity"]
    ecs.attach_component(entity, "sources", ["a"])
    detached = ecs.detach_component(entity, "sources")
    assert ecs.components_of(entity)["components"] == []
    event = detached["events"][0]
    assert event["event"] == "component_changed"
    assert event["data"]["detached"] is True
    assert event["data"]["revision"] == detached["current_revision"]


def test_set_upserts_and_detach_absent_is_an_error():
    ecs = _fresh()
    entity = ecs.create_entity()["entity"]
    ecs.set_component(entity, "sources", ["a"])
    ecs.set_component(entity, "sources", ["b"])
    assert ecs.get_component(entity, "sources")["data"] == ["b"]
    with pytest.raises(Exception) as excinfo:
        ecs.detach_component(entity, "nope")
    assert _code(excinfo) == "unknown_component"


def test_unknown_entity_fails_loudly_on_every_verb():
    ecs = _fresh()
    ghost = "ent-000000000000"
    with pytest.raises(Exception) as excinfo:
        ecs.get_component(ghost, "sources")
    assert _code(excinfo) == "unknown_entity"
    with pytest.raises(Exception) as excinfo:
        ecs.set_component(ghost, "sources", [])
    assert _code(excinfo) == "unknown_entity"
    with pytest.raises(Exception) as excinfo:
        ecs.attach_component(ghost, "sources", [])
    assert _code(excinfo) == "unknown_entity"
    with pytest.raises(Exception) as excinfo:
        ecs.detach_component(ghost, "sources")
    assert _code(excinfo) == "unknown_entity"
    with pytest.raises(Exception) as excinfo:
        ecs.delete_entity(ghost)
    assert _code(excinfo) == "unknown_entity"
    with pytest.raises(Exception) as excinfo:
        ecs.components_of(ghost)
    assert _code(excinfo) == "unknown_entity"


def test_delete_entity_removes_doc_and_event_marks_revision():
    ecs = _fresh()
    entity = ecs.create_entity()["entity"]
    ecs.set_component(entity, "sources", ["a"])
    deleted = ecs.delete_entity(entity)
    assert deleted["events"][0]["event"] == "entity_deleted"
    assert deleted["events"][0]["data"]["entity"] == entity
    assert deleted["events"][0]["data"]["revision"] == deleted[
        "current_revision"
    ]
    paths = [d["path"] for d in ecs.list_docs()["documents"]]
    assert store.entity_doc_path(entity) not in paths
    with pytest.raises(Exception) as excinfo:
        ecs.get_component(entity, "sources")
    assert _code(excinfo) == "unknown_entity"


def test_corrupt_entity_doc_fails_loudly_not_silently():
    ecs = _fresh()
    entity = ecs.create_entity()["entity"]
    ecs.write_doc(store.entity_doc_path(entity), "garbage {{{")
    with pytest.raises(Exception) as excinfo:
        ecs.get_component(entity, "sources")
    assert _code(excinfo) == "invalid_document"
    with pytest.raises(Exception) as excinfo:
        ecs.world_snapshot()
    assert _code(excinfo) == "invalid_document"


# --- filter queries --------------------------------------------------------

def test_components_of_lists_sorted_names():
    ecs = _fresh()
    entity = ecs.create_entity()["entity"]
    assert ecs.components_of(entity)["components"] == []
    ecs.set_component(entity, "wires", {})
    ecs.set_component(entity, "sources", [])
    assert ecs.components_of(entity)["components"] == ["sources", "wires"]


def test_entities_with_finds_holders_and_applies_predicates():
    ecs = _fresh()
    on_vdd = ecs.create_entity(kind="pin")["entity"]
    on_gnd = ecs.create_entity(kind="pin")["entity"]
    bare = ecs.create_entity(kind="pin")["entity"]
    ecs.set_component(on_vdd, "net", {"name": "VDD", "class": "power"})
    ecs.set_component(on_gnd, "net", {"name": "VSS", "class": "power"})
    ecs.set_component(bare, "other", {"name": "VDD"})
    assert ecs.entities_with("missing")["entities"] == []
    holders = ecs.entities_with("net")["entities"]
    assert holders == sorted([on_vdd, on_gnd])
    matched = ecs.entities_with("net", {"class": "power"})["entities"]
    assert matched == sorted([on_vdd, on_gnd])
    only_vdd = ecs.entities_with("net", {"name": "VDD"})["entities"]
    assert only_vdd == [on_vdd]
    assert ecs.entities_with("net", {"name": "NOPE"})["entities"] == []


def test_predicate_needs_dict_data_and_dict_predicate():
    assert store.match_predicate({"a": 1}, None) is True
    assert store.match_predicate({"a": 1}, {"a": 1}) is True
    assert store.match_predicate({"a": 1}, {"a": 2}) is False
    assert store.match_predicate(["not", "dict"], {"a": 1}) is False
    with pytest.raises(Exception) as excinfo:
        store.match_predicate({"a": 1}, ["nope"])
    assert _code(excinfo) == "invalid_predicate"
    ecs = _fresh()
    entity = ecs.create_entity()["entity"]
    ecs.set_component(entity, "tags", ["x"])
    assert ecs.entities_with("tags", {"x": 1})["entities"] == []


def test_filter_entities_pure_helper_matches_store():
    records = [
        {"id": "ent-000000000001", "kind": "", "components": {"n": {"v": 1}}},
        {"id": "ent-000000000002", "kind": "", "components": {"n": {"v": 2}}},
        {"id": "ent-000000000003", "kind": "", "components": {}},
    ]
    assert store.filter_entities(records, "n") == [
        "ent-000000000001", "ent-000000000002",
    ]
    assert store.filter_entities(records, "n", {"v": 2}) == [
        "ent-000000000002"
    ]
    assert store.filter_entities(records, "missing") == []


# --- world snapshot --------------------------------------------------------

def test_world_snapshot_is_miniplex_shaped_and_sorted():
    ecs = _fresh()
    second = ecs.create_entity(kind="net")["entity"]
    first = ecs.create_entity(kind="block")["entity"]
    ecs.set_component(first, "sources", ["a"])
    world = ecs.world_snapshot()
    assert world["project_id"] == "ecs_demo"
    assert world["current_revision"] == ecs.snapshot()["current_revision"]
    ids = [e["id"] for e in world["entities"]]
    assert ids == sorted(ids)
    assert {first, second} <= set(ids)
    by_id = {e["id"]: e for e in world["entities"]}
    assert by_id[first]["kind"] == "block"
    assert by_id[first]["components"] == {"sources": ["a"]}
    assert by_id[second]["components"] == {}


def test_build_world_snapshot_pure_helper_sorts_by_id():
    world = store.build_world_snapshot(
        "p", "p13",
        [
            {"id": "ent-000000000002", "kind": "b", "components": {}},
            {"id": "ent-000000000001", "kind": "a", "components": {"x": 1}},
        ],
    )
    assert [e["id"] for e in world["entities"]] == [
        "ent-000000000001", "ent-000000000002",
    ]


def test_component_changed_data_carries_entity_component_revision():
    data = store.component_changed_data("ent-1", "sources", "p13")
    assert data == {
        "entity": "ent-1", "component": "sources", "revision": "p13"
    }
    detached = store.component_changed_data(
        "ent-1", "sources", "p14", detached=True
    )
    assert detached["detached"] is True


# --- backfill: current docs as read-only entities --------------------------

def test_backfill_ids_are_deterministic_and_doc_prefixed():
    first = store.backfill_id_for_doc("design/top.yaml")
    assert first == store.backfill_id_for_doc("design/top.yaml")
    assert first.startswith("doc-")
    assert first != store.backfill_id_for_doc("design/other.yaml")
    assert store.is_backfill_id(first) is True
    assert store.is_backfill_id("ent-0123456789ab") is False
    expected = "doc-" + hashlib.sha1(
        b"design/top.yaml").hexdigest()[:12]
    assert first == expected


def test_world_snapshot_backfills_plain_docs_without_new_revisions():
    ecs = _fresh()
    ecs.write_doc("design/top.yaml", "top: true\n")
    ecs.write_doc("scripts/run.tcl", "run\n")
    before = ecs.snapshot()["current_revision"]
    world = ecs.world_snapshot()
    assert ecs.snapshot()["current_revision"] == before
    backfilled = [e for e in world["entities"] if e["id"].startswith("doc-")]
    assert len(backfilled) == 2
    by_path = {
        e["components"]["doc"]["path"]: e for e in backfilled
    }
    assert set(by_path) == {"design/top.yaml", "scripts/run.tcl"}
    assert by_path["design/top.yaml"]["kind"] == "backfilled-doc"
    assert by_path["design/top.yaml"]["components"]["doc"]["bytes"] == len(
        b"top: true\n"
    )
    lean = ecs.world_snapshot(include_backfill=False)
    assert [e for e in lean["entities"] if e["id"].startswith("doc-")] == []
    assert ecs.snapshot()["current_revision"] == before


def test_backfill_entities_pure_helper_skips_entity_docs():
    entries = [
        {"path": "design/top.yaml", "bytes": 9},
        {"path": "entities/ent-0123456789ab.json", "bytes": 3},
    ]
    backfilled = store.backfill_entities(entries)
    assert len(backfilled) == 1
    assert backfilled[0]["components"]["doc"]["path"] == "design/top.yaml"


def test_backfill_entities_are_readable_but_read_only():
    ecs = _fresh()
    ecs.write_doc("design/top.yaml", "top: true\n")
    virtual = store.backfill_id_for_doc("design/top.yaml")
    assert ecs.components_of(virtual)["components"] == ["doc"]
    fetched = ecs.get_component(virtual, "doc")
    assert fetched["data"] == {"path": "design/top.yaml", "bytes": 10}
    for verb in ("set", "attach", "detach", "delete"):
        with pytest.raises(Exception) as excinfo:
            if verb == "set":
                ecs.set_component(virtual, "doc", {})
            elif verb == "attach":
                ecs.attach_component(virtual, "extra", {})
            elif verb == "detach":
                ecs.detach_component(virtual, "doc")
            else:
                ecs.delete_entity(virtual)
        assert _code(excinfo) == "backfill_readonly"


def test_entities_with_doc_component_finds_backfilled_docs():
    ecs = _fresh()
    ecs.write_doc("design/top.yaml", "top: true\n")
    ecs.write_doc("design/other.yaml", "other: true\n")
    found = ecs.entities_with("doc")["entities"]
    assert found == sorted([
        store.backfill_id_for_doc("design/top.yaml"),
        store.backfill_id_for_doc("design/other.yaml"),
    ])
    only_top = ecs.entities_with("doc", {"path": "design/top.yaml"})[
        "entities"
    ]
    assert only_top == [store.backfill_id_for_doc("design/top.yaml")]


# --- ledger law: revisions, idempotency, gating ----------------------------

def test_every_mutation_advances_revision_and_logs_one_event():
    ecs = _fresh()
    head = ecs.snapshot()["current_revision"]
    created = ecs.create_entity()
    assert created["previous_revision"] == head
    assert created["current_revision"] != head
    assert len(created["events"]) == 1
    assert created["event_cursor"] == 1
    assert created["revision_transition"] == {
        "from": head, "to": created["current_revision"]
    }
    assert created["actor"] == "human"
    assert created["rewind_handle"]["revision"] == head


def test_replay_returns_stored_response_without_advancing():
    ecs = _fresh()
    first = ecs.create_entity(kind="a", request_id="req-ecs-1")
    again = ecs.create_entity(kind="a", request_id="req-ecs-1")
    assert again == first
    assert ecs.snapshot()["event_cursor"] == 1
    entity = first["entity"]
    written = ecs.set_component(
        entity, "sources", ["a"], request_id="req-ecs-2"
    )
    replayed = ecs.set_component(
        entity, "sources", ["a"], request_id="req-ecs-2"
    )
    assert replayed == written
    assert ecs.snapshot()["event_cursor"] == 2


def test_reused_request_id_with_new_text_conflicts():
    ecs = _fresh()
    ecs.create_entity(kind="a", request_id="req-ecs-9")
    with pytest.raises(Exception) as excinfo:
        ecs.create_entity(kind="b", request_id="req-ecs-9")
    assert _code(excinfo) == "request_conflict"


def test_stale_expected_revision_fails_instead_of_merging():
    ecs = _fresh()
    head = ecs.snapshot()["current_revision"]
    ecs.create_entity()
    with pytest.raises(Exception) as excinfo:
        ecs.create_entity(expected_revision=head)
    assert _code(excinfo) == "revision_conflict"
    entity = ecs.create_entity()["entity"]
    with pytest.raises(Exception) as excinfo:
        ecs.set_component(entity, "s", [], expected_revision=head)
    assert _code(excinfo) == "revision_conflict"


def test_events_since_pages_after_cursor():
    ecs = _fresh()
    ecs.create_entity()
    ecs.create_entity()
    assert [e["seq"] for e in ecs.events_since(0)] == [1, 2]
    assert [e["seq"] for e in ecs.events_since(1)] == [2]
    assert ecs.events_since(2) == []


def test_existing_doc_crud_keeps_working_alongside_entities():
    ecs = _fresh()
    written = ecs.write_doc("design/top.yaml", "top: true\n")
    assert written["events"][0]["event"] == "doc_written"
    assert ecs.read_doc("design/top.yaml")["content"] == "top: true\n"
    entity = ecs.create_entity()["entity"]
    ecs.set_component(entity, "sources", ["design/top.yaml"])
    assert ecs.read_doc("design/top.yaml")["content"] == "top: true\n"
    paths = [d["path"] for d in ecs.list_docs()["documents"]]
    assert "design/top.yaml" in paths
    assert store.entity_doc_path(entity) in paths
    with pytest.raises(Exception) as excinfo:
        ecs.read_doc("missing.yaml")
    assert _code(excinfo) == "unknown_document"


def test_kind_validation_rejects_non_text():
    with pytest.raises(Exception) as excinfo:
        store.validate_kind(123)
    assert _code(excinfo) == "invalid_kind"
    assert store.validate_kind("") == ""
    assert store.validate_kind("block") == "block"
