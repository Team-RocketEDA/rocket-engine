"""Per-entity compare-and-swap reads and writes.

Thin helpers over the ProjectService entity verbs: reads report
the live per-entity revision and writes gate on it, so editors
fail loudly with revision_conflict instead of merging.
"""

_MISSING = object()


def read_entity_revision(service, entity):
    """Return the live per-entity revision of one entity.

    Args:
        service: ProjectService handle to read through.
        entity: Engine-minted entity id to inspect.

    Returns:
        Integer entity revision (legacy records read as 1).

    Raises:
        Exception: Whatever the service raises for unknown or
            malformed entity ids.
    """
    names = service.components_of(entity)["components"]
    if not names:
        return 1
    got = service.get_component(entity, names[0])
    return got.get("entity_revision", 1)


def require_revision(service, entity, expected):
    """Check one entity revision without writing.

    Args:
        service: ProjectService handle to read through.
        entity: Engine-minted entity id to inspect.
        expected: Revision the writer read, or None to skip.

    Returns:
        Live entity revision the write may build on.

    Raises:
        Exception: revision_conflict when the live revision
            differs from the expected one.
    """
    live = read_entity_revision(service, entity)
    if expected is not None and expected != live:
        error = ValueError(
            f"Entity {entity} at revision {live}, "
            f"writer expected {expected}.",
        )
        error.code = "revision_conflict"
        raise error
    return live


def cas_set(service, entity, component, data, request_id,
            command_text, expected_entity_revision,
            expected_revision=None):
    """Upsert one component gated on its entity revision.

    Args:
        service: ProjectService handle to write through.
        entity: Entity id holding the component.
        component: Component name to write.
        data: JSON payload to store.
        request_id: Client envelope id for idempotent replay.
        command_text: Command text for identity comparison.
        expected_entity_revision: Entity revision the writer
            read; a stale value fails instead of merging.
        expected_revision: Global head gate, skipped when an
            entity revision is named (disjoint edits land).

    Returns:
        Service mutation mapping with the bumped
        entity_revision.

    Raises:
        Exception: revision_conflict for a stale entity
            revision, or whatever the service raises.
    """
    return service.set_component(
        entity, component, data, request_id, command_text,
        expected_revision=expected_revision,
        expected_entity_revision=expected_entity_revision,
    )
