"""IP lifecycle: per-PDK registries with symbol/footprint linkage.

IP blocks are prebuilt HIERARCHICAL schematic blocks on the
KiCad-catalogue model (buck converters, digital chips): each
ships a schematic symbol AND a footprint cell LINKED, and
"instantiate" places a block with that linkage intact.

INVARIANT (RULING-01): prebuilt IP is PER-PDK — each PDK
strictly owns its blocks. Searches scope to one named PDK;
instantiating a foreign-PDK block fails unless the block opted
into scope ``shared`` with a recorded reason (digital blocks
MAY generalize case-by-case; the default stays per-PDK).
"""

from ...interfaces.errors import ContractError

#: Component name registered IP blocks carry on their entity.
IP_COMPONENT = "IpBlock"

#: Component name placed IP instances carry beside Instance.
IP_LINK_COMPONENT = "IpLink"

#: Registry scopes: per-PDK by default, shared by recorded exception.
SCOPES = ("pdk", "shared")


def _need_text(value, what, code):
    """Accept non-empty text or raise the named code."""
    if not isinstance(value, str) or not value:
        raise ContractError(code, f"{what} must be non-empty text.")
    return value


def validate_ip_block(block):
    """Validate an IpBlock component mapping at edit time.

    Args:
        block: Block mapping with pdk, name, version, symbol,
            cell, pin_map, scope, reason, and promoted keys.

    Returns:
        Normalized IpBlock copy.

    Raises:
        ContractError: invalid_ip for any shape violation,
            invalid_scope for a shared scope without a reason.
    """
    if not isinstance(block, dict):
        raise ContractError(
            "invalid_ip", f"IpBlock must be a mapping, got {block!r}."
        )
    for key in block:
        if key not in ("pdk", "name", "version", "symbol", "cell",
                       "pin_map", "scope", "reason", "promoted"):
            raise ContractError(
                "invalid_ip", f"Unknown IpBlock key: {key}."
            )
    pdk = _need_text(block.get("pdk"), "IP pdk", "invalid_pdk")
    name = _need_text(block.get("name"), "IP name", "invalid_ip")
    version = _need_text(block.get("version"), "IP version", "invalid_ip")
    symbol = _need_text(block.get("symbol"), "IP symbol", "invalid_ip")
    cell = _need_text(block.get("cell"), "IP cell", "invalid_ip")
    pin_map = block.get("pin_map", [])
    if not isinstance(pin_map, list) or not all(
        isinstance(entry, dict)
        and set(entry) == {"symPin", "cellPin"}
        and entry.get("symPin") and entry.get("cellPin")
        for entry in pin_map
    ):
        raise ContractError(
            "invalid_ip",
            "IP pin_map must list {symPin, cellPin} entries.",
        )
    scope = block.get("scope", "pdk")
    if scope not in SCOPES:
        raise ContractError(
            "invalid_scope", f"IP scope must be one of {SCOPES}."
        )
    reason = block.get("reason", "")
    if not isinstance(reason, str):
        raise ContractError(
            "invalid_scope", "IP shared reason must be text."
        )
    if scope == "shared" and not reason:
        raise ContractError(
            "invalid_scope",
            "Shared-scope IP needs a recorded reason naming why "
            "this digital block generalizes across PDKs.",
        )
    promoted = block.get("promoted", False)
    if not isinstance(promoted, bool):
        raise ContractError(
            "invalid_ip", "IP promoted must be a bool."
        )
    return {
        "pdk": pdk, "name": name, "version": version,
        "symbol": symbol, "cell": cell,
        "pin_map": [dict(entry) for entry in pin_map],
        "scope": scope, "reason": reason, "promoted": promoted,
    }


def _all_blocks(store):
    """List every registered block mapping, (pdk, name, version)-sorted."""
    found = []
    for entity in store.entities_with(IP_COMPONENT):
        try:
            raw = store.get_component(entity, IP_COMPONENT)
        except LookupError:
            continue
        try:
            value = validate_ip_block(raw)
        except ContractError:
            continue
        value["id"] = entity
        found.append(value)
    found.sort(key=lambda item: (item["pdk"], item["name"],
                                 item["version"]))
    return found


def ip_register(store, actor, pdk, name, version, symbol, cell,
                pin_map=None, scope="pdk", reason=""):
    """Register one prebuilt IP block revision under its PDK.

    Args:
        store: Entity store serving the ENGINE-ECS seam.
        actor: Attribution recorded on the revision and events.
        pdk: Owning PDK id (the per-PDK invariant key).
        name: Block name within the PDK registry.
        version: Revision label ("" forbidden; latest = the
            greatest label in sort order).
        symbol: Linked schematic symbol reference.
        cell: Linked footprint cell reference.
        pin_map: Explicit [{symPin, cellPin}] entries.
        scope: "pdk" (default) or "shared" with a reason.
        reason: Recorded justification for shared scope.

    Returns:
        Receipt with op, actor, revision, ip id, and scope.

    Raises:
        ContractError: invalid_pdk for a missing PDK, ip_exists
            for a duplicate (pdk, name, version), invalid_ip
            for a malformed block, invalid_scope for shared
            scope without a reason.
    """
    value = validate_ip_block({
        "pdk": pdk, "name": name, "version": version,
        "symbol": symbol, "cell": cell,
        "pin_map": pin_map or [], "scope": scope,
        "reason": reason, "promoted": False,
    })
    for other in _all_blocks(store):
        if (
            other["pdk"] == value["pdk"]
            and other["name"] == value["name"]
            and other["version"] == value["version"]
        ):
            raise ContractError(
                "ip_exists",
                f"IP already registered: {pdk}/{name}@{version}.",
            )
    made = store.create_entity(actor, f"ip_register {pdk}/{name}")
    store.attach_component(
        actor, made["id"], IP_COMPONENT, value,
        f"ip_register {pdk}/{name}",
    )
    return {
        "op": "ip_register", "actor": actor,
        "revision": made["revision"], "ip": made["id"],
        "pdk": pdk, "name": name, "version": version,
        "scope": scope,
        "events": [
            {"event": "entity_created", "entity": made["id"]},
            {"event": "component_changed", "entity": made["id"],
             "component": IP_COMPONENT},
        ],
    }


def ip_search(store, pdk, name_filter=None):
    """Search one PDK's registry (the per-PDK invariant).

    Args:
        store: Entity store serving the ENGINE-ECS seam.
        pdk: Owning PDK id scoping the search (required —
            cross-PDK listing is refused by the invariant).
        name_filter: Optional substring the block name must hold.

    Returns:
        Block summaries (pdk, name, version, symbol, cell,
            scope, promoted), sorted by (name, version).

    Raises:
        ContractError: invalid_pdk for a missing PDK.
    """
    _need_text(pdk, "IP pdk", "invalid_pdk")
    hits = [
        {
            "id": item["id"], "pdk": item["pdk"], "name": item["name"],
            "version": item["version"], "symbol": item["symbol"],
            "cell": item["cell"], "scope": item["scope"],
            "promoted": item["promoted"],
        }
        for item in _all_blocks(store)
        if item["pdk"] == pdk
        and (name_filter is None or name_filter in item["name"])
    ]
    hits.sort(key=lambda item: (item["name"], item["version"]))
    return hits


def ip_get(store, pdk, name, version=None):
    """Read one registered block; the latest version by default.

    Args:
        store: Entity store serving the ENGINE-ECS seam.
        pdk: Owning PDK id scoping the lookup.
        name: Block name within the PDK registry.
        version: Revision label, or None for the greatest
            label in sort order.

    Returns:
        Full block mapping with id.

    Raises:
        ContractError: invalid_pdk for a missing PDK,
            unknown_ip when no such block (or version) exists
            under the PDK.
    """
    _need_text(pdk, "IP pdk", "invalid_pdk")
    candidates = [
        item for item in _all_blocks(store)
        if item["pdk"] == pdk and item["name"] == name
    ]
    if not candidates:
        candidates = [
            item for item in _all_blocks(store)
            if item["name"] == name and item["scope"] == "shared"
            and (version is None or item["version"] == version)
        ]
        candidates.sort(key=lambda item: (item["pdk"], item["version"]))
    if version is not None:
        for item in candidates:
            if item["version"] == version:
                return item
    elif candidates:
        return sorted(candidates,
                      key=lambda item: item["version"])[-1]
    raise ContractError(
        "unknown_ip",
        f"No such IP block: {pdk}/{name}"
        + (f"@{version}." if version is not None else "."),
    )


def ip_instantiate(store, actor, pdk, name, sheet, x, y,
                   version=None, rotation=0, mirror=False,
                   properties=None):
    """Place one IP block with its symbol/cell linkage intact.

    Args:
        store: Entity store serving the ENGINE-ECS seam.
        actor: Attribution recorded on the revision and events.
        pdk: Consuming PDK id (must own the block unless the
            block opted into shared scope).
        name: Block name within the PDK registry.
        sheet: Sheet entity id hosting the instance.
        x: X position in schematic units.
        y: Y position in schematic units.
        version: Revision label, or None for the latest.
        rotation: Rotation in degrees (0/90/180/270).
        mirror: Mirror flag.
        properties: Text-to-text instance properties.

    Returns:
        Receipt with op, actor, revision, instance id, and
            the resolved (pdk, name, version).

    Raises:
        ContractError: unknown_ip for a missing block,
            pdk_mismatch when a per-PDK block is asked from a
            foreign PDK, unknown_sheet for a missing sheet,
            invalid_instance for a malformed placement.
    """
    block = ip_get(store, pdk, name, version)
    if block["pdk"] != pdk and block["scope"] != "shared":
        raise ContractError(
            "pdk_mismatch",
            f"IP {block['pdk']}/{name} is per-PDK and cannot "
            f"instantiate under {pdk!r}.",
        )
    try:
        store.get_component(sheet, "Sheet")
    except LookupError:
        raise ContractError(
            "unknown_sheet", f"No such sheet entity: {sheet!r}."
        ) from None
    if rotation not in (0, 90, 180, 270):
        raise ContractError(
            "invalid_instance",
            "Instance rotation must be one of (0, 90, 180, 270).",
        )
    if not isinstance(mirror, bool):
        raise ContractError(
            "invalid_instance", "Instance mirror must be a bool."
        )
    clean_props = properties or {}
    if not isinstance(clean_props, dict) or not all(
        isinstance(key, str) and isinstance(val, str)
        for key, val in clean_props.items()
    ):
        raise ContractError(
            "invalid_instance",
            "Instance properties must map text to text.",
        )
    made = store.create_entity(actor, f"ip_instantiate {pdk}/{name}")
    store.attach_component(
        actor, made["id"], "Instance",
        {"sheet": sheet, "symbol": block["symbol"], "x": x, "y": y,
         "rotation": rotation, "mirror": mirror,
         "properties": dict(clean_props), "ref": ""},
        f"ip_instantiate {pdk}/{name}",
    )
    store.attach_component(
        actor, made["id"], IP_LINK_COMPONENT,
        {"pdk": block["pdk"], "name": name,
         "version": block["version"], "symbol": block["symbol"],
         "cell": block["cell"], "pin_map": block["pin_map"],
         "scope": block["scope"]},
        f"ip_instantiate {pdk}/{name}",
    )
    return {
        "op": "ip_instantiate", "actor": actor,
        "revision": made["revision"], "instance": made["id"],
        "pdk": block["pdk"], "name": name,
        "version": block["version"],
        "events": [
            {"event": "entity_created", "entity": made["id"]},
            {"event": "component_changed", "entity": made["id"],
             "component": "Instance"},
            {"event": "component_changed", "entity": made["id"],
             "component": IP_LINK_COMPONENT},
        ],
    }


def ip_promote(store, actor, pdk, name, version):
    """Promote one block version as the PDK registry's recommended one.

    Args:
        store: Entity store serving the ENGINE-ECS seam.
        actor: Attribution recorded on the revision and events.
        pdk: Owning PDK id scoping the registry.
        name: Block name within the PDK registry.
        version: Revision label to promote.

    Returns:
        Receipt with op, actor, revision, ip id, and the
            promoted flag.

    Raises:
        ContractError: unknown_ip when no such block version
            exists under the PDK.
    """
    _need_text(pdk, "IP pdk", "invalid_pdk")
    siblings = [
        item for item in _all_blocks(store)
        if item["pdk"] == pdk and item["name"] == name
    ]
    target = None
    for item in siblings:
        if item["version"] == version:
            target = item
    if target is None:
        raise ContractError(
            "unknown_ip",
            f"No such IP block: {pdk}/{name}@{version}.",
        )
    head = None
    for item in siblings:
        want = item["id"] == target["id"]
        if item["promoted"] != want:
            clean = validate_ip_block({
                "pdk": item["pdk"], "name": item["name"],
                "version": item["version"], "symbol": item["symbol"],
                "cell": item["cell"], "pin_map": item["pin_map"],
                "scope": item["scope"], "reason": item["reason"],
                "promoted": want,
            })
            changed = store.set_component(
                actor, item["id"], IP_COMPONENT, clean,
                f"ip_promote {pdk}/{name}@{version}",
            )
            head = changed["revision"]
    return {
        "op": "ip_promote", "actor": actor,
        "revision": head, "ip": target["id"], "pdk": pdk,
        "name": name, "version": version, "promoted": True,
        "events": [],
    }
