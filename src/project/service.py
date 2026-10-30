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
import io
import os
import re
import shutil
import tempfile
import uuid
from pathlib import Path

from ruamel.yaml import YAML

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
        try:
            if dest.is_symlink() or dest.is_file():
                dest.unlink()
            elif dest.is_dir():
                shutil.rmtree(dest)
            dest.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ProjectError(
                "invalid_ledger",
                f"Cannot snapshot revision {revision}: {exc}.",
            ) from exc
        for rel, _size in self._iter_doc_files():
            try:
                data = self._doc_path(rel).read_bytes()
            except OSError as exc:
                raise ProjectError(
                    "invalid_ledger",
                    f"Cannot snapshot {rel}: {exc}.",
                ) from exc
            target = dest / rel
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                _atomic_write_bytes(target, data)
            except OSError as exc:
                raise ProjectError(
                    "invalid_ledger",
                    f"Cannot snapshot {rel}: {exc}.",
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
