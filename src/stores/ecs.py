"""Engine entity store (ENGINE-ECS): entities + components over docs/ledger.

One identity per thing. Every new engine surface invented its own —
doc paths for sources, refs for blocks, names for nets — so this
module ends it: engine-minted entity IDs, generic component CRUD
instead of N bespoke endpoints, uniform ``component_changed``
events instead of per-feature notification plumbing, and filter
queries instead of one-off getters. Wires terminate on stable pin
entities only this store can mint.

Storage projection (documented, no second identity system): an
entity with id ``<id>`` lives at exactly one doc path,
``entities/<id>.json``, holding ``{"entity", "kind", "components"}``
as JSON. The path derives from the id alone — ``entity_doc_path``
and ``entity_from_doc_path`` are inverses — so CRUD, events, and
queries cannot drift: ``read_doc("entities/<id>.json")`` shows the
same bytes ``get_component`` serves, and ``list_docs`` lists every
entity. Canonical addressing is ``entity.component`` (one dot; ids
and component names never contain dots, so parsing is unambiguous).

Engine-provisioned IDs only: ``create_entity`` mints ``ent-<12hex>``
ids and takes no id argument — callers can never supply, guess, or
collide with an id. Backfill derives read-only ``doc-<12hex>`` ids
(sha1 of the doc path) for current project docs, so existing files
appear in the world snapshot and ``doc`` filters without a single
write: backfill never advances the revision.

Events: ``create_entity`` appends ``entity_created``,
``set/attach/detach_component`` append ``component_changed`` with
``{entity, component, revision}`` (detaches add ``detached: True``),
``delete_entity`` appends ``entity_deleted``. Every mutation gates
on ``expected_revision``, honors idempotent ``request_id`` replay,
advances the revision once, and returns the CRUD approval-UI fields
(actor, diff_summary, revision_transition, rewind_handle).

World snapshot is miniplex-shaped: ``{"entities": [{"id", "kind",
"components"}]}`` sorted by id maps one-to-one onto miniplex
entities (``{id, ...components}``), so mirrors load it directly.
Filter queries ``components_of`` / ``entities_with`` replace
one-off getters (nets-of-block, pins-of-net, open-problems); the
``entities_with`` predicate is an exact-match mapping over
top-level component fields.

``EntityStore`` is the in-memory reference implementation the unit
tests run standalone; the wiring patch teaches ``ProjectService``
the same verbs over the real doc store + durable ledger, reusing
these pure helpers for validation, addressing, encoding, and
backfill. Stdlib + ``json`` only (leaf module, no new deps, no
package-internal imports — no import cycle).
"""

import hashlib
import json
import re
import uuid

#: Doc prefix owning every entity record. Only ``ledger.yaml``,
#: ``events.yaml``, ``runs/``, and ``snapshots/`` are engine-owned
#: elsewhere, so ``entities/`` docs are plain documents: existing
#: ``list_docs`` / ``read_doc`` / ``write_doc`` keep working on them.
ENTITY_DOC_PREFIX = "entities/"

#: Entity records are JSON text (not YAML): one doc, one entity.
ENTITY_DOC_SUFFIX = ".json"

#: Engine ids (``ent-``) and backfill ids (``doc-``) share this shape:
#: lowercase, no dots — dots would make ``entity.component``
#: addresses ambiguous.
ENTITY_ID_PATTERN = r"^[a-z0-9][a-z0-9_-]*$"
_ENTITY_ID_RE = re.compile(ENTITY_ID_PATTERN)

#: Component names allow uppercase (``CellLink``-style) but no dots,
#: for the same addressing reason as entity ids.
COMPONENT_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_-]*$"
_COMPONENT_RE = re.compile(COMPONENT_PATTERN)

_KIND_RE = re.compile(r"^[A-Za-z0-9_.-]*$")
_HEX12_RE = re.compile(r"^[0-9a-f]{12}$")
_REVISION_RE = re.compile(r"^(.*?)(\d+)$")

#: Component name every backfilled doc carries (``{"path", "bytes"}``).
BACKFILL_COMPONENT = "doc"

#: Kind stamp on backfilled world-snapshot entries.
BACKFILL_KIND = "backfilled-doc"

#: One component may not exceed the doc-store write limit on its own.
MAX_COMPONENT_BYTES = 1_000_000

#: Component JSON nests no deeper than validated documents may.
MAX_NESTING_DEPTH = 100

__all__ = [
    "BACKFILL_COMPONENT",
    "BACKFILL_KIND",
    "ENTITY_DOC_PREFIX",
    "ENTITY_DOC_SUFFIX",
    "ENTITY_ID_PATTERN",
    "COMPONENT_PATTERN",
    "MAX_COMPONENT_BYTES",
    "MAX_NESTING_DEPTH",
    "EcsError",
    "validate_entity_id",
    "validate_component_name",
    "validate_kind",
    "validate_component_data",
    "validate_predicate",
    "mint_entity_id",
    "entity_doc_path",
    "entity_from_doc_path",
    "is_entity_doc",
    "parse_address",
    "format_address",
    "encode_entity_doc",
    "decode_entity_doc",
    "backfill_id_for_doc",
    "is_backfill_id",
    "backfill_entity_for_doc",
    "backfill_entities",
    "match_predicate",
    "filter_entities",
    "build_world_snapshot",
    "component_changed_data",
    "EntityStore",
]


class EcsError(Exception):
    """Entity-store violation with a stable machine code.

    Codes: invalid_entity, unknown_entity, backfill_readonly,
    invalid_component, unknown_component, component_exists,
    invalid_address, invalid_kind, invalid_data, invalid_predicate,
    invalid_document, unknown_document, invalid_path,
    revision_conflict, request_conflict.

    Args:
        code: Stable machine-readable error code.
        message: Human-readable detail.
        fields: Itemized fields, when the error names any.
    """

    def __init__(self, code, message, fields=None):
        super().__init__(message)
        self.code = code
        self.fields = fields or []


def validate_entity_id(entity):
    """Accept one engine-shaped entity id.

    Args:
        entity: Candidate id (``ent-…`` minted, ``doc-…`` backfilled).

    Returns:
        The same id, unchanged, when valid.

    Raises:
        EcsError: invalid_entity for non-text, empty, dotted,
            or otherwise malformed ids.
    """
    if not isinstance(entity, str) or _ENTITY_ID_RE.match(entity) is None:
        raise EcsError("invalid_entity", f"Bad entity id: {entity!r}.")
    return entity


def validate_component_name(name):
    """Accept one component name.

    Args:
        name: Candidate component name.

    Returns:
        The same name, unchanged, when valid.

    Raises:
        EcsError: invalid_component for non-text, empty, or dotted
            names (dots would break ``entity.component`` parsing).
    """
    if not isinstance(name, str) or _COMPONENT_RE.match(name) is None:
        raise EcsError(
            "invalid_component", f"Bad component name: {name!r}."
        )
    return name


def validate_kind(kind):
    """Accept one entity kind label.

    Args:
        kind: Candidate kind ("" means unclassified).

    Returns:
        The same kind, unchanged, when valid.

    Raises:
        EcsError: invalid_kind for non-text or over-punctuated kinds.
    """
    if not isinstance(kind, str) or _KIND_RE.match(kind) is None:
        raise EcsError("invalid_kind", f"Bad entity kind: {kind!r}.")
    return kind


def _check_depth(data, depth=0):
    if depth > MAX_NESTING_DEPTH:
        raise EcsError(
            "invalid_data", "Component data nests deeper than allowed."
        )
    if isinstance(data, dict):
        for value in data.values():
            _check_depth(value, depth + 1)
    elif isinstance(data, list):
        for value in data:
            _check_depth(value, depth + 1)


def validate_component_data(data):
    """Accept one JSON-serializable component payload.

    Args:
        data: Candidate payload (any JSON shape).

    Returns:
        The same payload, unchanged, when valid.

    Raises:
        EcsError: invalid_data for non-serializable payloads,
            non-finite scalars, over-deep nesting, or payloads past
            the byte limit.
    """
    try:
        text = json.dumps(data, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise EcsError(
            "invalid_data", f"Component data must be JSON: {exc}."
        ) from exc
    _check_depth(data)
    if len(text.encode("utf-8")) > MAX_COMPONENT_BYTES:
        raise EcsError(
            "invalid_data", "Component data exceeds the size limit."
        )
    return data


def validate_predicate(predicate):
    """Accept one entities_with predicate mapping.

    Args:
        predicate: Candidate predicate, or None for no filtering.

    Returns:
        The same predicate, unchanged, when valid.

    Raises:
        EcsError: invalid_predicate for a non-mapping predicate.
    """
    if predicate is not None and not isinstance(predicate, dict):
        raise EcsError(
            "invalid_predicate",
            f"Predicate must be a mapping, got {predicate!r}.",
        )
    return predicate


def mint_entity_id(existing=()):
    """Mint one fresh engine entity id.

    Args:
        existing: Container of taken ids the mint must avoid.

    Returns:
        Fresh ``ent-<12hex>`` id outside ``existing``.
    """
    while True:
        candidate = f"ent-{uuid.uuid4().hex[:12]}"
        if candidate not in existing:
            return candidate


def entity_doc_path(entity):
    """Derive the one doc path storing an entity.

    Args:
        entity: Entity id to project.

    Returns:
        Canonical ``entities/<id>.json`` path — the documented
        storage projection, derived from the id alone.

    Raises:
        EcsError: invalid_entity for a malformed id.
    """
    validate_entity_id(entity)
    return f"{ENTITY_DOC_PREFIX}{entity}{ENTITY_DOC_SUFFIX}"


def entity_from_doc_path(path):
    """Recover the entity id a doc path stores, if any.

    Args:
        path: Canonical doc path to inspect.

    Returns:
        Entity id for ``entities/<id>.json`` (single level),
        else None — never raises, so scans stay total.
    """
    if not isinstance(path, str):
        return None
    if not path.startswith(ENTITY_DOC_PREFIX):
        return None
    if not path.endswith(ENTITY_DOC_SUFFIX):
        return None
    middle = path[len(ENTITY_DOC_PREFIX):-len(ENTITY_DOC_SUFFIX)]
    if not middle or "/" in middle:
        return None
    return middle


def is_entity_doc(path):
    """True when a path is an entity record (not a plain doc).

    Args:
        path: Canonical doc path to inspect.

    Returns:
        True for single-level ``entities/*.json`` paths.
    """
    return entity_from_doc_path(path) is not None


def parse_address(address):
    """Split one canonical ``entity.component`` address.

    Args:
        address: Address text with exactly one dot.

    Returns:
        (entity, component) pair, both validated.

    Raises:
        EcsError: invalid_address for missing/extra dots or empty
            parts; invalid_entity / invalid_component for malformed
            parts.
    """
    if not isinstance(address, str) or address.count(".") != 1:
        raise EcsError(
            "invalid_address",
            f"Address must be entity.component, got {address!r}.",
        )
    entity, component = address.split(".")
    if not entity or not component:
        raise EcsError(
            "invalid_address",
            f"Address must be entity.component, got {address!r}.",
        )
    try:
        validate_entity_id(entity)
    except EcsError as exc:
        raise EcsError("invalid_address", str(exc)) from exc
    try:
        validate_component_name(component)
    except EcsError as exc:
        raise EcsError("invalid_address", str(exc)) from exc
    return entity, component


def format_address(entity, component):
    """Render one canonical ``entity.component`` address.

    Args:
        entity: Entity id part.
        component: Component name part.

    Returns:
        Canonical address text.

    Raises:
        EcsError: invalid_entity / invalid_component for malformed
            parts.
    """
    validate_entity_id(entity)
    validate_component_name(component)
    return f"{entity}.{component}"


def encode_entity_doc(entity, kind, components, entity_revision=1):
    """Render one entity record as canonical JSON text.

    Args:
        entity: Entity id the record stores.
        kind: Kind label carried beside the components.
        components: Mapping of component name to JSON payload.
        entity_revision: Per-entity revision (ENTITY-CAS): starts
            at 1, bumps on every accepted entity mutation.

    Returns:
        Deterministic JSON text (sorted keys): same record in,
        same bytes out.

    Raises:
        EcsError: invalid_entity / invalid_kind / invalid_component
            / invalid_data for malformed parts.
    """
    validate_entity_id(entity)
    validate_kind(kind)
    if not isinstance(components, dict):
        raise EcsError(
            "invalid_data", "Entity components must be a mapping."
        )
    for name, data in components.items():
        validate_component_name(name)
        validate_component_data(data)
    if (
        not isinstance(entity_revision, int)
        or isinstance(entity_revision, bool)
        or entity_revision < 1
    ):
        raise EcsError(
            "invalid_data", "Entity revision must be a positive int."
        )
    return (
        json.dumps(
            {
                "components": components,
                "entity": entity,
                "entity_revision": entity_revision,
                "kind": kind,
            },
            sort_keys=True,
            indent=2,
        )
        + "\n"
    )


def decode_entity_doc(text, path="<entity>"):
    """Parse one entity record back into its parts.

    Args:
        text: Entity doc text to parse.
        path: Doc path named in errors.

    Returns:
        Mapping with entity, kind, components, and
            entity_revision (legacy records without one read as 1).

    Raises:
        EcsError: invalid_document for unparsable text or a record
            whose shape breaks the projection.
    """
    try:
        data = json.loads(text)
    except (TypeError, ValueError) as exc:
        raise EcsError(
            "invalid_document",
            f"Entity record does not parse: {path} ({exc}).",
        ) from exc
    if not isinstance(data, dict):
        raise EcsError(
            "invalid_document",
            f"Entity record must be a mapping: {path}.",
        )
    entity = data.get("entity")
    kind = data.get("kind", "")
    components = data.get("components")
    try:
        validate_entity_id(entity)
        validate_kind(kind)
    except EcsError as exc:
        raise EcsError("invalid_document", f"{path}: {exc}.") from exc
    if not isinstance(components, dict):
        raise EcsError(
            "invalid_document",
            f"Entity record carries no components mapping: {path}.",
        )
    for name in components:
        try:
            validate_component_name(name)
        except EcsError as exc:
            raise EcsError(
                "invalid_document", f"{path}: {exc}."
            ) from exc
    entity_revision = data.get("entity_revision", 1)
    if (
        not isinstance(entity_revision, int)
        or isinstance(entity_revision, bool)
        or entity_revision < 1
    ):
        raise EcsError(
            "invalid_document",
            f"Entity record carries a bad revision: {path}.",
        )
    return {
        "entity": entity,
        "kind": kind,
        "components": components,
        "entity_revision": entity_revision,
    }


def backfill_id_for_doc(path):
    """Derive the stable read-only id backfilling one doc.

    Args:
        path: Canonical doc path to project.

    Returns:
        Deterministic ``doc-<12hex>`` id (sha1 of the path):
        same path in, same id out, across restarts.
    """
    digest = hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:12]
    return f"doc-{digest}"


def is_backfill_id(entity):
    """True when an id is a backfilled (read-only) doc id.

    Args:
        entity: Entity id to inspect.

    Returns:
        True for ``doc-<12hex>`` ids.
    """
    return (
        isinstance(entity, str)
        and entity.startswith("doc-")
        and _HEX12_RE.match(entity[len("doc-"):]) is not None
    )


def backfill_entity_for_doc(path, size):
    """Project one plain doc as a read-only virtual entity.

    Args:
        path: Canonical doc path to project.
        size: Byte size reported on the ``doc`` component.

    Returns:
        Virtual entity record (id, backfilled-doc kind, and a
        single ``doc`` component with path + bytes).
    """
    return {
        "id": backfill_id_for_doc(path),
        "kind": BACKFILL_KIND,
        "components": {
            BACKFILL_COMPONENT: {"bytes": size, "path": path}
        },
    }


def backfill_entities(entries):
    """Project plain docs as virtual entities (a pure read).

    Args:
        entries: Iterable of ``{"path", "bytes"}`` doc listings
            (the ``list_docs`` shape).

    Returns:
        Virtual entity records for every non-entity doc, sorted
        by path. Entity records are skipped — they already have
        engine ids, so backfilling them would mint a second
        identity. Never writes, never advances any revision.
    """
    backfilled = []
    for entry in entries:
        path = entry["path"]
        if is_entity_doc(path):
            continue
        backfilled.append(
            backfill_entity_for_doc(path, entry.get("bytes", 0))
        )
    return sorted(backfilled, key=lambda record: record["id"])


def match_predicate(data, predicate):
    """Test one component payload against an exact-match predicate.

    Args:
        data: Component payload to test.
        predicate: Exact-match mapping over top-level fields, or
            None for no filtering.

    Returns:
        True when the predicate is None or every predicate field
        equals the payload's; non-dict payloads never match a
        mapping predicate.

    Raises:
        EcsError: invalid_predicate for a non-mapping predicate.
    """
    validate_predicate(predicate)
    if predicate is None:
        return True
    if not isinstance(data, dict):
        return False
    return all(
        key in data and data[key] == value
        for key, value in predicate.items()
    )


def filter_entities(records, component, predicate=None):
    """Filter entity records to holders of one component.

    Args:
        records: Iterable of ``{"id", "kind", "components"}``
            records (real or backfilled).
        component: Component name holders must carry.
        predicate: Exact-match mapping the component payload must
            satisfy, or None for no filtering.

    Returns:
        Sorted holder ids (every holder when the predicate is
        None).

    Raises:
        EcsError: invalid_component for a malformed component
            name; invalid_predicate for a non-mapping predicate.
    """
    validate_component_name(component)
    validate_predicate(predicate)
    holders = [
        record["id"]
        for record in records
        if component in record["components"]
        and match_predicate(record["components"][component], predicate)
    ]
    return sorted(holders)


def build_world_snapshot(project_id, current_revision, records):
    """Bundle entity records as a miniplex-shaped world snapshot.

    Args:
        project_id: Project the snapshot mirrors.
        current_revision: Head revision the snapshot mirrors.
        records: Iterable of ``{"id", "kind", "components"}``
            records (real plus, optionally, backfilled).

    Returns:
        Snapshot mapping with project id, head revision, and the
        entities sorted by id — each entry maps one-to-one onto a
        miniplex entity (``{id, ...components}``), so mirrors load
        it directly.
    """
    ordered = sorted(records, key=lambda record: record["id"])
    return {
        "current_revision": current_revision,
        "entities": [
            {
                "components": dict(record["components"]),
                "id": record["id"],
                "kind": record["kind"],
            }
            for record in ordered
        ],
        "project_id": project_id,
    }


def component_changed_data(
    entity, component, revision, detached=False, entity_revision=None
):
    """Build one component_changed event payload.

    Args:
        entity: Entity whose component changed.
        component: Component that changed.
        revision: Head revision after the change.
        detached: True when the change removed the component.
        entity_revision: Per-entity revision after the change
            (ENTITY-CAS); omitted when unknown so legacy exact
            shapes keep passing.

    Returns:
        Event data mapping with entity, component, revision (plus
        detached True for removals, plus entity_revision when
        supplied).
    """
    data = {"component": component, "entity": entity, "revision": revision}
    if detached:
        data["detached"] = True
    if entity_revision is not None:
        data["entity_revision"] = entity_revision
    return data


def _advance_revision(revision):
    """Next revision: trailing digits increment, else `-2` is suffixed."""
    match = _REVISION_RE.match(revision or "")
    if match is None:
        return f"{revision}-2"
    return f"{match.group(1)}{int(match.group(2)) + 1}"


def _frozen_identity(operation, arguments):
    """Canonical identity text for idempotent request comparison."""
    return json.dumps(
        {"arguments": arguments, "operation": operation},
        sort_keys=True,
        default=str,
    )

# TODO: No need to handroll this. bro just get an ECS library
# Utilize the ESPER lib context and modify the context of esper to seet the default context for the runtime to world context
# WIth esper's ECS, a lot of the tools can just move to their own dedicated tools/ module outside of ports, for the simple reason that ports will be used for communicating with the engine
# While tools are tools the engine uses to power its services, and the result of said tools needs to propagate to all adapter ports to fan out the results, while port-specific formatting remains the responsibility of the adapter itself, it just needs to know what the tool sends back out; pydantic dataclass
class EntityStore:
    """In-memory entity store: the reference ECS implementation.

    Projects entities over an in-memory doc map plus an ordered
    event log with the ledger law: every accepted mutation gates on
    ``expected_revision``, honors idempotent ``request_id`` replay,
    advances the revision once, and appends one actor-attributed
    event. The wiring patch teaches ``ProjectService`` these same
    verbs over the real doc store + durable ledger; response shapes
    match field for field so unit and wiring tests assert one
    contract.

    Args:
        project_id: Project this store is bound to.
        actor: Attribution recorded on every appended event.
        current_revision: Starting head revision.

    Caution: An omitted expected_revision defaults to the live head
        (a test-seam leniency); the wired path follows
        ``ProjectService`` strictness instead — callers supply the
        head they read (MCP fills it), and stale writers fail.
    """

    def __init__(
        self, project_id="ecs-demo", actor="test",
        current_revision="p12",
    ):
        self._project_id = project_id
        self._actor = actor
        self._current_revision = current_revision
        self._docs = {}
        self._events = []
        self._requests = {}

    def _cursor(self):
        return self._events[-1]["seq"] if self._events else 0

    def _append_event(self, event, request_id, data):
        record = {
            "actor": self._actor,
            "data": data,
            "event": event,
            "project_id": self._project_id,
            "request_id": request_id,
            "seq": self._cursor() + 1,
        }
        self._events.append(record)
        return record

    def _check_replay(self, request_id, identity):
        prev = self._requests.get(request_id)
        if prev is None:
            return None
        prev_identity, prev_response = prev
        if prev_identity != identity:
            raise EcsError(
                "request_conflict",
                f"Request id reused with different input: {request_id}.",
            )
        return prev_response

    def _gate_revision(self, expected_revision):
        if expected_revision != self._current_revision:
            raise EcsError(
                "revision_conflict",
                f"Expected revision {self._current_revision}, "
                f"got {expected_revision}.",
            )

    def _refresh_expected(self, expected_revision):
        if expected_revision is None:
            return self._current_revision
        return expected_revision

    def _mutation_response(
        self, request_id, previous, diff, record, extra=None
    ):
        response = {
            "actor": self._actor,
            "current_revision": self._current_revision,
            "diff_summary": diff,
            "event_cursor": self._cursor(),
            "events": [record],
            "previous_revision": previous,
            "project_id": self._project_id,
            "request_id": request_id,
            "revision_transition": {
                "from": previous,
                "to": self._current_revision,
            },
            "rewind_handle": {
                "project_id": self._project_id,
                "request_id": request_id,
                "revision": previous,
            },
        }
        response.update(extra or {})
        return response

    def _read_entity(self, entity):
        validate_entity_id(entity)
        if is_backfill_id(entity):
            raise EcsError(
                "backfill_readonly",
                f"Backfilled entity is read-only: {entity}.",
            )
        path = entity_doc_path(entity)
        text = self._docs.get(path)
        if text is None:
            raise EcsError("unknown_entity", f"No such entity: {entity}.")
        decoded = decode_entity_doc(text, path)
        if decoded["entity"] != entity:
            raise EcsError(
                "invalid_document",
                f"Entity record id drift at {path}: stored "
                f"{decoded['entity']!r} for {entity!r}.",
            )
        return path, decoded

    def _doc_entries(self):
        return [
            {"bytes": len(text.encode("utf-8")), "path": path}
            for path, text in self._docs.items()
        ]

    def _entity_records(self):
        records = []
        for path in sorted(self._docs):
            entity = entity_from_doc_path(path)
            if entity is None:
                continue
            decoded = decode_entity_doc(self._docs[path], path)
            records.append({
                "components": decoded["components"],
                "id": decoded["entity"],
                "kind": decoded["kind"],
            })
        return records

    def _backfill_records(self):
        return backfill_entities(self._doc_entries())

    def _resolve_backfill(self, entity):
        for record in self._backfill_records():
            if record["id"] == entity:
                return record
        raise EcsError("unknown_entity", f"No such entity: {entity}.")

    def snapshot(self):
        """Read the store head: project, revision, and event cursor.

        Returns:
            Snapshot mapping with project_id, current_revision,
            and event_cursor.
        """
        return {
            "current_revision": self._current_revision,
            "event_cursor": self._cursor(),
            "project_id": self._project_id,
        }

    def events_since(self, cursor):
        """Read logged events after a cursor, oldest first.

        Args:
            cursor: Only events with a higher seq are returned.

        Returns:
            Logged events after the cursor, seq-ordered.
        """
        return [e for e in self._events if e["seq"] > cursor]

    def write_doc(
        self, path, content, request_id=None, expected_revision=None
    ):
        """Write one plain document: gate, store, advance, log.

        The existing CRUD spelling, kept working alongside
        entities — entity records written through here decode
        through the same projection on read.

        Args:
            path: Document path to create or overwrite.
            content: UTF-8 text to store.
            request_id: Client envelope id for idempotent replay;
                a fresh id when omitted.
            expected_revision: Revision the writer read; the live
                head when omitted.

        Returns:
            Mutation mapping with path, revision transition, new
            head, actor, diff summary, rewind handle, the
            appended event, cursor, and request id.

        Raises:
            EcsError: request_conflict for a reused id with new
                text; invalid_path for a bad path; invalid_command
                for non-text content; revision_conflict for a
                stale head.
        """
        request_id = request_id or uuid.uuid4().hex
        identity = _frozen_identity(
            "write_doc", {"content": content, "path": path}
        )
        replay = self._check_replay(request_id, identity)
        if replay is not None:
            return replay
        if (
            not isinstance(path, str)
            or not path
            or path.startswith("/")
            or ".." in path.split("/")
        ):
            raise EcsError("invalid_path", f"Bad document path: {path!r}.")
        if (
            path in ("ledger.yaml", "events.yaml")
            or path.startswith("runs/")
            or path.startswith("snapshots/")
        ):
            raise EcsError(
                "invalid_path",
                f"Engine-owned path is not a document: {path!r}.",
            )
        if not isinstance(content, str):
            raise EcsError(
                "invalid_command",
                f"Write needs text content for document {path}.",
            )
        self._gate_revision(self._refresh_expected(expected_revision))
        previous = self._current_revision
        old = self._docs.get(path)
        self._docs[path] = content
        self._current_revision = _advance_revision(previous)
        new_bytes = len(content.encode("utf-8"))
        if old is None:
            diff = f"created {path} ({new_bytes} bytes)"
        else:
            diff = (
                f"updated {path} "
                f"({len(old.encode('utf-8'))} -> {new_bytes} bytes)"
            )
        record = self._append_event(
            "doc_written",
            request_id,
            {
                "bytes": new_bytes,
                "diff_summary": diff,
                "operation": "write_doc",
                "path": path,
                "revision": self._current_revision,
            },
        )
        response = self._mutation_response(
            request_id, previous, diff, record, {"path": path}
        )
        self._requests[request_id] = (identity, response)
        return response

    def read_doc(self, path):
        """Read one document as text at the current head.

        Args:
            path: Document path to read.

        Returns:
            Mapping with project id, head revision, path,
            content text, and byte size.

        Raises:
            EcsError: unknown_document for a missing document.
        """
        content = self._docs.get(path)
        if content is None:
            raise EcsError("unknown_document", f"No such document: {path}.")
        return {
            "bytes": len(content.encode("utf-8")),
            "content": content,
            "current_revision": self._current_revision,
            "path": path,
            "project_id": self._project_id,
        }

    def list_docs(self, prefix=None):
        """List documents, optionally filtered by a path prefix.

        Args:
            prefix: Optional path prefix; empty matches everything.

        Returns:
            Mapping with project id, head revision, event cursor,
            and sorted document entries (path + bytes).
        """
        want = prefix or ""
        documents = []
        for path in sorted(self._docs):
            if want and not (path == want or path.startswith(want + "/")):
                if not path.startswith(want):
                    continue
            documents.append({
                "bytes": len(self._docs[path].encode("utf-8")),
                "path": path,
            })
        return {
            "current_revision": self._current_revision,
            "documents": documents,
            "event_cursor": self._cursor(),
            "project_id": self._project_id,
        }

    def create_entity(
        self, kind="", components=None, request_id=None,
        expected_revision=None,
    ):
        """Create one entity with an engine-minted id.

        The id is minted, never supplied: there is no id argument,
        so callers cannot collide with, guess, or squat on engine
        identity. The record persists as its projected doc path.

        Args:
            kind: Kind label carried beside the components.
            components: Optional initial component mapping.
            request_id: Client envelope id for idempotent replay;
                a fresh id when omitted.
            expected_revision: Revision the writer read; the live
                head when omitted.

        Returns:
            Mutation mapping with the minted entity, kind, storage
            path, revision transition, new head, actor, diff
            summary, rewind handle, the entity_created event,
            cursor, request id, and initial component names.

        Raises:
            EcsError: request_conflict for a reused id with new
                text; invalid_kind / invalid_component /
                invalid_data for malformed parts;
                revision_conflict for a stale head.
        """
        request_id = request_id or uuid.uuid4().hex
        validate_kind(kind)
        initial = dict(components or {})
        for name, data in initial.items():
            validate_component_name(name)
            validate_component_data(data)
        identity = _frozen_identity(
            "create_entity", {"components": initial, "kind": kind}
        )
        replay = self._check_replay(request_id, identity)
        if replay is not None:
            return replay
        self._gate_revision(self._refresh_expected(expected_revision))
        previous = self._current_revision
        taken = {
            entity_from_doc_path(path) for path in self._docs
        } - {None}
        entity = mint_entity_id(existing=taken)
        path = entity_doc_path(entity)
        self._docs[path] = encode_entity_doc(entity, kind, initial)
        self._current_revision = _advance_revision(previous)
        diff = f"created entity {entity} ({path})"
        record = self._append_event(
            "entity_created",
            request_id,
            {
                "components": sorted(initial),
                "entity": entity,
                "kind": kind,
                "revision": self._current_revision,
            },
        )
        response = self._mutation_response(
            request_id, previous, diff, record,
            {
                "components": sorted(initial),
                "entity": entity,
                "kind": kind,
                "path": path,
            },
        )
        self._requests[request_id] = (identity, response)
        return response

    def get_component(self, entity, component):
        """Read one component payload at the current head.

        Backfilled doc entities serve their projected ``doc``
        component here, so every world-snapshot entry stays
        addressable.

        Args:
            entity: Entity id holding the component.
            component: Component name to read.

        Returns:
            Mapping with project id, head revision, entity,
            component, canonical address, storage path (the
            projected doc path, or the backfilled doc path), and
            the component data.

        Raises:
            EcsError: invalid_entity / invalid_component for
                malformed parts; unknown_entity for a missing
                entity; unknown_component for a missing component;
                invalid_document for a corrupt entity record.
        """
        validate_entity_id(entity)
        validate_component_name(component)
        if is_backfill_id(entity):
            record = self._resolve_backfill(entity)
            if component != BACKFILL_COMPONENT:
                raise EcsError(
                    "unknown_component",
                    f"No component {component!r} on {entity}.",
                )
            data = record["components"][BACKFILL_COMPONENT]
            return {
                "address": format_address(entity, component),
                "component": component,
                "current_revision": self._current_revision,
                "data": dict(data),
                "entity": entity,
                "path": data["path"],
                "project_id": self._project_id,
            }
        path, decoded = self._read_entity(entity)
        if component not in decoded["components"]:
            raise EcsError(
                "unknown_component",
                f"No component {component!r} on {entity}.",
            )
        return {
            "address": format_address(entity, component),
            "component": component,
            "current_revision": self._current_revision,
            "data": decoded["components"][component],
            "entity": entity,
            "path": path,
            "project_id": self._project_id,
        }

    def set_component(
        self, entity, component, data, request_id=None,
        expected_revision=None,
    ):
        """Upsert one component payload (create or overwrite).

        Args:
            entity: Entity id holding the component.
            component: Component name to write.
            data: JSON payload to store.
            request_id: Client envelope id for idempotent replay;
                a fresh id when omitted.
            expected_revision: Revision the writer read; the live
                head when omitted.

        Returns:
            Mutation mapping with entity, component, canonical
            address, storage path, revision transition, new head,
            actor, diff summary, rewind handle, the
            component_changed event, cursor, and request id.

        Raises:
            EcsError: request_conflict for a reused id with new
                text; invalid_entity / invalid_component /
                invalid_data for malformed parts; unknown_entity
                for a missing entity; backfill_readonly for a
                backfilled id; invalid_document for a corrupt
                entity record; revision_conflict for a stale head.
        """
        request_id = request_id or uuid.uuid4().hex
        validate_entity_id(entity)
        validate_component_name(component)
        validate_component_data(data)
        identity = _frozen_identity(
            "set_component",
            {"component": component, "data": data, "entity": entity},
        )
        replay = self._check_replay(request_id, identity)
        if replay is not None:
            return replay
        path, decoded = self._read_entity(entity)
        self._gate_revision(self._refresh_expected(expected_revision))
        previous = self._current_revision
        existed = component in decoded["components"]
        merged = dict(decoded["components"])
        merged[component] = data
        self._docs[path] = encode_entity_doc(
            entity, decoded["kind"], merged
        )
        self._current_revision = _advance_revision(previous)
        verb = "updated" if existed else "set"
        diff = (
            f"{verb} {format_address(entity, component)} ({path})"
        )
        record = self._append_event(
            "component_changed",
            request_id,
            component_changed_data(
                entity, component, self._current_revision
            ),
        )
        response = self._mutation_response(
            request_id, previous, diff, record,
            {
                "address": format_address(entity, component),
                "component": component,
                "entity": entity,
                "path": path,
            },
        )
        self._requests[request_id] = (identity, response)
        return response

    def attach_component(
        self, entity, component, data, request_id=None,
        expected_revision=None,
    ):
        """Attach one new component (refuses overwrites).

        Args:
            entity: Entity id holding the component.
            component: Component name to attach.
            data: JSON payload to store.
            request_id: Client envelope id for idempotent replay;
                a fresh id when omitted.
            expected_revision: Revision the writer read; the live
                head when omitted.

        Returns:
            Mutation mapping (see set_component) with the
            component_changed event.

        Raises:
            EcsError: component_exists when the component already
                lives on the entity; otherwise like set_component.
        """
        request_id = request_id or uuid.uuid4().hex
        validate_entity_id(entity)
        validate_component_name(component)
        validate_component_data(data)
        identity = _frozen_identity(
            "attach_component",
            {"component": component, "data": data, "entity": entity},
        )
        replay = self._check_replay(request_id, identity)
        if replay is not None:
            return replay
        path, decoded = self._read_entity(entity)
        if component in decoded["components"]:
            raise EcsError(
                "component_exists",
                f"Component already attached: "
                f"{format_address(entity, component)}.",
            )
        self._gate_revision(self._refresh_expected(expected_revision))
        previous = self._current_revision
        merged = dict(decoded["components"])
        merged[component] = data
        self._docs[path] = encode_entity_doc(
            entity, decoded["kind"], merged
        )
        self._current_revision = _advance_revision(previous)
        diff = (
            f"attached {format_address(entity, component)} ({path})"
        )
        record = self._append_event(
            "component_changed",
            request_id,
            component_changed_data(
                entity, component, self._current_revision
            ),
        )
        response = self._mutation_response(
            request_id, previous, diff, record,
            {
                "address": format_address(entity, component),
                "component": component,
                "entity": entity,
                "path": path,
            },
        )
        self._requests[request_id] = (identity, response)
        return response

    def detach_component(
        self, entity, component, request_id=None,
        expected_revision=None,
    ):
        """Detach one component from its entity.

        Args:
            entity: Entity id holding the component.
            component: Component name to remove.
            request_id: Client envelope id for idempotent replay;
                a fresh id when omitted.
            expected_revision: Revision the writer read; the live
                head when omitted.

        Returns:
            Mutation mapping (see set_component); the
            component_changed event carries detached True.

        Raises:
            EcsError: unknown_component for a missing component;
                otherwise like set_component.
        """
        request_id = request_id or uuid.uuid4().hex
        validate_entity_id(entity)
        validate_component_name(component)
        identity = _frozen_identity(
            "detach_component",
            {"component": component, "entity": entity},
        )
        replay = self._check_replay(request_id, identity)
        if replay is not None:
            return replay
        path, decoded = self._read_entity(entity)
        if component not in decoded["components"]:
            raise EcsError(
                "unknown_component",
                f"No component {component!r} on {entity}.",
            )
        self._gate_revision(self._refresh_expected(expected_revision))
        previous = self._current_revision
        merged = dict(decoded["components"])
        del merged[component]
        self._docs[path] = encode_entity_doc(
            entity, decoded["kind"], merged
        )
        self._current_revision = _advance_revision(previous)
        diff = (
            f"detached {format_address(entity, component)} ({path})"
        )
        record = self._append_event(
            "component_changed",
            request_id,
            component_changed_data(
                entity, component, self._current_revision,
                detached=True,
            ),
        )
        response = self._mutation_response(
            request_id, previous, diff, record,
            {
                "address": format_address(entity, component),
                "component": component,
                "entity": entity,
                "path": path,
            },
        )
        self._requests[request_id] = (identity, response)
        return response

    def delete_entity(
        self, entity, request_id=None, expected_revision=None
    ):
        """Delete one entity and its projected record.

        Args:
            entity: Entity id to delete.
            request_id: Client envelope id for idempotent replay;
                a fresh id when omitted.
            expected_revision: Revision the writer read; the live
                head when omitted.

        Returns:
            Mutation mapping with entity, storage path, revision
            transition, new head, actor, diff summary, rewind
            handle, the entity_deleted event, cursor, and request
            id.

        Raises:
            EcsError: request_conflict for a reused id with new
                text; invalid_entity for a malformed id;
                unknown_entity for a missing entity;
                backfill_readonly for a backfilled id;
                invalid_document for a corrupt entity record;
                revision_conflict for a stale head.
        """
        request_id = request_id or uuid.uuid4().hex
        validate_entity_id(entity)
        identity = _frozen_identity("delete_entity", {"entity": entity})
        replay = self._check_replay(request_id, identity)
        if replay is not None:
            return replay
        path, _decoded = self._read_entity(entity)
        self._gate_revision(self._refresh_expected(expected_revision))
        previous = self._current_revision
        del self._docs[path]
        self._current_revision = _advance_revision(previous)
        diff = f"deleted entity {entity} ({path})"
        record = self._append_event(
            "entity_deleted",
            request_id,
            {"entity": entity, "revision": self._current_revision},
        )
        response = self._mutation_response(
            request_id, previous, diff, record,
            {"entity": entity, "path": path},
        )
        self._requests[request_id] = (identity, response)
        return response

    def components_of(self, entity):
        """List the component names one entity carries.

        Args:
            entity: Entity id to inspect (backfilled ids serve
                their projected ``doc`` component).

        Returns:
            Mapping with project id, head revision, entity,
            storage path, and sorted component names.

        Raises:
            EcsError: invalid_entity for a malformed id;
                unknown_entity for a missing entity;
                invalid_document for a corrupt entity record.
        """
        validate_entity_id(entity)
        if is_backfill_id(entity):
            record = self._resolve_backfill(entity)
            return {
                "components": sorted(record["components"]),
                "current_revision": self._current_revision,
                "entity": entity,
                "path": record["components"][BACKFILL_COMPONENT]["path"],
                "project_id": self._project_id,
            }
        path, decoded = self._read_entity(entity)
        return {
            "components": sorted(decoded["components"]),
            "current_revision": self._current_revision,
            "entity": entity,
            "path": path,
            "project_id": self._project_id,
        }

    def entities_with(self, component, predicate=None):
        """Filter entities to holders of one component.

        Nets-of-block, pins-of-net, and open-problems become
        filters here, not endpoints; backfilled docs answer the
        ``doc`` component, so current project files stay
        filterable without migration.

        Args:
            component: Component name holders must carry.
            predicate: Exact-match mapping the component payload
                must satisfy, or None for no filtering.

        Returns:
            Mapping with project id, head revision, component,
            predicate, and sorted holder ids.

        Raises:
            EcsError: invalid_component for a malformed component
                name; invalid_predicate for a non-mapping
                predicate; invalid_document for a corrupt entity
                record.
        """
        validate_component_name(component)
        validate_predicate(predicate)
        records = self._entity_records()
        if component == BACKFILL_COMPONENT:
            records.extend(self._backfill_records())
        return {
            "component": component,
            "current_revision": self._current_revision,
            "entities": filter_entities(records, component, predicate),
            "predicate": predicate,
            "project_id": self._project_id,
        }

    def world_snapshot(self, include_backfill=True):
        """Bundle the miniplex-shaped world snapshot for mirrors.

        A pure read: snapshotting never writes and never advances
        the revision, so backfill cannot break any revision.

        Args:
            include_backfill: Project current plain docs as
                read-only virtual entities alongside engine
                entities; engine entities only when False.

        Returns:
            Snapshot mapping with project id, head revision, and
            entities sorted by id (each with id, kind, and
            components).

        Raises:
            EcsError: invalid_document for a corrupt entity
                record.
        """
        records = self._entity_records()
        if include_backfill:
            records.extend(self._backfill_records())
        return build_world_snapshot(
            self._project_id, self._current_revision, records
        )
