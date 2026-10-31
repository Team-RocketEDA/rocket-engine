"""Durable project ledger (LEDGER-DURABLE/I30) + document CRUD (CRUD-API/I31).

Every engine-mediated mutation advances the revision and appends an
actor-attributed event; stale `expected_revision` fails with
`revision_conflict` instead of merging. With `engine_root` the
ledger persists under `ENGINE_ROOT/projects/<id>/` (`events.yaml`
+ `ledger.yaml`, both schematized in `layout_schema.yaml`) and
survives restart; without it the service keeps the previous
in-memory behavior. Retention trims oldest-first past
`max_retained_events`; readers that demand contiguity from trimmed
history get `resync_required` and must re-read from the snapshot.

Documents (CRUD-API/I31) live beside the ledger: files under the
project dir for durable projects, an in-memory map otherwise.
`ledger.yaml`, `events.yaml`, `runs/`, and `snapshots/` are
engine-owned and rejected as document paths; everything else —
including the conventional `components/` and `scripts/` prefixes —
is a plain document addressed by its unix path. Single
writes/deletes and the atomic `apply_mutations` batch reuse the
same admission machinery as `submit` (idempotent request ids,
revision gate, one new revision, one event, atomic persist).

Snapshots (REWIND) capture every head: each accepted mutation
stores the managed bytes for its previous revision (when missing)
and its new revision under `snapshots/<revision>/` (an in-memory
map without an engine root). `rewind` restores the target bytes
under a new head revision with a `project_rewound` event — history
stays append-only, never rewritten. Linked caller trees stay
untouched: only engine-tracked bytes restore, and files outside
`.rocket/` are reported, never written.
"""

import copy
import hashlib
import io
import os
import re
import shutil
import tempfile
import uuid
from pathlib import Path

from ruamel.yaml import YAML

from ..interfaces import engine_ecs_store
from ..interfaces import settings_store
from ..interfaces import wireplace
from ..interfaces.errors import ContractError
from ..interfaces.paths import join_contained, to_unix
from .errors import ProjectError

DEFAULT_MAX_RETAINED_EVENTS = 10000
_MAX_DOC_BYTES = 1_000_000
_EVENTS_FILENAME = "events.yaml"
_LEDGER_FILENAME = "ledger.yaml"
_SNAPSHOTS_DIRNAME = "snapshots"
_LINKED_CARVEOUT = ".rocket"
_REVISION_RE = re.compile(r"^(.*?)(\d+)$")
_PROJECT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")
_RUN_OUTCOMES = ("run_completed", "run_failed")
_RESERVED_DOCS = frozenset({_LEDGER_FILENAME, _EVENTS_FILENAME})

# Document prefix owning the five design-truth settings files.
_SETTINGS_DOC_PREFIX = "settings/"


def _advance_revision(revision):
    """Next revision: trailing digits increment, else `-2` is suffixed."""
    match = _REVISION_RE.match(revision or "")
    if match is None:
        return f"{revision}-2"
    return f"{match.group(1)}{int(match.group(2)) + 1}"


def _dump_yaml(data):
    buf = io.StringIO()
    YAML(typ="safe").dump(data, buf)
    return buf.getvalue()


def _atomic_write_text(path, text):
    """Write through a sibling temp file, then rename into place."""
    fd, tmp = tempfile.mkstemp(
        dir=str(path.parent), prefix=f"{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _atomic_write_bytes(path, data):
    """Write bytes through a sibling temp file, then rename."""
    fd, tmp = tempfile.mkstemp(
        dir=str(path.parent), prefix=f"{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _canonical_doc_path(path):
    """Canonical unix document path; rejects escapes and addresses.

    Args:
        path: Caller-supplied document path.

    Returns:
        Canonical slash-joined path with dot and empty segments
        dropped.

    Raises:
        ProjectError: invalid_path for a non-text, empty, or
            directory path; path_escape for an absolute path or
            one containing `..`. Every message names the supplied
            path.
    """
    if not isinstance(path, str):
        raise ProjectError(
            "invalid_path", f"Document path must be text, got {path!r}."
        )
    unix = to_unix(path)
    if unix == "" or unix.endswith("/"):
        raise ProjectError(
            "invalid_path", f"Bad document path: {path!r}."
        )
    if unix.startswith("/"):
        raise ProjectError(
            "path_escape", f"Absolute document path: {path!r}."
        )
    parts = [p for p in unix.split("/") if p not in ("", ".")]
    if ".." in parts:
        raise ProjectError(
            "path_escape", f"Document path escapes: {path!r}."
        )
    canonical = "/".join(parts)
    if canonical == "":
        raise ProjectError(
            "invalid_path", f"Bad document path: {path!r}."
        )
    return canonical


def _check_reserved_doc(canonical, original):
    """Reject engine-owned document paths.

    Args:
        canonical: Canonical document path.
        original: Caller-supplied path for error messages.

    Raises:
        ProjectError: invalid_path when the path names the ledger,
            the event log, or anything under `runs/` or
            `snapshots/`.
    """
    if (
        canonical in _RESERVED_DOCS
        or canonical == "runs"
        or canonical.startswith("runs/")
        or canonical == _SNAPSHOTS_DIRNAME
        or canonical.startswith(_SNAPSHOTS_DIRNAME + "/")
    ):
        raise ProjectError(
            "invalid_path",
            f"Engine-owned path is not a document: {original!r}.",
        )


def _canonical_prefix(prefix):
    """Canonical list filter; empty means no filtering.

    Args:
        prefix: Caller-supplied prefix or None.

    Returns:
        Canonical prefix string ("" matches everything).

    Raises:
        ProjectError: invalid_path for a non-text prefix;
            path_escape for an absolute prefix or one
            containing `..`.
    """
    if prefix is None:
        return ""
    if not isinstance(prefix, str):
        raise ProjectError(
            "invalid_path", f"Prefix must be text, got {prefix!r}."
        )
    unix = to_unix(prefix)
    if unix.startswith("/"):
        raise ProjectError(
            "path_escape", f"Absolute prefix: {prefix!r}."
        )
    parts = [p for p in unix.split("/") if p not in ("", ".")]
    if ".." in parts:
        raise ProjectError(
            "path_escape", f"Prefix escapes: {prefix!r}."
        )
    return "/".join(parts)


class _WireEntityStore:
    """WIRE-PLACE seam over the ENGINE-ECS ProjectService verbs.

    The wire ops take a store serving the seam in
    docs/work/WIRE-PLACE/report.md: reads return deep copies and
    raise LookupError for missing entities/components, and
    transact threads aliases through one call list. ENGINE-ECS
    landed as per-verb service methods with admission envelopes
    instead of a bound store, so this adapter binds those verbs
    to the seam: reads delegate with unknown/invalid entity and
    component codes mapped to LookupError, and transact runs its
    calls sequentially with alias resolution, one ledger
    revision per verb.

    Inner envelopes derive deterministically from the outer wire
    request id, so a retried envelope replays the verbs that
    already landed instead of minting duplicates. Sequential, not
    atomic: a mid-transact refusal leaves the earlier verbs
    applied (wire ops pre-validate, so a refusal after the first
    verb implies a concurrent writer, and the outer revision gate
    already serialized this op against those).
    """

    _READS = ("components_of", "get_component", "entities_with")
    _WRITES = (
        "create_entity", "set_component", "attach_component",
        "detach_component", "delete_entity",
    )
    _LOOKUP_CODES = frozenset({
        "unknown_entity", "unknown_component",
        "invalid_entity", "invalid_component",
    })

    def __init__(self, service, request_id):
        self._service = service
        self._request_id = request_id
        self._seq = 0

    def _envelope(self, verb):
        self._seq += 1
        sub_id = f"{self._request_id}:wire-ecs:{self._seq}"
        return sub_id, f"{verb} {sub_id}"

    def _lookup(self, entity, component=None):
        if component is None:
            return LookupError(f"Unknown entity: {entity!r}.")
        return LookupError(
            f"Unknown component {component!r} on {entity!r}."
        )

    def components_of(self, entity):
        """Return a deep copy of one entity's component mapping.

        Args:
            entity: Entity id to inspect.

        Returns:
            Mapping of component name to payload copy.

        Raises:
            LookupError: Unknown or malformed entity id.
        """
        try:
            names = self._service.components_of(entity)["components"]
        except ProjectError as exc:
            if exc.code in self._LOOKUP_CODES:
                raise self._lookup(entity) from None
            raise
        return {
            name: self.get_component(entity, name) for name in names
        }

    def get_component(self, entity, component):
        """Return a deep copy of one component payload.

        Args:
            entity: Entity id holding the component.
            component: Component name to read.

        Returns:
            Deep copy of the component payload.

        Raises:
            LookupError: Unknown or malformed entity id or
                component name.
        """
        try:
            data = self._service.get_component(
                entity, component
            )["data"]
        except ProjectError as exc:
            if exc.code in self._LOOKUP_CODES:
                raise self._lookup(entity, component) from None
            raise
        return copy.deepcopy(data)

    def entities_with(self, component, predicate=None):
        """List holder ids in id order, filtered by a callable.

        Args:
            component: Component name holders must carry.
            predicate: Callable over the payload copy, or None
                for no filtering.

        Returns:
            Sorted holder entity ids.
        """
        found = []
        for entity in self._service.entities_with(
            component
        )["entities"]:
            if predicate is None:
                found.append(entity)
            elif predicate(self.get_component(entity, component)):
                found.append(entity)
        return found

    def create_entity(self, actor, description):
        """Mint one entity; return its id and the new head.

        Args:
            actor: Attribution (the service actor applies).
            description: Human note (carried on inner envelopes).

        Returns:
            Mapping with the minted id and the new head revision.
        """
        del actor, description
        request_id, command_text = self._envelope("create_entity")
        response = self._service.create_entity(
            request_id, command_text,
            expected_revision=self._service._current_revision,
        )
        return {
            "id": response["entity"],
            "revision": response["current_revision"],
        }

    def set_component(self, actor, entity, component, value,
                      description):
        """Overwrite one component; refuse a missing target.

        Args:
            actor: Attribution (the service actor applies).
            entity: Entity id holding the component.
            component: Component name to overwrite.
            value: JSON payload to store.
            description: Human note (carried on inner envelopes).

        Returns:
            Mapping with the new head revision.

        Raises:
            ProjectError: unknown_entity or unknown_component
                for a missing target.
        """
        del actor, description
        try:
            names = self._service.components_of(entity)["components"]
        except ProjectError as exc:
            if exc.code in self._LOOKUP_CODES:
                raise ProjectError(
                    "unknown_entity",
                    f"Unknown entity: {entity!r}.",
                ) from None
            raise
        if component not in names:
            raise ProjectError(
                "unknown_component",
                f"Unknown component {component!r} on {entity!r}.",
            )
        request_id, command_text = self._envelope("set_component")
        response = self._service.set_component(
            entity, component, value, request_id, command_text,
            expected_revision=self._service._current_revision,
        )
        return {"revision": response["current_revision"]}

    def attach_component(self, actor, entity, component, value,
                         description):
        """Attach one new component to its entity.

        Args:
            actor: Attribution (the service actor applies).
            entity: Entity id gaining the component.
            component: Component name to attach.
            value: JSON payload to store.
            description: Human note (carried on inner envelopes).

        Returns:
            Mapping with the new head revision.

        Raises:
            ProjectError: component_exists for a duplicate;
                unknown_entity for a missing entity.
        """
        del actor, description
        request_id, command_text = self._envelope(
            "attach_component"
        )
        response = self._service.attach_component(
            entity, component, value, request_id, command_text,
            expected_revision=self._service._current_revision,
        )
        return {"revision": response["current_revision"]}

    def detach_component(self, actor, entity, component, description):
        """Detach one component from its entity.

        Args:
            actor: Attribution (the service actor applies).
            entity: Entity id losing the component.
            component: Component name to detach.
            description: Human note (carried on inner envelopes).

        Returns:
            Mapping with the new head revision.

        Raises:
            ProjectError: unknown_entity or unknown_component
                for a missing target.
        """
        del actor, description
        request_id, command_text = self._envelope(
            "detach_component"
        )
        response = self._service.detach_component(
            entity, component, request_id, command_text,
            expected_revision=self._service._current_revision,
        )
        return {"revision": response["current_revision"]}

    def delete_entity(self, actor, entity, description):
        """Delete one entity and its projected record.

        Args:
            actor: Attribution (the service actor applies).
            entity: Entity id to delete.
            description: Human note (carried on inner envelopes).

        Returns:
            Mapping with the new head revision.

        Raises:
            ProjectError: unknown_entity for a missing entity.
        """
        del actor, description
        request_id, command_text = self._envelope("delete_entity")
        response = self._service.delete_entity(
            entity, request_id, command_text,
            expected_revision=self._service._current_revision,
        )
        return {"revision": response["current_revision"]}

    def _resolve(self, node, aliases):
        if isinstance(node, dict) and set(node) == {"alias"}:
            try:
                return aliases[node["alias"]]
            except KeyError:
                raise ProjectError(
                    "invalid_command",
                    f"Unknown transact alias: {node['alias']!r}.",
                ) from None
        if isinstance(node, dict):
            return {
                key: self._resolve(val, aliases)
                for key, val in node.items()
            }
        if isinstance(node, list):
            return [self._resolve(val, aliases) for val in node]
        return node

    def transact(self, actor, description, calls):
        """Run calls sequentially with alias threading.

        Each call is {"verb", "args"?, "alias"?}; {"alias": name}
        values resolve at any depth to ids created earlier in the
        same call list.

        Args:
            actor: Attribution stamped on the seam events.
            description: Human note for the call list.
            calls: Verb calls with optional args and aliases.

        Returns:
            Mapping with the new head, the alias map, and the
            stamped seam events.

        Raises:
            ProjectError: invalid_command for an unknown verb,
                alias, or missing arg; the ECS refusal code
                (unknown_entity, component_exists, ...) for a
                refused verb.
        """
        aliases = {}
        events = []
        for call in calls:
            verb = call["verb"]
            try:
                args = self._resolve(
                    dict(call.get("args", {})), aliases
                )
            except KeyError as exc:
                raise ProjectError(
                    "invalid_command",
                    f"Malformed transact call: {call!r}.",
                ) from exc
            need = {
                "create_entity": (),
                "set_component": ("entity", "component", "value"),
                "attach_component": ("entity", "component", "value"),
                "detach_component": ("entity", "component"),
                "delete_entity": ("entity",),
            }
            if verb not in need:
                raise ProjectError(
                    "invalid_command",
                    f"Unknown transact verb: {verb!r}.",
                )
            missing = [k for k in need[verb] if k not in args]
            if missing:
                raise ProjectError(
                    "invalid_command",
                    f"transact {verb} misses {missing!r}.",
                )
            if verb == "create_entity":
                made = self.create_entity(actor, description)
                events.append({
                    "event": "entity_created",
                    "entity": made["id"],
                })
                if "alias" in call:
                    aliases[call["alias"]] = made["id"]
            elif verb in ("set_component", "attach_component"):
                method = getattr(self, verb)
                method(
                    actor, args["entity"], args["component"],
                    args["value"], description,
                )
                events.append({
                    "event": "component_changed",
                    "entity": args["entity"],
                    "component": args["component"],
                })
            elif verb == "detach_component":
                self.detach_component(
                    actor, args["entity"], args["component"],
                    description,
                )
                events.append({
                    "event": "component_changed",
                    "entity": args["entity"],
                    "component": args["component"],
                })
            else:
                self.delete_entity(
                    actor, args["entity"], description
                )
                events.append({
                    "event": "entity_deleted",
                    "entity": args["entity"],
                })
        revision = self._service._current_revision
        for event in events:
            event["revision"] = revision
            event["actor"] = actor
        return {
            "revision": revision,
            "aliases": aliases,
            "events": events,
        }

    def events_since(self, cursor):
        """List entity events past a ledger sequence cursor.

        Args:
            cursor: Ledger sequence; only later events return.

        Returns:
            Seam-shaped entity events in ledger order.
        """
        self._service._refresh_durable()
        found = []
        for record in self._service._events:
            if record["seq"] <= cursor:
                continue
            if record["event"] not in (
                "entity_created", "component_changed",
                "entity_deleted",
            ):
                continue
            data = record.get("data", {})
            event = {
                "event": record["event"],
                "entity": data.get("entity"),
                "revision": data.get("revision"),
                "actor": record.get("actor"),
            }
            if "component" in data:
                event["component"] = data["component"]
            found.append(event)
        return found


class ProjectService:
    """Revision-gated ledger with idempotent requests and cursored events.

    Args:
        project_id: Project this ledger is bound to.
        actor: Attribution recorded on every appended event
            (human / rocket-fuel / system by convention; the engine
            passes its own actor through verbatim).
        current_revision: Starting revision for a fresh ledger (one
            with no durable state yet).
        engine_root: Engine root for durability; the ledger lives at
            `projects/<project_id>/` beneath it (managed or linked
            alike — the ledger is engine truth, never caller-tree
            bytes). None keeps the in-memory behavior.
        max_retained_events: Retention bound; only the newest events
            are kept, trimmed oldest-first on every append.
        linked_root: Caller tree for linked projects; rewind
            reports files outside `.rocket/` and never writes to
            this tree. None means a managed project with no
            external report.

    Caution: A stale expected_revision fails with revision_conflict
        instead of merging — callers must re-read the snapshot and
        retry at the new head. Reads and mutations reload durable
        state first, so sequential writers through separate handles
        stay ordered; truly concurrent writers still need an
        external lock.
    """

    def __init__(self, project_id, actor, current_revision="p12",
                 engine_root=None, max_retained_events=None,
                 linked_root=None):
        if max_retained_events is None:
            max_retained_events = DEFAULT_MAX_RETAINED_EVENTS
        if (
            not isinstance(max_retained_events, int)
            or isinstance(max_retained_events, bool)
            or max_retained_events < 1
        ):
            raise ProjectError(
                "invalid_ledger",
                f"Bad max_retained_events: {max_retained_events!r}.",
            )
        self._project_id = project_id
        self._actor = actor
        self._current_revision = current_revision
        self._max_retained_events = max_retained_events
        self._requests = {}
        self._events = []
        self._docs = {}
        self._snapshots = {}
        self._yaml = YAML(typ="safe")
        self._dir = None
        self._linked_root = (
            Path(linked_root) if linked_root is not None else None
        )
        if engine_root is not None:
            if not isinstance(project_id, str) or not _PROJECT_ID_RE.match(
                project_id
            ):
                raise ProjectError(
                    "invalid_project", f"Bad project id: {project_id!r}."
                )
            self._dir = join_contained(engine_root, "projects", project_id)
            self._load()

    def _cursor(self):
        return self._events[-1]["seq"] if self._events else 0

    def _retained_head(self):
        return self._events[0]["seq"] if self._events else 0

    def _trim(self):
        over = len(self._events) - self._max_retained_events
        if over > 0:
            del self._events[:over]

    def _append_event(self, event, request_id, data):
        record = {
            "seq": self._cursor() + 1,
            "event": event,
            "request_id": request_id,
            "project_id": self._project_id,
            "actor": self._actor,
            "data": data,
        }
        self._events.append(record)
        self._trim()
        return record

    def _read_ledger_file(self, path):
        """Parse one durable file; missing reads as None, corrupt refuses."""
        try:
            text = Path(path).read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise ProjectError(
                "invalid_ledger", f"Cannot read ledger file {path}: {exc}."
            ) from exc
        try:
            data = self._yaml.load(text)
        except Exception as exc:
            raise ProjectError(
                "invalid_ledger",
                f"Cannot parse ledger file {path}: {exc}.",
            ) from exc
        if data is None:
            raise ProjectError(
                "invalid_ledger", f"Ledger file is empty: {path}."
            )
        return data

    def _load(self):
        """Refresh head + log from durable files (absent files read empty)."""
        ledger = self._read_ledger_file(self._dir / _LEDGER_FILENAME)
        if ledger is not None:
            if not isinstance(ledger, dict):
                raise ProjectError(
                    "invalid_ledger",
                    f"Ledger head must be a mapping: {self._dir}.",
                )
            revision = ledger.get("current_revision")
            requests = ledger.get("requests")
            if not isinstance(revision, str) or not revision:
                raise ProjectError(
                    "invalid_ledger",
                    f"Ledger head carries no revision: {self._dir}.",
                )
            if not isinstance(requests, dict):
                raise ProjectError(
                    "invalid_ledger",
                    f"Ledger head carries no request map: {self._dir}.",
                )
            for request_id, entry in requests.items():
                if (
                    not isinstance(entry, dict)
                    or not isinstance(entry.get("command_text"), str)
                    or not isinstance(entry.get("ack"), dict)
                ):
                    raise ProjectError(
                        "invalid_ledger",
                        f"Ledger request is malformed: {request_id}.",
                    )
            owner = ledger.get("project_id")
            if owner is not None and owner != self._project_id:
                raise ProjectError(
                    "invalid_ledger",
                    f"Ledger belongs to {owner}, not {self._project_id}.",
                )
            self._current_revision = revision
            self._requests = {
                request_id: (entry["command_text"], entry["ack"])
                for request_id, entry in requests.items()
            }
        events = self._read_ledger_file(self._dir / _EVENTS_FILENAME)
        if events is not None:
            if not isinstance(events, list):
                raise ProjectError(
                    "invalid_ledger",
                    f"Event log must be a sequence: {self._dir}.",
                )
            for entry in events:
                if (
                    not isinstance(entry, dict)
                    or not isinstance(entry.get("seq"), int)
                    or isinstance(entry.get("seq"), bool)
                    or not isinstance(entry.get("event"), str)
                ):
                    raise ProjectError(
                        "invalid_ledger",
                        f"Event record is malformed in {self._dir}.",
                    )
            self._events = events
            self._trim()

    def _persist(self):
        """Rewrite both durable files; events first, then the head."""
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            (self._dir / "runs").mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ProjectError(
                "invalid_ledger",
                f"Cannot create ledger dir {self._dir}: {exc}.",
            ) from exc
        try:
            _atomic_write_text(
                self._dir / _EVENTS_FILENAME, _dump_yaml(self._events)
            )
            _atomic_write_text(
                self._dir / _LEDGER_FILENAME,
                _dump_yaml(
                    {
                        "project_id": self._project_id,
                        "current_revision": self._current_revision,
                        "requests": {
                            request_id: {
                                "command_text": command_text,
                                "ack": ack,
                            }
                            for request_id, (command_text, ack)
                            in self._requests.items()
                        },
                    }
                ),
            )
        except OSError as exc:
            raise ProjectError(
                "invalid_ledger",
                f"Cannot persist ledger under {self._dir}: {exc}.",
            ) from exc

    def _refresh_durable(self):
        if self._dir is not None:
            self._load()

    def _persist_after_mutation(self):
        if self._dir is not None:
            self._persist()

    def _snapshot_exists(self, revision):
        """True when a restorable snapshot exists for a revision."""
        if self._dir is None:
            return revision in self._snapshots
        try:
            path = join_contained(
                self._dir, _SNAPSHOTS_DIRNAME, revision
            )
        except Exception:
            return False
        return path.is_dir()

    def _capture_snapshot(self, revision):
        """Store the current managed bytes under one revision id.

        Overwrites any previous capture for that id; empty trees
        leave an empty marker dir so the revision stays restorable.
        The copy lands in a sibling temp dir and renames into
        place, so a crash never leaves a partial snapshot behind.
        """
        if self._dir is None:
            self._snapshots[revision] = dict(self._docs)
            return
        try:
            dest = join_contained(
                self._dir, _SNAPSHOTS_DIRNAME, revision
            )
        except Exception as exc:
            raise ProjectError(
                "invalid_ledger",
                f"Cannot snapshot revision {revision}: {exc}.",
            ) from exc
        base = self._dir / _SNAPSHOTS_DIRNAME
        try:
            base.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ProjectError(
                "invalid_ledger",
                f"Cannot snapshot revision {revision}: {exc}.",
            ) from exc
        for stale in base.glob(".cap.*"):
            try:
                if stale.is_symlink() or stale.is_file():
                    stale.unlink()
                elif stale.is_dir():
                    shutil.rmtree(stale)
            except OSError:
                pass
        tmp = base / f".cap.{uuid.uuid4().hex}.tmp"
        try:
            tmp.mkdir(parents=True, exist_ok=False)
        except OSError as exc:
            raise ProjectError(
                "invalid_ledger",
                f"Cannot snapshot revision {revision}: {exc}.",
            ) from exc
        try:
            for rel, _size in self._iter_doc_files():
                try:
                    data = self._doc_path(rel).read_bytes()
                except OSError as exc:
                    raise ProjectError(
                        "invalid_ledger",
                        f"Cannot snapshot {rel}: {exc}.",
                    ) from exc
                target = tmp / rel
                try:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    _atomic_write_bytes(target, data)
                except OSError as exc:
                    raise ProjectError(
                        "invalid_ledger",
                        f"Cannot snapshot {rel}: {exc}.",
                    ) from exc
            if dest.is_symlink() or dest.is_file():
                dest.unlink()
            elif dest.is_dir():
                shutil.rmtree(dest)
            dest.parent.mkdir(parents=True, exist_ok=True)
            os.replace(tmp, dest)
        except ProjectError:
            try:
                shutil.rmtree(tmp, ignore_errors=True)
            except OSError:
                pass
            raise
        except OSError as exc:
            try:
                shutil.rmtree(tmp, ignore_errors=True)
            except OSError:
                pass
            raise ProjectError(
                "invalid_ledger",
                f"Cannot snapshot revision {revision}: {exc}.",
            ) from exc

    def _ensure_snapshot(self, revision):
        if not self._snapshot_exists(revision):
            self._capture_snapshot(revision)

    def _load_snapshot(self, revision):
        """Current snapshot bytes, or None when unrestorable."""
        if self._dir is None:
            snap = self._snapshots.get(revision)
            return dict(snap) if snap is not None else None
        try:
            src_dir = join_contained(
                self._dir, _SNAPSHOTS_DIRNAME, revision
            )
        except Exception:
            return None
        if not src_dir.is_dir():
            return None
        found = {}
        for target in sorted(src_dir.rglob("*")):
            if not target.is_file():
                continue
            try:
                rel = target.relative_to(src_dir).as_posix()
            except ValueError:
                continue
            try:
                found[rel] = target.read_bytes()
            except OSError as exc:
                raise ProjectError(
                    "invalid_ledger",
                    f"Cannot read snapshot {revision}/{rel}: {exc}.",
                ) from exc
        return found

    def _current_bytes(self):
        """All managed bytes for rollback staging."""
        found = {}
        for rel, _size in self._iter_doc_files():
            try:
                found[rel] = self._doc_path(rel).read_bytes()
            except OSError as exc:
                raise ProjectError(
                    "invalid_ledger",
                    f"Cannot stage {rel}: {exc}.",
                ) from exc
        return found

    def _clear_docs(self):
        """Delete every managed file, then prune emptied doc dirs."""
        for rel, _size in self._iter_doc_files():
            target = self._doc_path(rel)
            try:
                target.unlink()
            except FileNotFoundError:
                pass
            except OSError as exc:
                raise ProjectError(
                    "invalid_ledger",
                    f"Cannot clear {rel}: {exc}.",
                ) from exc
        for target in sorted(self._dir.rglob("*"), reverse=True):
            if not target.is_dir() or target == self._dir:
                continue
            try:
                rel = target.relative_to(self._dir).as_posix()
            except ValueError:
                continue
            if rel == "runs" or rel.startswith("runs/"):
                continue
            if rel == _SNAPSHOTS_DIRNAME or rel.startswith(
                _SNAPSHOTS_DIRNAME + "/"
            ):
                continue
            try:
                target.rmdir()
            except OSError:
                pass

    def _write_bytes_map(self, mapping):
        for rel, data in mapping.items():
            target = self._doc_path(rel)
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                _atomic_write_bytes(target, data)
            except OSError as exc:
                raise ProjectError(
                    "invalid_ledger",
                    f"Cannot restore {rel}: {exc}.",
                ) from exc

    def _restore_snapshot_bytes(self, snapshot, pre):
        """Replace managed bytes; best-effort rollback to pre."""
        try:
            self._clear_docs()
            self._write_bytes_map(snapshot)
        except ProjectError:
            try:
                self._clear_docs()
                self._write_bytes_map(pre)
            except Exception:
                pass
            raise

    def _linked_external_files(self):
        """Caller files outside `.rocket/`, sorted, never touched."""
        if self._linked_root is None:
            return []
        root = self._linked_root
        try:
            if not root.is_dir():
                return []
        except OSError:
            return []
        found = []
        try:
            targets = sorted(root.rglob("*"))
        except OSError:
            return []
        for target in targets:
            try:
                if not target.is_file():
                    continue
                rel = target.relative_to(root).as_posix()
            except (OSError, ValueError):
                continue
            if rel == _LINKED_CARVEOUT or rel.startswith(
                _LINKED_CARVEOUT + "/"
            ):
                continue
            try:
                size = target.stat().st_size
            except OSError:
                continue
            found.append({"path": rel, "bytes": size})
        return sorted(found, key=lambda e: e["path"])

    def submit(self, command_text, request_id, expected_revision=None):
        """Admit one mutation: replay idempotent resubmits, else gate and log.

        A resubmitted envelope returns its stored ack without
        advancing; a new envelope gates its expected_revision, and
        only an accepted mutation advances the revision and appends
        the job_queued event.

        Args:
            command_text: YAML command mapping with an operation.
            request_id: Client envelope id; resubmitting the identical
                text returns the identical ack without advancing.
            expected_revision: Revision the writer read; defaults to
                the command's own expected_revision entry.

        Returns:
            Admission ack with run_id, snapshot_id, state queued,
            the advanced current_revision, and the event cursor.

        Raises:
            ProjectError: invalid_yaml for an unparsable command,
                revision_conflict for a stale expected_revision,
                request_conflict for a reused id with new text.

        Caution: Every accepted mutation advances the revision — a
            second writer at the old head fails instead of merging.
        """
        try:
            command = self._yaml.load(command_text)
        except Exception as exc:
            raise ProjectError("invalid_yaml", f"Cannot parse command: {exc}") from exc
        if not isinstance(command, dict) or "operation" not in command:
            raise ProjectError("invalid_yaml", "Command must be a mapping with an operation.")
        self._refresh_durable()
        prev = self._requests.get(request_id)
        if prev is not None:
            prev_text, prev_ack = prev
            if prev_text != command_text:
                raise ProjectError(
                    "request_conflict",
                    f"Request id reused with different input: {request_id}.",
                )
            return prev_ack
        want = expected_revision if expected_revision is not None else command.get("expected_revision")
        if want != self._current_revision:
            raise ProjectError(
                "revision_conflict",
                f"Expected revision {self._current_revision}, got {want}.",
            )
        self._ensure_snapshot(want)
        advanced = _advance_revision(want)
        self._capture_snapshot(advanced)
        digest = hashlib.sha1(
            f"{self._project_id}:{want}:{command_text}".encode("utf-8")
        ).hexdigest()[:12]
        self._current_revision = advanced
        ack = {
            "request_id": request_id,
            "project_id": self._project_id,
            "run_id": uuid.uuid4().hex,
            "snapshot_id": f"snapshot_{digest}",
            "state": "queued",
            "current_revision": self._current_revision,
        }
        self._requests[request_id] = (command_text, ack)
        self._append_event(
            "job_queued",
            request_id,
            {
                "run_id": ack["run_id"],
                "revision": self._current_revision,
                "operation": command.get("operation"),
            },
        )
        ack["event_cursor"] = self._cursor()
        self._persist_after_mutation()
        return ack

    def append_run_event(self, outcome, run_id, operation, verdict,
                         request_id=None):
        """Append a run completion event with its verdict link.

        Args:
            outcome: run_completed for a judged run (PASS or FAIL),
                run_failed when no verdict exists (NOT_RUN).
            run_id: Run the verdict belongs to; findings read back
                through it.
            operation: Operation that ran.
            verdict: Full verdict mapping stored on the event.
            request_id: Queued request this run discharges, if any
                (run_job); direct runs carry None.

        Returns:
            The appended event record with its seq.

        Raises:
            ProjectError: invalid_command for an unknown outcome.

        Caution: Appends to the ordered log (and the cursor) but
            never advances the project revision — running judges,
            only submitting mutates.
        """
        if outcome not in _RUN_OUTCOMES:
            raise ProjectError(
                "invalid_command", f"Unknown run outcome: {outcome}."
            )
        self._refresh_durable()
        record = self._append_event(
            outcome,
            request_id,
            {"run_id": run_id, "operation": operation, "verdict": verdict},
        )
        self._persist_after_mutation()
        return record

    def command_for(self, request_id):
        """Return the admitted (command, ack) for a queued request.

        Phase 2 of submit-then-run: unknown ids raise
        `unknown_request` instead of running a stranger's job.

        Args:
            request_id: Envelope id admitted by an earlier submit.

        Returns:
            (command, ack) pair stored at admission time.

        Raises:
            ProjectError: unknown_request for an id never admitted.
        """
        self._refresh_durable()
        try:
            command_text, ack = self._requests[str(request_id)]
        except KeyError:
            raise ProjectError(
                "unknown_request", f"No queued request: {request_id}."
            ) from None
        return self._yaml.load(command_text), ack

    def snapshot(self):
        """Read the ledger head: project, revision, and event cursor.

        Returns:
            Snapshot mapping with project_id, current_revision, and
            event_cursor.
        """
        self._refresh_durable()
        return {
            "project_id": self._project_id,
            "current_revision": self._current_revision,
            "event_cursor": self._cursor(),
        }

    def events_since(self, cursor, require_contiguous_from=None):
        """Read retained events after a cursor, oldest first.

        Args:
            cursor: Only events with a higher seq are returned.
            require_contiguous_from: Assert the reader holds
                contiguous history from this seq; fails when the
                history aged out of retention or runs ahead of the
                live cursor.

        Returns:
            Retained events after the cursor, seq-ordered.

        Raises:
            ProjectError: resync_required when the contiguity demand
                cannot be met — the reader must re-read the snapshot
                plus the full retained log and reset its cursor.

        Caution: The log is retention-bounded, not infinite — a
            reader gone longer than the bound must resync, never
            assume the gap is empty.
        """
        self._refresh_durable()
        if (
            require_contiguous_from is not None
            and require_contiguous_from > self._cursor()
        ):
            raise ProjectError(
                "resync_required", "Retained history is insufficient; resync."
            )
        if (
            require_contiguous_from is not None
            and require_contiguous_from >= 1
            and self._events
            and require_contiguous_from < self._retained_head()
        ):
            raise ProjectError(
                "resync_required", "Retained history is insufficient; resync."
            )
        return [e for e in self._events if e["seq"] > cursor]

    def _check_replay(self, request_id, command_text):
        """Return the stored response for an idempotent replay, if any.

        Args:
            request_id: Client envelope id.
            command_text: YAML command text for identity comparison.

        Returns:
            Stored response when the id was seen with identical
            text, else None.

        Raises:
            ProjectError: request_conflict for a reused id with
                new text.
        """
        prev = self._requests.get(request_id)
        if prev is None:
            return None
        prev_text, prev_ack = prev
        if prev_text != command_text:
            raise ProjectError(
                "request_conflict",
                f"Request id reused with different input: {request_id}.",
            )
        return prev_ack

    def _gate_revision(self, expected_revision):
        """Fail stale writers before any effect lands.

        Args:
            expected_revision: Revision the writer read.

        Raises:
            ProjectError: revision_conflict for a stale head.
        """
        if expected_revision != self._current_revision:
            raise ProjectError(
                "revision_conflict",
                f"Expected revision {self._current_revision}, "
                f"got {expected_revision}.",
            )

    def _doc_path(self, canonical):
        """Resolve one canonical path under the project dir.

        Args:
            canonical: Canonical document path.

        Returns:
            Resolved absolute path inside the project dir.

        Raises:
            ProjectError: path_escape when containment fails.
        """
        try:
            return join_contained(self._dir, canonical)
        except Exception as exc:
            code = getattr(exc, "code", None) or "path_escape"
            raise ProjectError(code, str(exc)) from exc

    def _read_doc_text(self, canonical, original):
        """Read one document as text, or None when missing.

        Args:
            canonical: Canonical document path.
            original: Caller-supplied path for error messages.

        Returns:
            Document text, or None when the document is absent.

        Raises:
            ProjectError: invalid_command when the path names a
                directory; invalid_document when durable bytes are
                not UTF-8 text.
        """
        if self._dir is None:
            return self._docs.get(canonical)
        target = self._doc_path(canonical)
        if not target.exists():
            return None
        if target.is_dir():
            raise ProjectError(
                "invalid_command",
                f"Document path is a directory: {original!r}.",
            )
        try:
            return target.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ProjectError(
                "invalid_document",
                f"Document is not UTF-8 text: {original!r} ({exc}).",
            ) from exc
        except OSError as exc:
            raise ProjectError(
                "invalid_ledger",
                f"Cannot read document {original!r}: {exc}.",
            ) from exc

    def _write_doc_text(self, canonical, content, original):
        """Write one document (parents created, atomic rename).

        Args:
            canonical: Canonical document path.
            content: UTF-8 text to store.
            original: Caller-supplied path for error messages.

        Raises:
            ProjectError: invalid_command when the path names a
                directory; invalid_ledger when the durable write
                fails.
        """
        if self._dir is None:
            self._docs[canonical] = content
            return
        target = self._doc_path(canonical)
        if target.is_dir():
            raise ProjectError(
                "invalid_command",
                f"Document path is a directory: {original!r}.",
            )
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ProjectError(
                "invalid_ledger",
                f"Cannot create document dir for {original!r}: {exc}.",
            ) from exc
        try:
            _atomic_write_text(target, content)
        except OSError as exc:
            raise ProjectError(
                "invalid_ledger",
                f"Cannot write document {original!r}: {exc}.",
            ) from exc

    def _delete_doc_path(self, canonical, original):
        """Delete one existing document file.

        Args:
            canonical: Canonical document path.
            original: Caller-supplied path for error messages.

        Raises:
            ProjectError: invalid_command when the path names a
                directory; invalid_ledger when the delete fails.
        """
        if self._dir is None:
            self._docs.pop(canonical, None)
            return
        target = self._doc_path(canonical)
        if target.is_dir():
            raise ProjectError(
                "invalid_command",
                f"Document path is a directory: {original!r}.",
            )
        try:
            target.unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise ProjectError(
                "invalid_ledger",
                f"Cannot delete document {original!r}: {exc}.",
            ) from exc

    def _iter_doc_files(self):
        """Yield (canonical path, byte size) for every document.

        Returns:
            Sorted (path, bytes) pairs, engine-owned entries
            excluded.
        """
        if self._dir is None:
            return sorted(
                (path, len(text.encode("utf-8")))
                for path, text in self._docs.items()
            )
        if not self._dir.is_dir():
            return []
        found = []
        for target in sorted(self._dir.rglob("*")):
            if not target.is_file():
                continue
            try:
                rel = target.relative_to(self._dir).as_posix()
            except ValueError:
                continue
            if (
                rel in _RESERVED_DOCS
                or rel.startswith("runs/")
                or rel.startswith(_SNAPSHOTS_DIRNAME + "/")
            ):
                continue
            try:
                size = target.stat().st_size
            except OSError:
                continue
            found.append((rel, size))
        return sorted(found)

    def _entity_records(self):
        """Decode every entity record into world-snapshot entries."""
        records = []
        for rel, _size in self._iter_doc_files():
            entity = engine_ecs_store.entity_from_doc_path(rel)
            if entity is None:
                continue
            text = self._read_doc_text(rel, rel)
            if text is None:
                raise ProjectError(
                    "invalid_document",
                    f"Entity record vanished mid-read: {rel}.",
                )
            try:
                decoded = engine_ecs_store.decode_entity_doc(text, rel)
            except engine_ecs_store.EcsError as exc:
                raise ProjectError(exc.code, str(exc)) from exc
            records.append(
                {
                    "components": decoded["components"],
                    "id": decoded["entity"],
                    "kind": decoded["kind"],
                }
            )
        return records

    def _backfill_records(self):
        """Project every non-entity doc as a virtual entity."""
        entries = [
            {"bytes": size, "path": rel}
            for rel, size in self._iter_doc_files()
        ]
        return engine_ecs_store.backfill_entities(entries)

    def _find_backfill(self, entity):
        """Return the virtual record for one backfilled id."""
        for record in self._backfill_records():
            if record["id"] == entity:
                return record
        raise ProjectError("unknown_entity", f"No such entity: {entity}.")

    def _read_backfill_component(self, entity, component):
        """Serve one projected doc component for a backfilled id."""
        record = self._find_backfill(entity)
        if component != engine_ecs_store.BACKFILL_COMPONENT:
            raise ProjectError(
                "unknown_component",
                f"No component {component!r} on {entity}.",
            )
        data = record["components"][engine_ecs_store.BACKFILL_COMPONENT]
        return {
            "address": engine_ecs_store.format_address(entity, component),
            "component": component,
            "current_revision": self._current_revision,
            "data": dict(data),
            "entity": entity,
            "path": data["path"],
            "project_id": self._project_id,
        }

    def _read_entity_record(self, entity):
        """Return (path, decoded) for one live entity id."""
        path = engine_ecs_store.entity_doc_path(entity)
        text = self._read_doc_text(path, path)
        if text is None:
            raise ProjectError(
                "unknown_entity", f"No such entity: {entity}."
            )
        try:
            decoded = engine_ecs_store.decode_entity_doc(text, path)
        except engine_ecs_store.EcsError as exc:
            raise ProjectError(exc.code, str(exc)) from exc
        if decoded["entity"] != entity:
            raise ProjectError(
                "invalid_document",
                f"Entity record id drift at {path}.",
            )
        return path, decoded

    def _store_entity_record(self, path, entity, kind, components):
        """Encode and persist one entity record under its path."""
        text = engine_ecs_store.encode_entity_doc(entity, kind, components)
        if len(text.encode("utf-8")) > _MAX_DOC_BYTES:
            raise ProjectError(
                "invalid_command",
                f"Entity record exceeds the size limit: {path}.",
            )
        self._write_doc_text(path, text, path)

    def _ecs_response(self, request_id, previous, diff, record, extra):
        """CRUD-shaped mutation mapping for one entity change."""
        response = {
            "project_id": self._project_id,
            "previous_revision": previous,
            "current_revision": self._current_revision,
            "revision_transition": {
                "from": previous,
                "to": self._current_revision,
            },
            "actor": self._actor,
            "diff_summary": diff,
            "rewind_handle": {
                "project_id": self._project_id,
                "revision": previous,
                "request_id": request_id,
            },
            "events": [record],
            "event_cursor": self._cursor(),
            "request_id": request_id,
        }
        response.update(extra)
        return response

    def list_projects(self):
        """List projects under the engine root, bound always included.

        Without an engine root the bound in-memory project is the
        whole list; with one, every managed project dir plus the
        bound project is reported with its head revision.

        Returns:
            Mapping with the bound project id and the sorted
            project entries (project_id + current_revision).

        Raises:
            ProjectError: invalid_ledger when a sibling ledger
                head is unreadable or corrupt.

        Caution: A corrupt sibling ledger fails the whole list
            loudly instead of being skipped.
        """
        self._refresh_durable()
        if self._dir is None:
            return {
                "project_id": self._project_id,
                "projects": [
                    {
                        "project_id": self._project_id,
                        "current_revision": self._current_revision,
                    }
                ],
            }
        parent = self._dir.parent
        try:
            names = sorted(
                p.name for p in parent.iterdir() if p.is_dir()
            )
        except FileNotFoundError:
            names = []
        seen = {n for n in names if _PROJECT_ID_RE.match(n)}
        seen.add(self._project_id)
        entries = []
        for pid in sorted(seen):
            if pid == self._project_id:
                entries.append(
                    {
                        "project_id": pid,
                        "current_revision": self._current_revision,
                    }
                )
                continue
            ledger_path = parent / pid / _LEDGER_FILENAME
            try:
                text = ledger_path.read_text(encoding="utf-8")
            except FileNotFoundError:
                entries.append(
                    {"project_id": pid, "current_revision": "p12"}
                )
                continue
            except OSError as exc:
                raise ProjectError(
                    "invalid_ledger",
                    f"Cannot read ledger for {pid}: {exc}.",
                ) from exc
            try:
                data = self._yaml.load(text)
            except Exception as exc:
                raise ProjectError(
                    "invalid_ledger",
                    f"Cannot parse ledger for {pid}: {exc}.",
                ) from exc
            revision = (
                data.get("current_revision")
                if isinstance(data, dict)
                else None
            )
            if not isinstance(revision, str) or not revision:
                raise ProjectError(
                    "invalid_ledger",
                    f"Ledger head carries no revision: {pid}.",
                )
            entries.append(
                {"project_id": pid, "current_revision": revision}
            )
        return {"project_id": self._project_id, "projects": entries}

    def create_project(self, new_project_id, request_id, command_text):
        """Create one managed project at revision p12.

        The new ledger starts clean (no events); the response still
        carries the approval-UI fields with a None prior revision.
        Idempotent replays return the stored response instead of
        failing as duplicates.

        Args:
            new_project_id: Slug for the project to create.
            request_id: Client envelope id for idempotent replay.
            command_text: YAML command text for identity comparison.

        Returns:
            Creation mapping with the new project id, p12 head,
            actor, diff summary, revision transition, rewind
            handle, empty events, and request id.

        Raises:
            ProjectError: invalid_command without an engine root;
                invalid_project for a non-slug id; project_exists
                for a duplicate; request_conflict for a reused id
                with new text; invalid_ledger when the project
                dir cannot be written.

        Caution: Creating the bound project itself is a duplicate
            once its dir exists — create-then-list, never assume.
        """
        self._refresh_durable()
        replay = self._check_replay(request_id, command_text)
        if replay is not None:
            return replay
        if self._dir is None:
            raise ProjectError(
                "invalid_command", "create_project needs engine_root."
            )
        if not isinstance(new_project_id, str) or not _PROJECT_ID_RE.match(
            new_project_id
        ):
            raise ProjectError(
                "invalid_project", f"Bad project id: {new_project_id!r}."
            )
        new_dir = self._dir.parent / new_project_id
        if new_dir.exists():
            raise ProjectError(
                "project_exists",
                f"Project already exists: {new_project_id}.",
            )
        try:
            new_dir.mkdir(parents=True, exist_ok=False)
            (new_dir / "runs").mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ProjectError(
                "invalid_ledger",
                f"Cannot create project {new_project_id}: {exc}.",
            ) from exc
        try:
            _atomic_write_text(new_dir / _EVENTS_FILENAME, _dump_yaml([]))
            _atomic_write_text(
                new_dir / _LEDGER_FILENAME,
                _dump_yaml(
                    {
                        "project_id": new_project_id,
                        "current_revision": "p12",
                        "requests": {},
                    }
                ),
            )
        except OSError as exc:
            raise ProjectError(
                "invalid_ledger",
                f"Cannot init project {new_project_id}: {exc}.",
            ) from exc
        response = {
            "project_id": new_project_id,
            "current_revision": "p12",
            "previous_revision": None,
            "revision_transition": {"from": None, "to": "p12"},
            "actor": self._actor,
            "diff_summary": f"created project {new_project_id}",
            "rewind_handle": {
                "project_id": new_project_id,
                "revision": None,
                "request_id": request_id,
            },
            "events": [],
            "event_cursor": 0,
            "request_id": request_id,
        }
        self._requests[request_id] = (command_text, response)
        self._persist_after_mutation()
        return response

    def list_docs(self, prefix=None):
        """List documents, optionally filtered by a path prefix.

        Args:
            prefix: Optional unix path prefix; empty matches
                everything.

        Returns:
            Mapping with project id, head revision, event cursor,
            and sorted document entries (path + bytes).

        Raises:
            ProjectError: invalid_path for a non-text prefix;
                path_escape for an escaping prefix.
        """
        self._refresh_durable()
        want = _canonical_prefix(prefix)
        documents = []
        for path, size in self._iter_doc_files():
            if want and not (
                path == want or path.startswith(want + "/")
            ):
                continue
            documents.append({"path": path, "bytes": size})
        return {
            "project_id": self._project_id,
            "current_revision": self._current_revision,
            "event_cursor": self._cursor(),
            "documents": documents,
        }

    def read_doc(self, path):
        """Read one document as text at the current head.

        Args:
            path: Document path to read.

        Returns:
            Mapping with project id, head revision, canonical
            path, content text, and byte size.

        Raises:
            ProjectError: invalid_path or path_escape for a bad
                path; unknown_document for a missing document;
                invalid_command when the path names a directory;
                invalid_document when durable bytes are not text.
        """
        self._refresh_durable()
        canonical = _canonical_doc_path(path)
        _check_reserved_doc(canonical, path)
        content = self._read_doc_text(canonical, path)
        if content is None:
            raise ProjectError(
                "unknown_document", f"No such document: {path}."
            )
        return {
            "project_id": self._project_id,
            "current_revision": self._current_revision,
            "path": canonical,
            "content": content,
            "bytes": len(content.encode("utf-8")),
        }

    def read_settings(self, kind):
        """Read one settings kind at the current head.

        Absent files read as defaults (absent-default-is-clean):
        a fresh project needs no seeding write. Stored files
        migrate in memory to the known head; future files fail
        instead of serving truth this engine cannot validate.

        Args:
            kind: Settings kind (chip.manifest, design.rules,
                net.classes, text.vars, lib.tables).

        Returns:
            Mapping with project id, head revision, kind, stored
            flag, version, and the settings mapping.

        Raises:
            ProjectError: invalid_command for an unknown kind or
                stored settings that break the kind schema;
                invalid_document for stored settings that do not
                parse; future_format for a file newer than the
                head; missing_migration when no link covers the
                stored version.
        """
        self._refresh_durable()
        if kind not in settings_store.CURRENT_VERSIONS:
            raise ProjectError(
                "invalid_command", f"Unknown settings kind: {kind}."
            )
        canonical = _canonical_doc_path(f"{_SETTINGS_DOC_PREFIX}{kind}.yaml")
        text = self._read_doc_text(canonical, canonical)
        if text is None:
            return {
                "project_id": self._project_id,
                "current_revision": self._current_revision,
                "kind": kind,
                "stored": False,
                "version": settings_store.CURRENT_VERSIONS[kind],
                "settings": settings_store.default_settings(kind),
            }
        try:
            data = self._yaml.load(text)
        except Exception as exc:
            raise ProjectError(
                "invalid_document",
                f"Stored {kind} settings do not parse: {exc}.",
            ) from exc
        if not isinstance(data, dict):
            raise ProjectError(
                "invalid_document",
                f"Stored {kind} settings must be a mapping.",
            )
        try:
            migrated = settings_store.migrate(kind, data)
        except settings_store.SettingsError as exc:
            if exc.code in ("future_format", "missing_migration"):
                raise ProjectError(exc.code, str(exc)) from exc
            raise ProjectError(
                "invalid_command",
                f"Stored {kind} settings are invalid: {exc}.",
            ) from exc
        return {
            "project_id": self._project_id,
            "current_revision": self._current_revision,
            "kind": kind,
            "stored": True,
            "version": migrated["meta"]["version"],
            "settings": migrated,
        }

    def resolved_config(self, session_id=None, run_id=None):
        """Bundle the resolved config for one session/run fetch.

        All five kinds in one call — clients render from this
        snapshot instead of per-event round-trips. Absent files
        resolve to defaults; library refs stay unresolved here
        (callers resolve lib.tables refs against their own roots).

        Args:
            session_id: Client session this snapshot serves.
            run_id: Run this snapshot was resolved for, if any.

        Returns:
            Snapshot mapping with project id, head revision,
            session/run ids, per-kind versions, all five settings
            mappings, and library refs.

        Raises:
            ProjectError: future_format when any stored file is
                newer than the head; missing_migration when no
                link covers a stored version; invalid_document
                for stored settings that do not parse.
        """
        self._refresh_durable()
        settings = {}
        for kind in settings_store.CURRENT_VERSIONS:
            read = self.read_settings(kind)
            settings[read["kind"]] = read["settings"]
        snapshot = settings_store.snapshot_settings(
            settings, session_id=session_id, run_id=run_id
        )
        snapshot["project_id"] = self._project_id
        snapshot["current_revision"] = self._current_revision
        return snapshot

    def get_component(self, entity, component):
        """Read one entity component payload at the current head.

        Entities project over plain documents: the record lives at
        entities/<entity>.json and reads through the same bytes
        read_doc serves. Backfilled doc entities serve their
        projected doc component here, so every world-snapshot
        entry stays addressable.

        Args:
            entity: Entity id holding the component.
            component: Component name to read.

        Returns:
            Mapping with project id, head revision, entity,
            component, canonical address, storage path, and the
            component data.

        Raises:
            ProjectError: invalid_entity or invalid_component for
                malformed parts; unknown_entity for a missing
                entity; unknown_component for a missing component;
                invalid_document for a corrupt entity record.
        """
        self._refresh_durable()
        try:
            engine_ecs_store.validate_entity_id(entity)
            engine_ecs_store.validate_component_name(component)
        except engine_ecs_store.EcsError as exc:
            raise ProjectError(exc.code, str(exc)) from exc
        if engine_ecs_store.is_backfill_id(entity):
            return self._read_backfill_component(entity, component)
        path, decoded = self._read_entity_record(entity)
        if component not in decoded["components"]:
            raise ProjectError(
                "unknown_component",
                f"No component {component!r} on {entity}.",
            )
        return {
            "address": engine_ecs_store.format_address(entity, component),
            "component": component,
            "current_revision": self._current_revision,
            "data": decoded["components"][component],
            "entity": entity,
            "path": path,
            "project_id": self._project_id,
        }

    def components_of(self, entity):
        """List the component names one entity carries.

        Args:
            entity: Entity id to inspect (backfilled ids serve
                their projected doc component).

        Returns:
            Mapping with project id, head revision, entity,
            storage path, and sorted component names.

        Raises:
            ProjectError: invalid_entity for a malformed id;
                unknown_entity for a missing entity;
                invalid_document for a corrupt entity record.
        """
        self._refresh_durable()
        try:
            engine_ecs_store.validate_entity_id(entity)
        except engine_ecs_store.EcsError as exc:
            raise ProjectError(exc.code, str(exc)) from exc
        if engine_ecs_store.is_backfill_id(entity):
            record = self._find_backfill(entity)
            return {
                "components": sorted(record["components"]),
                "current_revision": self._current_revision,
                "entity": entity,
                "path": record["components"][
                    engine_ecs_store.BACKFILL_COMPONENT
                ]["path"],
                "project_id": self._project_id,
            }
        path, decoded = self._read_entity_record(entity)
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
        doc component, so current project files stay filterable
        without migration.

        Args:
            component: Component name holders must carry.
            predicate: Exact-match mapping the component payload
                must satisfy, or None for no filtering.

        Returns:
            Mapping with project id, head revision, component,
            predicate, and sorted holder ids.

        Raises:
            ProjectError: invalid_component for a malformed
                component name; invalid_predicate for a
                non-mapping predicate; invalid_document for a
                corrupt entity record.
        """
        self._refresh_durable()
        try:
            engine_ecs_store.validate_component_name(component)
            engine_ecs_store.validate_predicate(predicate)
        except engine_ecs_store.EcsError as exc:
            raise ProjectError(exc.code, str(exc)) from exc
        records = self._entity_records()
        if component == engine_ecs_store.BACKFILL_COMPONENT:
            records.extend(self._backfill_records())
        holders = engine_ecs_store.filter_entities(
            records, component, predicate
        )
        return {
            "component": component,
            "current_revision": self._current_revision,
            "entities": holders,
            "predicate": predicate,
            "project_id": self._project_id,
        }

    def world_snapshot(self, include_backfill=True):
        """Bundle the miniplex-shaped world snapshot for mirrors.

        A pure read: snapshotting never writes and never advances
        the revision, so backfill cannot break any revision. Each
        entry maps one-to-one onto a miniplex entity (id plus its
        components), so mirrors load it directly.

        Args:
            include_backfill: Project current plain docs as
                read-only virtual entities alongside engine
                entities; engine entities only when False.

        Returns:
            Snapshot mapping with project id, head revision, and
            entities sorted by id (each with id, kind, and
            components).

        Raises:
            ProjectError: invalid_command for a non-bool flag;
                invalid_document for a corrupt entity record.
        """
        self._refresh_durable()
        if not isinstance(include_backfill, bool):
            raise ProjectError(
                "invalid_command",
                "include_backfill must be a bool, "
                f"got {include_backfill!r}.",
            )
        records = self._entity_records()
        if include_backfill:
            records.extend(self._backfill_records())
        return engine_ecs_store.build_world_snapshot(
            self._project_id, self._current_revision, records
        )

    def write_doc(self, path, content, request_id, command_text,
                  expected_revision=None):
        """Write one document: gate, store, advance, log.

        A resubmitted envelope returns its stored response without
        advancing; a new envelope gates its expected_revision, and
        only an accepted write advances the revision and appends
        the doc_written event.

        Args:
            path: Document path to create or overwrite.
            content: UTF-8 text to store (1 MB limit).
            request_id: Client envelope id; resubmitting the
                identical text returns the identical response
                without advancing.
            command_text: YAML command text for identity comparison.
            expected_revision: Revision the writer read.

        Returns:
            Mutation mapping with path, revision transition, new
            head, actor, diff summary, rewind handle, the
            appended event, cursor, and request id.

        Raises:
            ProjectError: request_conflict for a reused id with
                new text; invalid_path or path_escape for a bad
                path; invalid_command for non-text or oversize
                content or a directory path; revision_conflict
                for a stale head; invalid_ledger when the durable
                write fails.

        Caution: Every accepted write advances the revision — a
            second writer at the old head fails instead of
            merging.
        """
        self._refresh_durable()
        replay = self._check_replay(request_id, command_text)
        if replay is not None:
            return replay
        canonical = _canonical_doc_path(path)
        _check_reserved_doc(canonical, path)
        if not isinstance(content, str):
            raise ProjectError(
                "invalid_command",
                f"Write needs text content for document {path}.",
            )
        if len(content.encode("utf-8")) > _MAX_DOC_BYTES:
            raise ProjectError(
                "invalid_command",
                f"Document exceeds the size limit: {path}.",
            )
        self._gate_revision(expected_revision)
        previous = self._current_revision
        self._ensure_snapshot(previous)
        old = self._read_doc_text(canonical, path)
        self._write_doc_text(canonical, content, path)
        advanced = _advance_revision(previous)
        try:
            self._capture_snapshot(advanced)
        except ProjectError:
            try:
                if old is None:
                    self._delete_doc_path(canonical, path)
                else:
                    self._write_doc_text(canonical, old, path)
            except Exception:
                pass
            raise
        self._current_revision = advanced
        new_bytes = len(content.encode("utf-8"))
        if old is None:
            diff = f"created {canonical} ({new_bytes} bytes)"
        else:
            diff = (
                f"updated {canonical} "
                f"({len(old.encode('utf-8'))} -> {new_bytes} bytes)"
            )
        record = self._append_event(
            "doc_written",
            request_id,
            {
                "revision": self._current_revision,
                "operation": "write_doc",
                "path": canonical,
                "bytes": new_bytes,
                "diff_summary": diff,
            },
        )
        response = {
            "project_id": self._project_id,
            "path": canonical,
            "previous_revision": previous,
            "current_revision": self._current_revision,
            "revision_transition": {
                "from": previous,
                "to": self._current_revision,
            },
            "actor": self._actor,
            "diff_summary": diff,
            "rewind_handle": {
                "project_id": self._project_id,
                "revision": previous,
                "request_id": request_id,
            },
            "events": [record],
            "event_cursor": self._cursor(),
            "request_id": request_id,
        }
        self._requests[request_id] = (command_text, response)
        self._persist_after_mutation()
        return response

    def write_settings(self, kind, settings, request_id, command_text,
                       expected_revision=None):
        """Write one settings kind: validate, gate, merge, log.

        Full replacement of the kind's truth, persisted as the
        settings/<kind>.yaml document through the same admission
        machinery as write_doc (idempotent request ids, revision
        gate, one new revision, one event, atomic persist, rewind
        snapshots). The write merges onto the stored bytes so
        unknown keys survive; data maps replace wholesale, so
        text.vars deletes propagate. Unchanged bytes skip the
        write: no new revision, no event.

        A resubmitted envelope returns its stored response without
        advancing.

        Args:
            kind: Settings kind (chip.manifest, design.rules,
                net.classes, text.vars, lib.tables).
            settings: Complete settings mapping at the head
                version.
            request_id: Client envelope id; resubmitting the
                identical text returns the identical response
                without advancing.
            command_text: YAML command text for identity comparison.
            expected_revision: Revision the writer read.

        Returns:
            Mutation mapping with path, revision transition, new
            head, actor, diff summary, rewind handle, the
            appended event, cursor, request id, written flag, and
            settings version.

        Raises:
            ProjectError: request_conflict for a reused id with
                new text; invalid_command for an unknown kind or
                settings that break the kind schema;
                revision_conflict for a stale head; future_format
                when the stored file is newer than the head;
                invalid_document for stored settings that do not
                parse; invalid_ledger when the durable write fails.

        Caution: Every accepted write advances the revision — a
            second writer at the old head fails instead of
            merging — and text.vars writes delete vars the new
            map omits.
        """
        self._refresh_durable()
        replay = self._check_replay(request_id, command_text)
        if replay is not None:
            return replay
        try:
            settings_store.validate_settings(kind, settings)
        except settings_store.SettingsError as exc:
            raise ProjectError(
                "invalid_command", f"Bad {kind} settings: {exc}."
            ) from exc
        self._gate_revision(expected_revision)
        canonical = _canonical_doc_path(f"{_SETTINGS_DOC_PREFIX}{kind}.yaml")
        old_text = self._read_doc_text(canonical, canonical)
        old_data = None
        if old_text is not None:
            try:
                old_data = self._yaml.load(old_text)
            except Exception as exc:
                raise ProjectError(
                    "invalid_document",
                    f"Stored {kind} settings do not parse: {exc}.",
                ) from exc
            if not isinstance(old_data, dict):
                raise ProjectError(
                    "invalid_document",
                    f"Stored {kind} settings must be a mapping.",
                )
            old_version = settings_store.settings_version(kind, old_data)
            if old_version > settings_store.settings_version(kind, settings):
                raise ProjectError(
                    "future_format",
                    f"Stored {kind} settings are newer than this "
                    "engine knows; refusing autosave.",
                )
        merged = settings_store.merge_settings(kind, old_data, settings)
        text = settings_store.dump_settings_text(merged)
        version = settings_store.settings_version(kind, merged)
        if old_text is not None and text == old_text:
            response = {
                "project_id": self._project_id,
                "path": canonical,
                "previous_revision": self._current_revision,
                "current_revision": self._current_revision,
                "revision_transition": {
                    "from": self._current_revision,
                    "to": self._current_revision,
                },
                "actor": self._actor,
                "diff_summary": f"unchanged {canonical}",
                "rewind_handle": {
                    "project_id": self._project_id,
                    "revision": self._current_revision,
                    "request_id": request_id,
                },
                "events": [],
                "event_cursor": self._cursor(),
                "request_id": request_id,
                "written": False,
                "settings_version": version,
            }
            self._requests[request_id] = (command_text, response)
            self._persist_after_mutation()
            return response
        response = self.write_doc(
            canonical, text, request_id, command_text,
            expected_revision=expected_revision,
        )
        response["written"] = True
        response["settings_version"] = version
        return response

    def create_entity(self, request_id, command_text, kind="",
                      components=None, expected_revision=None):
        """Create one entity with an engine-minted id.

        The id is minted, never supplied: there is no id argument,
        so callers cannot collide with, guess, or squat on engine
        identity. The record persists as entities/<id>.json through
        the same admission machinery as write_doc (idempotent
        request ids, revision gate, one new revision, one event,
        atomic persist, rewind snapshots).

        A resubmitted envelope returns its stored response without
        advancing.

        Args:
            request_id: Client envelope id; resubmitting the
                identical text returns the identical response
                without advancing.
            command_text: YAML command text for identity comparison.
            kind: Kind label carried beside the components.
            components: Optional initial component mapping.
            expected_revision: Revision the writer read.

        Returns:
            Mutation mapping with the minted entity, kind, storage
            path, revision transition, new head, actor, diff
            summary, rewind handle, the entity_created event,
            cursor, request id, and initial component names.

        Raises:
            ProjectError: request_conflict for a reused id with
                new text; invalid_kind, invalid_component, or
                invalid_data for malformed parts;
                revision_conflict for a stale head; invalid_ledger
                when the durable write fails.

        Caution: Every accepted create advances the revision — a
            second writer at the old head fails instead of
            merging.
        """
        self._refresh_durable()
        replay = self._check_replay(request_id, command_text)
        if replay is not None:
            return replay
        try:
            engine_ecs_store.validate_kind(kind)
            if components is not None and not isinstance(
                components, dict
            ):
                raise engine_ecs_store.EcsError(
                    "invalid_data",
                    "Initial components must be a mapping.",
                )
            initial = dict(components or {})
            for name, data in initial.items():
                engine_ecs_store.validate_component_name(name)
                engine_ecs_store.validate_component_data(data)
        except engine_ecs_store.EcsError as exc:
            raise ProjectError(exc.code, str(exc)) from exc
        self._gate_revision(expected_revision)
        previous = self._current_revision
        self._ensure_snapshot(previous)
        taken = set()
        for rel, _size in self._iter_doc_files():
            found = engine_ecs_store.entity_from_doc_path(rel)
            if found is not None:
                taken.add(found)
        entity = engine_ecs_store.mint_entity_id(existing=taken)
        path = engine_ecs_store.entity_doc_path(entity)
        self._store_entity_record(path, entity, kind, initial)
        advanced = _advance_revision(previous)
        try:
            self._capture_snapshot(advanced)
        except ProjectError:
            try:
                self._delete_doc_path(path, path)
            except Exception:
                pass
            raise
        self._current_revision = advanced
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
        response = self._ecs_response(
            request_id, previous, diff, record,
            {
                "components": sorted(initial),
                "entity": entity,
                "kind": kind,
                "path": path,
            },
        )
        self._requests[request_id] = (command_text, response)
        self._persist_after_mutation()
        return response

    def set_component(self, entity, component, data, request_id,
                      command_text, expected_revision=None):
        """Upsert one component payload (create or overwrite).

        Persists through the entity record at entities/<entity>.json
        with the same admission machinery as write_doc, and appends
        component_changed with entity, component, and revision.

        A resubmitted envelope returns its stored response without
        advancing.

        Args:
            entity: Entity id holding the component.
            component: Component name to write.
            data: JSON payload to store.
            request_id: Client envelope id; resubmitting the
                identical text returns the identical response
                without advancing.
            command_text: YAML command text for identity comparison.
            expected_revision: Revision the writer read.

        Returns:
            Mutation mapping with entity, component, canonical
            address, storage path, revision transition, new head,
            actor, diff summary, rewind handle, the
            component_changed event, cursor, and request id.

        Raises:
            ProjectError: request_conflict for a reused id with
                new text; invalid_entity, invalid_component, or
                invalid_data for malformed parts; unknown_entity
                for a missing entity; backfill_readonly for a
                backfilled id; invalid_document for a corrupt
                entity record; revision_conflict for a stale head;
                invalid_ledger when the durable write fails.

        Caution: Every accepted write advances the revision — a
            second writer at the old head fails instead of
            merging.
        """
        self._refresh_durable()
        replay = self._check_replay(request_id, command_text)
        if replay is not None:
            return replay
        try:
            engine_ecs_store.validate_entity_id(entity)
            engine_ecs_store.validate_component_name(component)
            engine_ecs_store.validate_component_data(data)
        except engine_ecs_store.EcsError as exc:
            raise ProjectError(exc.code, str(exc)) from exc
        if engine_ecs_store.is_backfill_id(entity):
            raise ProjectError(
                "backfill_readonly",
                f"Backfilled entity is read-only: {entity}.",
            )
        path, decoded = self._read_entity_record(entity)
        self._gate_revision(expected_revision)
        previous = self._current_revision
        self._ensure_snapshot(previous)
        existed = component in decoded["components"]
        merged = dict(decoded["components"])
        merged[component] = data
        old_text = self._read_doc_text(path, path)
        self._store_entity_record(path, entity, decoded["kind"], merged)
        advanced = _advance_revision(previous)
        try:
            self._capture_snapshot(advanced)
        except ProjectError:
            try:
                self._write_doc_text(path, old_text, path)
            except Exception:
                pass
            raise
        self._current_revision = advanced
        verb = "updated" if existed else "set"
        address = engine_ecs_store.format_address(entity, component)
        diff = f"{verb} {address} ({path})"
        record = self._append_event(
            "component_changed",
            request_id,
            engine_ecs_store.component_changed_data(
                entity, component, self._current_revision
            ),
        )
        response = self._ecs_response(
            request_id, previous, diff, record,
            {
                "address": address,
                "component": component,
                "entity": entity,
                "path": path,
            },
        )
        self._requests[request_id] = (command_text, response)
        self._persist_after_mutation()
        return response

    def attach_component(self, entity, component, data, request_id,
                         command_text, expected_revision=None):
        """Attach one new component (refuses overwrites).

        Like set_component, but a component already living on the
        entity fails instead of overwriting — attach means add.

        A resubmitted envelope returns its stored response without
        advancing.

        Args:
            entity: Entity id holding the component.
            component: Component name to attach.
            data: JSON payload to store.
            request_id: Client envelope id; resubmitting the
                identical text returns the identical response
                without advancing.
            command_text: YAML command text for identity comparison.
            expected_revision: Revision the writer read.

        Returns:
            Mutation mapping with entity, component, canonical
            address, storage path, revision transition, new head,
            actor, diff summary, rewind handle, the
            component_changed event, cursor, and request id.

        Raises:
            ProjectError: component_exists when the component
                already lives on the entity; otherwise like
                set_component.

        Caution: Every accepted attach advances the revision — a
            second writer at the old head fails instead of
            merging.
        """
        self._refresh_durable()
        replay = self._check_replay(request_id, command_text)
        if replay is not None:
            return replay
        try:
            engine_ecs_store.validate_entity_id(entity)
            engine_ecs_store.validate_component_name(component)
            engine_ecs_store.validate_component_data(data)
        except engine_ecs_store.EcsError as exc:
            raise ProjectError(exc.code, str(exc)) from exc
        if engine_ecs_store.is_backfill_id(entity):
            raise ProjectError(
                "backfill_readonly",
                f"Backfilled entity is read-only: {entity}.",
            )
        path, decoded = self._read_entity_record(entity)
        if component in decoded["components"]:
            raise ProjectError(
                "component_exists",
                "Component already attached: "
                f"{engine_ecs_store.format_address(entity, component)}.",
            )
        self._gate_revision(expected_revision)
        previous = self._current_revision
        self._ensure_snapshot(previous)
        merged = dict(decoded["components"])
        merged[component] = data
        old_text = self._read_doc_text(path, path)
        self._store_entity_record(path, entity, decoded["kind"], merged)
        advanced = _advance_revision(previous)
        try:
            self._capture_snapshot(advanced)
        except ProjectError:
            try:
                self._write_doc_text(path, old_text, path)
            except Exception:
                pass
            raise
        self._current_revision = advanced
        address = engine_ecs_store.format_address(entity, component)
        diff = f"attached {address} ({path})"
        record = self._append_event(
            "component_changed",
            request_id,
            engine_ecs_store.component_changed_data(
                entity, component, self._current_revision
            ),
        )
        response = self._ecs_response(
            request_id, previous, diff, record,
            {
                "address": address,
                "component": component,
                "entity": entity,
                "path": path,
            },
        )
        self._requests[request_id] = (command_text, response)
        self._persist_after_mutation()
        return response

    def detach_component(self, entity, component, request_id,
                         command_text, expected_revision=None):
        """Detach one component from its entity.

        Persists through the entity record with the same admission
        machinery as write_doc; the component_changed event carries
        detached True.

        A resubmitted envelope returns its stored response without
        advancing.

        Args:
            entity: Entity id holding the component.
            component: Component name to remove.
            request_id: Client envelope id; resubmitting the
                identical text returns the identical response
                without advancing.
            command_text: YAML command text for identity comparison.
            expected_revision: Revision the writer read.

        Returns:
            Mutation mapping with entity, component, canonical
            address, storage path, revision transition, new head,
            actor, diff summary, rewind handle, the
            component_changed event, cursor, and request id.

        Raises:
            ProjectError: unknown_component for a missing
                component; otherwise like set_component without
                the data errors.

        Caution: Every accepted detach advances the revision — a
            second writer at the old head fails instead of
            merging.
        """
        self._refresh_durable()
        replay = self._check_replay(request_id, command_text)
        if replay is not None:
            return replay
        try:
            engine_ecs_store.validate_entity_id(entity)
            engine_ecs_store.validate_component_name(component)
        except engine_ecs_store.EcsError as exc:
            raise ProjectError(exc.code, str(exc)) from exc
        if engine_ecs_store.is_backfill_id(entity):
            raise ProjectError(
                "backfill_readonly",
                f"Backfilled entity is read-only: {entity}.",
            )
        path, decoded = self._read_entity_record(entity)
        if component not in decoded["components"]:
            raise ProjectError(
                "unknown_component",
                f"No component {component!r} on {entity}.",
            )
        self._gate_revision(expected_revision)
        previous = self._current_revision
        self._ensure_snapshot(previous)
        merged = dict(decoded["components"])
        del merged[component]
        old_text = self._read_doc_text(path, path)
        self._store_entity_record(path, entity, decoded["kind"], merged)
        advanced = _advance_revision(previous)
        try:
            self._capture_snapshot(advanced)
        except ProjectError:
            try:
                self._write_doc_text(path, old_text, path)
            except Exception:
                pass
            raise
        self._current_revision = advanced
        address = engine_ecs_store.format_address(entity, component)
        diff = f"detached {address} ({path})"
        record = self._append_event(
            "component_changed",
            request_id,
            engine_ecs_store.component_changed_data(
                entity, component, self._current_revision,
                detached=True,
            ),
        )
        response = self._ecs_response(
            request_id, previous, diff, record,
            {
                "address": address,
                "component": component,
                "entity": entity,
                "path": path,
            },
        )
        self._requests[request_id] = (command_text, response)
        self._persist_after_mutation()
        return response

    def delete_entity(self, entity, request_id, command_text,
                      expected_revision=None):
        """Delete one entity and its projected record.

        Removes entities/<entity>.json through the same admission
        machinery as delete_doc, and appends entity_deleted.

        A resubmitted envelope returns its stored response without
        advancing.

        Args:
            entity: Entity id to delete.
            request_id: Client envelope id; resubmitting the
                identical text returns the identical response
                without advancing.
            command_text: YAML command text for identity comparison.
            expected_revision: Revision the writer read.

        Returns:
            Mutation mapping with entity, storage path, revision
            transition, new head, actor, diff summary, rewind
            handle, the entity_deleted event, cursor, and request
            id.

        Raises:
            ProjectError: request_conflict for a reused id with
                new text; invalid_entity for a malformed id;
                unknown_entity for a missing entity;
                backfill_readonly for a backfilled id;
                invalid_document for a corrupt entity record;
                revision_conflict for a stale head; invalid_ledger
                when the durable delete fails.

        Caution: Deleting advances the revision like any mutation
            — stale writers fail instead of merging.
        """
        self._refresh_durable()
        replay = self._check_replay(request_id, command_text)
        if replay is not None:
            return replay
        try:
            engine_ecs_store.validate_entity_id(entity)
        except engine_ecs_store.EcsError as exc:
            raise ProjectError(exc.code, str(exc)) from exc
        if engine_ecs_store.is_backfill_id(entity):
            raise ProjectError(
                "backfill_readonly",
                f"Backfilled entity is read-only: {entity}.",
            )
        path, _decoded = self._read_entity_record(entity)
        self._gate_revision(expected_revision)
        previous = self._current_revision
        self._ensure_snapshot(previous)
        old_text = self._read_doc_text(path, path)
        self._delete_doc_path(path, path)
        advanced = _advance_revision(previous)
        try:
            self._capture_snapshot(advanced)
        except ProjectError:
            try:
                self._write_doc_text(path, old_text, path)
            except Exception:
                pass
            raise
        self._current_revision = advanced
        diff = f"deleted entity {entity} ({path})"
        record = self._append_event(
            "entity_deleted",
            request_id,
            {"entity": entity, "revision": self._current_revision},
        )
        response = self._ecs_response(
            request_id, previous, diff, record,
            {"entity": entity, "path": path},
        )
        self._requests[request_id] = (command_text, response)
        self._persist_after_mutation()
        return response

    def delete_doc(self, path, request_id, command_text,
                   expected_revision=None):
        """Delete one document: gate, remove, advance, log.

        Args:
            path: Document path to delete.
            request_id: Client envelope id for idempotent replay.
            command_text: YAML command text for identity comparison.
            expected_revision: Revision the writer read.

        Returns:
            Mutation mapping with path, revision transition, new
            head, actor, diff summary, rewind handle, the
            appended event, cursor, and request id.

        Raises:
            ProjectError: request_conflict for a reused id with
                new text; invalid_path or path_escape for a bad
                path; unknown_document for a missing document;
                invalid_command when the path names a directory;
                revision_conflict for a stale head; invalid_ledger
                when the durable delete fails.

        Caution: Deleting advances the revision like any mutation
            — stale writers fail instead of merging.
        """
        self._refresh_durable()
        replay = self._check_replay(request_id, command_text)
        if replay is not None:
            return replay
        canonical = _canonical_doc_path(path)
        _check_reserved_doc(canonical, path)
        old = self._read_doc_text(canonical, path)
        if old is None:
            raise ProjectError(
                "unknown_document", f"No such document: {path}."
            )
        self._gate_revision(expected_revision)
        previous = self._current_revision
        self._ensure_snapshot(previous)
        self._delete_doc_path(canonical, path)
        advanced = _advance_revision(previous)
        try:
            self._capture_snapshot(advanced)
        except ProjectError:
            try:
                self._write_doc_text(canonical, old, path)
            except Exception:
                pass
            raise
        self._current_revision = advanced
        diff = f"deleted {canonical} ({len(old.encode('utf-8'))} bytes)"
        record = self._append_event(
            "doc_deleted",
            request_id,
            {
                "revision": self._current_revision,
                "operation": "delete_doc",
                "path": canonical,
                "bytes": len(old.encode("utf-8")),
                "diff_summary": diff,
            },
        )
        response = {
            "project_id": self._project_id,
            "path": canonical,
            "previous_revision": previous,
            "current_revision": self._current_revision,
            "revision_transition": {
                "from": previous,
                "to": self._current_revision,
            },
            "actor": self._actor,
            "diff_summary": diff,
            "rewind_handle": {
                "project_id": self._project_id,
                "revision": previous,
                "request_id": request_id,
            },
            "events": [record],
            "event_cursor": self._cursor(),
            "request_id": request_id,
        }
        self._requests[request_id] = (command_text, response)
        self._persist_after_mutation()
        return response

    def apply_mutations(self, mutations, request_id, command_text,
                        expected_revision=None):
        """Apply a batch atomically under one new revision (I31).

        Every mutation is validated before anything lands: any
        failure names its document and leaves the revision, the
        files, and the log untouched. Only a fully valid batch at
        the live head advances once and appends a single
        mutations_applied event.

        Args:
            mutations: Non-empty list of {op, path, content?}
                mappings; op is write (needs text content) or
                delete (takes none).
            request_id: Client envelope id for idempotent replay.
            command_text: YAML command text for identity comparison.
            expected_revision: Revision the writer read.

        Returns:
            Mutation mapping with revision transition, new head,
            actor, joined diff summary, rewind handle, the single
            appended event, per-mutation results, cursor, and
            request id.

        Raises:
            ProjectError: request_conflict for a reused id with
                new text; invalid_command for a malformed batch
                (names the document when one is addressable);
                invalid_path or path_escape for a bad path;
                unknown_document for a delete of a missing
                document; revision_conflict for a stale head;
                invalid_ledger when a durable write fails (best
                effort rollback already attempted).

        Caution: All-or-nothing means one revision for the whole
            batch — a half-landed batch is a bug, never a state.
        """
        self._refresh_durable()
        replay = self._check_replay(request_id, command_text)
        if replay is not None:
            return replay
        if not isinstance(mutations, list) or not mutations:
            raise ProjectError(
                "invalid_command",
                "apply_mutations needs a non-empty mutations list.",
            )
        prepared = []
        for index, item in enumerate(mutations):
            if not isinstance(item, dict):
                raise ProjectError(
                    "invalid_command",
                    f"Mutation {index} must be a mapping.",
                )
            op = item.get("op")
            raw_path = item.get("path")
            if op not in ("write", "delete"):
                if isinstance(raw_path, str):
                    raise ProjectError(
                        "invalid_command",
                        f"Unknown op {op!r} for document {raw_path}.",
                    )
                raise ProjectError(
                    "invalid_command",
                    f"Mutation {index} needs op write/delete.",
                )
            if not isinstance(raw_path, str):
                raise ProjectError(
                    "invalid_command",
                    f"Mutation {index} needs a text path.",
                )
            canonical = _canonical_doc_path(raw_path)
            _check_reserved_doc(canonical, raw_path)
            if op == "write":
                unknown = set(item) - {"op", "path", "content"}
                if unknown:
                    raise ProjectError(
                        "invalid_command",
                        f"Unknown fields for document {raw_path}: "
                        f"{', '.join(sorted(unknown))}.",
                    )
                content = item.get("content")
                if "content" not in item or not isinstance(
                    content, str
                ):
                    raise ProjectError(
                        "invalid_command",
                        f"Write needs text content for document "
                        f"{raw_path}.",
                    )
                if len(content.encode("utf-8")) > _MAX_DOC_BYTES:
                    raise ProjectError(
                        "invalid_command",
                        f"Document exceeds the size limit: {raw_path}.",
                    )
            else:
                unknown = set(item) - {"op", "path"}
                if unknown:
                    raise ProjectError(
                        "invalid_command",
                        f"Unknown fields for document {raw_path}: "
                        f"{', '.join(sorted(unknown))}.",
                    )
                if "content" in item:
                    raise ProjectError(
                        "invalid_command",
                        f"Delete takes no content for document "
                        f"{raw_path}.",
                    )
                content = None
            old = self._read_doc_text(canonical, raw_path)
            if op == "delete" and old is None:
                raise ProjectError(
                    "unknown_document",
                    f"No such document: {raw_path}.",
                )
            prepared.append((op, canonical, content, old, raw_path))
        self._gate_revision(expected_revision)
        previous = self._current_revision
        self._ensure_snapshot(previous)
        applied = []
        try:
            for op, canonical, content, _old, raw_path in prepared:
                if op == "write":
                    self._write_doc_text(canonical, content, raw_path)
                else:
                    self._delete_doc_path(canonical, raw_path)
                applied.append((canonical, _old))
        except ProjectError:
            for canonical, old in reversed(applied):
                try:
                    if old is None:
                        self._delete_doc_path(canonical, canonical)
                    else:
                        self._write_doc_text(
                            canonical, old, canonical
                        )
                except Exception:
                    pass
            raise
        except OSError as exc:
            for canonical, old in reversed(applied):
                try:
                    if old is None:
                        self._delete_doc_path(canonical, canonical)
                    else:
                        self._write_doc_text(
                            canonical, old, canonical
                        )
                except Exception:
                    pass
            raise ProjectError(
                "invalid_ledger",
                f"Batch write failed; rolled back: {exc}.",
            ) from exc
        advanced = _advance_revision(previous)
        try:
            self._capture_snapshot(advanced)
        except ProjectError:
            for _op, canonical, _content, old, _raw in reversed(prepared):
                try:
                    if old is None:
                        self._delete_doc_path(canonical, canonical)
                    else:
                        self._write_doc_text(
                            canonical, old, canonical
                        )
                except Exception:
                    pass
            raise
        self._current_revision = advanced
        parts = []
        results = []
        for op, canonical, content, old, _raw in prepared:
            if op == "write":
                new_bytes = len(content.encode("utf-8"))
                if old is None:
                    parts.append(
                        f"created {canonical} ({new_bytes} bytes)"
                    )
                else:
                    parts.append(
                        f"updated {canonical} "
                        f"({len(old.encode('utf-8'))} -> "
                        f"{new_bytes} bytes)"
                    )
                results.append(
                    {"op": "write", "path": canonical, "bytes": new_bytes}
                )
            else:
                old_bytes = len(old.encode("utf-8"))
                parts.append(f"deleted {canonical} ({old_bytes} bytes)")
                results.append(
                    {"op": "delete", "path": canonical, "bytes": old_bytes}
                )
        diff = "; ".join(parts)
        record = self._append_event(
            "mutations_applied",
            request_id,
            {
                "revision": self._current_revision,
                "operation": "apply_mutations",
                "mutations": [
                    {"op": op, "path": canonical}
                    for op, canonical, _, _, _ in prepared
                ],
                "diff_summary": diff,
            },
        )
        response = {
            "project_id": self._project_id,
            "previous_revision": previous,
            "current_revision": self._current_revision,
            "revision_transition": {
                "from": previous,
                "to": self._current_revision,
            },
            "actor": self._actor,
            "diff_summary": diff,
            "rewind_handle": {
                "project_id": self._project_id,
                "revision": previous,
                "request_id": request_id,
            },
            "events": [record],
            "results": results,
            "event_cursor": self._cursor(),
            "request_id": request_id,
        }
        self._requests[request_id] = (command_text, response)
        self._persist_after_mutation()
        return response

    def _entity_store(self, request_id):
        """Return the ENGINE-ECS entity store seam for one wire op.

        WIRE-PLACE/ENGINE-ECS seam: ENGINE-ECS owns the durable
        store as per-verb service methods, so this binds the
        _WireEntityStore adapter over those verbs for the given
        outer request id (inner envelopes derive from it).

        Args:
            request_id: Outer wire envelope id; inner ECS
                envelopes derive deterministically from it.

        Returns:
            Entity store serving the wireplace seam.

        Raises:
            ProjectError: unsupported_operation when the
                ENGINE-ECS verbs are not present.
        """
        for name in (
            _WireEntityStore._READS + _WireEntityStore._WRITES
        ):
            if not callable(getattr(self, name, None)):
                raise ProjectError(
                    "unsupported_operation",
                    "Wire ops need the ENGINE-ECS entity store, "
                    "which is not wired yet.",
                )
        return _WireEntityStore(self, request_id)

    def _wire_mutation(self, operation, request_id, command_text,
                       expected_revision, run, describe):
        """Admit one wire op through the ledger admission machinery.

        A resubmitted envelope returns its stored response; a new
        envelope gates its expected_revision, snapshots the
        previous head, runs the entity transact (one ledger
        revision per verb), then advances once more for the wire
        event and logs. A noop receipt returns the head
        unadvanced with an empty event list.

        Args:
            operation: Wire operation name for the event data.
            request_id: Client envelope id for idempotent replay.
            command_text: YAML command text for identity comparison.
            expected_revision: Revision the writer read.
            run: Callable (store) -> wireplace receipt.
            describe: Callable (receipt) -> diff summary text.

        Returns:
            Mutation mapping with the entity receipt, revision
            transition, actor, diff summary, rewind handle,
            appended event, cursor, and request id — or the
            unadvanced noop mapping when the receipt is a noop.

        Raises:
            ProjectError: request_conflict for a reused id with
                new text; revision_conflict for a stale head;
                unsupported_operation without the ENGINE-ECS
                store; the wire contract code (unknown_wire,
                unknown_ref, ...) for a refused op.
        """
        self._refresh_durable()
        replay = self._check_replay(request_id, command_text)
        if replay is not None:
            return replay
        self._gate_revision(expected_revision)
        store = self._entity_store(request_id)
        previous = self._current_revision
        self._ensure_snapshot(previous)
        try:
            receipt = run(store)
        except ContractError as exc:
            raise ProjectError(exc.code, str(exc)) from exc
        if receipt.get("noop"):
            response = {
                "project_id": self._project_id,
                "previous_revision": previous,
                "current_revision": previous,
                "revision_transition": {"from": previous, "to": previous},
                "actor": self._actor,
                "diff_summary": f"{operation} changed nothing",
                "rewind_handle": {
                    "project_id": self._project_id,
                    "revision": previous,
                    "request_id": request_id,
                },
                "noop": True,
                "receipt": receipt,
                "events": [],
                "event_cursor": self._cursor(),
                "request_id": request_id,
            }
            self._requests[request_id] = (command_text, response)
            self._persist_after_mutation()
            return response
        # Chain from the live head: the transact's verbs already
        # advanced past `previous`, so advancing from `previous`
        # would fork the revision line backwards.
        advanced = _advance_revision(self._current_revision)
        self._capture_snapshot(advanced)
        self._current_revision = advanced
        diff = describe(receipt)
        record = self._append_event(
            operation,
            request_id,
            {
                "revision": self._current_revision,
                "operation": operation,
                "diff_summary": diff,
                "receipt": receipt,
            },
        )
        response = {
            "project_id": self._project_id,
            "previous_revision": previous,
            "current_revision": self._current_revision,
            "revision_transition": {
                "from": previous,
                "to": self._current_revision,
            },
            "actor": self._actor,
            "diff_summary": diff,
            "rewind_handle": {
                "project_id": self._project_id,
                "revision": previous,
                "request_id": request_id,
            },
            "receipt": receipt,
            "events": [record],
            "event_cursor": self._cursor(),
            "request_id": request_id,
        }
        self._requests[request_id] = (command_text, response)
        self._persist_after_mutation()
        return response

    def place_wire(self, segments, layer, endpoints, request_id,
                   command_text, expected_revision=None):
        """Place one wire: gate, transact, advance, log.

        A resubmitted envelope returns its stored response without
        advancing; a new envelope gates its expected_revision, and
        only an accepted placement advances the revision and
        appends the place_wire event carrying the entity receipt.

        Args:
            segments: Non-empty list of integer polylines.
            layer: Layer name for every segment.
            endpoints: [a, b] endpoint mappings; each ref is a
                pin/port/junction/net entity ID or null when
                dangling.
            request_id: Client envelope id; resubmitting the
                identical text returns the identical response
                without advancing.
            command_text: YAML command text for identity comparison.
            expected_revision: Revision the writer read.

        Returns:
            Mutation mapping with the wire receipt, revision
            transition, new head, actor, diff summary, rewind
            handle, the appended event, cursor, and request id.

        Raises:
            ProjectError: request_conflict for a reused id with
                new text; revision_conflict for a stale head;
                unknown_ref for a ref naming no entity;
                invalid_ref for a wire ref; invalid_wire for a
                malformed wire; unsupported_operation without the
                ENGINE-ECS entity store.

        Caution: Every accepted placement advances the revision —
            a second writer at the old head fails instead of
            merging.
        """
        return self._wire_mutation(
            "place_wire", request_id, command_text, expected_revision,
            lambda store: wireplace.place_wire(
                store, self._actor, segments, layer, endpoints
            ),
            lambda receipt: f"placed wire {receipt['wire']} on {layer}",
        )

    def place_junction(self, xy, layer, request_id, command_text,
                       expected_revision=None):
        """Place one junction dot: gate, transact, advance, log.

        Args:
            xy: Integer [x, y] dot position.
            layer: Layer name for the dot.
            request_id: Client envelope id for idempotent replay.
            command_text: YAML command text for identity comparison.
            expected_revision: Revision the writer read.

        Returns:
            Mutation mapping with the junction receipt, revision
            transition, new head, actor, diff summary, rewind
            handle, the appended event, cursor, and request id.

        Raises:
            ProjectError: request_conflict for a reused id with
                new text; revision_conflict for a stale head;
                invalid_junction for a malformed dot;
                unsupported_operation without the ENGINE-ECS
                entity store.

        Caution: Every accepted placement advances the revision —
            a second writer at the old head fails instead of
            merging.
        """
        return self._wire_mutation(
            "place_junction", request_id, command_text, expected_revision,
            lambda store: wireplace.place_junction(
                store, self._actor, xy, layer
            ),
            lambda receipt: f"placed junction {receipt['junction']}",
        )

    def connect_endpoint(self, wire_id, end, ref, request_id,
                         command_text, expected_revision=None):
        """Point one wire endpoint at a new terminus: gate, run, log.

        Geometry never moves — only the ref changes — and a
        no-change call returns the head unadvanced with an empty
        event list instead of logging a phantom revision.

        Args:
            wire_id: Wire entity to rewire.
            end: "a" or "b" selecting the endpoint.
            ref: Pin/port/junction/net entity ID, or null to
                dangle the endpoint.
            request_id: Client envelope id for idempotent replay.
            command_text: YAML command text for identity comparison.
            expected_revision: Revision the writer read.

        Returns:
            Mutation mapping with the connect receipt, revision
            transition, actor, diff summary, rewind handle, the
            appended event, cursor, and request id — or the
            unadvanced noop mapping when the ref is already set.

        Raises:
            ProjectError: request_conflict for a reused id with
                new text; revision_conflict for a stale head;
                unknown_wire for a missing wire; invalid_endpoint
                for a bad selector; unknown_ref for a missing
                entity; invalid_ref for a wire/self ref;
                unsupported_operation without the ENGINE-ECS
                entity store.
        """
        return self._wire_mutation(
            "connect_endpoint", request_id, command_text,
            expected_revision,
            lambda store: wireplace.connect_endpoint(
                store, self._actor, wire_id, end, ref
            ),
            lambda receipt: (
                f"connected wire {wire_id} end {end} to {ref!r}"
            ),
        )

    def move_wire(self, wire_id, dx, dy, request_id, command_text,
                  expected_revision=None):
        """Translate one wire: gate, transact, advance, log.

        Refs survive the move; a zero move returns the head
        unadvanced with an empty event list.

        Args:
            wire_id: Wire entity to move.
            dx: Integer x translation.
            dy: Integer y translation.
            request_id: Client envelope id for idempotent replay.
            command_text: YAML command text for identity comparison.
            expected_revision: Revision the writer read.

        Returns:
            Mutation mapping with the move receipt, revision
            transition, actor, diff summary, rewind handle, the
            appended event, cursor, and request id — or the
            unadvanced noop mapping for a zero move.

        Raises:
            ProjectError: request_conflict for a reused id with
                new text; revision_conflict for a stale head;
                unknown_wire for a missing wire; invalid_geometry
                for non-integer deltas; unsupported_operation
                without the ENGINE-ECS entity store.
        """
        return self._wire_mutation(
            "move_wire", request_id, command_text, expected_revision,
            lambda store: wireplace.move_wire(
                store, self._actor, wire_id, dx, dy
            ),
            lambda receipt: f"moved wire {wire_id} by ({dx}, {dy})",
        )

    def split_wire(self, wire_id, at, request_id, command_text,
                   expected_revision=None):
        """Split one wire at an interior point: gate, run, log.

        The junction dot, the head rewrite, and the new tail wire
        land in one revision under one event.

        Args:
            wire_id: Wire entity to split.
            at: Integer [x, y] point on the polyline interior.
            request_id: Client envelope id for idempotent replay.
            command_text: YAML command text for identity comparison.
            expected_revision: Revision the writer read.

        Returns:
            Mutation mapping with the split receipt (wire,
            junction, new_wire), revision transition, new head,
            actor, diff summary, rewind handle, the appended
            event, cursor, and request id.

        Raises:
            ProjectError: request_conflict for a reused id with
                new text; revision_conflict for a stale head;
                unknown_wire for a missing wire; invalid_split for
                a point off the interior or a multi-polyline wire;
                unsupported_operation without the ENGINE-ECS
                entity store.
        """
        return self._wire_mutation(
            "split_wire", request_id, command_text, expected_revision,
            lambda store: wireplace.split_wire(
                store, self._actor, wire_id, at
            ),
            lambda receipt: (
                f"split wire {wire_id} at {at} "
                f"(junction {receipt['junction']}, "
                f"tail {receipt['new_wire']})"
            ),
        )

    def delete_wire(self, wire_id, request_id, command_text,
                    expected_revision=None):
        """Delete one wire: gate, remove, advance, log.

        Referenced junctions persist; Net entities rematerialize
        on the next materialize_nets call.

        Args:
            wire_id: Wire entity to delete.
            request_id: Client envelope id for idempotent replay.
            command_text: YAML command text for identity comparison.
            expected_revision: Revision the writer read.

        Returns:
            Mutation mapping with the delete receipt, revision
            transition, new head, actor, diff summary, rewind
            handle, the appended event, cursor, and request id.

        Raises:
            ProjectError: request_conflict for a reused id with
                new text; revision_conflict for a stale head;
                unknown_wire for a missing wire;
                unsupported_operation without the ENGINE-ECS
                entity store.
        """
        return self._wire_mutation(
            "delete_wire", request_id, command_text, expected_revision,
            lambda store: wireplace.delete_wire(
                store, self._actor, wire_id
            ),
            lambda receipt: f"deleted wire {wire_id}",
        )

    def delete_junction(self, junction_id, request_id, command_text,
                        expected_revision=None):
        """Delete one unreferenced junction: gate, remove, log.

        Args:
            junction_id: Junction entity to delete.
            request_id: Client envelope id for idempotent replay.
            command_text: YAML command text for identity comparison.
            expected_revision: Revision the writer read.

        Returns:
            Mutation mapping with the delete receipt, revision
            transition, new head, actor, diff summary, rewind
            handle, the appended event, cursor, and request id.

        Raises:
            ProjectError: request_conflict for a reused id with
                new text; revision_conflict for a stale head;
                unknown_junction for a missing junction;
                junction_in_use naming the referencing wires;
                unsupported_operation without the ENGINE-ECS
                entity store.
        """
        return self._wire_mutation(
            "delete_junction", request_id, command_text,
            expected_revision,
            lambda store: wireplace.delete_junction(
                store, self._actor, junction_id
            ),
            lambda receipt: f"deleted junction {junction_id}",
        )

    def materialize_nets(self, pins, request_id, command_text,
                         labels=None, ports=None, cell="top",
                         named_refs=None, expected_revision=None):
        """Extract connectivity, upsert Net entities: gate, run, log.

        Extraction always rebuilds from the stored wires; Nets
        keyed by canonical name are created or refreshed, vanished
        names pruned, all in one revision. An unchanged world
        returns the head unadvanced with an empty event list.

        Args:
            pins: Caller pin records [{entity, instance, pin, xy}].
            request_id: Client envelope id for idempotent replay.
            command_text: YAML command text for identity comparison.
            labels: Caller label records [{name, xy}].
            ports: Caller port records [{name, direction}].
            cell: Top cell name.
            named_refs: {entity ID: net name} for port-style refs.
            expected_revision: Revision the writer read.

        Returns:
            Mutation mapping with the materialize receipt (nets,
            created/updated/pruned, unresolved), revision
            transition, actor, diff summary, rewind handle, the
            appended event, cursor, and request id — or the
            unadvanced noop mapping when every Net matches.

        Raises:
            ProjectError: request_conflict for a reused id with
                new text; revision_conflict for a stale head;
                invalid_pin / invalid_label / invalid_port /
                invalid_cell / invalid_ref for malformed inputs;
                extraction_failed when extraction refuses the
                world; unsupported_operation without the
                ENGINE-ECS entity store.
        """
        return self._wire_mutation(
            "materialize_nets", request_id, command_text,
            expected_revision,
            lambda store: wireplace.materialize_nets(
                store, self._actor, pins, labels=labels or (),
                ports=ports or (), cell=cell, named_refs=named_refs,
            ),
            lambda receipt: (
                f"materialized {len(receipt['nets'])} nets "
                f"({len(receipt['created'])} created, "
                f"{len(receipt['updated'])} updated, "
                f"{len(receipt['pruned'])} pruned)"
            ),
        )

    def rewind(self, target_revision, request_id, command_text,
               expected_revision=None):
        """Restore managed bytes to a prior revision under a new head.

        The target snapshot replaces every managed document
        byte-identically; runs, the ledger, and the snapshots
        themselves are left alone. History stays append-only: the
        restore advances from the live head and appends a single
        `project_rewound` event recording the target. Linked caller
        trees are never written — files outside `.rocket/` are
        listed in the response as left untouched.

        Args:
            target_revision: Snapshot revision to restore.
            request_id: Client envelope id for idempotent replay.
            command_text: YAML command text for identity comparison.
            expected_revision: Revision the writer read.

        Returns:
            Mutation mapping with revision transition, target
            revision, new head, actor, diff summary, external-file
            report, rewind handle, the appended event, cursor, and
            request id.

        Raises:
            ProjectError: request_conflict for a reused id with new
                text; invalid_command for a missing target or a
                target that equals the live head; unknown_revision
                for a revision with no snapshot; revision_conflict
                for a stale head; invalid_ledger when the durable
                restore fails (best-effort rollback already
                attempted).

        Caution: Rewinding advances — the new head is not the target
            id, and stale writers fail instead of merging. Caller
            files outside `.rocket/` are reported, never touched.
        """
        self._refresh_durable()
        replay = self._check_replay(request_id, command_text)
        if replay is not None:
            return replay
        if not isinstance(target_revision, str) or not target_revision:
            raise ProjectError(
                "invalid_command",
                "rewind needs a target_revision argument.",
            )
        snapshot = self._load_snapshot(target_revision)
        if snapshot is None:
            raise ProjectError(
                "unknown_revision",
                f"No snapshot for revision: {target_revision}.",
            )
        if target_revision == self._current_revision:
            raise ProjectError(
                "invalid_command",
                f"Already at revision {target_revision}.",
            )
        self._gate_revision(expected_revision)
        previous = self._current_revision
        self._ensure_snapshot(previous)
        if self._dir is None:
            self._docs = dict(snapshot)
        else:
            pre = self._current_bytes()
            self._restore_snapshot_bytes(snapshot, pre)
        advanced = _advance_revision(previous)
        if self._dir is None:
            self._snapshots[advanced] = dict(self._docs)
        else:
            try:
                self._capture_snapshot(advanced)
            except ProjectError:
                try:
                    self._clear_docs()
                    self._write_bytes_map(pre)
                except Exception:
                    pass
                raise
        self._current_revision = advanced
        external = self._linked_external_files()
        count = len(snapshot)
        noun = "doc" if count == 1 else "docs"
        diff = (
            f"rewound {previous} to {target_revision} "
            f"(restored {count} {noun} as {advanced})"
        )
        record = self._append_event(
            "project_rewound",
            request_id,
            {
                "revision": self._current_revision,
                "operation": "rewind",
                "target_revision": target_revision,
                "previous_revision": previous,
                "diff_summary": diff,
                "external_files": [e["path"] for e in external],
            },
        )
        response = {
            "project_id": self._project_id,
            "previous_revision": previous,
            "current_revision": self._current_revision,
            "revision_transition": {
                "from": previous,
                "to": self._current_revision,
            },
            "target_revision": target_revision,
            "actor": self._actor,
            "diff_summary": diff,
            "external_files": external,
            "rewind_handle": {
                "project_id": self._project_id,
                "revision": previous,
                "request_id": request_id,
            },
            "events": [record],
            "event_cursor": self._cursor(),
            "request_id": request_id,
        }
        self._requests[request_id] = (command_text, response)
        self._persist_after_mutation()
        return response
