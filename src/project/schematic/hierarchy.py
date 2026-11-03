"""Hierarchy: parent-sheet to child-sheet bindings through block instances."""

from ...interfaces.errors import ContractError

#: Component name hierarchy bindings carry on their entity.
HIERARCHY_COMPONENT = "Hierarchy"


def validate_hierarchy(binding):
    """Validate a Hierarchy binding mapping at edit time.

    Args:
        binding: Binding mapping with parent_sheet, child_sheet,
            instance, and port_map keys.

    Returns:
        Normalized binding copy.

    Raises:
        ContractError: invalid_hierarchy for any shape violation.
    """
    if not isinstance(binding, dict):
        raise ContractError(
            "invalid_hierarchy",
            f"Hierarchy must be a mapping, got {binding!r}.",
        )
    for key in binding:
        if key not in ("parent_sheet", "child_sheet", "instance",
                       "port_map"):
            raise ContractError(
                "invalid_hierarchy", f"Unknown Hierarchy key: {key}."
            )
    parent = binding.get("parent_sheet")
    child = binding.get("child_sheet")
    instance = binding.get("instance")
    for label, value in (("parent_sheet", parent),
                         ("child_sheet", child),
                         ("instance", instance)):
        if not isinstance(value, str) or not value:
            raise ContractError(
                "invalid_hierarchy",
                f"Hierarchy {label} must be an entity id.",
            )
    if parent == child:
        raise ContractError(
            "invalid_hierarchy",
            "Hierarchy parent and child must differ.",
        )
    port_map = binding.get("port_map", [])
    if not isinstance(port_map, list):
        raise ContractError(
            "invalid_hierarchy", "Hierarchy port_map must be a list."
        )
    clean_map = []
    seen = set()
    for entry in port_map:
        if (
            not isinstance(entry, dict)
            or set(entry) != {"parent", "child"}
            or not entry["parent"]
            or not isinstance(entry["parent"], str)
            or not entry["child"]
            or not isinstance(entry["child"], str)
        ):
            raise ContractError(
                "invalid_hierarchy",
                "port_map entries need parent + child text.",
            )
        if entry["child"] in seen:
            raise ContractError(
                "invalid_hierarchy",
                f"Child port {entry['child']!r} maps more than once.",
            )
        seen.add(entry["child"])
        clean_map.append(
            {"parent": entry["parent"], "child": entry["child"]}
        )
    return {
        "parent_sheet": parent, "child_sheet": child,
        "instance": instance, "port_map": clean_map,
    }


def _read_binding(store, binding_id):
    """Return the normalized binding for one entity id."""
    try:
        raw = store.get_component(binding_id, HIERARCHY_COMPONENT)
    except LookupError:
        raise ContractError(
            "unknown_binding",
            f"No such hierarchy binding: {binding_id!r}.",
        ) from None
    value = validate_hierarchy(raw)
    value["id"] = binding_id
    return value


def _check_sheet(store, sheet_id):
    """Fail loudly when a sheet entity is missing."""
    try:
        store.get_component(sheet_id, "Sheet")
    except LookupError:
        raise ContractError(
            "unknown_sheet", f"No such sheet entity: {sheet_id!r}."
        ) from None


def _check_instance(store, instance_id):
    """Fail loudly when an instance entity is missing."""
    try:
        store.get_component(instance_id, "Instance")
    except LookupError:
        raise ContractError(
            "unknown_instance",
            f"No such instance entity: {instance_id!r}.",
        ) from None


def _all_bindings(store):
    """List every binding mapping, id-sorted."""
    found = []
    for entity in store.entities_with(HIERARCHY_COMPONENT):
        try:
            found.append(_read_binding(store, entity))
        except ContractError:
            continue
    found.sort(key=lambda item: item["id"])
    return found


def bind_block(store, actor, parent_sheet, child_sheet, instance):
    """Bind a child sheet under a parent through a block instance.

    Args:
        store: Entity store serving the ENGINE-ECS seam.
        actor: Attribution recorded on the revision and events.
        parent_sheet: Parent sheet entity id.
        child_sheet: Child sheet entity id.
        instance: Block instance entity id on the parent sheet.

    Returns:
        Receipt with op, actor, revision, binding id, and events.

    Raises:
        ContractError: unknown_sheet for a missing sheet,
            unknown_instance for a missing instance,
            binding_exists for a duplicate binding,
            invalid_hierarchy for a self-binding.
    """
    value = validate_hierarchy({
        "parent_sheet": parent_sheet, "child_sheet": child_sheet,
        "instance": instance, "port_map": [],
    })
    _check_sheet(store, parent_sheet)
    _check_sheet(store, child_sheet)
    _check_instance(store, instance)
    for other in _all_bindings(store):
        if (
            other["parent_sheet"] == parent_sheet
            and other["child_sheet"] == child_sheet
            and other["instance"] == instance
        ):
            raise ContractError(
                "binding_exists",
                f"Sheet {child_sheet!r} is already bound under "
                f"{parent_sheet!r} through {instance!r}.",
            )
    made = store.create_entity(actor, f"bind_block {child_sheet}")
    store.attach_component(
        actor, made["id"], HIERARCHY_COMPONENT, value,
        f"bind_block {child_sheet}",
    )
    return {
        "op": "bind_block", "actor": actor,
        "revision": made["revision"], "binding": made["id"],
        "events": [
            {"event": "entity_created", "entity": made["id"]},
            {"event": "component_changed", "entity": made["id"],
             "component": HIERARCHY_COMPONENT},
        ],
    }


def set_port_map(store, actor, binding_id, port_map):
    """Replace one binding's parent-to-child port map.

    Args:
        store: Entity store serving the ENGINE-ECS seam.
        actor: Attribution recorded on the revision and events.
        binding_id: Binding entity id to update.
        port_map: New [{parent, child}] port mappings.

    Returns:
        Receipt with op, actor, revision, binding id, and
            the new port map.

    Raises:
        ContractError: unknown_binding for a missing binding,
            invalid_hierarchy for a malformed map.
    """
    value = _read_binding(store, binding_id)
    clean = validate_hierarchy({
        "parent_sheet": value["parent_sheet"],
        "child_sheet": value["child_sheet"],
        "instance": value["instance"], "port_map": port_map,
    })
    changed = store.set_component(
        actor, binding_id, HIERARCHY_COMPONENT, clean,
        f"set_port_map {binding_id}",
    )
    return {
        "op": "set_port_map", "actor": actor,
        "revision": changed["revision"], "binding": binding_id,
        "port_map": clean["port_map"], "events": [],
    }


def unbind_block(store, actor, binding_id):
    """Delete one hierarchy binding.

    Args:
        store: Entity store serving the ENGINE-ECS seam.
        actor: Attribution recorded on the revision and events.
        binding_id: Binding entity id to delete.

    Returns:
        Receipt with op, actor, revision, and binding id.

    Raises:
        ContractError: unknown_binding for a missing binding.
    """
    _read_binding(store, binding_id)
    done = store.delete_entity(
        actor, binding_id, f"unbind_block {binding_id}"
    )
    return {
        "op": "unbind_block", "actor": actor,
        "revision": done["revision"], "binding": binding_id,
        "events": [{"event": "entity_deleted", "entity": binding_id}],
    }


def children_of(store, parent_sheet):
    """List child sheet ids bound under one parent, id-sorted.

    Args:
        store: Entity store serving the ENGINE-ECS seam.
        parent_sheet: Parent sheet entity id.

    Returns:
        Child sheet entity ids, id-sorted.
    """
    return sorted(
        item["child_sheet"] for item in _all_bindings(store)
        if item["parent_sheet"] == parent_sheet
    )


def parent_of(store, child_sheet):
    """List parent sheet ids binding one child, id-sorted.

    Args:
        store: Entity store serving the ENGINE-ECS seam.
        child_sheet: Child sheet entity id.

    Returns:
        Parent sheet entity ids, id-sorted.
    """
    return sorted(
        item["parent_sheet"] for item in _all_bindings(store)
        if item["child_sheet"] == child_sheet
    )


def hierarchy_tree(store, root_sheet):
    """Render the hierarchy subtree rooted at one sheet.

    Args:
        store: Entity store serving the ENGINE-ECS seam.
        root_sheet: Root sheet entity id.

    Returns:
        Nested mapping with sheet plus children subtrees.
    """
    return {
        "sheet": root_sheet,
        "children": [
            hierarchy_tree(store, child)
            for child in children_of(store, root_sheet)
        ],
    }


def sheet_path(store, sheet):
    """Return the root-to-sheet chain through first parents.

    Args:
        store: Entity store serving the ENGINE-ECS seam.
        sheet: Sheet entity id to locate.

    Returns:
        Sheet ids from the root down to the sheet itself.
    """
    chain = [sheet]
    seen = {sheet}
    while True:
        parents = parent_of(store, chain[0])
        if not parents or parents[0] in seen:
            break
        chain.insert(0, parents[0])
        seen.add(parents[0])
    return chain
