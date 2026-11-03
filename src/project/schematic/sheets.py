"""Schematic sheets: durable sheet identities for hierarchical schematics."""

from ...interfaces.errors import ContractError

#: Component name sheets carry on their entity.
SHEET_COMPONENT = "Sheet"


def _need_name(value):
    """Accept one sheet name (non-empty, no whitespace)."""
    if not isinstance(value, str) or not value or value.split() != [value]:
        raise ContractError(
            "invalid_sheet", f"Sheet name must be blank-free text, got {value!r}."
        )
    return value


def validate_sheet(sheet):
    """Validate a Sheet component mapping at edit time.

    Args:
        sheet: Sheet mapping with name and title keys.

    Returns:
        Normalized Sheet copy.

    Raises:
        ContractError: invalid_sheet for any shape violation.
    """
    if not isinstance(sheet, dict):
        raise ContractError(
            "invalid_sheet", f"Sheet must be a mapping, got {sheet!r}."
        )
    for key in sheet:
        if key not in ("name", "title"):
            raise ContractError(
                "invalid_sheet", f"Unknown Sheet key: {key}."
            )
    title = sheet.get("title", "")
    if not isinstance(title, str):
        raise ContractError("invalid_sheet", "Sheet title must be text.")
    return {"name": _need_name(sheet.get("name")), "title": title}


def _read_sheet(store, sheet_id):
    """Return the normalized Sheet for one entity id."""
    try:
        raw = store.get_component(sheet_id, SHEET_COMPONENT)
    except LookupError:
        raise ContractError(
            "unknown_sheet", f"No such sheet entity: {sheet_id!r}."
        ) from None
    sheet = validate_sheet(raw)
    sheet["id"] = sheet_id
    return sheet


def _sheet_entities(store):
    """List (entity, sheet) pairs for every sheet, name-sorted."""
    found = []
    for entity in store.entities_with(SHEET_COMPONENT):
        found.append((entity, _read_sheet(store, entity)))
    found.sort(key=lambda pair: pair[1]["name"])
    return found


def create_sheet(store, actor, name, title=""):
    """Create one schematic sheet as a durable attributed revision.

    Args:
        store: Entity store serving the ENGINE-ECS seam.
        actor: Attribution recorded on the revision and events.
        name: Unique sheet name (blank-free text).
        title: Human title shown on the sheet frame.

    Returns:
        Receipt with op, actor, revision, sheet id, and events.

    Raises:
        ContractError: invalid_sheet for a malformed sheet,
            sheet_exists for a duplicate name.
    """
    value = validate_sheet({"name": name, "title": title})
    for _, sheet in _sheet_entities(store):
        if sheet["name"] == value["name"]:
            raise ContractError(
                "sheet_exists", f"Sheet already exists: {value['name']!r}."
            )
    made = store.create_entity(actor, f"create_sheet {value['name']}")
    store.attach_component(
        actor, made["id"], SHEET_COMPONENT, value,
        f"create_sheet {value['name']}",
    )
    return {
        "op": "create_sheet", "actor": actor,
        "revision": made["revision"], "sheet": made["id"],
        "events": [
            {"event": "entity_created", "entity": made["id"]},
            {"event": "component_changed", "entity": made["id"],
             "component": SHEET_COMPONENT},
        ],
    }


def rename_sheet(store, actor, sheet_id, name):
    """Rename one schematic sheet.

    Args:
        store: Entity store serving the ENGINE-ECS seam.
        actor: Attribution recorded on the revision and events.
        sheet_id: Sheet entity id to rename.
        name: New unique sheet name.

    Returns:
        Receipt with op, actor, revision, sheet id, and name.

    Raises:
        ContractError: unknown_sheet for a missing sheet,
            sheet_exists for a duplicate name.
    """
    sheet = _read_sheet(store, sheet_id)
    value = validate_sheet({"name": name, "title": sheet["title"]})
    for entity, other in _sheet_entities(store):
        if entity != sheet_id and other["name"] == value["name"]:
            raise ContractError(
                "sheet_exists", f"Sheet already exists: {value['name']!r}."
            )
    changed = store.set_component(
        actor, sheet_id, SHEET_COMPONENT, value,
        f"rename_sheet {value['name']}",
    )
    return {
        "op": "rename_sheet", "actor": actor,
        "revision": changed["revision"], "sheet": sheet_id,
        "name": value["name"], "events": [],
    }


def get_sheet(store, sheet_id):
    """Read one schematic sheet by entity id.

    Args:
        store: Entity store serving the ENGINE-ECS seam.
        sheet_id: Sheet entity id to read.

    Returns:
        Sheet mapping with id, name, and title.

    Raises:
        ContractError: unknown_sheet for a missing sheet.
    """
    return _read_sheet(store, sheet_id)


def list_sheets(store):
    """List every schematic sheet, name-sorted.

    Args:
        store: Entity store serving the ENGINE-ECS seam.

    Returns:
        Sheet mappings with id, name, and title.
    """
    return [sheet for _, sheet in _sheet_entities(store)]


def delete_sheet(store, actor, sheet_id):
    """Delete one schematic sheet; refuse when instances remain.

    Args:
        store: Entity store serving the ENGINE-ECS seam.
        actor: Attribution recorded on the revision and events.
        sheet_id: Sheet entity id to delete.

    Returns:
        Receipt with op, actor, revision, and sheet id.

    Raises:
        ContractError: unknown_sheet for a missing sheet,
            sheet_in_use when instances still sit on it.
    """
    _read_sheet(store, sheet_id)
    for entity in store.entities_with("Instance"):
        try:
            instance = store.get_component(entity, "Instance")
        except LookupError:
            continue
        if isinstance(instance, dict) and instance.get("sheet") == sheet_id:
            raise ContractError(
                "sheet_in_use",
                f"Sheet {sheet_id!r} still hosts instance {entity!r}.",
            )
    done = store.delete_entity(actor, sheet_id, f"delete_sheet {sheet_id}")
    return {
        "op": "delete_sheet", "actor": actor,
        "revision": done["revision"], "sheet": sheet_id,
        "events": [{"event": "entity_deleted", "entity": sheet_id}],
    }
