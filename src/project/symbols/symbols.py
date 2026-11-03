"""Project-owned schematic symbols: pins, graphics, properties, revisions."""

from ...interfaces.errors import ContractError

#: Component name symbols carry on their entity.
SYMBOL_COMPONENT = "Symbol"

#: Electrical pin types a symbol pin may carry.
PIN_TYPES = ("input", "output", "inout", "passive", "power")


def _is_int(value):
    """True for real ints (bools excluded)."""
    return isinstance(value, int) and not isinstance(value, bool)


def validate_pin(pin):
    """Validate one symbol pin record at edit time.

    Args:
        pin: Pin mapping with name, pin_type, x, and y keys.

    Returns:
        Normalized pin copy.

    Raises:
        ContractError: invalid_symbol for any shape violation.
    """
    if not isinstance(pin, dict):
        raise ContractError(
            "invalid_symbol", f"Symbol pin must be a mapping, got {pin!r}."
        )
    for key in pin:
        if key not in ("name", "pin_type", "x", "y"):
            raise ContractError(
                "invalid_symbol", f"Unknown symbol pin key: {key}."
            )
    name = pin.get("name")
    if not isinstance(name, str) or not name:
        raise ContractError(
            "invalid_symbol", "Symbol pin name must be non-empty text."
        )
    if pin.get("pin_type") not in PIN_TYPES:
        raise ContractError(
            "invalid_symbol",
            f"Symbol pin type must be one of {PIN_TYPES}.",
        )
    for axis in ("x", "y"):
        if not _is_int(pin.get(axis)):
            raise ContractError(
                "invalid_symbol",
                f"Symbol pin {axis} must be an int, got "
                f"{pin.get(axis)!r}.",
            )
    return {
        "name": name, "pin_type": pin["pin_type"],
        "x": pin["x"], "y": pin["y"],
    }


def validate_symbol(symbol):
    """Validate a Symbol component mapping at edit time.

    Args:
        symbol: Symbol mapping with name, pins, graphics,
            properties, and revision keys.

    Returns:
        Normalized Symbol copy.

    Raises:
        ContractError: invalid_symbol for any shape violation.
    """
    if not isinstance(symbol, dict):
        raise ContractError(
            "invalid_symbol", f"Symbol must be a mapping, got {symbol!r}."
        )
    for key in symbol:
        if key not in ("name", "pins", "graphics", "properties",
                       "revision"):
            raise ContractError(
                "invalid_symbol", f"Unknown Symbol key: {key}."
            )
    name = symbol.get("name")
    if not isinstance(name, str) or not name:
        raise ContractError(
            "invalid_symbol", "Symbol name must be non-empty text."
        )
    pins = symbol.get("pins", [])
    if not isinstance(pins, list):
        raise ContractError(
            "invalid_symbol", "Symbol pins must be a list."
        )
    clean_pins = [validate_pin(pin) for pin in pins]
    seen = [pin["name"] for pin in clean_pins]
    if len(set(seen)) != len(seen):
        raise ContractError(
            "invalid_symbol", "Symbol pin names must be distinct."
        )
    graphics = symbol.get("graphics", [])
    if not isinstance(graphics, list) or not all(
        isinstance(item, dict) and isinstance(item.get("kind"), str)
        for item in graphics
    ):
        raise ContractError(
            "invalid_symbol",
            "Symbol graphics must be a list of {kind, ...} items.",
        )
    properties = symbol.get("properties", {})
    if not isinstance(properties, dict) or not all(
        isinstance(key, str) and isinstance(val, str)
        for key, val in properties.items()
    ):
        raise ContractError(
            "invalid_symbol",
            "Symbol properties must map text to text.",
        )
    revision = symbol.get("revision", 1)
    if not _is_int(revision) or revision < 1:
        raise ContractError(
            "invalid_symbol", "Symbol revision must be a positive int."
        )
    return {
        "name": name, "pins": clean_pins,
        "graphics": [dict(item) for item in graphics],
        "properties": dict(properties), "revision": revision,
    }


def _read_symbol(store, symbol_id):
    """Return the normalized Symbol for one entity id."""
    try:
        raw = store.get_component(symbol_id, SYMBOL_COMPONENT)
    except LookupError:
        raise ContractError(
            "unknown_symbol",
            f"No such symbol entity: {symbol_id!r}.",
        ) from None
    value = validate_symbol(raw)
    value["id"] = symbol_id
    return value


def _all_symbols(store):
    """List every symbol mapping, name-sorted."""
    found = []
    for entity in store.entities_with(SYMBOL_COMPONENT):
        try:
            found.append(_read_symbol(store, entity))
        except ContractError:
            continue
    found.sort(key=lambda item: item["name"])
    return found


def _check_name_free(store, name, except_id=None):
    """Fail loudly when a symbol name is already taken."""
    for item in _all_symbols(store):
        if item["name"] == name and item["id"] != except_id:
            raise ContractError(
                "symbol_exists", f"Symbol already exists: {name!r}."
            )


def create_symbol(store, actor, name, pins, graphics=None,
                  properties=None):
    """Create one project-owned symbol definition.

    Args:
        store: Entity store serving the ENGINE-ECS seam.
        actor: Attribution recorded on the revision and events.
        name: Unique symbol name.
        pins: Pin records with name, pin_type, x, and y.
        graphics: Editable graphics items ({kind, ...}).
        properties: Text-to-text symbol properties.

    Returns:
        Receipt with op, actor, revision, symbol id, and events.

    Raises:
        ContractError: invalid_symbol for a malformed symbol,
            symbol_exists for a duplicate name.
    """
    value = validate_symbol({
        "name": name, "pins": pins, "graphics": graphics or [],
        "properties": properties or {}, "revision": 1,
    })
    _check_name_free(store, value["name"])
    made = store.create_entity(actor, f"create_symbol {value['name']}")
    store.attach_component(
        actor, made["id"], SYMBOL_COMPONENT, value,
        f"create_symbol {value['name']}",
    )
    return {
        "op": "create_symbol", "actor": actor,
        "revision": made["revision"], "symbol": made["id"],
        "events": [
            {"event": "entity_created", "entity": made["id"]},
            {"event": "component_changed", "entity": made["id"],
             "component": SYMBOL_COMPONENT},
        ],
    }


def copy_symbol(store, actor, symbol_id, name):
    """Copy one symbol definition under a new name at revision 1.

    Args:
        store: Entity store serving the ENGINE-ECS seam.
        actor: Attribution recorded on the revision and events.
        symbol_id: Source symbol entity id.
        name: New unique symbol name.

    Returns:
        Receipt with op, actor, revision, symbol id, and events.

    Raises:
        ContractError: unknown_symbol for a missing source,
            symbol_exists for a duplicate name.
    """
    source = _read_symbol(store, symbol_id)
    return create_symbol(
        store, actor, name, source["pins"],
        graphics=source["graphics"], properties=source["properties"],
    )


def rename_symbol(store, actor, symbol_id, name):
    """Rename one symbol; refuse while instances reference it.

    Args:
        store: Entity store serving the ENGINE-ECS seam.
        actor: Attribution recorded on the revision and events.
        symbol_id: Symbol entity id to rename.
        name: New unique symbol name.

    Returns:
        Receipt with op, actor, revision, symbol id, and name.

    Raises:
        ContractError: unknown_symbol for a missing symbol,
            symbol_exists for a duplicate name, symbol_in_use
            when instances reference the old name.
    """
    value = _read_symbol(store, symbol_id)
    if not isinstance(name, str) or not name:
        raise ContractError(
            "invalid_symbol", "Symbol name must be non-empty text."
        )
    _check_name_free(store, name, except_id=symbol_id)
    for entity in store.entities_with("Instance"):
        try:
            instance = store.get_component(entity, "Instance")
        except LookupError:
            continue
        if (
            isinstance(instance, dict)
            and instance.get("symbol") == value["name"]
        ):
            raise ContractError(
                "symbol_in_use",
                f"Symbol {value['name']!r} is placed on instance "
                f"{entity!r}.",
            )
    clean = validate_symbol({
        "name": name, "pins": value["pins"],
        "graphics": value["graphics"],
        "properties": value["properties"],
        "revision": value["revision"],
    })
    changed = store.set_component(
        actor, symbol_id, SYMBOL_COMPONENT, clean,
        f"rename_symbol {name}",
    )
    return {
        "op": "rename_symbol", "actor": actor,
        "revision": changed["revision"], "symbol": symbol_id,
        "name": name, "events": [],
    }


def revise_symbol(store, actor, symbol_id, pins=None, graphics=None,
                  properties=None):
    """Revise one symbol definition, bumping its revision.

    Args:
        store: Entity store serving the ENGINE-ECS seam.
        actor: Attribution recorded on the revision and events.
        symbol_id: Symbol entity id to revise.
        pins: Replacement pin records, or None to keep.
        graphics: Replacement graphics items, or None to keep.
        properties: Replacement properties, or None to keep.

    Returns:
        Receipt with op, actor, revision, symbol id, and the
            new symbol revision.

    Raises:
        ContractError: unknown_symbol for a missing symbol,
            invalid_symbol for a malformed revision.
    """
    value = _read_symbol(store, symbol_id)
    clean = validate_symbol({
        "name": value["name"],
        "pins": pins if pins is not None else value["pins"],
        "graphics": (
            graphics if graphics is not None else value["graphics"]
        ),
        "properties": (
            properties if properties is not None
            else value["properties"]
        ),
        "revision": value["revision"] + 1,
    })
    changed = store.set_component(
        actor, symbol_id, SYMBOL_COMPONENT, clean,
        f"revise_symbol {value['name']}",
    )
    return {
        "op": "revise_symbol", "actor": actor,
        "revision": changed["revision"], "symbol": symbol_id,
        "symbol_revision": clean["revision"], "events": [],
    }


def get_symbol(store, symbol_id):
    """Read one symbol definition by entity id.

    Args:
        store: Entity store serving the ENGINE-ECS seam.
        symbol_id: Symbol entity id to read.

    Returns:
        Symbol mapping with id, name, pins, graphics,
            properties, and revision.

    Raises:
        ContractError: unknown_symbol for a missing symbol.
    """
    return _read_symbol(store, symbol_id)


def list_symbols(store):
    """List every symbol definition, name-sorted.

    Args:
        store: Entity store serving the ENGINE-ECS seam.

    Returns:
        Symbol mappings with ids, name-sorted.
    """
    return _all_symbols(store)
