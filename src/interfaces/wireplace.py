"""Wire/junction entities + connect ops (WIRE-PLACE).

Wires are first-class entities — placeable, movable, splittable,
deletable, rewindable — with endpoints terminating on stable
pin/port/junction/net entity IDs. Junctions are explicit dots: two
wires join only at a shared endpoint, a T-tap, or a junction they
both reference; crossing interiors never connect. Nets derive from
CONNECT-GRAPH extraction, then materialize as Net entities keyed by
the shared `net_name()` authority, so emitters, ERC, and agents all
read the same net identity.

Every op runs through the ENGINE-ECS entity store seam as exactly
one attributed transaction (one revision, one description, actor on
every event); a no-op returns a receipt with a None revision and
writes nothing. Dangling endpoints (null refs) are legal transiently
and ERC-flagged, never silently dropped; refs to deleted entities
are ERC errors, and deleting a referenced junction is refused
loudly. This module owns no storage: `store` is any object serving
the seam documented in `docs/work/WIRE-PLACE/report.md` (tests carry
an in-memory fake; the ENGINE-ECS lane owns the durable one).

Component schemas (JSON-safe, edit-time validated):

- Wire: {segments, layer, endpoints}; segments is a non-empty list
  of integer polylines ([x, y] points, no zero-length runs);
  endpoints holds exactly [a, b] with xy pinned to the first and
  last polyline points and ref a pin/port/junction/net entity ID
  or null when dangling.
- Junction: {xy, layer}; the explicit dot.
- Net: {name, extraction {cell, net_ids}, members {pins, labels,
  wires, junctions}, has_wires}; materialized, keyed by name.

Extraction groups that resolve to the same canonical name merge
into one Net entity: a name is global, so a net-ref tap and a
repeated label both join every group carrying the name.
"""

from .errors import ContractError

__all__ = [
    "DEFAULT_WIRE_POLICY",
    "ENDPOINTS",
    "JUNCTION_COMPONENT",
    "NET_COMPONENT",
    "RULE_DANGLING_ENDPOINT",
    "RULE_ORPHAN_JUNCTION",
    "RULE_STALE_GEOMETRY",
    "RULE_UNKNOWN_REF",
    "WIRE_COMPONENT",
    "collect_wire_erc",
    "connect_endpoint",
    "delete_junction",
    "delete_wire",
    "materialize_nets",
    "move_wire",
    "place_junction",
    "place_wire",
    "split_wire",
    "validate_junction",
    "validate_label",
    "validate_net",
    "validate_pin",
    "validate_wire",
    "world_schematic",
]

#: Component names as stored on entities.
WIRE_COMPONENT = "Wire"
JUNCTION_COMPONENT = "Junction"
NET_COMPONENT = "Net"

#: ERC rule codes for wire/junction findings.
RULE_DANGLING_ENDPOINT = "wire.dangling_endpoint"
RULE_UNKNOWN_REF = "wire.unknown_ref"
RULE_STALE_GEOMETRY = "wire.stale_geometry"
RULE_ORPHAN_JUNCTION = "wire.orphan_junction"

#: Default finding severities; unknown-ref is the only error.
DEFAULT_WIRE_POLICY = {
    RULE_DANGLING_ENDPOINT: "warning",
    RULE_UNKNOWN_REF: "error",
    RULE_STALE_GEOMETRY: "warning",
    RULE_ORPHAN_JUNCTION: "warning",
}

#: Endpoint selector order: a is the first polyline point.
ENDPOINTS = ("a", "b")

_PORT_DIRECTIONS = ("input", "output", "inout")


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _need_point(value, what, code):
    if (
        not isinstance(value, (list, tuple))
        or len(value) != 2
        or not all(_is_int(c) for c in value)
    ):
        raise ContractError(code, f"{what} must be [x, y] ints, got {value!r}.")
    return [value[0], value[1]]


def _need_nonempty_str(value, what, code):
    if not isinstance(value, str) or not value:
        raise ContractError(code, f"{what} must be a non-empty string.")
    return value


def _need_actor(actor):
    return _need_nonempty_str(actor, "actor", "invalid_actor")


def _point_on_segment(point, seg_a, seg_b):
    (px, py), (ax, ay), (bx, by) = point, seg_a, seg_b
    if (bx - ax) * (py - ay) != (by - ay) * (px - ax):
        return False
    return min(ax, bx) <= px <= max(ax, bx) and min(ay, by) <= py <= max(ay, by)


def _point_on_wire(point, wire):
    for polyline in wire["segments"]:
        for seg_a, seg_b in zip(polyline, polyline[1:]):
            if _point_on_segment(point, seg_a, seg_b):
                return True
    return False


def _sorted_str_list(value, what, code):
    if not isinstance(value, list) or not all(
        isinstance(v, str) and v for v in value
    ):
        raise ContractError(code, f"{what} must be a non-empty-str list.")
    if sorted(value) != value or len(set(value)) != len(value):
        raise ContractError(code, f"{what} must be sorted and distinct.")
    return list(value)


def validate_wire(wire):
    """Validate a Wire component mapping at edit time.

    Checks shape only — segment geometry, layer text, endpoint
    count, endpoint xy pinned to the polyline ends — and returns a
    normalized copy. Ref existence is never checked here; the ops
    resolve refs through the store and fail unknown_ref loudly.

    Args:
        wire: Wire mapping with segments, layer, endpoints keys.

    Returns:
        Normalized Wire copy (lists, storage untouched).

    Raises:
        ContractError: invalid_wire for any shape violation.
    """
    if not isinstance(wire, dict):
        raise ContractError(
            "invalid_wire", f"Wire must be a mapping, got {wire!r}."
        )
    for key in wire:
        if key not in ("segments", "layer", "endpoints"):
            raise ContractError("invalid_wire", f"Unknown Wire key: {key}.")
    segments = wire.get("segments")
    if not isinstance(segments, list) or not segments:
        raise ContractError("invalid_wire", "segments must be a non-empty list.")
    clean_segments = []
    for index, polyline in enumerate(segments):
        if not isinstance(polyline, (list, tuple)) or len(polyline) < 2:
            raise ContractError(
                "invalid_wire",
                f"segments[{index}] must hold at least 2 points.",
            )
        points = [
            _need_point(p, f"segments[{index}]", "invalid_wire")
            for p in polyline
        ]
        for first, second in zip(points, points[1:]):
            if first == second:
                raise ContractError(
                    "invalid_wire",
                    f"segments[{index}] holds a zero-length run.",
                )
        clean_segments.append(points)
    layer = _need_nonempty_str(wire.get("layer"), "layer", "invalid_wire")
    endpoints = wire.get("endpoints")
    if not isinstance(endpoints, list) or len(endpoints) != 2:
        raise ContractError("invalid_wire", "endpoints must hold exactly [a, b].")
    clean_endpoints = []
    for index, endpoint in enumerate(endpoints):
        if not isinstance(endpoint, dict):
            raise ContractError("invalid_wire", "endpoints must be mappings.")
        for key in endpoint:
            if key not in ("ref", "xy"):
                raise ContractError(
                    "invalid_wire", f"Unknown endpoint key: {key}."
                )
        ref = endpoint.get("ref")
        if ref is not None and (not isinstance(ref, str) or not ref):
            raise ContractError(
                "invalid_wire", "endpoint ref must be an ID or null."
            )
        xy = _need_point(
            endpoint.get("xy"), f"endpoints[{ENDPOINTS[index]}].xy",
            "invalid_wire",
        )
        clean_endpoints.append({"ref": ref, "xy": xy})
    if clean_endpoints[0]["xy"] != clean_segments[0][0]:
        raise ContractError(
            "invalid_wire", "endpoint a.xy must equal the first polyline point."
        )
    if clean_endpoints[1]["xy"] != clean_segments[-1][-1]:
        raise ContractError(
            "invalid_wire", "endpoint b.xy must equal the last polyline point."
        )
    return {"segments": clean_segments, "layer": layer,
            "endpoints": clean_endpoints}


def validate_junction(junction):
    """Validate a Junction component mapping at edit time.

    Args:
        junction: Junction mapping with xy and layer keys.

    Returns:
        Normalized Junction copy.

    Raises:
        ContractError: invalid_junction for any shape violation.
    """
    if not isinstance(junction, dict):
        raise ContractError(
            "invalid_junction", f"Junction must be a mapping, got {junction!r}."
        )
    for key in junction:
        if key not in ("xy", "layer"):
            raise ContractError(
                "invalid_junction", f"Unknown Junction key: {key}."
            )
    return {
        "xy": _need_point(junction.get("xy"), "xy", "invalid_junction"),
        "layer": _need_nonempty_str(
            junction.get("layer"), "layer", "invalid_junction"
        ),
    }


def validate_net(net):
    """Validate a Net component mapping at edit time.

    Args:
        net: Net mapping with name, extraction, members, has_wires.

    Returns:
        Normalized Net copy.

    Raises:
        ContractError: invalid_net for any shape violation.
    """
    if not isinstance(net, dict):
        raise ContractError(
            "invalid_net", f"Net must be a mapping, got {net!r}."
        )
    for key in net:
        if key not in ("name", "extraction", "members", "has_wires"):
            raise ContractError("invalid_net", f"Unknown Net key: {key}.")
    name = _need_nonempty_str(net.get("name"), "name", "invalid_net")
    extraction = net.get("extraction")
    if not isinstance(extraction, dict):
        raise ContractError("invalid_net", "extraction must be a mapping.")
    cell = _need_nonempty_str(
        extraction.get("cell"), "extraction.cell", "invalid_net"
    )
    net_ids = extraction.get("net_ids")
    if (
        not isinstance(net_ids, list)
        or not net_ids
        or not all(_is_int(n) for n in net_ids)
        or sorted(net_ids) != list(net_ids)
    ):
        raise ContractError(
            "invalid_net", "extraction.net_ids must be a sorted int list."
        )
    members = net.get("members")
    if not isinstance(members, dict):
        raise ContractError("invalid_net", "members must be a mapping.")
    for key in members:
        if key not in ("pins", "labels", "wires", "junctions"):
            raise ContractError(
                "invalid_net", f"Unknown members key: {key}."
            )
    pins = members.get("pins")
    if not isinstance(pins, list):
        raise ContractError("invalid_net", "members.pins must be a list.")
    clean_pins = []
    for entry in pins:
        if (
            not isinstance(entry, dict)
            or set(entry) != {"instance", "pin"}
            or not entry["instance"]
            or not isinstance(entry["instance"], str)
            or not entry["pin"]
            or not isinstance(entry["pin"], str)
        ):
            raise ContractError(
                "invalid_net", "members.pins entries need instance + pin."
            )
        clean_pins.append(
            {"instance": entry["instance"], "pin": entry["pin"]}
        )
    keys = [(p["instance"], p["pin"]) for p in clean_pins]
    if sorted(keys) != keys or len(set(keys)) != len(keys):
        raise ContractError(
            "invalid_net", "members.pins must be sorted and distinct."
        )
    clean_members = {
        "pins": clean_pins,
        "labels": _sorted_str_list(
            members.get("labels"), "members.labels", "invalid_net"
        ),
        "wires": _sorted_str_list(
            members.get("wires"), "members.wires", "invalid_net"
        ),
        "junctions": _sorted_str_list(
            members.get("junctions"), "members.junctions", "invalid_net"
        ),
    }
    has_wires = net.get("has_wires")
    if not isinstance(has_wires, bool):
        raise ContractError("invalid_net", "has_wires must be a bool.")
    return {
        "name": name,
        "extraction": {"cell": cell, "net_ids": list(net_ids)},
        "members": clean_members,
        "has_wires": has_wires,
    }


def validate_pin(pin):
    """Validate one caller-supplied pin record at edit time.

    Pin entities belong to the Block lane; callers map each entity
    to its schematic (instance, pin, xy) triple through these
    records.

    Args:
        pin: Pin mapping with entity, instance, pin, xy keys.

    Returns:
        Normalized pin copy.

    Raises:
        ContractError: invalid_pin for any shape violation.
    """
    if not isinstance(pin, dict):
        raise ContractError(
            "invalid_pin", f"Pin must be a mapping, got {pin!r}."
        )
    for key in pin:
        if key not in ("entity", "instance", "pin", "xy"):
            raise ContractError("invalid_pin", f"Unknown pin key: {key}.")
    return {
        "entity": _need_nonempty_str(
            pin.get("entity"), "entity", "invalid_pin"
        ),
        "instance": _need_nonempty_str(
            pin.get("instance"), "instance", "invalid_pin"
        ),
        "pin": _need_nonempty_str(pin.get("pin"), "pin", "invalid_pin"),
        "xy": _need_point(pin.get("xy"), "xy", "invalid_pin"),
    }


def validate_label(label):
    """Validate one caller-supplied label record at edit time.

    Args:
        label: Label mapping with name and xy keys.

    Returns:
        Normalized label copy.

    Raises:
        ContractError: invalid_label for any shape violation.
    """
    if not isinstance(label, dict):
        raise ContractError(
            "invalid_label", f"Label must be a mapping, got {label!r}."
        )
    for key in label:
        if key not in ("name", "xy"):
            raise ContractError("invalid_label", f"Unknown label key: {key}.")
    return {
        "name": _need_nonempty_str(
            label.get("name"), "name", "invalid_label"
        ),
        "xy": _need_point(label.get("xy"), "xy", "invalid_label"),
    }


def _read_wire(store, wire_id):
    try:
        components = store.components_of(wire_id)
    except LookupError:
        raise ContractError(
            "unknown_wire", f"No such wire entity: {wire_id!r}."
        ) from None
    if WIRE_COMPONENT not in components:
        raise ContractError(
            "unknown_wire", f"Entity {wire_id!r} carries no Wire component."
        )
    return validate_wire(components[WIRE_COMPONENT])


def _check_ref(store, ref, wire_id=None):
    """Resolve one endpoint ref; fail loudly when unusable.

    Args:
        store: Entity store serving the seam.
        ref: Referenced entity ID.
        wire_id: Connecting wire, rejected as a self-ref.

    Returns:
        The referenced entity's components.

    Raises:
        ContractError: invalid_ref for a wire/self ref, unknown_ref
            for a missing entity.
    """
    if not isinstance(ref, str) or not ref:
        raise ContractError("invalid_ref", "endpoint ref must be an ID or null.")
    if ref == wire_id:
        raise ContractError(
            "invalid_ref", f"Wire {wire_id!r} cannot terminate on itself."
        )
    try:
        components = store.components_of(ref)
    except LookupError:
        raise ContractError(
            "unknown_ref", f"Endpoint ref names no entity: {ref!r}."
        ) from None
    if WIRE_COMPONENT in components:
        raise ContractError(
            "invalid_ref",
            f"Endpoint ref {ref!r} names a Wire entity; endpoints "
            "terminate on pin/port/junction/net IDs only.",
        )
    return components


def _receipt(op, actor, transact_receipt, **ids):
    receipt = {
        "op": op, "actor": actor,
        "revision": transact_receipt["revision"],
        "events": transact_receipt["events"],
    }
    receipt.update(ids)
    return receipt


def _describe(op, detail):
    return f"{op} {detail}"


def place_wire(store, actor, segments, layer, endpoints):
    """Place one wire as a durable attributed revision.

    Args:
        store: Entity store serving the seam.
        actor: Attribution recorded on the revision and events.
        segments: Non-empty list of integer polylines.
        layer: Layer name for every segment.
        endpoints: [a, b] endpoint mappings; each ref is a
            pin/port/junction/net entity ID or null when dangling.

    Returns:
        Receipt with op, actor, revision, wire ID, and events.

    Raises:
        ContractError: invalid_actor for empty attribution,
            invalid_wire for a malformed wire, unknown_ref for a
            ref naming no entity, invalid_ref for a wire ref.
    """
    _need_actor(actor)
    value = validate_wire(
        {"segments": segments, "layer": layer, "endpoints": endpoints}
    )
    for endpoint in value["endpoints"]:
        if endpoint["ref"] is not None:
            _check_ref(store, endpoint["ref"])
    result = store.transact(
        actor, _describe("place_wire", f"layer={value['layer']}"),
        [
            {"verb": "create_entity", "alias": "wire"},
            {
                "verb": "attach_component",
                "args": {
                    "entity": {"alias": "wire"},
                    "component": WIRE_COMPONENT, "value": value,
                },
            },
        ],
    )
    return _receipt("place_wire", actor, result, wire=result["aliases"]["wire"])


def place_junction(store, actor, xy, layer):
    """Place one explicit junction dot as a durable revision.

    Args:
        store: Entity store serving the seam.
        actor: Attribution recorded on the revision and events.
        xy: Integer [x, y] dot position.
        layer: Layer name for the dot.

    Returns:
        Receipt with op, actor, revision, junction ID, and events.

    Raises:
        ContractError: invalid_actor for empty attribution,
            invalid_junction for a malformed dot.
    """
    _need_actor(actor)
    value = validate_junction({"xy": xy, "layer": layer})
    result = store.transact(
        actor, _describe("place_junction", f"xy={value['xy']}"),
        [
            {"verb": "create_entity", "alias": "junction"},
            {
                "verb": "attach_component",
                "args": {
                    "entity": {"alias": "junction"},
                    "component": JUNCTION_COMPONENT, "value": value,
                },
            },
        ],
    )
    return _receipt(
        "place_junction", actor, result,
        junction=result["aliases"]["junction"],
    )


def connect_endpoint(store, actor, wire_id, end, ref):
    """Point one wire endpoint at a new terminus entity.

    Geometry never moves: the endpoint keeps its xy and only the
    ref changes, so a caller that moved the target re-resolves
    through move_wire while ERC flags the stale span. A no-change
    call writes nothing and reports a None revision.

    Args:
        store: Entity store serving the seam.
        actor: Attribution recorded on the revision and events.
        wire_id: Wire entity to rewire.
        end: "a" or "b" selecting the endpoint.
        ref: Pin/port/junction/net entity ID, or null to dangle.

    Returns:
        Receipt with op, actor, revision, wire ID, and events —
            or a noop receipt (revision None) when the ref is
            already set.

    Raises:
        ContractError: invalid_actor for empty attribution,
            unknown_wire for a missing wire, invalid_endpoint for
            a bad selector, unknown_ref for a missing entity,
            invalid_ref for a wire/self ref.
    """
    _need_actor(actor)
    if end not in ENDPOINTS:
        raise ContractError(
            "invalid_endpoint", f"end must be one of {ENDPOINTS}, got {end!r}."
        )
    if ref is not None:
        _check_ref(store, ref, wire_id=wire_id)
    wire = _read_wire(store, wire_id)
    index = ENDPOINTS.index(end)
    if wire["endpoints"][index]["ref"] == ref:
        return {"op": "connect_endpoint", "actor": actor, "revision": None,
                "noop": True, "wire": wire_id}
    wire["endpoints"][index]["ref"] = ref
    result = store.transact(
        actor, _describe("connect_endpoint", f"wire={wire_id} end={end}"),
        [
            {
                "verb": "set_component",
                "args": {
                    "entity": wire_id, "component": WIRE_COMPONENT,
                    "value": wire,
                },
            },
        ],
    )
    return _receipt("connect_endpoint", actor, result, wire=wire_id)


def move_wire(store, actor, wire_id, dx, dy):
    """Translate one wire, keeping every endpoint ref attached.

    Attachment is by entity ID, not geometry: refs survive the
    move while ERC flags spans whose xy no longer meets the
    target. A zero move writes nothing.

    Args:
        store: Entity store serving the seam.
        actor: Attribution recorded on the revision and events.
        wire_id: Wire entity to move.
        dx: Integer x translation.
        dy: Integer y translation.

    Returns:
        Receipt with op, actor, revision, wire ID, and events —
            or a noop receipt (revision None) for a zero move.

    Raises:
        ContractError: invalid_actor for empty attribution,
            unknown_wire for a missing wire, invalid_geometry for
            non-integer deltas.
    """
    _need_actor(actor)
    if not _is_int(dx) or not _is_int(dy):
        raise ContractError(
            "invalid_geometry",
            f"dx/dy must be ints, got {(dx, dy)!r}.",
        )
    if dx == 0 and dy == 0:
        return {"op": "move_wire", "actor": actor, "revision": None,
                "noop": True, "wire": wire_id}
    wire = _read_wire(store, wire_id)
    wire["segments"] = [
        [[x + dx, y + dy] for x, y in polyline]
        for polyline in wire["segments"]
    ]
    for endpoint in wire["endpoints"]:
        endpoint["xy"] = [endpoint["xy"][0] + dx, endpoint["xy"][1] + dy]
    result = store.transact(
        actor, _describe("move_wire", f"wire={wire_id} d=({dx}, {dy})"),
        [
            {
                "verb": "set_component",
                "args": {
                    "entity": wire_id, "component": WIRE_COMPONENT,
                    "value": wire,
                },
            },
        ],
    )
    return _receipt("move_wire", actor, result, wire=wire_id)


def split_wire(store, actor, wire_id, at):
    """Split one single-polyline wire at an interior point.

    A junction dot is placed at the split, the original wire keeps
    its head plus endpoint a, and a new wire entity carries the
    tail plus endpoint b; both abutting ends reference the new
    junction. All three land in one revision.

    Args:
        store: Entity store serving the seam.
        actor: Attribution recorded on the revision and events.
        wire_id: Wire entity to split.
        at: Integer [x, y] point on the polyline interior (never a
            wire end).

    Returns:
        Receipt with op, actor, revision, wire, junction, and
            new_wire IDs, plus events.

    Raises:
        ContractError: invalid_actor for empty attribution,
            unknown_wire for a missing wire, invalid_split for a
            point off the interior or a multi-polyline wire.
    """
    _need_actor(actor)
    point = _need_point(at, "at", "invalid_split")
    wire = _read_wire(store, wire_id)
    if len(wire["segments"]) != 1:
        raise ContractError(
            "invalid_split",
            "split_wire needs a single-polyline wire.",
        )
    (polyline,) = wire["segments"]
    if point == wire["endpoints"][0]["xy"] or point == wire["endpoints"][1]["xy"]:
        raise ContractError(
            "invalid_split", f"Split point {point} is a wire end."
        )
    cut = None
    for index, (seg_a, seg_b) in enumerate(zip(polyline, polyline[1:])):
        if _point_on_segment(point, seg_a, seg_b):
            cut = index
            break
    if cut is None:
        raise ContractError(
            "invalid_split", f"Split point {point} lies off the wire."
        )
    head_points = polyline[:cut + 1] + [point]
    tail_points = [point] + polyline[cut + 1:]
    head = {
        "segments": [head_points], "layer": wire["layer"],
        "endpoints": [
            dict(wire["endpoints"][0]),
            {"ref": {"alias": "junction"}, "xy": list(point)},
        ],
    }
    tail = {
        "segments": [tail_points], "layer": wire["layer"],
        "endpoints": [
            {"ref": {"alias": "junction"}, "xy": list(point)},
            dict(wire["endpoints"][1]),
        ],
    }
    result = store.transact(
        actor, _describe("split_wire", f"wire={wire_id} at={point}"),
        [
            {"verb": "create_entity", "alias": "junction"},
            {
                "verb": "attach_component",
                "args": {
                    "entity": {"alias": "junction"},
                    "component": JUNCTION_COMPONENT,
                    "value": {"xy": list(point), "layer": wire["layer"]},
                },
            },
            {"verb": "create_entity", "alias": "tail"},
            {
                "verb": "attach_component",
                "args": {
                    "entity": {"alias": "tail"},
                    "component": WIRE_COMPONENT, "value": tail,
                },
            },
            {
                "verb": "set_component",
                "args": {
                    "entity": wire_id, "component": WIRE_COMPONENT,
                    "value": head,
                },
            },
        ],
    )
    return _receipt(
        "split_wire", actor, result, wire=wire_id,
        junction=result["aliases"]["junction"],
        new_wire=result["aliases"]["tail"],
    )


def delete_wire(store, actor, wire_id):
    """Delete one wire entity as a durable revision.

    Junctions the wire referenced persist — explicit dots are
    never cascade-deleted — and Net entities rematerialize on the
    next materialize_nets call, which prunes names the extraction
    no longer yields.

    Args:
        store: Entity store serving the seam.
        actor: Attribution recorded on the revision and events.
        wire_id: Wire entity to delete.

    Returns:
        Receipt with op, actor, revision, wire ID, and events.

    Raises:
        ContractError: invalid_actor for empty attribution,
            unknown_wire for a missing wire.
    """
    _need_actor(actor)
    _read_wire(store, wire_id)
    result = store.transact(
        actor, _describe("delete_wire", f"wire={wire_id}"),
        [{"verb": "delete_entity", "args": {"entity": wire_id}}],
    )
    return _receipt("delete_wire", actor, result, wire=wire_id)


def delete_junction(store, actor, junction_id):
    """Delete one unreferenced junction as a durable revision.

    Args:
        store: Entity store serving the seam.
        actor: Attribution recorded on the revision and events.
        junction_id: Junction entity to delete.

    Returns:
        Receipt with op, actor, revision, junction ID, and events.

    Raises:
        ContractError: invalid_actor for empty attribution,
            unknown_junction for a missing junction,
            junction_in_use naming the wires still referencing it.
    """
    _need_actor(actor)
    try:
        components = store.components_of(junction_id)
    except LookupError:
        raise ContractError(
            "unknown_junction", f"No such junction entity: {junction_id!r}."
        ) from None
    if JUNCTION_COMPONENT not in components:
        raise ContractError(
            "unknown_junction",
            f"Entity {junction_id!r} carries no Junction component.",
        )
    users = []
    for wire_id in store.entities_with(WIRE_COMPONENT):
        wire = validate_wire(
            store.get_component(wire_id, WIRE_COMPONENT)
        )
        if any(e["ref"] == junction_id for e in wire["endpoints"]):
            users.append(wire_id)
    if users:
        raise ContractError(
            "junction_in_use",
            f"Junction {junction_id!r} is referenced by wires "
            f"{sorted(users)}; rewire them first.",
        )
    result = store.transact(
        actor, _describe("delete_junction", f"junction={junction_id}"),
        [{"verb": "delete_entity", "args": {"entity": junction_id}}],
    )
    return _receipt("delete_junction", actor, result, junction=junction_id)


def _index_pins(pins):
    if not isinstance(pins, (list, tuple)):
        raise ContractError("invalid_pin", "pins must be a list.")
    indexed = {}
    seen = set()
    for pin in pins:
        clean = validate_pin(pin)
        if clean["entity"] in indexed:
            raise ContractError(
                "invalid_pin",
                f"Duplicate pin entity: {clean['entity']!r}.",
            )
        key = (clean["instance"], clean["pin"])
        if key in seen:
            raise ContractError(
                "invalid_pin", f"Duplicate pin: {key[0]}.{key[1]}."
            )
        seen.add(key)
        indexed[clean["entity"]] = clean
    return indexed


def _check_named_refs(named_refs):
    if named_refs is None:
        return {}
    if not isinstance(named_refs, dict):
        raise ContractError("invalid_ref", "named_refs must be a mapping.")
    clean = {}
    for entity, name in named_refs.items():
        _need_nonempty_str(entity, "named_refs entity", "invalid_ref")
        _need_nonempty_str(name, f"named_refs[{entity}]", "invalid_ref")
        clean[entity] = name
    return clean


def _check_ports(ports):
    if not isinstance(ports, (list, tuple)):
        raise ContractError("invalid_port", "ports must be a list.")
    clean = []
    for index, port in enumerate(ports):
        if not isinstance(port, dict):
            raise ContractError(
                "invalid_port", f"ports[{index}] must be a mapping."
            )
        name = port.get("name")
        direction = port.get("direction")
        if not isinstance(name, str) or not name:
            raise ContractError("invalid_port", f"ports[{index}] needs a name.")
        if direction not in _PORT_DIRECTIONS:
            raise ContractError(
                "invalid_port",
                f"ports[{index}] direction must be one of "
                f"{_PORT_DIRECTIONS}, got {direction!r}.",
            )
        clean.append({"name": name, "direction": direction})
    return clean


def _read_world(store):
    wires = {}
    for wire_id in store.entities_with(WIRE_COMPONENT):
        wires[wire_id] = validate_wire(
            store.get_component(wire_id, WIRE_COMPONENT)
        )
    junctions = {}
    for junction_id in store.entities_with(JUNCTION_COMPONENT):
        junctions[junction_id] = validate_junction(
            store.get_component(junction_id, JUNCTION_COMPONENT)
        )
    nets = {}
    for net_id in store.entities_with(NET_COMPONENT):
        nets[net_id] = validate_net(store.get_component(net_id, NET_COMPONENT))
    return wires, junctions, nets


def world_schematic(store, pins, labels=(), ports=(), cell="top",
                    named_refs=None):
    """Build the CONNECT-GRAPH schematic for the stored wires.

    Wire polylines feed extraction verbatim; endpoints that
    reference Net entities (or named_refs entries such as ports)
    become labels carrying the referenced name at the endpoint xy,
    so a tap joins every group already carrying that name. Stale
    refs are reported, never silently dropped.

    Args:
        store: Entity store serving the seam.
        pins: Caller pin records [{entity, instance, pin, xy}].
        labels: Caller label records [{name, xy}].
        ports: Caller port records [{name, direction}].
        cell: Top cell name.
        named_refs: {entity ID: net name} for port-style refs the
            store cannot resolve to geometry.

    Returns:
        World view with the schematic mapping, the pin index by
            entity, and unresolved [{wire, end, ref}] entries.

    Raises:
        ContractError: invalid_pin for malformed pins,
            invalid_label for malformed labels, invalid_port for
            malformed ports, invalid_cell for a bad cell name,
            invalid_ref for malformed named_refs, invalid_wire /
            invalid_junction / invalid_net for corrupt storage.
    """
    _need_nonempty_str(cell, "cell", "invalid_cell")
    indexed = _index_pins(pins)
    if not isinstance(labels, (list, tuple)):
        raise ContractError("invalid_label", "labels must be a list.")
    clean_labels = [validate_label(label) for label in labels]
    clean_ports = _check_ports(ports)
    names = _check_named_refs(named_refs)
    wires, _junctions, nets = _read_world(store)
    net_names = {net_id: net["name"] for net_id, net in nets.items()}
    known = set(indexed) | set(wires) | set(_junctions) | set(nets) | set(names)
    schematic_labels = list(clean_labels)
    unresolved = []
    for wire_id in sorted(wires):
        for index, end in enumerate(ENDPOINTS):
            ref = wires[wire_id]["endpoints"][index]["ref"]
            if ref is None or ref in indexed or ref in _junctions:
                continue
            if ref in net_names:
                schematic_labels.append(
                    {"name": net_names[ref],
                     "xy": wires[wire_id]["endpoints"][index]["xy"]}
                )
            elif ref in names:
                schematic_labels.append(
                    {"name": names[ref],
                     "xy": wires[wire_id]["endpoints"][index]["xy"]}
                )
            elif ref in known:
                continue
            else:
                try:
                    store.components_of(ref)
                except LookupError:
                    unresolved.append(
                        {"wire": wire_id, "end": end, "ref": ref}
                    )
    by_instance = {}
    for pin in indexed.values():
        by_instance.setdefault(pin["instance"], []).append(pin["pin"])
    schematic = {
        "cell": cell,
        "wires": [
            polyline
            for wire_id in sorted(wires)
            for polyline in wires[wire_id]["segments"]
        ],
        "pins": [
            {"instance": pin["instance"], "pin": pin["pin"], "xy": pin["xy"]}
            for pin in indexed.values()
        ],
        "labels": schematic_labels,
        "instances": [
            {"name": name, "symbol": name} for name in sorted(by_instance)
        ],
        "symbols": {
            name: {"pins": sorted(pins)} for name, pins in by_instance.items()
        },
        "ports": clean_ports,
    }
    return {"schematic": schematic, "pins": indexed, "unresolved": unresolved}


def _default_extract(schematic):
    from ..workflows.connectgraph import prepare_netlist_structs

    return prepare_netlist_structs(schematic)


def _merge_by_name(connectivity):
    merged = {}
    for net in connectivity.nets:
        name = connectivity.net_name(net.id)
        slot = merged.setdefault(
            name, {"net_ids": [], "pins": set(), "labels": set(),
                   "has_wires": False}
        )
        slot["net_ids"].append(net.id)
        slot["pins"].update(net.pins)
        slot["labels"].update(net.labels)
        slot["has_wires"] = slot["has_wires"] or net.has_wires
    for slot in merged.values():
        slot["net_ids"].sort()
    return merged


def _membership(names_of_net, wires, junctions, indexed, nets, names,
                connectivity):
    """Map every wire/junction onto its net names by ref closure."""
    stored_names = {net_id: net["name"] for net_id, net in nets.items()}
    pin_net = {}
    for pin in indexed.values():
        net_id = connectivity.pin_net(pin["instance"], pin["pin"])
        if net_id is not None:
            pin_net[pin["entity"]] = names_of_net[net_id]
    wire_names = {wire_id: set() for wire_id in wires}
    for wire_id, wire in wires.items():
        for endpoint in wire["endpoints"]:
            ref = endpoint["ref"]
            if ref is None:
                continue
            if ref in pin_net:
                wire_names[wire_id].add(pin_net[ref])
            elif ref in stored_names and stored_names[ref] in names_of_net.values():
                wire_names[wire_id].add(stored_names[ref])
            elif ref in names and names[ref] in names_of_net.values():
                wire_names[wire_id].add(names[ref])
    junction_names = {junction_id: set() for junction_id in junctions}
    changed = True
    while changed:
        changed = False
        for wire_id, wire in wires.items():
            for endpoint in wire["endpoints"]:
                ref = endpoint["ref"]
                if ref in junction_names:
                    before = len(wire_names[wire_id])
                    wire_names[wire_id] |= junction_names[ref]
                    changed = changed or len(wire_names[wire_id]) != before
        for wire_id, wire in wires.items():
            for endpoint in wire["endpoints"]:
                ref = endpoint["ref"]
                if ref in junction_names:
                    before = len(junction_names[ref])
                    junction_names[ref] |= wire_names[wire_id]
                    changed = changed or len(junction_names[ref]) != before
    for junction_id, junction in junctions.items():
        if junction_names[junction_id]:
            continue
        if any(
            wire["endpoints"][i]["ref"] == junction_id
            for wire in wires.values() for i in range(2)
        ):
            continue
        for wire_id, wire in wires.items():
            if _point_on_wire(junction["xy"], wire):
                junction_names[junction_id] |= wire_names[wire_id]
    return wire_names, junction_names


def materialize_nets(store, actor, pins, labels=(), ports=(), cell="top",
                     named_refs=None, extract=None):
    """Extract connectivity, then upsert Net entities by name.

    Extraction always rebuilds (never a cached run): the world
    view feeds CONNECT-GRAPH, groups sharing a canonical name
    merge into one Net, wires/junctions attach by ref closure,
    and stored Nets whose names vanish are pruned — all in one
    revision. An unchanged world writes nothing (noop receipt).

    Args:
        store: Entity store serving the seam.
        actor: Attribution recorded on the revision and events.
        pins: Caller pin records [{entity, instance, pin, xy}].
        labels: Caller label records [{name, xy}].
        ports: Caller port records [{name, direction}].
        cell: Top cell name.
        named_refs: {entity ID: net name} for port-style refs the
            store cannot resolve to geometry.
        extract: Optional extraction callable (schematic) ->
            NetlistStructs; defaults to the in-tree CONNECT-GRAPH
            extraction.

    Returns:
        Receipt with op, actor, revision, nets {name: entity ID},
            created/updated/pruned ID lists, unresolved refs, and
            events — or a noop receipt (revision None) when every
            Net already matches.

    Raises:
        ContractError: invalid_actor for empty attribution,
            invalid_pin / invalid_label / invalid_port /
            invalid_cell / invalid_ref for malformed inputs,
            extraction_failed when extraction refuses the world.
    """
    _need_actor(actor)
    names = _check_named_refs(named_refs)
    view = world_schematic(
        store, pins, labels=labels, ports=ports, cell=cell,
        named_refs=named_refs,
    )
    extractor = extract if extract is not None else _default_extract
    try:
        structs = extractor(view["schematic"])
        connectivity = structs.connectivity
        merged = _merge_by_name(connectivity)
    except ContractError:
        raise
    except Exception as exc:
        raise ContractError(
            "extraction_failed", f"Connectivity extraction failed: {exc}."
        ) from exc
    wires, junctions, nets = _read_world(store)
    names_of_net = {
        net.id: connectivity.net_name(net.id) for net in connectivity.nets
    }
    wire_names, junction_names = _membership(
        names_of_net, wires, junctions, view["pins"], nets, names,
        connectivity,
    )
    by_name = {net["name"]: net_id for net_id, net in nets.items()}
    calls = []
    created = []
    updated = []
    nets_out = {}
    for name in sorted(merged):
        slot = merged[name]
        value = validate_net({
            "name": name,
            "extraction": {"cell": cell, "net_ids": slot["net_ids"]},
            "members": {
                "pins": [
                    {"instance": instance, "pin": pin}
                    for instance, pin in sorted(slot["pins"])
                ],
                "labels": sorted(slot["labels"]),
                "wires": sorted(
                    w for w, found in wire_names.items() if name in found
                ),
                "junctions": sorted(
                    j for j, found in junction_names.items() if name in found
                ),
            },
            "has_wires": slot["has_wires"],
        })
        if name in by_name and nets[by_name[name]] == value:
            nets_out[name] = by_name[name]
            continue
        if name in by_name:
            nets_out[name] = by_name[name]
            updated.append(by_name[name])
            calls.append({
                "verb": "set_component",
                "args": {
                    "entity": by_name[name], "component": NET_COMPONENT,
                    "value": value,
                },
            })
        else:
            alias = f"net:{name}"
            calls.append({"verb": "create_entity", "alias": alias})
            calls.append({
                "verb": "attach_component",
                "args": {
                    "entity": {"alias": alias}, "component": NET_COMPONENT,
                    "value": value,
                },
            })
            created.append(alias)
    pruned = [
        net_id for name, net_id in sorted(by_name.items()) if name not in merged
    ]
    for net_id in pruned:
        calls.append({
            "verb": "delete_entity", "args": {"entity": net_id},
        })
    if not calls:
        return {
            "op": "materialize_nets", "actor": actor, "revision": None,
            "noop": True, "nets": nets_out, "created": [], "updated": [],
            "pruned": [], "unresolved": view["unresolved"],
        }
    result = store.transact(
        actor, _describe("materialize_nets", f"cell={cell}"),
        calls,
    )
    for alias in created:
        name = alias[len("net:"):]
        nets_out[name] = result["aliases"][alias]
    receipt = _receipt(
        "materialize_nets", actor, result, nets=nets_out,
        unresolved=view["unresolved"],
    )
    receipt["created"] = [nets_out[alias[len("net:"):]] for alias in created]
    receipt["updated"] = updated
    receipt["pruned"] = pruned
    return receipt


def collect_wire_erc(store, pins, policy=None, named_refs=None):
    """Collect wire/junction ERC findings over the stored world.

    Dangling endpoints are warnings, refs to deleted entities are
    errors, spans whose xy no longer meets a pin/junction target
    are warnings, and junctions touching nothing are warnings.
    Nothing is ever silently dropped: every anomaly names its
    entity.

    Args:
        store: Entity store serving the seam.
        pins: Caller pin records [{entity, instance, pin, xy}].
        policy: rule -> severity overrides.
        named_refs: {entity ID: net name} for port-style refs the
            store cannot resolve to geometry.

    Returns:
        Findings sorted by (rule, entity, end), each with rule,
            severity, message, and locator keys.

    Raises:
        ContractError: invalid_pin for malformed pins,
            invalid_policy for an unknown rule, invalid_wire /
            invalid_junction for corrupt storage.
    """
    merged = dict(DEFAULT_WIRE_POLICY)
    for rule in (policy or {}):
        if rule not in merged:
            raise ContractError(
                "invalid_policy", f"Unknown ERC rule: {rule!r}."
            )
        merged[rule] = policy[rule]
    indexed = _index_pins(pins)
    _check_named_refs(named_refs)
    wires, junctions, _nets = _read_world(store)
    findings = []
    for wire_id in sorted(wires):
        wire = wires[wire_id]
        for index, end in enumerate(ENDPOINTS):
            endpoint = wire["endpoints"][index]
            ref = endpoint["ref"]
            if ref is None:
                findings.append({
                    "rule": RULE_DANGLING_ENDPOINT,
                    "severity": merged[RULE_DANGLING_ENDPOINT],
                    "message": (
                        f"wire {wire_id} end {end} dangles "
                        f"at {endpoint['xy']}"
                    ),
                    "wire": wire_id, "end": end, "xy": endpoint["xy"],
                })
                continue
            try:
                components = store.components_of(ref)
            except LookupError:
                findings.append({
                    "rule": RULE_UNKNOWN_REF,
                    "severity": merged[RULE_UNKNOWN_REF],
                    "message": (
                        f"wire {wire_id} end {end} references "
                        f"deleted entity {ref!r}"
                    ),
                    "wire": wire_id, "end": end, "ref": ref,
                })
                continue
            if WIRE_COMPONENT in components:
                findings.append({
                    "rule": RULE_UNKNOWN_REF,
                    "severity": merged[RULE_UNKNOWN_REF],
                    "message": (
                        f"wire {wire_id} end {end} references wire "
                        f"entity {ref!r}; endpoints terminate on "
                        "pin/port/junction/net IDs only"
                    ),
                    "wire": wire_id, "end": end, "ref": ref,
                })
                continue
            target = None
            if ref in indexed:
                target = indexed[ref]["xy"]
            elif ref in junctions:
                target = junctions[ref]["xy"]
            if target is not None and endpoint["xy"] != target:
                findings.append({
                    "rule": RULE_STALE_GEOMETRY,
                    "severity": merged[RULE_STALE_GEOMETRY],
                    "message": (
                        f"wire {wire_id} end {end} sits at "
                        f"{endpoint['xy']} but {ref!r} is at {target}"
                    ),
                    "wire": wire_id, "end": end, "ref": ref,
                    "xy": endpoint["xy"], "target": target,
                })
    referenced = {
        endpoint["ref"]
        for wire in wires.values() for endpoint in wire["endpoints"]
    }
    for junction_id in sorted(junctions):
        if junction_id in referenced:
            continue
        xy = junctions[junction_id]["xy"]
        if any(_point_on_wire(xy, wire) for wire in wires.values()):
            continue
        findings.append({
            "rule": RULE_ORPHAN_JUNCTION,
            "severity": merged[RULE_ORPHAN_JUNCTION],
            "message": f"junction {junction_id} at {xy} touches no wire",
            "junction": junction_id, "xy": xy,
        })
    findings.sort(
        key=lambda f: (f["rule"], f.get("wire", f.get("junction", "")),
                       f.get("end", ""))
    )
    return findings
