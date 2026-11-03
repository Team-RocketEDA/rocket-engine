"""Symbol-to-cell linkage: durable pin maps with CELL-LINK semantics.

A Linkage entity binds one project symbol to one cell with an
explicit symbol-pin-to-cell-port map. Resolution reuses the
CELL-LINK contract (explicit entries win, unlisted pins resolve
to themselves); the frontend renders persisted maps as visible
pin-link strings while unmatched and conflicting pins are
reported explicitly, never hidden.
"""

from ...interfaces import celllink
from ...interfaces.errors import ContractError

#: Component name linkages carry on their entity.
LINKAGE_COMPONENT = "Linkage"

#: Prefixes treated as immutable upstream cell references.
SCOPED_PREFIXES = ("pdk:", "lib:", "pkg:")


def _is_int(value):
    """True for real ints (bools excluded)."""
    return isinstance(value, int) and not isinstance(value, bool)


def validate_linkage(linkage):
    """Validate a Linkage component mapping at edit time.

    Args:
        linkage: Linkage mapping with symbol, cell, pin_map, and
            revision keys.

    Returns:
        Normalized Linkage copy.

    Raises:
        ContractError: invalid_linkage for any shape violation.
    """
    if not isinstance(linkage, dict):
        raise ContractError(
            "invalid_linkage",
            f"Linkage must be a mapping, got {linkage!r}.",
        )
    for key in linkage:
        if key not in ("symbol", "cell", "pin_map", "revision"):
            raise ContractError(
                "invalid_linkage", f"Unknown Linkage key: {key}."
            )
    symbol = linkage.get("symbol")
    cell = linkage.get("cell")
    if not isinstance(symbol, str) or not symbol:
        raise ContractError(
            "invalid_linkage", "Linkage symbol must be non-empty text."
        )
    if not isinstance(cell, str) or not cell:
        raise ContractError(
            "invalid_linkage", "Linkage cell must be non-empty text."
        )
    pin_map = linkage.get("pin_map", [])
    if not isinstance(pin_map, list):
        raise ContractError(
            "invalid_linkage", "Linkage pin_map must be a list."
        )
    clean_map = []
    seen = set()
    for entry in pin_map:
        if (
            not isinstance(entry, dict)
            or set(entry) != {"symPin", "cellPin"}
            or not entry.get("symPin")
            or not isinstance(entry["symPin"], str)
            or not entry.get("cellPin")
            or not isinstance(entry["cellPin"], str)
        ):
            raise ContractError(
                "invalid_linkage",
                "pin_map entries need symPin + cellPin text.",
            )
        if entry["symPin"] in seen:
            raise ContractError(
                "invalid_linkage",
                f"symPin {entry['symPin']!r} names more than one target.",
            )
        seen.add(entry["symPin"])
        clean_map.append(
            {"symPin": entry["symPin"], "cellPin": entry["cellPin"]}
        )
    revision = linkage.get("revision", 1)
    if not _is_int(revision) or revision < 1:
        raise ContractError(
            "invalid_linkage", "Linkage revision must be a positive int."
        )
    return {
        "symbol": symbol, "cell": cell,
        "pin_map": clean_map, "revision": revision,
    }


def _symbol_pins(store, symbol):
    """Return pin names for one project symbol, failing loudly."""
    for entity in store.entities_with("Symbol"):
        try:
            found = store.get_component(entity, "Symbol")
        except LookupError:
            continue
        if isinstance(found, dict) and found.get("name") == symbol:
            pins = found.get("pins", [])
            return [pin["name"] for pin in pins
                    if isinstance(pin, dict) and pin.get("name")]
    raise ContractError(
        "unknown_symbol", f"No such project symbol: {symbol!r}."
    )


def _cell_ports(store, cell):
    """Return port names for one cell; scoped refs pass with []."""
    if cell.startswith(SCOPED_PREFIXES):
        return []
    for entity in store.entities_with("Cell"):
        try:
            found = store.get_component(entity, "Cell")
        except LookupError:
            continue
        if isinstance(found, dict) and found.get("name") == cell:
            ports = found.get("ports", [])
            return [port["name"] for port in ports
                    if isinstance(port, dict) and port.get("name")]
    raise ContractError(
        "unknown_cell", f"No such project cell: {cell!r}."
    )


def _find_linkage(store, symbol, cell):
    """Return (entity, linkage) for one pair, or (None, None)."""
    for entity in store.entities_with(LINKAGE_COMPONENT):
        try:
            raw = store.get_component(entity, LINKAGE_COMPONENT)
        except LookupError:
            continue
        try:
            value = validate_linkage(raw)
        except ContractError:
            continue
        if value["symbol"] == symbol and value["cell"] == cell:
            value["id"] = entity
            return entity, value
    return None, None


def map_pins(store, actor, symbol, cell, pin_map):
    """Create or remap the pin map for one symbol-cell pair.

    A first map lands at revision 1; remapping the same pair
    bumps the stored revision. Geometry is never duplicated —
    only the pin correspondence is stored.

    Args:
        store: Entity store serving the ENGINE-ECS seam.
        actor: Attribution recorded on the revision and events.
        symbol: Project symbol name being linked.
        cell: Project cell name (or scoped upstream reference).
        pin_map: Explicit [{symPin, cellPin}] entries.

    Returns:
        Receipt with op, actor, revision, linkage id, and the
            stored linkage revision.

    Raises:
        ContractError: unknown_symbol for a missing symbol,
            unknown_cell for a missing project cell,
            invalid_linkage for a malformed map.
    """
    _symbol_pins(store, symbol)
    _cell_ports(store, cell)
    value = validate_linkage({
        "symbol": symbol, "cell": cell,
        "pin_map": pin_map, "revision": 1,
    })
    entity, current = _find_linkage(store, symbol, cell)
    if entity is None:
        made = store.create_entity(actor, f"map_pins {symbol}")
        store.attach_component(
            actor, made["id"], LINKAGE_COMPONENT, value,
            f"map_pins {symbol}",
        )
        return {
            "op": "map_pins", "actor": actor,
            "revision": made["revision"], "linkage": made["id"],
            "linkage_revision": 1,
            "events": [
                {"event": "entity_created", "entity": made["id"]},
                {"event": "component_changed", "entity": made["id"],
                 "component": LINKAGE_COMPONENT},
            ],
        }
    value["revision"] = current["revision"] + 1
    changed = store.set_component(
        actor, entity, LINKAGE_COMPONENT, value,
        f"map_pins {symbol}",
    )
    return {
        "op": "map_pins", "actor": actor,
        "revision": changed["revision"], "linkage": entity,
        "linkage_revision": value["revision"], "events": [],
    }


def check_mapping(store, symbol, cell=None):
    """Report unmatched and conflicting pins for one linkage.

    Args:
        store: Entity store serving the ENGINE-ECS seam.
        symbol: Project symbol name to check.
        cell: Cell name, or None to use the stored linkage cell.

    Returns:
        Mapping with symbol, cell, unmatched_symbol_pins,
            unmatched_cell_ports, and conflicts (each naming
            the offending symPin and reason).

    Raises:
        ContractError: unknown_symbol for a missing symbol,
            unknown_linkage when no linkage exists.
    """
    pins = _symbol_pins(store, symbol)
    entity, value = None, None
    if cell is not None:
        _cell_ports(store, cell)
        entity, value = _find_linkage(store, symbol, cell)
    else:
        for candidate in store.entities_with(LINKAGE_COMPONENT):
            try:
                raw = store.get_component(candidate, LINKAGE_COMPONENT)
            except LookupError:
                continue
            try:
                parsed = validate_linkage(raw)
            except ContractError:
                continue
            if parsed["symbol"] == symbol:
                entity, value = candidate, parsed
                value["id"] = candidate
                break
    if value is None:
        raise ContractError(
            "unknown_linkage",
            f"No linkage stored for symbol {symbol!r}.",
        )
    ports = _cell_ports(store, value["cell"])
    mapped = {entry["symPin"] for entry in value["pin_map"]}
    targeted = {entry["cellPin"] for entry in value["pin_map"]}
    conflicts = []
    for entry in value["pin_map"]:
        if entry["symPin"] not in pins:
            conflicts.append({
                "symPin": entry["symPin"],
                "reason": f"no such symbol pin on {symbol!r}",
            })
        elif ports and entry["cellPin"] not in ports:
            conflicts.append({
                "symPin": entry["symPin"],
                "reason": f"no such cell port on {value['cell']!r}",
            })
    return {
        "symbol": symbol, "cell": value["cell"], "linkage": entity,
        "unmatched_symbol_pins": sorted(set(pins) - mapped),
        "unmatched_cell_ports": sorted(set(ports) - targeted),
        "conflicts": conflicts,
    }


def pin_link_strings(store, symbol, cell=None):
    """Render persisted maps as visible pin-link strings.

    Args:
        store: Entity store serving the ENGINE-ECS seam.
        symbol: Project symbol name to render.
        cell: Cell name, or None to use the stored linkage cell.

    Returns:
        Mapping with symbol, cell, links (``SYM.pin ->
            CELL.port`` strings in map order), plus the
            unmatched and conflicting pin reports.

    Raises:
        ContractError: unknown_symbol for a missing symbol,
            unknown_linkage when no linkage exists.
    """
    report = check_mapping(store, symbol, cell)
    entity = report["linkage"]
    try:
        raw = store.get_component(entity, LINKAGE_COMPONENT)
    except LookupError:
        raise ContractError(
            "unknown_linkage",
            f"Linkage vanished mid-read: {entity!r}.",
        ) from None
    value = validate_linkage(raw)
    return {
        "symbol": symbol, "cell": report["cell"],
        "links": [
            f"{symbol}.{entry['symPin']} -> "
            f"{report['cell']}.{entry['cellPin']}"
            for entry in value["pin_map"]
        ],
        "unmatched_symbol_pins": report["unmatched_symbol_pins"],
        "unmatched_cell_ports": report["unmatched_cell_ports"],
        "conflicts": report["conflicts"],
    }


def resolve_mapped_pin(store, symbol, pin, cell=None):
    """Resolve one symbol pin to its cell pin (pin chokepoint).

    Explicit map entries win; unlisted pins resolve to
    themselves (identity default), per CELL-LINK semantics.

    Args:
        store: Entity store serving the ENGINE-ECS seam.
        symbol: Project symbol name holding the pin.
        pin: Symbol pin to resolve.
        cell: Cell name, or None to use the stored linkage cell.

    Returns:
        Resolved cell-pin name ("" when no linkage exists —
            resolution stays total for the query lane).

    Raises:
        ContractError: unknown_symbol for a missing symbol.
    """
    _symbol_pins(store, symbol)
    _, value = (None, None)
    if cell is not None:
        _, value = _find_linkage(store, symbol, cell)
    else:
        for candidate in store.entities_with(LINKAGE_COMPONENT):
            try:
                raw = store.get_component(candidate, LINKAGE_COMPONENT)
            except LookupError:
                continue
            try:
                parsed = validate_linkage(raw)
            except ContractError:
                continue
            if parsed["symbol"] == symbol:
                value = parsed
                break
    if value is None:
        return pin
    block = {"CellLink": {
        "cell": value["cell"],
        "pinMap": value["pin_map"],
        "cellFilters": [],
        "variantOverrides": {},
    }}
    return celllink.resolve_pin(block, pin)
