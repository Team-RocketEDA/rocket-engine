"""Durable project ledger (LEDGER-DURABLE/I30): revisions, requests, events.

Every engine-mediated mutation advances the revision and appends an
actor-attributed event; stale `expected_revision` fails with
`revision_conflict` instead of merging. With `engine_root` the
ledger persists under `ENGINE_ROOT/projects/<id>/` (`events.yaml`
+ `ledger.yaml`, both schematized in `layout_schema.yaml`) and
survives restart; without it the service keeps the previous
in-memory behavior. Retention trims oldest-first past
`max_retained_events`; readers that demand contiguity from trimmed
history get `resync_required` and must re-read from the snapshot.
"""

import hashlib
import io
import os
import re
import tempfile
import uuid
from pathlib import Path

from ruamel.yaml import YAML

from ..interfaces.paths import join_contained
from .errors import ProjectError

DEFAULT_MAX_RETAINED_EVENTS = 10000
_EVENTS_FILENAME = "events.yaml"
_LEDGER_FILENAME = "ledger.yaml"
_REVISION_RE = re.compile(r"^(.*?)(\d+)$")
_PROJECT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")
_RUN_OUTCOMES = ("run_completed", "run_failed")


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

    Caution: A stale expected_revision fails with revision_conflict
        instead of merging — callers must re-read the snapshot and
        retry at the new head. Reads and mutations reload durable
        state first, so sequential writers through separate handles
        stay ordered; truly concurrent writers still need an
        external lock.
    """

    def __init__(self, project_id, actor, current_revision="p12",
                 engine_root=None, max_retained_events=None):
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
        self._yaml = YAML(typ="safe")
        self._dir = None
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
        digest = hashlib.sha1(
            f"{self._project_id}:{want}:{command_text}".encode("utf-8")
        ).hexdigest()[:12]
        self._current_revision = _advance_revision(want)
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
