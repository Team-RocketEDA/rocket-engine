"""ENTITY-CAS RED — per-entity revisions + compare-and-swap.

Valid RED = entity records carry no per-entity revision yet, so every
test asserting entity_revision fails.
"""
import pytest

from rocket_engine.project.errors import ProjectError
from rocket_engine.project.service import ProjectService


def _handles(tmp_path=None):
    # Two handles share one durable root so human/agent writes are
    # mutually visible (the collaboration the ticket is about).
    kwargs = {} if tmp_path is None else {"engine_root": str(tmp_path)}
    human = ProjectService(
        project_id="cas_demo", actor={"kind": "user"}, **kwargs
    )
    agent = ProjectService(
        project_id="cas_demo", actor={"kind": "agent"}, **kwargs
    )
    return human, agent


def _create(service, kind="cell", components=None):
    head = service.snapshot()["current_revision"]
    return service.create_entity(
        f"req-create-{kind}-{head}", f"create {kind} at {head}",
        kind=kind, components=components or {},
        expected_revision=head,
    )


# record shape ------------------------------------------------------------


def test_create_entity_response_carries_entity_revision_one(tmp_path):
    human, _ = _handles(tmp_path)
    created = _create(human)
    assert created["entity_revision"] == 1


def test_get_component_reports_entity_revision(tmp_path):
    human, _ = _handles(tmp_path)
    created = _create(human, components={"spec": {"w": 1}})
    got = human.get_component(created["entity"], "spec")
    assert got["entity_revision"] == 1


def test_legacy_record_without_revision_decodes_as_one(tmp_path):
    from rocket_engine.stores import ecs

    text = (
        '{"components": {"spec": {"w": 1}}, '
        '"entity": "e-abcdef123456", "kind": "cell"}'
    )
    assert ecs.decode_entity_doc(text)["entity_revision"] == 1


# compare-and-swap ---------------------------------------------------------


def test_set_with_matching_entity_revision_lands_and_bumps(tmp_path):
    human, _ = _handles(tmp_path)
    created = _create(human, components={"spec": {"w": 1}})
    entity = created["entity"]

    out = human.set_component(
        entity, "spec", {"w": 2}, "req-set-1", "set spec",
        expected_revision=created["current_revision"],
        expected_entity_revision=1,
    )
    assert out["entity_revision"] == 2
    assert human.get_component(entity, "spec")["entity_revision"] == 2


def test_set_with_stale_entity_revision_conflicts_loudly(tmp_path):
    human, _ = _handles(tmp_path)
    created = _create(human, components={"spec": {"w": 1}})
    entity = created["entity"]
    first = human.set_component(
        entity, "spec", {"w": 2}, "req-set-1", "set spec",
        expected_revision=created["current_revision"],
        expected_entity_revision=1,
    )
    with pytest.raises(ProjectError) as exc:
        human.set_component(
            entity, "spec", {"w": 3}, "req-set-2", "set spec again",
            expected_revision=first["current_revision"],
            expected_entity_revision=1,
        )
    assert exc.value.code == "revision_conflict"
    assert entity in str(exc.value)
    assert "1" in str(exc.value) and "2" in str(exc.value)


def test_different_entities_with_stale_global_head_both_land(tmp_path):
    human, agent = _handles(tmp_path)
    head_a = human.snapshot()["current_revision"]
    ea = _create(human, kind="cell-a")
    # Agent read the head before the human's create advanced it.
    eb = agent.create_entity(
        "req-create-b", "create b",
        kind="cell-b", components={},
        expected_revision=head_a,
    )
    first = agent.set_component(
        eb["entity"], "spec", {"w": 1}, "req-b-1", "agent spec",
        expected_entity_revision=1,
    )
    # Human's global head is stale (agent advanced it), but the entity
    # revision is current: different entities never conflict.
    out = human.set_component(
        ea["entity"], "spec", {"w": 9}, "req-a-1", "human spec",
        expected_revision=head_a,
        expected_entity_revision=1,
    )
    assert out["entity_revision"] == 2
    assert first["entity_revision"] == 2


def test_same_entity_race_exactly_one_wins(tmp_path):
    human, agent = _handles(tmp_path)
    created = _create(human, components={"spec": {"w": 1}})
    entity = created["entity"]
    rev = created["entity_revision"]
    head = created["current_revision"]

    agent.set_component(
        entity, "spec", {"w": 2}, "req-agent-1", "agent spec",
        expected_revision=head, expected_entity_revision=rev,
    )
    with pytest.raises(ProjectError) as exc:
        human.set_component(
            entity, "spec", {"w": 3}, "req-human-1", "human spec",
            expected_revision=head, expected_entity_revision=rev,
        )
    assert exc.value.code == "revision_conflict"
    assert human.get_component(entity, "spec")["data"] == {"w": 2}


def test_missing_entity_revision_keeps_legacy_global_gate(tmp_path):
    human, _ = _handles(tmp_path)
    created = _create(human, components={"spec": {"w": 1}})
    with pytest.raises(ProjectError) as exc:
        human.set_component(
            created["entity"], "spec", {"w": 2},
            "req-legacy-1", "legacy write",
            expected_revision="p0",
        )
    assert exc.value.code == "revision_conflict"


def test_delete_entity_cas_guards_stale_revision(tmp_path):
    human, _ = _handles(tmp_path)
    created = _create(human)
    entity = created["entity"]
    human.set_component(
        entity, "x", {"v": 1}, "req-x-1", "add x",
        expected_revision=created["current_revision"],
        expected_entity_revision=1,
    )
    with pytest.raises(ProjectError) as exc:
        human.delete_entity(
            entity, "req-del-1", "delete",
            expected_revision=human.snapshot()["current_revision"],
            expected_entity_revision=1,
        )
    assert exc.value.code == "revision_conflict"
