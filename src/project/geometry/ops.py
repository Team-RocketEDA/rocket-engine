"""Typed layout geometry records over engine entities.

Rectangles, polygons, paths, and labels live as kind=shape
entities with a geom component (shape_type, layer lid, units,
data) plus provenance (actor, profile pin). Object identity is
the stable entity id; cell hierarchy, ports, and links stay on
sibling components the ops never touch. Transforms (move,
rotate, mirror, array, copy) mint or reuse identity explicitly:
move-style ops keep the id, copy/array mint new ones.
"""

import copy
import math

SHAPE_TYPES = ("rect", "polygon", "path", "label")
GEOM_COMPONENT = "geom"
PROVENANCE_COMPONENT = "shape_provenance"
SHAPE_KIND = "shape"


def validate_shape(shape_type, data):
    """Check one shape payload against its type schema.

    Args:
        shape_type: One of rect, polygon, path, or label.
        data: Shape payload mapping to check.

    Returns:
        Deep copy of the validated payload.

    Raises:
        ValueError: For an unknown type or a malformed
            payload naming the offending field.
    """
    if shape_type not in SHAPE_TYPES:
        raise ValueError(f"Unknown shape type: {shape_type!r}.")
    body = copy.deepcopy(dict(data))
    if shape_type == "rect":
        for field in ("x", "y", "w", "h"):
            if field not in body:
                raise ValueError(
                    f"Rect is missing field: {field}.")
        if body["w"] <= 0 or body["h"] <= 0:
            raise ValueError("Rect needs positive w and h.")
    elif shape_type == "polygon":
        points = body.get("points", [])
        if len(points) < 3:
            raise ValueError("Polygon needs 3+ points.")
    elif shape_type == "path":
        if len(body.get("points", [])) < 2:
            raise ValueError("Path needs 2+ points.")
        if body.get("width", 0) <= 0:
            raise ValueError("Path needs a positive width.")
    else:
        for field in ("x", "y", "text"):
            if field not in body:
                raise ValueError(
                    f"Label is missing field: {field}.")
    return body


def _live_revision(service, entity):
    """Read the live entity revision an unnamed write builds on.

    Args:
        service: ProjectService handle to read through.
        entity: Shape entity id.

    Returns:
        Live entity revision for the gate.
    """
    names = service.components_of(entity)["components"]
    if not names:
        return 1
    return service.get_component(entity, names[0]).get(
        "entity_revision", 1)


def _geom(shape_type, layer, units, data, profile=None):
    """Build one geom component payload.

    Args:
        shape_type: Validated shape type name.
        layer: Stable layer lid the shape is drawn on.
        units: Coordinate units label.
        data: Validated shape payload.
        profile: Technology profile pin, if resolved.

    Returns:
        Geom component mapping.
    """
    return {
        "data": validate_shape(shape_type, data),
        "layer": layer,
        "profile": copy.deepcopy(profile),
        "shape_type": shape_type,
        "units": units,
    }


def create_shape(service, request_id, command_text, shape_type,
                 layer, data, units="nm", profile=None,
                 anchor=None, expected_revision=None):
    """Create one shape entity with provenance.

    Args:
        service: ProjectService handle to write through.
        request_id: Client envelope id.
        command_text: Command text for identity comparison.
        shape_type: One of rect, polygon, path, label.
        layer: Stable layer lid (mapped or not — both draw).
        data: Shape payload for the type.
        units: Coordinate units label.
        profile: Technology profile pin for provenance.
        anchor: Optional cell-port anchor {x, y, port}.
        expected_revision: Accepted and ignored (minted ids
            never conflict).

    Returns:
        Creation mapping with entity, shape_type, layer,
            and revision transition.

    Raises:
        ValueError: For an unknown shape type or payload.
        Exception: Whatever the service raises.
    """
    components = {
        GEOM_COMPONENT: _geom(
            shape_type, layer, units, data, profile),
        PROVENANCE_COMPONENT: {
            "anchor": copy.deepcopy(anchor),
            "profile": copy.deepcopy(profile),
        },
    }
    created = service.create_entity(
        request_id, command_text, kind=SHAPE_KIND,
        components=components,
        expected_revision=expected_revision,
    )
    return {
        "current_revision": created["current_revision"],
        "entity": created["entity"],
        "entity_revision": created["entity_revision"],
        "layer": layer,
        "shape_type": shape_type,
    }


def read_shape(service, entity):
    """Read one shape with its provenance.

    Args:
        service: ProjectService handle to read through.
        entity: Shape entity id.

    Returns:
        Mapping with entity, shape_type, layer, units,
            data, anchor, profile, and entity_revision.

    Raises:
        Exception: Whatever the service raises for unknown
            entities or components.
    """
    geom = service.get_component(entity, GEOM_COMPONENT)
    try:
        provenance = service.get_component(
            entity, PROVENANCE_COMPONENT)["data"]
    except Exception:
        provenance = {}
    body = geom["data"]
    return {
        "anchor": copy.deepcopy(provenance.get("anchor")),
        "current_revision": geom["current_revision"],
        "data": copy.deepcopy(body["data"]),
        "entity": entity,
        "entity_revision": geom["entity_revision"],
        "layer": body["layer"],
        "profile": copy.deepcopy(body.get("profile")),
        "shape_type": body["shape_type"],
        "units": body["units"],
    }


def update_shape(service, request_id, command_text, entity,
                 data=None, layer=None,
                 expected_entity_revision=None,
                 expected_revision=None):
    """Update one shape payload gated on its entity revision.

    Args:
        service: ProjectService handle to write through.
        request_id: Client envelope id.
        command_text: Command text for identity comparison.
        entity: Shape entity id.
        data: Replacement shape payload, if changing.
        layer: New stable layer lid, if moving layers.
        expected_entity_revision: Entity revision the writer
            read; stale values fail with revision_conflict.
        expected_revision: Global head gate (skipped when an
            entity revision is named).

    Returns:
        Mutation mapping with the bumped entity_revision.

    Raises:
        Exception: revision_conflict for a stale entity
            revision, or whatever the service raises.
    """
    current = read_shape(service, entity)
    payload = _geom(
        current["shape_type"],
        layer if layer is not None else current["layer"],
        current["units"],
        data if data is not None else current["data"],
        current["profile"],
    )
    gate = expected_entity_revision
    if gate is None and expected_revision is None:
        gate = _live_revision(service, entity)
    return service.set_component(
        entity, GEOM_COMPONENT, payload, request_id,
        command_text, expected_revision=expected_revision,
        expected_entity_revision=gate,
    )


def delete_shape(service, request_id, command_text, entity,
                 expected_entity_revision=None,
                 expected_revision=None):
    """Delete one shape entity.

    Args:
        service: ProjectService handle to write through.
        request_id: Client envelope id.
        command_text: Command text for identity comparison.
        entity: Shape entity id.
        expected_entity_revision: Entity revision gate.
        expected_revision: Global head gate.

    Returns:
        Service deletion mapping.

    Raises:
        Exception: Whatever the service raises.
    """
    return service.delete_entity(
        entity, request_id, command_text,
        expected_revision=expected_revision,
        expected_entity_revision=expected_entity_revision,
    )


def move_shape(service, request_id, command_text, entity, dx,
               dy, expected_entity_revision=None):
    """Move one shape by a delta, keeping its identity.

    Args:
        service: ProjectService handle to write through.
        request_id: Client envelope id.
        command_text: Command text for identity comparison.
        entity: Shape entity id.
        dx: Delta in x storage units.
        dy: Delta in y storage units.
        expected_entity_revision: Entity revision gate.

    Returns:
        Mutation mapping with the bumped entity_revision.

    Raises:
        Exception: Whatever update_shape raises.
    """
    current = read_shape(service, entity)
    data = copy.deepcopy(current["data"])
    if current["shape_type"] in ("rect", "label"):
        data["x"] += dx
        data["y"] += dy
    else:
        data["points"] = [[px + dx, py + dy] for px, py in
                          data["points"]]
    out = update_shape(
        service, request_id, command_text, entity, data=data,
        expected_entity_revision=expected_entity_revision,
    )
    return {"entity": entity, "entity_revision": out.get(
        "entity_revision"), "response": out}


def _rotate_point(px, py, degrees):
    """Rotate one point about the origin.

    Args:
        px: X coordinate.
        py: Y coordinate.
        degrees: Rotation angle in degrees.

    Returns:
        Rotated [x, y] pair.
    """
    radians = math.radians(degrees)
    cosine, sine = math.cos(radians), math.sin(radians)
    return [px * cosine - py * sine, px * sine + py * cosine]


def transform_shape(service, request_id, command_text, entity,
                    rotate_deg=0, mirror=None,
                    expected_entity_revision=None):
    """Rotate or mirror one shape in place.

    Args:
        service: ProjectService handle to write through.
        request_id: Client envelope id.
        command_text: Command text for identity comparison.
        entity: Shape entity id.
        rotate_deg: Rotation angle in degrees (0 skips).
        mirror: Mirror axis (x, y, or None).
        expected_entity_revision: Entity revision gate.

    Returns:
        Mapping with entity and bumped entity_revision.

    Raises:
        ValueError: For an unknown mirror axis.
        Exception: Whatever update_shape raises.
    """
    if mirror not in (None, "x", "y"):
        raise ValueError(f"Unknown mirror axis: {mirror!r}.")
    current = read_shape(service, entity)
    data = copy.deepcopy(current["data"])

    def _point(px, py):
        if mirror == "x":
            px = -px
        elif mirror == "y":
            py = -py
        if rotate_deg:
            px, py = _rotate_point(px, py, rotate_deg)
        return [px, py]

    if current["shape_type"] in ("rect", "label"):
        data["x"], data["y"] = _point(data["x"], data["y"])
    else:
        data["points"] = [_point(px, py) for px, py in
                          data["points"]]
    out = update_shape(
        service, request_id, command_text, entity, data=data,
        expected_entity_revision=expected_entity_revision,
    )
    return {"entity": entity, "entity_revision": out.get(
        "entity_revision"), "response": out}


def copy_shape(service, request_id, command_text, entity,
               dx=0, dy=0):
    """Copy one shape to a new entity with an optional offset.

    Args:
        service: ProjectService handle to write through.
        request_id: Client envelope id.
        command_text: Command text for identity comparison.
        entity: Source shape entity id.
        dx: Offset in x storage units.
        dy: Offset in y storage units.

    Returns:
        Creation mapping for the new shape entity.

    Raises:
        Exception: Whatever the service raises.
    """
    current = read_shape(service, entity)
    data = copy.deepcopy(current["data"])
    if current["shape_type"] in ("rect", "label"):
        data["x"] += dx
        data["y"] += dy
    else:
        data["points"] = [[px + dx, py + dy] for px, py in
                          data["points"]]
    return create_shape(
        service, request_id, command_text,
        current["shape_type"], current["layer"], data,
        units=current["units"], profile=current["profile"],
        anchor=current["anchor"],
    )


def array_shape(service, request_id, command_text, entity,
                count_x, count_y, pitch_x, pitch_y):
    """Array one shape into a grid of new entities.

    Args:
        service: ProjectService handle to write through.
        request_id: Client envelope id; members derive
            sub-envelopes from it.
        command_text: Command text for identity comparison.
        entity: Source shape entity id.
        count_x: Copies along x (at least 1).
        count_y: Copies along y (at least 1).
        pitch_x: Pitch between columns in storage units.
        pitch_y: Pitch between rows in storage units.

    Returns:
        List of creation mappings, one per member.

    Raises:
        ValueError: For counts below 1.
        Exception: Whatever the service raises.
    """
    if count_x < 1 or count_y < 1:
        raise ValueError("Array counts must be at least 1.")
    members = []
    for row in range(count_y):
        for col in range(count_x):
            members.append(copy_shape(
                service, f"{request_id}:array:{col}:{row}",
                f"{command_text} array {col},{row}", entity,
                dx=col * pitch_x, dy=row * pitch_y,
            ))
    return members


def set_anchor(service, request_id, command_text, entity,
               anchor, expected_entity_revision=None):
    """Store one cell-port anchor on a shape.

    Args:
        service: ProjectService handle to write through.
        request_id: Client envelope id.
        command_text: Command text for identity comparison.
        entity: Shape entity id.
        anchor: Anchor mapping {x, y, port}.
        expected_entity_revision: Entity revision gate.

    Returns:
        Mutation mapping with the bumped entity_revision.

    Raises:
        Exception: Whatever the service raises.
    """
    current = read_shape(service, entity)
    provenance = {
        "anchor": copy.deepcopy(anchor),
        "profile": current["profile"],
    }
    gate = expected_entity_revision
    if gate is None:
        gate = _live_revision(service, entity)
    return service.set_component(
        entity, PROVENANCE_COMPONENT, provenance, request_id,
        command_text, expected_revision=None,
        expected_entity_revision=gate,
    )
