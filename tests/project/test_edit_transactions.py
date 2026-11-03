"""API-V1-EDITORS RED — typed transactions + CAS over ProjectService.

Valid RED = src/project/edit/transactions.py and cas.py do not
exist yet, so the loader below fails.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SRC = ROOT / "src" / "project"


def _load(name, rel):
    path = SRC / rel
    assert path.is_file(), f"RED: missing owned module {path}"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def mods():
    cas = _load("edit_cas_red", "edit/cas.py")
    txn = _load("edit_txn_red", "edit/transactions.py")
    return cas, txn


def _service(tmp_path):
    from rocket_engine.project.service import ProjectService
    return ProjectService(
        project_id="edit_demo", actor={"kind": "user"},
        engine_root=str(tmp_path),
    )


def _create(service, head, kind="cell", components=None):
    return service.create_entity(
        f"req-create-{kind}-{head}-{id(service):x}",
        f"create {kind} at {head}",
        kind=kind, components=components or {},
        expected_revision=head,
    )


def test_cas_read_reports_live_revision(tmp_path, mods):
    cas, _ = mods
    service = _service(tmp_path)
    created = _create(service, service.snapshot()["current_revision"])
    assert cas.read_entity_revision(service, created["entity"]) == 1


def test_cas_stale_write_conflicts(tmp_path, mods):
    cas, _ = mods
    service = _service(tmp_path)
    created = _create(
        service, service.snapshot()["current_revision"],
        components={"spec": {"w": 1}},
    )
    entity = created["entity"]
    service.set_component(
        entity, "spec", {"w": 2}, "req-cas-1", "set spec",
        expected_revision=created["current_revision"],
        expected_entity_revision=1,
    )
    with pytest.raises(Exception) as excinfo:
        cas.cas_set(
            service, entity, "spec", {"w": 3}, "req-cas-2",
            "set spec again", expected_entity_revision=1,
        )
    assert getattr(excinfo.value, "code", None) == "revision_conflict"


def test_disjoint_entities_both_land(tmp_path, mods):
    _, txn = mods
    service = _service(tmp_path)
    head = service.snapshot()["current_revision"]
    first = _create(service, head, kind="cell-a")
    second = _create(service, first["current_revision"], kind="cell-b")
    receipt = txn.apply_transaction(
        service, "req-disjoint-1", "disjoint edit",
        changes=[
            {"op": "set", "entity": first["entity"],
             "component": "spec", "data": {"w": 1},
             "expected_entity_revision": 1},
            {"op": "set", "entity": second["entity"],
             "component": "spec", "data": {"h": 2},
             "expected_entity_revision": 1},
        ],
        expected_revision=second["current_revision"],
    )
    assert receipt["applied"] == 2
    assert service.get_component(
        first["entity"], "spec")["data"] == {"w": 1}


def test_failed_final_change_rolls_back(tmp_path, mods):
    _, txn = mods
    service = _service(tmp_path)
    head = service.snapshot()["current_revision"]
    created = _create(
        service, head, components={"spec": {"w": 1}},
    )
    entity = created["entity"]
    with pytest.raises(Exception):
        txn.apply_transaction(
            service, "req-rollback-1", "bad batch",
            changes=[
                {"op": "set", "entity": entity,
                 "component": "spec", "data": {"w": 9},
                 "expected_entity_revision": 1},
                {"op": "set", "entity": entity,
                 "component": "spec", "data": {"w": 10},
                 "expected_entity_revision": 1},
            ],
            expected_revision=created["current_revision"],
        )
    assert service.get_component(entity, "spec")["data"] == {"w": 1}


def test_alias_creation_resolves_local_ref(tmp_path, mods):
    _, txn = mods
    service = _service(tmp_path)
    receipt = txn.apply_transaction(
        service, "req-alias-1", "alias create",
        changes=[
            {"op": "create", "alias": "cellA", "kind": "cell",
             "components": {"spec": {"w": 1}}},
            {"op": "set", "entity": "$cellA",
             "component": "extra", "data": {"tag": True},
             "expected_entity_revision": 1},
        ],
        expected_revision=service.snapshot()["current_revision"],
    )
    assert receipt["applied"] == 2
    entity = receipt["aliases"]["cellA"]
    assert service.get_component(entity, "extra")["data"] == {"tag": True}
