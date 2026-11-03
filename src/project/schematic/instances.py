"""Symbol instances: placed schematic references with transforms.

Instances point at a sheet plus a symbol: a bare project symbol
name (resolved against project Symbol entities) or a scoped
upstream reference (``pdk:``, ``lib:``, ``pkg:``) that passes
through untouched — PDK/library bytes are never edited here.
"""

from ...interfaces.errors import ContractError

#: Component name instances carry on their entity.
INSTANCE_COMPONENT = "Instance"

#: Allowed rotation steps in degrees.
ROTATIONS = (0, 90, 180, 270)

#: Prefixes treated as immutable upstream references.
SCOPED_PREFIXES = ("pdk:", "lib:", "pkg:")


def _is_int(value):
    """True for real ints (bools excluded)."""
    return isinstance(value, int) and not isinstance(value, bool)


def validate_instance(instance):
    """Validate an Instance component mapping at edit time.

    Args:
        instance: Instance mapping with sheet, symbol, x, y,
            rotation, mirror, properties, and ref keys.

    Returns:
        Normalized Instance copy.

    Raises:
        ContractError: invalid_instance for any shape violation.
    """
    if not isinstance(instance, dict):
        raise ContractError(
            "invalid_instance",
            f"Instance must be a mapping, got {instance!r}.",
        )
    for key in instance:
        if key not in ("sheet", "symbol", "x", "y", "rotation",
                       "mirror", "properties", "ref"):
            raise ContractError(
                "invalid_instance", f"Unknown Instance key: {key}."
            )
    sheet = instance.get("sheet")
    if not isinstance(sheet, str) or not sheet:
        raise ContractError(
            "invalid_instance", "Instance sheet must be an entity id."
        )
    symbol = instance.get("symbol")
    if not isinstance(symbol, str) or not symbol:
        raise ContractError(
            "invalid_instance", "Instance symbol must be a reference."
        )
    for axis in ("x", "y"):
        if not _is_int(instance.get(axis)):
            raise ContractError(
                "invalid_instance",
                f"Instance {axis} must be an int, got "
                f"{instance.get(axis)!r}.",
            )
    if instance.get("rotation") not in ROTATIONS:
        raise ContractError(
            "invalid_instance",
            f"Instance rotation must be one of {ROTATIONS}.",
        )
    if not isinstance(instance.get("mirror"), bool):
        raise ContractError(
            "invalid_instance", "Instance mirror must be a bool."
        )
    properties = instance.get("properties", {})
    if not isinstance(properties, dict) or not all(
        isinstance(key, str) and isinstance(val, str)
        for key, val in properties.items()
    ):
        raise ContractError(
            "invalid_instance",
            "Instance properties must map text to text.",
        )
    ref = instance.get("ref", "")
    if not isinstance(ref, str):
        raise ContractError(
            "invalid_instance", "Instance ref must be text."
        )
    return {
        "sheet": sheet, "symbol": symbol,
        "x": instance["x"], "y": instance["y"],
        "rotation": instance["rotation"],
        "mirror": instance["mirror"],
        "properties": dict(properties), "ref": ref,
    }


def _read_instance(store, instance_id):
    """Return the normalized Instance for one entity id."""
    try:
        raw = store.get_component(instance_id, INSTANCE_COMPONENT)
    except LookupError:
        raise ContractError(
            "unknown_instance",
            f"No such instance entity: {instance_id!r}.",
        ) from None
    value = validate_instance(raw)
    value["id"] = instance_id
    return value


def _check_sheet(store, sheet_id):
    """Fail loudly when a sheet entity is missing."""
    try:
        store.get_component(sheet_id, "Sheet")
    except LookupError:
        raise ContractError(
            "unknown_sheet", f"No such sheet entity: {sheet_id!r}."
        ) from None


def _check_symbol(store, symbol):
    """Resolve one symbol ref: bare names must exist, scoped pass."""
    if symbol.startswith(SCOPED_PREFIXES):
        return
    for entity in store.entities_with("Symbol"):
        try:
            found = store.get_component(entity, "Symbol")
        except LookupError:
            continue
        if isinstance(found, dict) and found.get("name") == symbol:
            return
    raise ContractError(
        "unknown_symbol", f"No such project symbol: {symbol!r}."
    )


def place_instance(store, actor, sheet, symbol, x, y, rotation=0,
                   mirror=False, properties=None, ref=""):
    """Place one symbol instance on a sheet.

    Args:
        store: Entity store serving the ENGINE-ECS seam.
        actor: Attribution recorded on the revision and events.
        sheet: Sheet entity id hosting the instance.
        symbol: Bare project symbol name or a scoped upstream
            reference (``pdk:``, ``lib:``, ``pkg:``).
        x: X position in schematic units.
        y: Y position in schematic units.
        rotation: Rotation in degrees (0/90/180/270).
        mirror: Mirror flag.
        properties: Text-to-text instance properties.
        ref: Annotation reference ("" means unannotated).

    Returns:
        Receipt with op, actor, revision, instance id, and events.

    Raises:
        ContractError: unknown_sheet for a missing sheet,
            unknown_symbol for a missing project symbol,
            invalid_instance for a malformed instance.
    """
    _check_sheet(store, sheet)
    _check_symbol(store, symbol)
    value = validate_instance({
        "sheet": sheet, "symbol": symbol, "x": x, "y": y,
        "rotation": rotation, "mirror": mirror,
        "properties": properties or {}, "ref": ref,
    })
    made = store.create_entity(actor, f"place_instance {symbol}")
    store.attach_component(
        actor, made["id"], INSTANCE_COMPONENT, value,
        f"place_instance {symbol}",
    )
    return {
        "op": "place_instance", "actor": actor,
        "revision": made["revision"], "instance": made["id"],
        "events": [
            {"event": "entity_created", "entity": made["id"]},
            {"event": "component_changed", "entity": made["id"],
             "component": INSTANCE_COMPONENT},
        ],
    }


def _rewrite(store, actor, instance_id, mutate, op):
    """Apply one instance mutation and report the receipt."""
    value = _read_instance(store, instance_id)
    mutate(value)
    clean = validate_instance({
        key: value[key] for key in (
            "sheet", "symbol", "x", "y", "rotation",
            "mirror", "properties", "ref")
    })
    changed = store.set_component(
        actor, instance_id, INSTANCE_COMPONENT, clean,
        f"{op} {instance_id}",
    )
    receipt = {
        "op": op, "actor": actor,
        "revision": changed["revision"], "instance": instance_id,
        "events": [],
    }
    receipt.update({
        key: clean[key] for key in (
            "x", "y", "rotation", "mirror", "properties", "ref")
    })
    return receipt


def move_instance(store, actor, instance_id, x, y):
    """Move one instance to a new schematic position.

    Args:
        store: Entity store serving the ENGINE-ECS seam.
        actor: Attribution recorded on the revision and events.
        instance_id: Instance entity id to move.
        x: New X position in schematic units.
        y: New Y position in schematic units.

    Returns:
        Receipt with op, actor, revision, instance id, and
            the new position.

    Raises:
        ContractError: unknown_instance for a missing instance,
            invalid_instance for a malformed position.
    """
    def _move(value):
        value["x"] = x
        value["y"] = y

    return _rewrite(store, actor, instance_id, _move, "move_instance")


def rotate_instance(store, actor, instance_id, rotation):
    """Rotate one instance to an orthogonal orientation.

    Args:
        store: Entity store serving the ENGINE-ECS seam.
        actor: Attribution recorded on the revision and events.
        instance_id: Instance entity id to rotate.
        rotation: New rotation in degrees (0/90/180/270).

    Returns:
        Receipt with op, actor, revision, instance id, and
            the new rotation.

    Raises:
        ContractError: unknown_instance for a missing instance,
            invalid_instance for a bad rotation.
    """
    def _rotate(value):
        value["rotation"] = rotation

    return _rewrite(store, actor, instance_id, _rotate, "rotate_instance")


def mirror_instance(store, actor, instance_id, mirror=True):
    """Mirror (or unmirror) one instance.

    Args:
        store: Entity store serving the ENGINE-ECS seam.
        actor: Attribution recorded on the revision and events.
        instance_id: Instance entity id to mirror.
        mirror: Mirror flag to set.

    Returns:
        Receipt with op, actor, revision, instance id, and
            the new mirror flag.

    Raises:
        ContractError: unknown_instance for a missing instance,
            invalid_instance for a non-bool flag.
    """
    def _mirror(value):
        value["mirror"] = mirror

    return _rewrite(store, actor, instance_id, _mirror, "mirror_instance")


def set_instance_properties(store, actor, instance_id, properties):
    """Replace one instance's text properties.

    Args:
        store: Entity store serving the ENGINE-ECS seam.
        actor: Attribution recorded on the revision and events.
        instance_id: Instance entity id to update.
        properties: New text-to-text property mapping.

    Returns:
        Receipt with op, actor, revision, instance id, and
            the new properties.

    Raises:
        ContractError: unknown_instance for a missing instance,
            invalid_instance for malformed properties.
    """
    def _props(value):
        value["properties"] = properties

    return _rewrite(
        store, actor, instance_id, _props, "set_instance_properties"
    )


def set_instance_ref(store, actor, instance_id, ref):
    """Set one instance's annotation reference.

    Args:
        store: Entity store serving the ENGINE-ECS seam.
        actor: Attribution recorded on the revision and events.
        instance_id: Instance entity id to annotate.
        ref: New reference text ("" clears the annotation).

    Returns:
        Receipt with op, actor, revision, instance id, and ref.

    Raises:
        ContractError: unknown_instance for a missing instance,
            invalid_instance for a non-text ref.
    """
    def _ref(value):
        value["ref"] = ref

    return _rewrite(
        store, actor, instance_id, _ref, "set_instance_ref"
    )


def get_instance(store, instance_id):
    """Read one instance by entity id.

    Args:
        store: Entity store serving the ENGINE-ECS seam.
        instance_id: Instance entity id to read.

    Returns:
        Instance mapping with id, sheet, symbol, transform,
            properties, and ref.

    Raises:
        ContractError: unknown_instance for a missing instance.
    """
    return _read_instance(store, instance_id)


def instances_on_sheet(store, sheet):
    """List every instance placed on one sheet, id-sorted.

    Args:
        store: Entity store serving the ENGINE-ECS seam.
        sheet: Sheet entity id to scan.

    Returns:
        Instance mappings with ids, id-sorted.
    """
    found = []
    for entity in store.entities_with(INSTANCE_COMPONENT):
        try:
            value = _read_instance(store, entity)
        except ContractError:
            continue
        if value["sheet"] == sheet:
            found.append(value)
    found.sort(key=lambda item: item["id"])
    return found


def delete_instance(store, actor, instance_id):
    """Delete one instance entity.

    Args:
        store: Entity store serving the ENGINE-ECS seam.
        actor: Attribution recorded on the revision and events.
        instance_id: Instance entity id to delete.

    Returns:
        Receipt with op, actor, revision, and instance id.

    Raises:
        ContractError: unknown_instance for a missing instance.
    """
    _read_instance(store, instance_id)
    done = store.delete_entity(
        actor, instance_id, f"delete_instance {instance_id}"
    )
    return {
        "op": "delete_instance", "actor": actor,
        "revision": done["revision"], "instance": instance_id,
        "events": [{"event": "entity_deleted", "entity": instance_id}],
    }
