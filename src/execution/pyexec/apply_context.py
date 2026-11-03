"""Atomic session apply-context (CONSOLE-APPLY, ADR-016).

A console session stages layout intents (gf objects in) and lands
them as exactly one atomic transaction at block exit (intents out).
Sinks record unconditionally; only an open ``edit`` block stages a
batch, calls outside any block return scratch handles that commit
nothing. The outermost clean exit emits one batch; any exception
inside drops the whole block. A retired session refuses everything.

The batch lands through :meth:`Engine.apply_batch`, which compiles
intents to transaction changes and submits one ``apply_transaction``
— the same atomic path the editor surface uses, so console writes
are never a side-channel writer.
"""

import hashlib
import json

from ...project.errors import ProjectError

#: Pinned provisional gdsfactory profile stamped on landed shapes.
GF_PIN = "9.11.0"

#: Sink kinds the compiler lands; anything else fails loudly.
SINK_KINDS = ("cell", "rect")


class UnknownLayer(Exception):
    """A layer spec the session resolver cannot map.

    Args:
        spec: The unresolvable layer spec the caller passed.
    """

    def __init__(self, spec):
        self.spec = spec
        super().__init__(f"Unknown layer: {spec!r}.")


class _Handle:
    """Provisional sink handle: scratch outside a block, staged in one."""

    def __init__(self, name, scratch):
        self.name = name
        self.scratch = scratch

    def __repr__(self):
        state = "scratch" if self.scratch else "staged"
        return f"<apply {state}: {self.name}>"


def _port_records(component):
    """Split component ports into typed records plus bare names.

    gf ports carry center/layer; name-only ports (and name-only
    iteration) keep their names for provenance while landing no
    port rows the cell schema cannot type.

    Args:
        component: gf component (or duck-typed stand-in).

    Returns:
        Pair of typed port records and bare port names.
    """
    try:
        items = list(component.ports)
    except (AttributeError, TypeError):
        items = []
    records = []
    names = []
    for item in items:
        if isinstance(item, str):
            names.append(item)
            continue
        pname = getattr(item, "name", None)
        center = getattr(item, "center", None)
        layer = getattr(item, "layer", None)
        if (
            isinstance(pname, str)
            and pname
            and center is not None
            and isinstance(layer, (tuple, list))
            and len(layer) == 2
        ):
            try:
                lid = f"{layer[0]}/{layer[1]}"
                records.append(
                    {
                        "name": pname,
                        "x": int(round(float(center[0]))),
                        "y": int(round(float(center[1]))),
                        "layer": lid,
                    }
                )
                continue
            except (TypeError, ValueError, IndexError):
                pass
        names.append(str(pname if pname else item))
    return records, names


def _child_names(component):
    """Best-effort child instance names for hierarchy honesty.

    Args:
        component: gf component (or duck-typed stand-in).

    Returns:
        List of child instance names, possibly empty.
    """
    try:
        insts = list(getattr(component, "insts", None) or ())
    except TypeError:
        return []
    names = []
    for child in insts:
        label = getattr(child, "name", None)
        names.append(str(label) if label else type(child).__name__)
    return names


def compile_batch(batch):
    """Compile one emitted batch to transaction changes.

    Rect intents become shape-kind creates with the pinned gf
    profile; cell intents become Cell-definition creates. Child
    instances ride the batch as declared-unlanded metadata: the
    engine has no layout-instance model yet, so hierarchy is
    reported, never silently dropped and never phantom-landed.

    Args:
        batch: Emitted batch with label and intents.

    Returns:
        Mapping with changes, landed kinds, and unlanded entries.

    Raises:
        ProjectError: invalid_command for an unknown sink kind,
            a malformed rect, or an unnamed cell.
    """
    changes = []
    landed = []
    unlanded = []
    pdk = batch.get("pdk")
    profile = {"pdk": pdk, "tool": "gdsfactory", "version": GF_PIN}
    for index, intent in enumerate(batch.get("intents", ())):
        kind = intent.get("kind")
        if kind == "rect":
            bbox = intent.get("bbox", ())
            if (
                len(bbox) != 4
                or bbox[2] <= bbox[0]
                or bbox[3] <= bbox[1]
            ):
                raise ProjectError(
                    "invalid_command",
                    f"Rect needs x0<y1 ordering: {bbox!r}.",
                )
            data = {
                "x": bbox[0],
                "y": bbox[1],
                "w": bbox[2] - bbox[0],
                "h": bbox[3] - bbox[1],
            }
            changes.append(
                {
                    "op": "create",
                    "alias": f"rect-{index}",
                    "kind": "shape",
                    "components": {
                        "geom": {
                            "shape_type": "rect",
                            "layer": intent.get("layer"),
                            "units": "um",
                            "data": data,
                            "profile": dict(profile),
                        },
                        "shape_provenance": {
                            "anchor": None,
                            "profile": dict(profile),
                        },
                    },
                }
            )
            landed.append("rect")
        elif kind == "cell":
            name = intent.get("name")
            if not isinstance(name, str) or not name:
                raise ProjectError(
                    "invalid_command",
                    "Cell intent needs a non-empty name.",
                )
            changes.append(
                {
                    "op": "create",
                    "alias": f"cell:{name}",
                    "kind": "cell",
                    "components": {
                        "Cell": {
                            "name": name,
                            "ports": list(intent.get("ports", ())),
                            "properties": {"pdk": str(pdk)},
                            "revision": 1,
                        }
                    },
                }
            )
            landed.append("cell")
            for child in intent.get("children", ()):
                unlanded.append(
                    {
                        "kind": "instance",
                        "name": str(child),
                        "reason": "hierarchy landing deferred: "
                        "no layout-instance model; "
                        "definition landed",
                    }
                )
        else:
            raise ProjectError(
                "invalid_command",
                f"Unknown sink kind: {kind!r}.",
            )
    return {"changes": changes, "landed": landed, "unlanded": unlanded}


def session_prelude(project_id, console_id, generation):
    """Render the worker-side session snippet (prelude binding).

    The snippet appends after the pinned preamble without touching
    its digest: it exposes a ``session`` facade whose sink calls
    append JSON intent lines to the worker ops log using the same
    sink vocabulary the host session speaks. The host stages them
    with :meth:`ApplySession.collect_ops` into the next edit block.

    Args:
        project_id: Project the worker cell is bound to.
        console_id: Console session the worker cell runs under.
        generation: Session generation fenced against replays.

    Returns:
        Worker source text defining the ``session`` facade.
    """
    context = json.dumps(
        {
            "project_id": project_id,
            "console_id": console_id,
            "generation": generation,
        },
        sort_keys=True,
    )
    return (
        "# --- rocket apply-context: session binding (appended) ---\n"
        "import json as _json\n"
        f"__APPLY_CONTEXT__ = {context}\n"
        "\n"
        "\n"
        "class _WorkerSession:\n"
        '    """Session facade: sink calls stage JSON intent lines."""\n'
        "\n"
        "    def __init__(self):\n"
        "        self._index = 0\n"
        "\n"
        "    def _record(self, kind, payload):\n"
        "        entry = {'apply_intent': dict(payload, kind=kind)}\n"
        "        with open(__PYEXEC_OPS_LOG__, 'a', encoding='utf-8') as h:\n"
        "            h.write(_json.dumps(entry, sort_keys=True) + '\\n')\n"
        "        self._index += 1\n"
        "        return {'state': 'staged', 'kind': kind,\n"
        "                'index': self._index}\n"
        "\n"
        "    def cell(self, component, name):\n"
        "        ports, names, children = [], [], []\n"
        "        for port in list(getattr(component, 'ports', None) or ()):\n"
        "            label = port if isinstance(port, str) else getattr(\n"
        "                port, 'name', None) or str(port)\n"
        "            names.append(str(label))\n"
        "        for child in list(getattr(component, 'insts', None) or ()):\n"
        "            tag = getattr(child, 'name', None) or type(child).__name__\n"
        "            children.append(str(tag))\n"
        "        comp = getattr(component, 'name', None) or str(component)\n"
        "        return self._record('cell', {'name': name,\n"
        "            'component': str(comp), 'ports': ports,\n"
        "            'port_names': names, 'children': children})\n"
        "\n"
        "    def rect(self, layer, bbox):\n"
        "        return self._record('rect', {'layer': list(layer)\n"
        "            if isinstance(layer, (tuple, list)) else layer,\n"
        "            'bbox': list(bbox)})\n"
        "\n"
        "\n"
        "session = _WorkerSession()\n"
    )


class ApplySession:
    """One generation-bound atomic apply session (host side).

    Args:
        emit: Callable receiving each outermost-exit batch.
        project_id: Project batches land on.
        console_id: Console session owning this context.
        generation: Fence retiring stale sessions on reset.
        pdk_name: PDK auto-activated at first block entry.
        activate_pdk: Callable mapping the PDK name to proof.
        resolve_layer: Callable mapping a layer spec to its lid;
            raising :class:`UnknownLayer` fails the block loudly.
    """

    def __init__(self, *, emit, project_id, console_id, generation,
                 pdk_name, activate_pdk, resolve_layer):
        self._emit = emit
        self._project_id = project_id
        self._console_id = console_id
        self._generation = generation
        self._pdk_name = pdk_name
        self._activate_pdk = activate_pdk
        self._resolve_layer = resolve_layer
        self._depth = 0
        self._buffer = []
        self._span = []
        self._staged = []
        self._pdk_active = False
        self._retired = False
        self._counter = 0
        self.last_batch = None

    def _live(self):
        """Refuse work on a retired session.

        Raises:
            ProjectError: retired_session once retired.
        """
        if self._retired:
            raise ProjectError(
                "retired_session",
                "ApplySession is retired; open a new session.",
            )

    def retire(self):
        """Retire the session; later calls fail loudly."""
        self._retired = True
        self._buffer = []
        self._staged = []

    def edit(self, label):
        """Open one atomic edit block (nestable, outermost wins).

        Args:
            label: Batch label carried on the envelope.

        Returns:
            Block guard committing one batch at outermost exit.
        """
        return _Edit(self, label)

    def cell(self, component, name):
        """Stage one cell-definition intent from a gf component.

        Direct gf instances are refused: instances are not
        components, and landing one as a definition would lie
        about the hierarchy.

        Args:
            component: gf Component (duck-typed: name/ports/insts).
            name: Session handle name for the definition.

        Returns:
            Provisional handle (scratch outside a block).

        Raises:
            ProjectError: invalid_command for a direct gf
                Instance, retired_session once retired.
        """
        self._live()
        if getattr(component, "_gf_kind", None) == "Instance":
            raise ProjectError(
                "invalid_command",
                "session.cell refuses a direct gf Instance: "
                "instances are not components.",
            )
        records, names = _port_records(component)
        intent = {
            "kind": "cell",
            "name": name,
            "component": str(getattr(component, "name", component)),
            "ports": records,
            "port_names": names,
            "children": _child_names(component),
            "pdk": self._pdk_name,
        }
        return self._stage(f"cell:{name}", intent)

    def rect(self, layer_spec, bbox):
        """Stage one rectangle intent with a resolved layer.

        Args:
            layer_spec: Caller layer spec for resolve_layer.
            bbox: Bounds pair (x0, y0, x1, y1).

        Returns:
            Provisional handle (scratch outside a block).

        Raises:
            UnknownLayer: For an unresolvable layer spec.
            ProjectError: retired_session once retired.
        """
        self._live()
        layer = self._resolve_layer(layer_spec)
        if layer is None:
            raise UnknownLayer(layer_spec)
        bounds = tuple(bbox)
        intent = {
            "kind": "rect",
            "layer": layer,
            "bbox": list(bounds),
            "pdk": self._pdk_name,
        }
        self._counter += 1
        return self._stage(f"rect-{self._counter}", intent)

    def _stage(self, name, intent):
        """Buffer one intent or hand back a scratch handle."""
        if self._depth == 0:
            return _Handle(name, True)
        self._buffer.append(intent)
        return _Handle(name, False)

    def stage_intent(self, intent):
        """Stage one pre-built intent (worker-collected lines).

        Args:
            intent: Intent mapping with a known sink kind.

        Raises:
            ProjectError: invalid_command for an unknown kind,
                retired_session once retired.
        """
        self._live()
        if intent.get("kind") not in SINK_KINDS:
            raise ProjectError(
                "invalid_command",
                f"Unknown sink kind: {intent.get('kind')!r}.",
            )
        if self._depth == 0:
            self._staged.append(dict(intent))
        else:
            self._buffer.append(dict(intent))

    def collect_ops(self, path):
        """Stage worker-log intent lines into the session.

        Lines shaped ``{"apply_intent": {...}}`` join the open
        block, else wait staged for the next block. Anything else
        in the log is not ours and stays unread.

        Args:
            path: Worker ops-log path to drain.

        Returns:
            Count of staged intent lines.

        Raises:
            ProjectError: retired_session once retired.
        """
        self._live()
        staged = 0
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                intent = entry.get("apply_intent")
                if isinstance(intent, dict):
                    self.stage_intent(intent)
                    staged += 1
        return staged

    def _enter(self, label):
        """Open one block level; activate the PDK once."""
        self._live()
        if self._depth == 0 and not self._pdk_active:
            self._activate_pdk(self._pdk_name)
            self._pdk_active = True
        if self._depth == 0:
            self._buffer.extend(self._staged)
            self._staged = []
        self._depth += 1
        self._span.append(label)

    def _exit(self, label, failed):
        """Close one block level; outermost clean exit emits."""
        self._depth -= 1
        if failed:
            self._buffer = []
            self._span = []
            return
        if self._depth > 0:
            return
        batch = {
            "label": self._span[0],
            "blocks": self._span,
            "project_id": self._project_id,
            "console_id": self._console_id,
            "generation": self._generation,
            "pdk": self._pdk_name,
            "intents": self._buffer,
            "envelope": (
                f"rocket apply {self._project_id}:{label} "
                f"console={self._console_id} "
                f"gen={self._generation} "
                f"intents={len(self._buffer)}"
            ),
        }
        self._buffer = []
        self._span = []
        self.last_batch = batch
        self._emit(batch)

    def batch_digest(self, batch):
        """Stable request id seed for one batch.

        Args:
            batch: Emitted batch mapping.

        Returns:
            Hex digest of the batch envelope.
        """
        return hashlib.sha256(
            batch["envelope"].encode("utf-8")).hexdigest()


class _Edit:
    """One edit-block guard owned by its session."""

    def __init__(self, session, label):
        self._session = session
        self._label = label

    def __enter__(self):
        self._session._enter(self._label)
        return self._session

    def __exit__(self, exc_type, exc, tb):
        self._session._exit(self._label, exc_type is not None)
        return False
