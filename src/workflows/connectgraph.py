"""Shared schematic connectivity extraction (CONNECT-GRAPH).

One extraction feeds every netlist backend plus ERC: wires and
instance pins coalesce through a spatial hash, labels propagate net
names, unlabeled nets and instances get stable generated names, and
`lvs_ignore` instances stay out of the graph. Emitters and ERC never
name a net themselves — `Connectivity.net_name` is the single
authority they all read.

Schematic record (plain data, JSON-safe):

- cell: top cell name (default "top").
- wires: list of polylines; each a list of [x, y] integer points.
  Zero-length segments are skipped.
- pins: [{instance, pin, xy}]; instance may be "" only when the
  schematic holds exactly one unnamed instance.
- labels: [{name, xy}]; names propagate onto the nets they touch.
- instances: [{name?, symbol, attrs?, custom?, format?, generics?}];
  attrs.lvs_ignore excludes the instance from graph and netlist.
- symbols: {name: {pins?, custom?, format?, generics?}}.
- ports: [{name, direction}]; direction is input/output/inout and
  every port must name an extracted net.

Two wires connect when an endpoint of one lies on the other (shared
endpoints and T-junctions); crossing interiors do not connect.
"""

import hashlib
import json

RULE_SHORT = "connectivity.short"
RULE_UNCONNECTED_PIN = "connectivity.unconnected_pin"
RULE_DANGLING_NET = "connectivity.dangling_net"
RULE_ORPHAN_LABEL = "connectivity.orphan_label"

DEFAULT_POLICY = {
    RULE_SHORT: "error",
    RULE_UNCONNECTED_PIN: "warning",
    RULE_DANGLING_NET: "warning",
    RULE_ORPHAN_LABEL: "warning",
}

_PORT_DIRECTIONS = ("input", "output", "inout")
_HASH_CELL = 16

_CACHE = {}


class ConnectGraphError(ValueError):
    """Malformed schematic, unknown net id, or bad extraction request."""


class Net:
    """One extracted net: canonical name plus its members.

    Args:
        id: Deterministic net id (nets sort by anchor member).
        name: Canonical name from label propagation or generation.
        pins: Sorted ((instance, pin)) members.
        labels: Distinct sorted label names attached to this net.
        has_wires: True when at least one wire segment joins.
    """

    def __init__(self, id, name, pins, labels, has_wires):
        self.id = id
        self.name = name
        self.pins = tuple(pins)
        self.labels = tuple(labels)
        self.has_wires = has_wires

    def __eq__(self, other):
        if not isinstance(other, Net):
            return NotImplemented
        return (
            self.id,
            self.name,
            self.pins,
            self.labels,
            self.has_wires,
        ) == (
            other.id,
            other.name,
            other.pins,
            other.labels,
            other.has_wires,
        )

    def __repr__(self):
        return f"Net(id={self.id!r}, name={self.name!r})"


class ResolvedInstance:
    """One netlisted instance with pins bound to net ids.

    Args:
        name: Instance name (generated when the schematic omits it).
        symbol: Symbol name.
        pins: ((pin, net_id)) in symbol pin order, else pin-name order.
        generics: Symbol defaults overridden by instance values.
        custom: Instance-level custom templates by language.
        format: Instance-level format templates by language.
    """

    def __init__(self, name, symbol, pins, generics, custom=None, format=None):
        self.name = name
        self.symbol = symbol
        self.pins = tuple(pins)
        self.generics = dict(generics)
        self.custom = dict(custom or {})
        self.format = dict(format or {})

    def __eq__(self, other):
        if not isinstance(other, ResolvedInstance):
            return NotImplemented
        return (
            self.name,
            self.symbol,
            self.pins,
            self.generics,
            self.custom,
            self.format,
        ) == (
            other.name,
            other.symbol,
            other.pins,
            other.generics,
            other.custom,
            other.format,
        )

    def __repr__(self):
        return f"ResolvedInstance(name={self.name!r}, symbol={self.symbol!r})"


class Connectivity:
    """Extracted nets with the shared net-naming authority.

    Args:
        cell: Top cell name.
        nets: Nets in id order.
        shorts: [{net, labels}] for nets with conflicting labels.
        pin_index: (instance, pin) -> net id for graphed pins.
    """

    def __init__(self, cell, nets, shorts, pin_index):
        self.cell = cell
        self.nets = tuple(nets)
        self.shorts = tuple(dict(s) for s in shorts)
        self._pin_index = dict(pin_index)
        self._names = {net.id: net.name for net in self.nets}

    def net_name(self, net_id):
        """Return the canonical name of one net.

        The single naming authority: emitters and ERC resolve every
        net through this method, never from their own tables.

        Args:
            net_id: Extracted net id.

        Returns:
            Canonical net name.

        Raises:
            ConnectGraphError: Unknown net id.
        """
        try:
            return self._names[net_id]
        except KeyError:
            raise ConnectGraphError(f"Unknown net id: {net_id!r}.") from None

    def pin_net(self, instance, pin):
        """Return the net id of one instance pin.

        Args:
            instance: Instance name.
            pin: Pin name.

        Returns:
            Net id, or None for pins of `lvs_ignore` instances.
        """
        return self._pin_index.get((instance, pin))


class NetlistStructs:
    """Everything the emitters need: connectivity plus instances.

    Args:
        cell: Top cell name.
        connectivity: Extracted nets and the naming authority.
        instances: Resolved non-ignored instances, schematic order.
        symbols: Normalized symbol mappings (pins/custom/format).
        ports: [{name, direction}] in schematic order.
        ignored: Ignored instance names in schematic order.
    """

    def __init__(self, cell, connectivity, instances, symbols, ports, ignored):
        self.cell = cell
        self.connectivity = connectivity
        self.instances = tuple(instances)
        self.symbols = dict(symbols)
        self.ports = tuple(dict(p) for p in ports)
        self.ignored = tuple(ignored)


def prepare_netlist_structs(schematic, run_key=None):
    """Extract connectivity plus resolved instances from a schematic.

    Wires and pins coalesce through a spatial hash, labels propagate
    names, unlabeled nets become net1..netN in net order, unnamed
    instances become X<n>, and `lvs_ignore` instances drop out.
    Results cache only behind an explicit run key, and a changed
    schematic under a reused key rebuilds instead of serving stale
    nets.

    Args:
        schematic: Schematic record (see module docstring).
        run_key: Explicit cache key (run/snapshot id); None
            disables the cache and always rebuilds.

    Returns:
        NetlistStructs with connectivity, instances, and ports.

    Raises:
        ConnectGraphError: Malformed schematic, dangling port,
            unknown symbol, or a non-string run key.
    """
    if run_key is not None and (not isinstance(run_key, str) or not run_key):
        raise ConnectGraphError(f"run_key must be a non-empty string, got {run_key!r}.")
    normalized = _normalize_schematic(schematic)
    if run_key is None:
        return _extract(normalized)
    digest = _digest(normalized)
    hit = _CACHE.get(run_key)
    if hit is not None and hit[0] == digest:
        return hit[1]
    structs = _extract(normalized)
    _CACHE[run_key] = (digest, structs)
    return structs


def invalidate_run(run_key):
    """Drop one cached extraction.

    Args:
        run_key: Cache key passed to prepare_netlist_structs.

    Returns:
        1 when an entry was dropped, else 0.
    """
    return 1 if _CACHE.pop(run_key, None) is not None else 0


def clear_connectivity_cache():
    """Drop every cached extraction.

    Returns:
        Number of entries dropped.
    """
    count = len(_CACHE)
    _CACHE.clear()
    return count


def erc_findings(connectivity, policy=None):
    """List connectivity findings with authority-resolved net names.

    Args:
        connectivity: Extracted connectivity.
        policy: rule -> severity overrides; defaults warn on
            everything but shorts.

    Returns:
        Findings sorted by (rule, net id); every finding names its
        net through `Connectivity.net_name`.

    Raises:
        ConnectGraphError: Unknown rule in the policy.
    """
    merged = dict(DEFAULT_POLICY)
    for rule in (policy or {}):
        if rule not in merged:
            raise ConnectGraphError(f"Unknown ERC rule: {rule!r}.")
        merged[rule] = policy[rule]
    findings = []
    for net in connectivity.nets:
        name = connectivity.net_name(net.id)
        if len(net.labels) > 1:
            findings.append(
                {
                    "rule": RULE_SHORT,
                    "severity": merged[RULE_SHORT],
                    "message": (
                        f"net {name} has conflicting labels: "
                        + ", ".join(net.labels)
                    ),
                    "net": name,
                    "net_id": net.id,
                    "labels": list(net.labels),
                }
            )
        if len(net.pins) == 1 and not net.has_wires and not net.labels:
            (instance, pin) = net.pins[0]
            findings.append(
                {
                    "rule": RULE_UNCONNECTED_PIN,
                    "severity": merged[RULE_UNCONNECTED_PIN],
                    "message": f"pin {instance}.{pin} on net {name} connects to nothing",
                    "net": name,
                    "net_id": net.id,
                    "pins": [{"instance": instance, "pin": pin}],
                }
            )
        elif not net.pins and net.has_wires:
            findings.append(
                {
                    "rule": RULE_DANGLING_NET,
                    "severity": merged[RULE_DANGLING_NET],
                    "message": f"net {name} has wires but no pins",
                    "net": name,
                    "net_id": net.id,
                }
            )
        elif not net.pins and not net.has_wires and net.labels:
            findings.append(
                {
                    "rule": RULE_ORPHAN_LABEL,
                    "severity": merged[RULE_ORPHAN_LABEL],
                    "message": f"label {net.labels[0]} on net {name} touches nothing",
                    "net": name,
                    "net_id": net.id,
                    "labels": list(net.labels),
                }
            )
    findings.sort(key=lambda f: (f["rule"], f["net_id"]))
    return findings


def _parse_point(value, what):
    if (
        not isinstance(value, (list, tuple))
        or len(value) != 2
        or any(not isinstance(c, int) or isinstance(c, bool) for c in value)
    ):
        raise ConnectGraphError(f"{what} must be [x, y] ints, got {value!r}.")
    return (value[0], value[1])


def _parse_mapping(value, what):
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConnectGraphError(f"{what} must be a mapping, got {value!r}.")
    return dict(value)


def _normalize_schematic(schematic):
    if not isinstance(schematic, dict):
        raise ConnectGraphError(f"Schematic must be a mapping, got {schematic!r}.")
    cell = schematic.get("cell", "top")
    if not isinstance(cell, str) or not cell:
        raise ConnectGraphError(f"cell must be a non-empty string, got {cell!r}.")

    wires = schematic.get("wires", [])
    if not isinstance(wires, list):
        raise ConnectGraphError(f"wires must be a list, got {wires!r}.")
    segments = []
    for index, polyline in enumerate(wires):
        if not isinstance(polyline, (list, tuple)) or len(polyline) < 2:
            raise ConnectGraphError(
                f"wires[{index}] must hold at least 2 points, got {polyline!r}."
            )
        points = [_parse_point(p, f"wires[{index}]") for p in polyline]
        for a, b in zip(points, points[1:]):
            if a != b:
                segments.append((a, b))

    symbols = schematic.get("symbols", {})
    if not isinstance(symbols, dict):
        raise ConnectGraphError(f"symbols must be a mapping, got {symbols!r}.")
    normalized_symbols = {}
    for name, symbol in symbols.items():
        if not isinstance(symbol, dict):
            raise ConnectGraphError(f"symbol {name!r} must be a mapping.")
        pin_order = symbol.get("pins", [])
        if not isinstance(pin_order, list) or not all(
            isinstance(p, str) and p for p in pin_order
        ):
            raise ConnectGraphError(f"symbol {name!r} pins must be a str list.")
        normalized_symbols[name] = {
            "pins": list(pin_order),
            "custom": _parse_mapping(symbol.get("custom"), f"symbol {name!r} custom"),
            "format": _parse_mapping(symbol.get("format"), f"symbol {name!r} format"),
            "generics": _parse_mapping(symbol.get("generics"), f"symbol {name!r} generics"),
        }

    instances = schematic.get("instances", [])
    if not isinstance(instances, list):
        raise ConnectGraphError(f"instances must be a list, got {instances!r}.")
    normalized_instances = []
    taken = set()
    for index, instance in enumerate(instances):
        if not isinstance(instance, dict):
            raise ConnectGraphError(f"instances[{index}] must be a mapping.")
        symbol = instance.get("symbol")
        if not isinstance(symbol, str) or not symbol:
            raise ConnectGraphError(f"instances[{index}] needs a symbol name.")
        if symbol not in normalized_symbols:
            raise ConnectGraphError(
                f"instances[{index}] names unknown symbol {symbol!r}."
            )
        name = instance.get("name") or ""
        if not isinstance(name, str):
            raise ConnectGraphError(f"instances[{index}] name must be a string.")
        if name:
            if name in taken:
                raise ConnectGraphError(f"Duplicate instance name: {name!r}.")
            taken.add(name)
        attrs = _parse_mapping(instance.get("attrs"), f"instances[{index}] attrs")
        normalized_instances.append(
            {
                "name": name,
                "symbol": symbol,
                "ignored": bool(attrs.get("lvs_ignore", False)),
                "custom": _parse_mapping(instance.get("custom"), f"instances[{index}] custom"),
                "format": _parse_mapping(instance.get("format"), f"instances[{index}] format"),
                "generics": _parse_mapping(
                    instance.get("generics"), f"instances[{index}] generics"
                ),
            }
        )
    unnamed = [i for i in normalized_instances if not i["name"]]
    counter = 1
    for instance in unnamed:
        while f"X{counter}" in taken:
            counter += 1
        instance["name"] = f"X{counter}"
        taken.add(instance["name"])
        counter += 1

    pins = schematic.get("pins", [])
    if not isinstance(pins, list):
        raise ConnectGraphError(f"pins must be a list, got {pins!r}.")
    normalized_pins = []
    seen_pins = set()
    for index, pin in enumerate(pins):
        if not isinstance(pin, dict):
            raise ConnectGraphError(f"pins[{index}] must be a mapping.")
        instance = pin.get("instance", "")
        if not isinstance(instance, str):
            raise ConnectGraphError(f"pins[{index}] instance must be a string.")
        if not instance:
            if len(unnamed) != 1:
                raise ConnectGraphError(
                    f"pins[{index}] names no instance and the schematic holds "
                    f"{len(unnamed)} unnamed instances."
                )
            instance = unnamed[0]["name"]
        if instance not in taken:
            raise ConnectGraphError(f"pins[{index}] names unknown instance {instance!r}.")
        pin_name = pin.get("pin")
        if not isinstance(pin_name, str) or not pin_name:
            raise ConnectGraphError(f"pins[{index}] needs a pin name.")
        if (instance, pin_name) in seen_pins:
            raise ConnectGraphError(f"Duplicate pin: {instance}.{pin_name}.")
        seen_pins.add((instance, pin_name))
        normalized_pins.append(
            {"instance": instance, "pin": pin_name, "xy": _parse_point(pin.get("xy"), f"pins[{index}]")}
        )

    labels = schematic.get("labels", [])
    if not isinstance(labels, list):
        raise ConnectGraphError(f"labels must be a list, got {labels!r}.")
    normalized_labels = []
    for index, label in enumerate(labels):
        if not isinstance(label, dict):
            raise ConnectGraphError(f"labels[{index}] must be a mapping.")
        name = label.get("name")
        if not isinstance(name, str) or not name:
            raise ConnectGraphError(f"labels[{index}] needs a name.")
        normalized_labels.append(
            {"name": name, "xy": _parse_point(label.get("xy"), f"labels[{index}]")}
        )

    ports = schematic.get("ports", [])
    if not isinstance(ports, list):
        raise ConnectGraphError(f"ports must be a list, got {ports!r}.")
    normalized_ports = []
    for index, port in enumerate(ports):
        if not isinstance(port, dict):
            raise ConnectGraphError(f"ports[{index}] must be a mapping.")
        name = port.get("name")
        direction = port.get("direction")
        if not isinstance(name, str) or not name:
            raise ConnectGraphError(f"ports[{index}] needs a name.")
        if direction not in _PORT_DIRECTIONS:
            raise ConnectGraphError(
                f"ports[{index}] direction must be one of {_PORT_DIRECTIONS}, "
                f"got {direction!r}."
            )
        normalized_ports.append({"name": name, "direction": direction})

    return {
        "cell": cell,
        "segments": segments,
        "pins": normalized_pins,
        "labels": normalized_labels,
        "instances": normalized_instances,
        "symbols": normalized_symbols,
        "ports": normalized_ports,
    }


def _digest(normalized):
    text = json.dumps(
        {
            "cell": normalized["cell"],
            "segments": [sorted([list(a), list(b)]) for a, b in normalized["segments"]],
            "pins": normalized["pins"],
            "labels": normalized["labels"],
            "instances": normalized["instances"],
            "symbols": normalized["symbols"],
            "ports": normalized["ports"],
        },
        sort_keys=True,
    )
    return hashlib.sha256(text.encode()).hexdigest()


def _point_on_segment(point, seg_a, seg_b):
    (px, py), (ax, ay), (bx, by) = point, seg_a, seg_b
    if (bx - ax) * (py - ay) != (by - ay) * (px - ax):
        return False
    return min(ax, bx) <= px <= max(ax, bx) and min(ay, by) <= py <= max(ay, by)


class _UnionFind:
    """Union-find with path compression over small integer ids."""

    def __init__(self):
        self._parent = {}

    def _root(self, node):
        parent = self._parent.setdefault(node, node)
        while parent != self._parent[parent]:
            self._parent[node] = self._parent[parent]
            node = parent
            parent = self._parent[node]
        return parent

    def union(self, first, second):
        """Merge the sets holding two nodes.

        Args:
            first: First node.
            second: Second node.
        """
        root_first, root_second = self._root(first), self._root(second)
        if root_first != root_second:
            self._parent[root_second] = root_first

    def groups(self):
        """Return the disjoint node sets.

        Returns:
            List of node groups.
        """
        grouped = {}
        for node in self._parent:
            grouped.setdefault(self._root(node), []).append(node)
        return list(grouped.values())


class _SpatialHash:
    """Grid index from segment bboxes to segment ids."""

    def __init__(self, segments):
        self._segments = segments
        self._cells = {}
        for index, (a, b) in enumerate(segments):
            for cx in range(
                min(a[0], b[0]) // _HASH_CELL, max(a[0], b[0]) // _HASH_CELL + 1
            ):
                for cy in range(
                    min(a[1], b[1]) // _HASH_CELL, max(a[1], b[1]) // _HASH_CELL + 1
                ):
                    self._cells.setdefault((cx, cy), []).append(index)

    def segments_near(self, point):
        """Return candidate segment ids whose bbox covers a point.

        Args:
            point: (x, y) query point.

        Returns:
            Segment ids indexed under the point's grid cell.
        """
        return self._cells.get((point[0] // _HASH_CELL, point[1] // _HASH_CELL), [])


def _extract(normalized):
    ignored = {i["name"] for i in normalized["instances"] if i["ignored"]}
    pins = [p for p in normalized["pins"] if p["instance"] not in ignored]
    segments = normalized["segments"]
    labels = normalized["labels"]

    union = _UnionFind()
    point_nodes = {}

    def _claim(point, node):
        union._root(node)
        first = point_nodes.setdefault(point, node)
        union.union(first, node)

    for index, (a, b) in enumerate(segments):
        _claim(a, ("s", index))
        _claim(b, ("s", index))
    for index, pin in enumerate(pins):
        _claim(pin["xy"], ("p", index))
    for index, label in enumerate(labels):
        _claim(label["xy"], ("l", index))

    grid = _SpatialHash(segments)
    touch_points = (
        [a for a, _ in segments]
        + [b for _, b in segments]
        + [p["xy"] for p in pins]
        + [label["xy"] for label in labels]
    )
    for point in touch_points:
        for index in grid.segments_near(point):
            if _point_on_segment(point, *segments[index]):
                union.union(point_nodes[point], ("s", index))

    member_of = {}
    for index, pin in enumerate(pins):
        member_of[("p", index)] = ("pin", pin["instance"], pin["pin"])
    for index, label in enumerate(labels):
        member_of[("l", index)] = ("label", label["name"], index)
    for index in range(len(segments)):
        member_of[("s", index)] = ("seg", index)

    nets = []
    for group in union.groups():
        members = sorted(member_of[n] for n in group)
        pins_here = sorted((m[1], m[2]) for m in members if m[0] == "pin")
        labels_here = sorted({m[1] for m in members if m[0] == "label"})
        nets.append(
            {"anchor": members[0], "pins": pins_here, "labels": labels_here,
             "has_wires": any(m[0] == "seg" for m in members)}
        )
    nets.sort(key=lambda n: n["anchor"])

    used_names = {label for net in nets for label in net["labels"]}
    counter = 1
    final = []
    for net_id, net in enumerate(nets):
        if net["labels"]:
            name = net["labels"][0]
        else:
            while f"net{counter}" in used_names:
                counter += 1
            name = f"net{counter}"
            used_names.add(name)
            counter += 1
        final.append(
            Net(
                id=net_id,
                name=name,
                pins=net["pins"],
                labels=net["labels"],
                has_wires=net["has_wires"],
            )
        )

    pin_index = {}
    for net in final:
        for member in net.pins:
            pin_index[member] = net.id
    shorts = [
        {"net": net.id, "labels": list(net.labels)}
        for net in final
        if len(net.labels) > 1
    ]
    connectivity = Connectivity(
        cell=normalized["cell"], nets=final, shorts=shorts, pin_index=pin_index
    )

    canonical = {net.name for net in final}
    for port in normalized["ports"]:
        if port["name"] not in canonical:
            raise ConnectGraphError(
                f"Port {port['name']!r} names no extracted net "
                f"(nets: {sorted(canonical)})."
            )

    by_instance = {}
    for pin in normalized["pins"]:
        if pin["instance"] in ignored:
            continue
        by_instance.setdefault(pin["instance"], {})[pin["pin"]] = pin_index[
            (pin["instance"], pin["pin"])
        ]
    instances = []
    for instance in normalized["instances"]:
        if instance["ignored"]:
            continue
        symbol = normalized["symbols"][instance["symbol"]]
        order = symbol["pins"]
        pin_map = by_instance.get(instance["name"], {})
        if order:
            ordered = [(p, pin_map[p]) for p in order if p in pin_map]
            ordered += sorted((p, n) for p, n in pin_map.items() if p not in order)
        else:
            ordered = sorted(pin_map.items())
        instances.append(
            ResolvedInstance(
                name=instance["name"],
                symbol=instance["symbol"],
                pins=ordered,
                generics={**symbol["generics"], **instance["generics"]},
                custom=instance["custom"],
                format=instance["format"],
            )
        )

    return NetlistStructs(
        cell=normalized["cell"],
        connectivity=connectivity,
        instances=instances,
        symbols=normalized["symbols"],
        ports=normalized["ports"],
        ignored=[i["name"] for i in normalized["instances"] if i["ignored"]],
    )
