"""Project-owned physical cells: ports, properties, revisions, hierarchy."""

from ...interfaces.errors import ContractError

#: Component name cells carry on their entity.
CELL_COMPONENT = "Cell"


def _is_int(value):
    """True for real ints (bools excluded)."""
    return isinstance(value, int) and not isinstance(value, bool)


def validate_port(port):
    """Validate one cell port record at edit time.

    Args:
        port: Port mapping with name, x, y, and layer keys.

    Returns:
        Normalized port copy.

    Raises:
        ContractError: invalid_cell for any shape violation.
    """
    if not isinstance(port, dict):
        raise ContractError(
            "invalid_cell", f"Cell port must be a mapping, got {port!r}."
        )
    for key in port:
        if key not in ("name", "x", "y", "layer"):
            raise ContractError(
                "invalid_cell", f"Unknown cell port key: {key}."
            )
    name = port.get("name")
    if not isinstance(name, str) or not name:
        raise ContractError(
            "invalid_cell", "Cell port name must be non-empty text."
        )
    for axis in ("x", "y"):
        if not _is_int(port.get(axis)):
            raise ContractError(
                "invalid_cell",
                f"Cell port {axis} must be an int, got "
                f"{port.get(axis)!r}.",
            )
    layer = port.get("layer")
    if not isinstance(layer, str) or not layer:
        raise ContractError(
            "invalid_cell", "Cell port layer must be non-empty text."
        )
    return {"name": name, "x": port["x"], "y": port["y"], "layer": layer}


def validate_cell(cell):
    """Validate a Cell component mapping at edit time.

    Args:
        cell: Cell mapping with name, ports, properties, and
            revision keys.

    Returns:
        Normalized Cell copy.

    Raises:
        ContractError: invalid_cell for any shape violation.
    """
    if not isinstance(cell, dict):
        raise ContractError(
            "invalid_cell", f"Cell must be a mapping, got {cell!r}."
        )
    for key in cell:
        if key not in ("name", "ports", "properties", "revision"):
            raise ContractError(
                "invalid_cell", f"Unknown Cell key: {key}."
            )
    name = cell.get("name")
    if not isinstance(name, str) or not name:
        raise ContractError(
            "invalid_cell", "Cell name must be non-empty text."
        )
    ports = cell.get("ports", [])
    if not isinstance(ports, list):
        raise ContractError(
            "invalid_cell", "Cell ports must be a list."
        )
    clean_ports = [validate_port(port) for port in ports]
    seen = [port["name"] for port in clean_ports]
    if len(set(seen)) != len(seen):
        raise ContractError(
            "invalid_cell", "Cell port names must be distinct."
        )
    properties = cell.get("properties", {})
    if not isinstance(properties, dict) or not all(
        isinstance(key, str) and isinstance(val, str)
        for key, val in properties.items()
    ):
        raise ContractError(
            "invalid_cell", "Cell properties must map text to text."
        )
    revision = cell.get("revision", 1)
    if not _is_int(revision) or revision < 1:
        raise ContractError(
            "invalid_cell", "Cell revision must be a positive int."
        )
    return {
        "name": name, "ports": clean_ports,
        "properties": dict(properties), "revision": revision,
    }


def _read_cell(store, cell_id):
    """Return the normalized Cell for one entity id."""
    try:
        raw = store.get_component(cell_id, CELL_COMPONENT)
    except LookupError:
        raise ContractError(
            "unknown_cell", f"No such cell entity: {cell_id!r}."
        ) from None
    value = validate_cell(raw)
    value["id"] = cell_id
    return value


def _all_cells(store):
    """List every cell mapping, name-sorted."""
    found = []
    for entity in store.entities_with(CELL_COMPONENT):
        try:
            found.append(_read_cell(store, entity))
        except ContractError:
            continue
    found.sort(key=lambda item: item["name"])
    return found


def _check_name_free(store, name, except_id=None):
    """Fail loudly when a cell name is already taken."""
    for item in _all_cells(store):
        if item["name"] == name and item["id"] != except_id:
            raise ContractError(
                "cell_exists", f"Cell already exists: {name!r}."
            )


def create_cell(store, actor, name, ports, properties=None):
    """Create one project-owned physical cell definition.

    Args:
        store: Entity store serving the ENGINE-ECS seam.
        actor: Attribution recorded on the revision and events.
        name: Unique cell name.
        ports: Port records with name, x, y, and layer.
        properties: Text-to-text cell properties.

    Returns:
        Receipt with op, actor, revision, cell id, and events.

    Raises:
        ContractError: invalid_cell for a malformed cell,
            cell_exists for a duplicate name.
    """
    value = validate_cell({
        "name": name, "ports": ports,
        "properties": properties or {}, "revision": 1,
    })
    _check_name_free(store, value["name"])
    made = store.create_entity(actor, f"create_cell {value['name']}")
    store.attach_component(
        actor, made["id"], CELL_COMPONENT, value,
        f"create_cell {value['name']}",
    )
    return {
        "op": "create_cell", "actor": actor,
        "revision": made["revision"], "cell": made["id"],
        "events": [
            {"event": "entity_created", "entity": made["id"]},
            {"event": "component_changed", "entity": made["id"],
             "component": CELL_COMPONENT},
        ],
    }


def copy_cell(store, actor, cell_id, name):
    """Copy one cell definition under a new name at revision 1.

    Args:
        store: Entity store serving the ENGINE-ECS seam.
        actor: Attribution recorded on the revision and events.
        cell_id: Source cell entity id.
        name: New unique cell name.

    Returns:
        Receipt with op, actor, revision, cell id, and events.

    Raises:
        ContractError: unknown_cell for a missing source,
            cell_exists for a duplicate name.
    """
    source = _read_cell(store, cell_id)
    return create_cell(
        store, actor, name, source["ports"],
        properties=source["properties"],
    )


def rename_cell(store, actor, cell_id, name):
    """Rename one cell; refuse while linkage references it.

    Args:
        store: Entity store serving the ENGINE-ECS seam.
        actor: Attribution recorded on the revision and events.
        cell_id: Cell entity id to rename.
        name: New unique cell name.

    Returns:
        Receipt with op, actor, revision, cell id, and name.

    Raises:
        ContractError: unknown_cell for a missing cell,
            cell_exists for a duplicate name, cell_in_use when
            linkage references the old name.
    """
    value = _read_cell(store, cell_id)
    if not isinstance(name, str) or not name:
        raise ContractError(
            "invalid_cell", "Cell name must be non-empty text."
        )
    _check_name_free(store, name, except_id=cell_id)
    for entity in store.entities_with("Linkage"):
        try:
            link = store.get_component(entity, "Linkage")
        except LookupError:
            continue
        if (
            isinstance(link, dict)
            and link.get("cell") == value["name"]
        ):
            raise ContractError(
                "cell_in_use",
                f"Cell {value['name']!r} is linked by {entity!r}.",
            )
    clean = validate_cell({
        "name": name, "ports": value["ports"],
        "properties": value["properties"],
        "revision": value["revision"],
    })
    changed = store.set_component(
        actor, cell_id, CELL_COMPONENT, clean,
        f"rename_cell {name}",
    )
    return {
        "op": "rename_cell", "actor": actor,
        "revision": changed["revision"], "cell": cell_id,
        "name": name, "events": [],
    }


def revise_cell(store, actor, cell_id, ports=None, properties=None):
    """Revise one cell definition, bumping its revision.

    Args:
        store: Entity store serving the ENGINE-ECS seam.
        actor: Attribution recorded on the revision and events.
        cell_id: Cell entity id to revise.
        ports: Replacement port records, or None to keep.
        properties: Replacement properties, or None to keep.

    Returns:
        Receipt with op, actor, revision, cell id, and the new
            cell revision.

    Raises:
        ContractError: unknown_cell for a missing cell,
            invalid_cell for a malformed revision.
    """
    value = _read_cell(store, cell_id)
    clean = validate_cell({
        "name": value["name"],
        "ports": ports if ports is not None else value["ports"],
        "properties": (
            properties if properties is not None
            else value["properties"]
        ),
        "revision": value["revision"] + 1,
    })
    changed = store.set_component(
        actor, cell_id, CELL_COMPONENT, clean,
        f"revise_cell {value['name']}",
    )
    return {
        "op": "revise_cell", "actor": actor,
        "revision": changed["revision"], "cell": cell_id,
        "cell_revision": clean["revision"], "events": [],
    }


def get_cell(store, cell_id):
    """Read one cell definition by entity id.

    Args:
        store: Entity store serving the ENGINE-ECS seam.
        cell_id: Cell entity id to read.

    Returns:
        Cell mapping with id, name, ports, properties, and
            revision.

    Raises:
        ContractError: unknown_cell for a missing cell.
    """
    return _read_cell(store, cell_id)


def list_cells(store):
    """List every cell definition, name-sorted.

    Args:
        store: Entity store serving the ENGINE-ECS seam.

    Returns:
        Cell mappings with ids, name-sorted.
    """
    return _all_cells(store)
