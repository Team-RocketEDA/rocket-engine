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

import hashlib
import threading
import uuid
from pathlib import Path

from ruamel.yaml import YAML

from ..ops import editors as _editors
from ..ops.ports import ecs
from ..ops.ports import settings as settings_store
from ..ops.ports import wireplace
from ..interfaces.paths import join_contained
from ..interfaces.refs import pin_closure

from . import frontend13 as _frontend13
from .edit import cas as _cas
from .edit import transactions as _transactions
from .errors import ProjectError
from .geometry import ops as _geometry
from .ip.verbs import _IpMixin
from .layers import bindings as _layer_bindings
from .layers import catalog as _layer_catalog
from .process import model as _process
from .schematic import hierarchy as _hierarchy
from .schematic import instances as _instances
from .schematic import sheets as _sheets
from .symbols import cells as _cells
from .symbols import linkage as _linkage
from .symbols import symbols as _symbols
from .testbench import blocks as _testbench
from .ledger.docs import _DocMixin
from .ledger.entities import _EntityMixin
from .ledger.events import _EventMixin
from .ledger.runs import _RunMixin
from .ledger.snapshots import _SnapshotMixin
from .ledger.wires import _WireEntityStore as _WireEntityStore
from .ledger.wires import _WireMixin

from .ledger.shared import (
    DEFAULT_MAX_RETAINED_EVENTS,
    _EVENTS_FILENAME,
    _LEDGER_FILENAME,
    _MAX_DOC_BYTES,
    _PROJECT_ID_RE,
    _SETTINGS_DOC_PREFIX,
    _advance_revision,
    _atomic_write_text,
    _canonical_doc_path,
    _canonical_prefix,
    _check_reserved_doc,
    _dump_yaml,
)

class ProjectService(_DocMixin, _EntityMixin, _EventMixin, _IpMixin, _RunMixin, _SnapshotMixin, _WireMixin):
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
        # BATCH-PARALLEL: concurrent drains append run/replay events
        # from worker threads — refresh/append/persist runs as one
        # critical section so the durable log never interleaves.
        self._ledger_lock = threading.RLock()
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
        # Lazy: keeps the project import chain free of the execution
        # package (REPLAY-SAFE content keys).
        from ..execution.replay_safe import content_key_for
        key_arguments = {
            key: value
            for key, value in (command.get("arguments") or {}).items()
            if key != "expected_revision"
        }
        self._append_event(
            "job_queued",
            request_id,
            {
                "run_id": ack["run_id"],
                "revision": self._current_revision,
                "operation": command.get("operation"),
                "content_key": content_key_for(
                    command.get("operation"), key_arguments
                ),
            },
        )
        ack["event_cursor"] = self._cursor()
        self._persist_after_mutation()
        return ack

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
        by_kind = {}
        for kind in settings_store.CURRENT_VERSIONS:
            read = self.read_settings(kind)
            by_kind[read["kind"]] = read["settings"]
        snapshot = settings_store.snapshot_settings(
            by_kind, session_id=session_id, run_id=run_id
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
            component, canonical address, storage path, the
            component data, and the entity revision.

        Raises:
            ProjectError: invalid_entity or invalid_component for
                malformed parts; unknown_entity for a missing
                entity; unknown_component for a missing component;
                invalid_document for a corrupt entity record.
        """
        self._refresh_durable()
        try:
            ecs.validate_entity_id(entity)
            ecs.validate_component_name(component)
        except ecs.EcsError as exc:
            raise ProjectError(exc.code, str(exc)) from exc
        if ecs.is_backfill_id(entity):
            return self._read_backfill_component(entity, component)
        path, decoded = self._read_entity_record(entity)
        if component not in decoded["components"]:
            raise ProjectError(
                "unknown_component",
                f"No component {component!r} on {entity}.",
            )
        return {
            "address": ecs.format_address(entity, component),
            "component": component,
            "current_revision": self._current_revision,
            "data": decoded["components"][component],
            "entity": entity,
            "entity_revision": self._entity_revision_of(decoded),
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
            ecs.validate_entity_id(entity)
        except ecs.EcsError as exc:
            raise ProjectError(exc.code, str(exc)) from exc
        if ecs.is_backfill_id(entity):
            record = self._find_backfill(entity)
            return {
                "components": sorted(record["components"]),
                "current_revision": self._current_revision,
                "entity": entity,
                "path": record["components"][
                    ecs.BACKFILL_COMPONENT
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
            ecs.validate_component_name(component)
            ecs.validate_predicate(predicate)
        except ecs.EcsError as exc:
            raise ProjectError(exc.code, str(exc)) from exc
        records = self._entity_records()
        if component == ecs.BACKFILL_COMPONENT:
            records.extend(self._backfill_records())
        holders = ecs.filter_entities(
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
        return ecs.build_world_snapshot(
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
            expected_revision: Accepted and ignored (ENTITY-CAS):
                minted ids cannot collide, so creates never
                conflict — concurrent creates always land with
                distinct ids.

        Returns:
            Mutation mapping with the minted entity, kind, storage
            path, revision transition, new head, actor, diff
            summary, rewind handle, the entity_created event,
            cursor, request id, initial component names, and the
            entity_revision (1).

        Raises:
            ProjectError: request_conflict for a reused id with
                new text; invalid_kind, invalid_component, or
                invalid_data for malformed parts;
                invalid_ledger when the durable write fails.

        Caution: Every accepted create advances the revision, but
            never fails on a stale head — identity is minted, so
            there is nothing to merge or conflict with.
        """
        self._refresh_durable()
        replay = self._check_replay(request_id, command_text)
        if replay is not None:
            return replay
        try:
            ecs.validate_kind(kind)
            if components is not None and not isinstance(
                components, dict
            ):
                raise ecs.EcsError(
                    "invalid_data",
                    "Initial components must be a mapping.",
                )
            initial = dict(components or {})
            for name, data in initial.items():
                ecs.validate_component_name(name)
                ecs.validate_component_data(data)
        except ecs.EcsError as exc:
            raise ProjectError(exc.code, str(exc)) from exc
        # No head gate: minted identity cannot collide, so concurrent
        # creates never conflict (ENTITY-CAS).
        previous = self._current_revision
        self._ensure_snapshot(previous)
        taken = set()
        for rel, _size in self._iter_doc_files():
            found = ecs.entity_from_doc_path(rel)
            if found is not None:
                taken.add(found)
        entity = ecs.mint_entity_id(existing=taken)
        path = ecs.entity_doc_path(entity)
        self._store_entity_record(path, entity, kind, initial, 1)
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
                "entity_revision": 1,
                "kind": kind,
                "path": path,
            },
        )
        self._requests[request_id] = (command_text, response)
        self._persist_after_mutation()
        return response

    def set_component(self, entity, component, data, request_id,
                      command_text, expected_revision=None,
                      expected_entity_revision=None):
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
            expected_entity_revision: Entity revision the writer
                read (ENTITY-CAS). Naming a current one skips the
                global head gate even beside a stale head, so
                writers on different entities never conflict; a
                stale entity revision fails with revision_conflict.

        Returns:
            Mutation mapping with entity, component, canonical
            address, storage path, revision transition, new head,
            actor, diff summary, rewind handle, the
            component_changed event, cursor, request id, and the
            bumped entity_revision.

        Raises:
            ProjectError: request_conflict for a reused id with
                new text; invalid_entity, invalid_component, or
                invalid_data for malformed parts; unknown_entity
                for a missing entity; backfill_readonly for a
                backfilled id; invalid_document for a corrupt
                entity record; revision_conflict for a stale head
                or a stale entity revision; invalid_ledger when
                the durable write fails.

        Caution: Every accepted write advances the revision — a
            second writer at the old head fails instead of
            merging, unless it names a current entity
            revision.
        """
        self._refresh_durable()
        replay = self._check_replay(request_id, command_text)
        if replay is not None:
            return replay
        try:
            ecs.validate_entity_id(entity)
            ecs.validate_component_name(component)
            ecs.validate_component_data(data)
        except ecs.EcsError as exc:
            raise ProjectError(exc.code, str(exc)) from exc
        if ecs.is_backfill_id(entity):
            raise ProjectError(
                "backfill_readonly",
                f"Backfilled entity is read-only: {entity}.",
            )
        path, decoded = self._read_entity_record(entity)
        live = self._gate_entity_revision(
            entity, decoded, expected_entity_revision
        )
        self._gate_entity_write(expected_revision, expected_entity_revision)
        previous = self._current_revision
        self._ensure_snapshot(previous)
        existed = component in decoded["components"]
        merged = dict(decoded["components"])
        merged[component] = data
        bumped = live + 1
        old_text = self._read_doc_text(path, path)
        self._store_entity_record(
            path, entity, decoded["kind"], merged, bumped
        )
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
        address = ecs.format_address(entity, component)
        diff = f"{verb} {address} ({path})"
        record = self._append_event(
            "component_changed",
            request_id,
            ecs.component_changed_data(
                entity, component, self._current_revision,
                entity_revision=bumped,
            ),
        )
        response = self._ecs_response(
            request_id, previous, diff, record,
            {
                "address": address,
                "component": component,
                "entity": entity,
                "entity_revision": bumped,
                "path": path,
            },
        )
        self._requests[request_id] = (command_text, response)
        self._persist_after_mutation()
        return response

    def attach_component(self, entity, component, data, request_id,
                         command_text, expected_revision=None,
                         expected_entity_revision=None):
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
            expected_entity_revision: Entity revision the writer
                read (ENTITY-CAS); naming a current one skips the
                global head gate even beside a stale head.

        Returns:
            Mutation mapping with entity, component, canonical
            address, storage path, revision transition, new head,
            actor, diff summary, rewind handle, the
            component_changed event, cursor, request id, and the
            bumped entity_revision.

        Raises:
            ProjectError: component_exists when the component
                already lives on the entity; otherwise like
                set_component.

        Caution: Every accepted attach advances the revision — a
            second writer at the old head fails instead of
            merging, unless it names a current entity
            revision.
        """
        self._refresh_durable()
        replay = self._check_replay(request_id, command_text)
        if replay is not None:
            return replay
        try:
            ecs.validate_entity_id(entity)
            ecs.validate_component_name(component)
            ecs.validate_component_data(data)
        except ecs.EcsError as exc:
            raise ProjectError(exc.code, str(exc)) from exc
        if ecs.is_backfill_id(entity):
            raise ProjectError(
                "backfill_readonly",
                f"Backfilled entity is read-only: {entity}.",
            )
        path, decoded = self._read_entity_record(entity)
        if component in decoded["components"]:
            raise ProjectError(
                "component_exists",
                "Component already attached: "
                f"{ecs.format_address(entity, component)}.",
            )
        live = self._gate_entity_revision(
            entity, decoded, expected_entity_revision
        )
        self._gate_entity_write(expected_revision, expected_entity_revision)
        previous = self._current_revision
        self._ensure_snapshot(previous)
        merged = dict(decoded["components"])
        merged[component] = data
        bumped = live + 1
        old_text = self._read_doc_text(path, path)
        self._store_entity_record(
            path, entity, decoded["kind"], merged, bumped
        )
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
        address = ecs.format_address(entity, component)
        diff = f"attached {address} ({path})"
        record = self._append_event(
            "component_changed",
            request_id,
            ecs.component_changed_data(
                entity, component, self._current_revision,
                entity_revision=bumped,
            ),
        )
        response = self._ecs_response(
            request_id, previous, diff, record,
            {
                "address": address,
                "component": component,
                "entity": entity,
                "entity_revision": bumped,
                "path": path,
            },
        )
        self._requests[request_id] = (command_text, response)
        self._persist_after_mutation()
        return response

    def detach_component(self, entity, component, request_id,
                         command_text, expected_revision=None,
                         expected_entity_revision=None):
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
            expected_entity_revision: Entity revision the writer
                read (ENTITY-CAS).

        Returns:
            Mutation mapping with entity, component, canonical
            address, storage path, revision transition, new head,
            actor, diff summary, rewind handle, the
            component_changed event, cursor, request id, and the
            bumped entity_revision.

        Raises:
            ProjectError: unknown_component for a missing
                component; otherwise like set_component without
                the data errors.

        Caution: Every accepted detach advances the revision — a
            second writer at the old head fails instead of
            merging, unless it names a current entity
            revision.
        """
        self._refresh_durable()
        replay = self._check_replay(request_id, command_text)
        if replay is not None:
            return replay
        try:
            ecs.validate_entity_id(entity)
            ecs.validate_component_name(component)
        except ecs.EcsError as exc:
            raise ProjectError(exc.code, str(exc)) from exc
        if ecs.is_backfill_id(entity):
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
        live = self._gate_entity_revision(
            entity, decoded, expected_entity_revision
        )
        self._gate_entity_write(expected_revision, expected_entity_revision)
        previous = self._current_revision
        self._ensure_snapshot(previous)
        merged = dict(decoded["components"])
        del merged[component]
        bumped = live + 1
        old_text = self._read_doc_text(path, path)
        self._store_entity_record(
            path, entity, decoded["kind"], merged, bumped
        )
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
        address = ecs.format_address(entity, component)
        diff = f"detached {address} ({path})"
        record = self._append_event(
            "component_changed",
            request_id,
            ecs.component_changed_data(
                entity, component, self._current_revision,
                detached=True, entity_revision=bumped,
            ),
        )
        response = self._ecs_response(
            request_id, previous, diff, record,
            {
                "address": address,
                "component": component,
                "entity": entity,
                "entity_revision": bumped,
                "path": path,
            },
        )
        self._requests[request_id] = (command_text, response)
        self._persist_after_mutation()
        return response

    def delete_entity(self, entity, request_id, command_text,
                      expected_revision=None,
                      expected_entity_revision=None):
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
            expected_entity_revision: Entity revision the writer
                read (ENTITY-CAS).

        Returns:
            Mutation mapping with entity, storage path, revision
            transition, new head, actor, diff summary, rewind
            handle, the entity_deleted event, cursor, request id,
            and the deleted entity_revision.

        Raises:
            ProjectError: request_conflict for a reused id with
                new text; invalid_entity for a malformed id;
                unknown_entity for a missing entity;
                backfill_readonly for a backfilled id;
                invalid_document for a corrupt entity record;
                revision_conflict for a stale head or a stale
                entity revision; invalid_ledger
                when the durable delete fails.

        Caution: Deleting advances the revision like any mutation
            — stale writers fail instead of merging, unless they
            name a current entity revision.
        """
        self._refresh_durable()
        replay = self._check_replay(request_id, command_text)
        if replay is not None:
            return replay
        try:
            ecs.validate_entity_id(entity)
        except ecs.EcsError as exc:
            raise ProjectError(exc.code, str(exc)) from exc
        if ecs.is_backfill_id(entity):
            raise ProjectError(
                "backfill_readonly",
                f"Backfilled entity is read-only: {entity}.",
            )
        path, decoded = self._read_entity_record(entity)
        live = self._gate_entity_revision(
            entity, decoded, expected_entity_revision
        )
        self._gate_entity_write(expected_revision, expected_entity_revision)
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
            {"entity": entity, "entity_revision": live, "path": path},
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

    def apply_transaction(self, changes, request_id, command_text,
                          expected_revision=None):
        """Apply one atomic batch of entity changes (API-V1-EDITORS).

        Alias creation resolves LocalRef before persistence; every
        change gates CAS, and a failed late change rolls back.

        Args:
            changes: Change mappings with an op each.
            request_id: Client envelope id for idempotent replay.
            command_text: YAML command text for identity comparison.
            expected_revision: Revision the writer read.

        Returns:
            Mutation mapping with receipt, events, and cursor.

        Raises:
            ProjectError: request_conflict, revision_conflict,
                invalid_command, or the CAS refusal code.
        """
        return _editors.editor_mutation(self,
            "apply_transaction", request_id, command_text,
            expected_revision,
            lambda _store, rid, rtext, live: (
                _transactions.apply_transaction(
                    self, rid, rtext, changes, live)),
            lambda receipt: (
                f"applied {receipt.get('applied', len(changes))} "
                "changes"),
        )

    def create_shape(self, shape_type, layer, data, request_id,
                     command_text, units="nm", profile=None,
                     anchor=None, expected_revision=None):
        """Create one layout shape entity with provenance.

        Args:
            shape_type: One of rect, polygon, path, label.
            layer: Stable layer lid the shape is drawn on.
            data: Shape payload for the type.
            request_id: Client envelope id for idempotent replay.
            command_text: YAML command text for identity comparison.
            units: Coordinate units label.
            profile: Technology profile pin for provenance.
            anchor: Optional cell-port anchor.
            expected_revision: Revision the writer read.

        Returns:
            Mutation mapping with receipt, events, and cursor.

        Raises:
            ProjectError: request_conflict, revision_conflict,
                invalid_command for a malformed payload.
        """
        return _editors.editor_mutation(self,
            "create_shape", request_id, command_text,
            expected_revision,
            lambda _store, rid, rtext, live: _geometry.create_shape(
                self, rid, rtext, shape_type, layer, data,
                units=units, profile=profile, anchor=anchor,
                expected_revision=live),
            lambda receipt: (
                f"created {shape_type} shape "
                f"({receipt.get('entity')})"),
        )

    def create_sheet(self, name, request_id, command_text, title="",
                     expected_revision=None):
        """Create one schematic sheet.

        Args:
            name: Unique sheet name.
            request_id: Client envelope id for idempotent replay.
            command_text: YAML command text for identity comparison.
            title: Human title shown on the sheet frame.
            expected_revision: Revision the writer read.

        Returns:
            Mutation mapping with receipt, events, and cursor.

        Raises:
            ProjectError: request_conflict, revision_conflict,
                invalid_sheet, sheet_exists.
        """
        return _editors.editor_mutation(self,
            "create_sheet", request_id, command_text,
            expected_revision,
            lambda store, _rid, _rtext, _live: _sheets.create_sheet(
                store, self._actor, name, title=title),
            lambda receipt: (
                f"created sheet {name} ({receipt.get('sheet')})"),
        )

    def place_instance(self, sheet, symbol, x, y, request_id,
                       command_text, rotation=0, mirror=False,
                       properties=None, ref="",
                       expected_revision=None):
        """Place one symbol instance on a sheet.

        Args:
            sheet: Sheet entity id hosting the instance.
            symbol: Bare project symbol name or scoped upstream ref.
            x: X position in schematic units.
            y: Y position in schematic units.
            request_id: Client envelope id for idempotent replay.
            command_text: YAML command text for identity comparison.
            rotation: Rotation in degrees (0/90/180/270).
            mirror: Mirror flag.
            properties: Text-to-text instance properties.
            ref: Annotation reference ("" means unannotated).
            expected_revision: Revision the writer read.

        Returns:
            Mutation mapping with receipt, events, and cursor.

        Raises:
            ProjectError: request_conflict, revision_conflict,
                unknown_sheet, unknown_symbol, invalid_instance.
        """
        return _editors.editor_mutation(self,
            "place_instance", request_id, command_text,
            expected_revision,
            lambda store, _rid, _rt, _live: _instances.place_instance(
                store, self._actor, sheet, symbol, x, y,
                rotation=rotation, mirror=mirror,
                properties=properties or {}, ref=ref),
            lambda receipt: (
                f"placed {symbol} ({receipt.get('instance')})"),
        )

    def bind_block(self, parent_sheet, child_sheet, instance,
                   request_id, command_text, expected_revision=None):
        """Bind a child sheet under a parent through a block instance.

        Args:
            parent_sheet: Parent sheet entity id.
            child_sheet: Child sheet entity id.
            instance: Block instance entity id in the parent.
            request_id: Client envelope id for idempotent replay.
            command_text: YAML command text for identity comparison.
            expected_revision: Revision the writer read.

        Returns:
            Mutation mapping with receipt, events, and cursor.

        Raises:
            ProjectError: request_conflict, revision_conflict,
                unknown_sheet, unknown_instance, binding_conflict,
                invalid_hierarchy.
        """
        return _editors.editor_mutation(self,
            "bind_block", request_id, command_text,
            expected_revision,
            lambda store, _rid, _rt, _live: _hierarchy.bind_block(
                store, self._actor, parent_sheet, child_sheet,
                instance),
            lambda receipt: (
                f"bound {child_sheet} under {parent_sheet}"),
        )

    def create_symbol(self, name, pins, request_id, command_text,
                      graphics=None, properties=None,
                      expected_revision=None):
        """Create one project-owned symbol definition.

        Args:
            name: Unique symbol name.
            pins: Pin records with name, pin_type, x, and y.
            request_id: Client envelope id for idempotent replay.
            command_text: YAML command text for identity comparison.
            graphics: Editable graphics items.
            properties: Text-to-text symbol properties.
            expected_revision: Revision the writer read.

        Returns:
            Mutation mapping with receipt, events, and cursor.

        Raises:
            ProjectError: request_conflict, revision_conflict,
                invalid_symbol, symbol_exists.
        """
        return _editors.editor_mutation(self,
            "create_symbol", request_id, command_text,
            expected_revision,
            lambda store, _rid, _rt, _live: _symbols.create_symbol(
                store, self._actor, name, pins, graphics=graphics,
                properties=properties),
            lambda receipt: (
                f"created symbol {name} ({receipt.get('symbol')})"),
        )

    def create_cell(self, name, ports, request_id, command_text,
                    properties=None, expected_revision=None):
        """Create one physical cell definition.

        Args:
            name: Unique cell name.
            ports: Port records for the cell.
            request_id: Client envelope id for idempotent replay.
            command_text: YAML command text for identity comparison.
            properties: Text-to-text cell properties.
            expected_revision: Revision the writer read.

        Returns:
            Mutation mapping with receipt, events, and cursor.

        Raises:
            ProjectError: request_conflict, revision_conflict,
                invalid_cell, cell_exists.
        """
        return _editors.editor_mutation(self,
            "create_cell", request_id, command_text,
            expected_revision,
            lambda store, _rid, _rt, _live: _cells.create_cell(
                store, self._actor, name, ports,
                properties=properties),
            lambda receipt: (
                f"created cell {name} ({receipt.get('cell')})"),
        )

    def map_pins(self, symbol, cell, pin_map, request_id,
                 command_text, expected_revision=None):
        """Create or remap the pin map for one symbol-cell pair.

        Args:
            symbol: Project symbol name being linked.
            cell: Project cell name (or scoped upstream ref).
            pin_map: Explicit [{symPin, cellPin}] entries.
            request_id: Client envelope id for idempotent replay.
            command_text: YAML command text for identity comparison.
            expected_revision: Revision the writer read.

        Returns:
            Mutation mapping with receipt, events, and cursor.

        Raises:
            ProjectError: request_conflict, revision_conflict,
                unknown_symbol, unknown_cell, invalid_linkage.
        """
        return _editors.editor_mutation(self,
            "map_pins", request_id, command_text,
            expected_revision,
            lambda store, _rid, _rt, _live: _linkage.map_pins(
                store, self._actor, symbol, cell, pin_map),
            lambda receipt: f"mapped {symbol} to {cell}",
        )

    def bind_layers(self, profile, layers, request_id,
                    command_text, source="profile",
                    version="unknown", expected_revision=None):
        """Bind project layers to a technology profile and save.

        Builds the catalog from the given layers, binds it, and
        saves the report as `layers/bindings.yaml`. A missing
        binding never reinterprets geometry.

        Args:
            profile: Technology profile mapping (name, version).
            layers: Layer entries with display attributes.
            request_id: Client envelope id for idempotent replay.
            command_text: YAML command text for identity comparison.
            source: Provenance label for the profile source.
            version: Profile version pinned into the report.
            expected_revision: Revision the writer read.

        Returns:
            Mutation mapping with receipt, events, and cursor.

        Raises:
            ProjectError: request_conflict, revision_conflict,
                invalid_command for a malformed catalog.
        """
        def _run(_store, rid, rtext, live):
            catalog = _layer_catalog.LayerCatalog(
                profile=dict(profile or {}))
            for entry in layers or []:
                catalog.add_layer(
                    entry.get("name"), purpose=entry.get(
                        "purpose", "drawing"),
                    color=entry.get("color", "#ffffff"),
                    order=entry.get("order", 0),
                    visible=entry.get("visible", True))
            report = _layer_bindings.bind_layers(
                catalog, (profile or {}).get("layers", []),
                source=source, version=version)
            self.write_doc(
                "layers/bindings.yaml",
                _dump_yaml(report),
                f"{rid}:bindings", f"{rtext}\n#inner bindings",
                expected_revision=live,
            )
            return {
                "op": "bind_layers",
                "profile": report["profile"],
                "profile_version": report["profile_version"],
                "entries": report["entries"],
                "i28": {"profile": {
                    "name": report["profile"],
                    "version": report["profile_version"]}},
            }
        return _editors.editor_mutation(self,
            "bind_layers", request_id, command_text,
            expected_revision, _run,
            lambda receipt: (
                f"bound {len(receipt.get('entries', []))} layers "
                f"to {receipt.get('profile')}"),
        )

    def annotate(self, request_id, command_text, prefixes=None,
                 sheet=None, expected_revision=None):
        """Assign reference designators to unannotated instances.

        Counters continue past the highest numeric suffix already
        on the sheet set; annotated instances keep their refs.

        Args:
            request_id: Client envelope id for idempotent replay.
            command_text: YAML command text for identity comparison.
            prefixes: Optional per-symbol prefix overrides.
            sheet: Sheet entity id to scope to, or None for all.
            expected_revision: Revision the writer read.

        Returns:
            Mutation mapping with receipt, events, and cursor.

        Raises:
            ProjectError: request_conflict, revision_conflict.
        """
        return _editors.editor_mutation(self,
            "annotate", request_id, command_text,
            expected_revision,
            lambda store, _rid, _rt, _live: _frontend13.annotate(
                store, self._actor, prefixes=prefixes,
                sheet=sheet),
            lambda receipt: (
                f"annotated {len(receipt.get('annotated', []))} "
                "instances"),
        )

    def create_testbench(self, name, kind, targets, request_id,
                         command_text, probes=None, harness=None,
                         template=None, expected_revision=None):
        """Create one scoped testbench block with editable source.

        Validates the DUT scope, materializes the interface, renders
        the template source, stores the record, and saves the source.

        Args:
            name: Block name (source saved as testbench/<name>).
            kind: Template kind (spice, hdl, or cocotb).
            targets: DUT target set (primary plus additional).
            request_id: Client envelope id for idempotent replay.
            command_text: YAML command text for identity comparison.
            probes: Probe mappings inside the DUT closure.
            harness: Explicit harness binding mapping.
            template: Reserved template override (unused).
            expected_revision: Revision the writer read.

        Returns:
            Mutation mapping with receipt, events, and cursor.

        Raises:
            ProjectError: request_conflict, revision_conflict,
                invalid_kind, invalid_target, overlapping_targets,
                illegal_scope.
        """
        return _editors.editor_mutation(self,
            "create_testbench", request_id, command_text,
            expected_revision,
            lambda _store, rid, rtext, live: _testbench.create_block(
                self, rid, rtext, name, kind, targets,
                probes or [], harness or {}, template=template,
                expected_revision=live),
            lambda receipt: (
                f"created {kind} testbench {name} "
                f"({receipt.get('testbench')})"),
        )

    def regenerate_testbench(self, testbench, request_id,
                             command_text, expected_revision=None):
        """Regenerate one block to a candidate without overwriting.

        A fresh link returns a noop receipt; a drifted link renders
        the candidate beside the edited live source for adoption.

        Args:
            testbench: Testbench entity id.
            request_id: Client envelope id for idempotent replay.
            command_text: YAML command text for identity comparison.
            expected_revision: Revision the writer read.

        Returns:
            Mutation mapping with receipt, events, and cursor.

        Raises:
            ProjectError: request_conflict, revision_conflict,
                unknown_entity.
        """
        return _editors.editor_mutation(self,
            "regenerate_testbench", request_id, command_text,
            expected_revision,
            lambda _store, rid, rtext, live: (
                _testbench.regenerate_block(
                    self, rid, rtext, testbench,
                    expected_revision=live)),
            lambda receipt: (
                "testbench fresh" if receipt.get("noop")
                else f"regenerated {testbench}"),
        )

    def entity_revision(self, entity):
        """Read the live per-entity revision of one entity.

        Args:
            entity: Engine-minted entity id to inspect.

        Returns:
            Mapping with entity, head revision, and the live
            entity revision plus the I28 closure pin.

        Raises:
            ProjectError: unknown_entity for a missing id.
        """
        revision = _cas.read_entity_revision(self, entity)
        return {
            "entity": entity,
            "entity_revision": revision,
            "current_revision": self._current_revision,
            "i28": pin_closure(
                self._current_revision,
                entities={entity: revision}),
        }

    def erc_report(self, severities=None, pin_conflict=None,
                   net_pins=None):
        """Run the ERC_TESTER rule set over the schematic.

        Args:
            severities: Rule-to-severity overrides.
            pin_conflict: Pin-conflict severity overrides.
            net_pins: Materialized rows for the pin-conflict rule.

        Returns:
            Findings with verdict plus revision and I28 pin.

        Raises:
            ProjectError: invalid_command for a malformed config.
        """
        check = lambda store: _frontend13.erc_check(  # noqa: E731
            store, severities=severities, pin_conflict=pin_conflict,
            net_pins=net_pins)
        return _editors.editor_read(self, "erc_check", check)

    def graph_report(self, sheet=None, net=None, net_pins=None):
        """Report the connection graph or one net's occurrences.

        Args:
            sheet: Sheet entity id to scope to, or None for all.
            net: Net name to collect, or None for the graph.
            net_pins: Materialized rows net collection needs.

        Returns:
            Graph nodes/edges (or occurrence rows) with I28 pin.

        Raises:
            ProjectError: invalid_command for a missing net.
        """
        if net is not None:
            if not isinstance(net_pins, list):
                raise ProjectError(
                    "invalid_command",
                    "net_occurrences needs net_pins rows.")
            return {
                "net": net,
                "occurrences": _frontend13.net_occurrences(
                    net_pins, net),
                "current_revision": self._current_revision,
                "i28": pin_closure(self._current_revision),
            }
        graph = lambda store: _frontend13.connection_graph(  # noqa: E731
            store, sheet=sheet)
        return _editors.editor_read(self, "connection_graph", graph)

    def probe_report(self, instance, pin, net_pins=None):
        """Cross-probe one pin: symbol, cell, cell pin, net.

        Without extracted net_pins the probe reports net_known
        False instead of guessing.

        Args:
            instance: Instance entity id to probe.
            pin: Symbol pin to probe.
            net_pins: Materialized rows, or None when none ran.

        Returns:
            Probe mapping with I28 pin.

        Raises:
            ProjectError: unknown_instance, unknown_pin.
        """
        probe = lambda store: _frontend13.xprobe(  # noqa: E731
            store, instance, pin, net_pins=net_pins)
        return _editors.editor_read(self, "xprobe", probe)

    def plot_report(self, format="svg", sheet=None):
        """Export the schematic drawing (plot/export op).

        Args:
            format: Drawing format (svg or json).
            sheet: Sheet entity id to scope to, or None for all.

        Returns:
            Drawing with I28 pin.

        Raises:
            ProjectError: invalid_format for an unknown format.
        """
        plot = lambda store: _frontend13.plot_export(  # noqa: E731
            store, format=format, sheet=sheet)
        return _editors.editor_read(self, "plot_export", plot)

    def netlist_report(self, language, sheet=None, title="top",
                       net_pins=None, prior_text=None,
                       adopted=False):
        """Write (or rewrite and diff) a netlist for the schematic.

        Harness-owned instances stay excluded unless the design
        adopted the block. Dangling pins emit explicit stubs.

        Args:
            language: Netlist language (spice or verilog).
            sheet: Sheet entity id to scope to, or None for all.
            title: Netlist/circuit title.
            net_pins: Materialized rows (required).
            prior_text: Previously emitted text for rewrites.
            adopted: True includes adopted harness instances.

        Returns:
            Netlist text, counts, and I28 pin.

        Raises:
            ProjectError: invalid_language, invalid_command.
        """
        if not isinstance(net_pins, list):
            raise ProjectError(
                "invalid_command",
                "Netlist emission needs net_pins rows.")
        rows = list(net_pins)
        if not adopted:
            excluded = _testbench.excluded_harness_instances(self)
            rows = [row for row in rows
                    if row.get("instance") not in excluded]
        if prior_text is None:
            emit = lambda store: _frontend13.write_netlist(  # noqa: E731
                store, language=language, sheet=sheet,
                title=title, net_pins=rows)
        else:
            emit = lambda store: _frontend13.update_netlist(  # noqa: E731
                store, language, prior_text, sheet=sheet,
                title=title, net_pins=rows)
        return _editors.editor_read(self, "netlist", emit)

    def capability_report(self, profile, operation, bindings=None):
        """Check whether one operation may run under a profile.

        Args:
            profile: Technology profile mapping with name,
                version, source hash, and capabilities.
            operation: Operation name to check.
            bindings: Layer bindings the design needs.

        Returns:
            Capability verdict with profile pin and I28 pin.

        Raises:
            ProjectError: invalid_command for a malformed profile.
        """
        for key in ("name", "version", "source_hash"):
            if not isinstance(profile, dict) or not profile.get(key):
                raise ProjectError(
                    "invalid_command",
                    f"capability_report needs profile {key}.")
        tech = _process.TechProfile(
            profile["name"], profile["version"],
            profile["source_hash"],
            units=profile.get("units", "nm"),
            grid=profile.get("grid", 1),
            deck=profile.get("deck"),
            capabilities=profile.get("capabilities"),
        )
        result = _editors.editor_value_error(
            lambda: _process.check_capability(
                tech, operation, bindings or []))
        return {
            **result, "current_revision": self._current_revision,
            "i28": pin_closure(
                self._current_revision, profile=tech.pin()),
        }

    def testbench_report(self, testbench):
        """Describe one testbench block with freshness and pins.

        Args:
            testbench: Testbench entity id.

        Returns:
            Record with freshness, pins, digest, and I28 pin.

        Raises:
            ProjectError: unknown_entity for a missing block.
        """
        record = _testbench.describe_block(self, testbench)
        record["current_revision"] = self._current_revision
        return record
