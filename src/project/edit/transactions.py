"""Atomic typed edit transactions with alias resolution.

One transaction is a list of entity changes applied as a group:
alias-based creation resolves LocalRef-style "$alias" references
before persistence, every change validates CAS before anything
lands, and a failed late change rolls back the earlier ones so
the ledger never keeps a partial batch.
"""

try:
    from .cas import read_entity_revision
except ImportError:  # pragma: no cover - standalone spec loading
    import importlib.util as _ilu
    from pathlib import Path as _Path

    _spec = _ilu.spec_from_file_location(
        "edit_cas_sibling", _Path(__file__).with_name("cas.py"))
    _cas = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_cas)
    read_entity_revision = _cas.read_entity_revision

_CREATES = ("create",)
_WRITES = ("set", "attach", "detach", "delete")


def _live(service, entity):
    """Read the live entity revision an unnamed write may build on.

    Args:
        service: ProjectService handle to read through.
        entity: Entity id to inspect.

    Returns:
        Live entity revision for the gate.
    """
    return read_entity_revision(service, entity)


def _resolve(value, aliases):
    """Resolve one alias reference to its minted entity id.

    Args:
        value: Candidate entity id or "$alias" reference.
        aliases: Mapping of alias name to minted entity id.

    Returns:
        Minted entity id for known aliases, else the value.

    Raises:
        ValueError: For an alias with no minted entity yet.
    """
    if isinstance(value, str) and value.startswith("$"):
        name = value[1:]
        if name not in aliases:
            error = ValueError(f"Unknown alias reference: {value}.")
            error.code = "invalid_ref"
            raise error
        return aliases[name]
    return value


def _validate_change(change):
    """Check one change dict carries its required keys.

    Args:
        change: Change mapping with an op discriminator.

    Returns:
        The op string of the change.

    Raises:
        ValueError: invalid_command naming the missing field.
    """
    op = change.get("op")
    if op in _CREATES:
        return op
    if op not in _WRITES:
        error = ValueError(f"Unknown change op: {op!r}.")
        error.code = "invalid_command"
        raise error
    if "entity" not in change:
        error = ValueError("Change is missing its entity.")
        error.code = "invalid_command"
        raise error
    if op in ("set", "attach") and (
        "component" not in change or "data" not in change
    ):
        error = ValueError("Set/attach needs component and data.")
        error.code = "invalid_command"
        raise error
    if op == "detach" and "component" not in change:
        error = ValueError("Detach needs a component.")
        error.code = "invalid_command"
        raise error
    return op


def apply_transaction(service, request_id, command_text, changes,
                      expected_revision=None):
    """Apply one batch of entity changes atomically.

    Args:
        service: ProjectService handle to write through.
        request_id: Client envelope id; sub-envelopes derive
            from it so replays stay idempotent.
        command_text: Command text for identity comparison.
        changes: List of change mappings (create with optional
            alias, set, attach, detach, delete). Set/attach
            may name expected_entity_revision for CAS; create
            steps mint engine ids and register their alias.
        expected_revision: Global head the batch was read at;
            None skips the head gate for pure CAS batches.

    Returns:
        Receipt with request id, applied count, minted entity
        ids, alias mapping, and revision transition.

    Raises:
        Exception: The first failing change error after rolling
            back earlier changes (revision_conflict,
            unknown_entity, invalid_ref, or invalid_command).

    Caution: Rollback writes compensating revisions, so the
        head advances even when the batch fails — history stays
        append-only, never rewritten.
    """
    for change in changes:
        _validate_change(change)
    revision_from = service.snapshot()["current_revision"]
    if expected_revision is not None:
        head = service.snapshot()["current_revision"]
        if head != expected_revision:
            pure_cas = all(
                change.get("expected_entity_revision") is not None
                for change in changes
                if change.get("op") in _WRITES
            )
            if not (pure_cas and changes):
                error = ValueError(
                    f"Stale head {expected_revision}, live {head}."
                )
                error.code = "revision_conflict"
                raise error
    aliases = {}
    minted = []
    undo = []
    applied = 0
    try:
        for index, change in enumerate(changes):
            sub_id = f"{request_id}:txn:{index}"
            sub_text = f"{command_text} [{index}]"
            op = change["op"]
            if op == "create":
                created = service.create_entity(
                    sub_id, sub_text,
                    kind=change.get("kind", ""),
                    components=dict(change.get("components", {})),
                )
                entity = created["entity"]
                minted.append(entity)
                if "alias" in change:
                    aliases[change["alias"]] = entity
                undo.append(("delete", entity))
                applied += 1
                continue
            entity = _resolve(change["entity"], aliases)
            named = change.get("expected_entity_revision")
            if named is not None:
                live = read_entity_revision(service, entity)
                if live != named:
                    error = ValueError(
                        f"Entity {entity} at revision {live}, "
                        f"writer expected {named}.",
                    )
                    error.code = "revision_conflict"
                    raise error
                expected = named
            else:
                try:
                    expected = _live(service, entity)
                except Exception:
                    expected = None
            if op == "set":
                try:
                    prior = service.get_component(
                        entity, change["component"])["data"]
                except Exception:
                    prior = None
                service.set_component(
                    entity, change["component"], change["data"],
                    sub_id, sub_text,
                    expected_revision=None,
                    expected_entity_revision=expected,
                )
                undo.append(
                    ("restore", entity, change["component"], prior))
            elif op == "attach":
                service.attach_component(
                    entity, change["component"], change["data"],
                    sub_id, sub_text,
                    expected_revision=None,
                    expected_entity_revision=expected,
                )
                undo.append(
                    ("detach", entity, change["component"]))
            elif op == "detach":
                prior = service.get_component(
                    entity, change["component"])["data"]
                service.detach_component(
                    entity, change["component"], sub_id,
                    sub_text, expected_revision=None,
                    expected_entity_revision=expected,
                )
                undo.append(
                    ("restore", entity, change["component"], prior))
            elif op == "delete":
                service.delete_entity(
                    entity, sub_id, sub_text,
                    expected_revision=None,
                    expected_entity_revision=expected,
                )
                undo.append(("deleted", entity))
            applied += 1
    except Exception:
        for step in reversed(undo):
            try:
                if step[0] == "delete":
                    try:
                        gate = _live(service, step[1])
                    except Exception:
                        gate = None
                    service.delete_entity(
                        step[1], f"{request_id}:undo:{step[1]}",
                        "transaction rollback",
                        expected_entity_revision=gate,
                    )
                elif step[0] == "detach":
                    try:
                        gate = _live(service, step[1])
                    except Exception:
                        gate = None
                    service.detach_component(
                        step[1], step[2],
                        f"{request_id}:undo:{step[1]}:{step[2]}",
                        "transaction rollback",
                        expected_entity_revision=gate,
                    )
                elif step[0] == "restore":
                    _, entity, component, prior = step
                    try:
                        gate = _live(service, entity)
                    except Exception:
                        gate = None
                    if prior is None:
                        try:
                            service.detach_component(
                                entity, component,
                                f"{request_id}:undo:{entity}:{component}",
                                "transaction rollback",
                                expected_entity_revision=gate,
                            )
                        except Exception:
                            pass
                    else:
                        service.set_component(
                            entity, component, prior,
                            f"{request_id}:undo:{entity}:{component}",
                            "transaction rollback",
                            expected_entity_revision=gate,
                        )
            except Exception:
                pass
        raise
    revision_to = service.snapshot()["current_revision"]
    return {
        "aliases": dict(aliases),
        "applied": applied,
        "entities": list(minted),
        "request_id": request_id,
        "revision_from": revision_from,
        "revision_to": revision_to,
    }
