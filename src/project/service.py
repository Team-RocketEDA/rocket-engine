"""In-memory project service (B3): revisions, idempotency, ordered events.

Persistence and file watching arrive in later slices; this slice owns
the semantics — revision preconditions, request identity, and the
ordered event log with cursor resync.
"""

import hashlib
import uuid

from ruamel.yaml import YAML

from .errors import ProjectError


class ProjectService:
    def __init__(self, project_id, actor, current_revision="p12"):
        self._project_id = project_id
        self._actor = actor
        self._current_revision = current_revision
        self._requests = {}
        self._events = []
        self._yaml = YAML(typ="safe")

    def _cursor(self):
        return self._events[-1]["seq"] if self._events else 0

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
        return record

    def submit(self, command_text, request_id, expected_revision=None):
        try:
            command = self._yaml.load(command_text)
        except Exception as exc:
            raise ProjectError("invalid_yaml", f"Cannot parse command: {exc}") from exc
        if not isinstance(command, dict) or "operation" not in command:
            raise ProjectError("invalid_yaml", "Command must be a mapping with an operation.")
        want = expected_revision if expected_revision is not None else command.get("expected_revision")
        if want != self._current_revision:
            raise ProjectError(
                "revision_conflict",
                f"Expected revision {self._current_revision}, got {want}.",
            )
        prev = self._requests.get(request_id)
        if prev is not None:
            prev_text, prev_ack = prev
            if prev_text != command_text:
                raise ProjectError(
                    "request_conflict",
                    f"Request id reused with different input: {request_id}.",
                )
            return prev_ack
        digest = hashlib.sha1(
            f"{self._project_id}:{want}:{command_text}".encode("utf-8")
        ).hexdigest()[:12]
        ack = {
            "request_id": request_id,
            "project_id": self._project_id,
            "run_id": uuid.uuid4().hex,
            "snapshot_id": f"snapshot_{digest}",
            "state": "queued",
        }
        self._requests[request_id] = (command_text, ack)
        self._append_event("job_queued", request_id, {"run_id": ack["run_id"]})
        ack["event_cursor"] = self._cursor()
        return ack

    def command_for(self, request_id):
        """Return the admitted (command, ack) for a queued request.

        Phase 2 of submit-then-run: unknown ids raise
        `unknown_request` instead of running a stranger's job.
        """
        try:
            command_text, ack = self._requests[str(request_id)]
        except KeyError:
            raise ProjectError(
                "unknown_request", f"No queued request: {request_id}."
            ) from None
        return self._yaml.load(command_text), ack

    def snapshot(self):
        return {
            "project_id": self._project_id,
            "current_revision": self._current_revision,
            "event_cursor": self._cursor(),
        }

    def events_since(self, cursor, require_contiguous_from=None):
        if (
            require_contiguous_from is not None
            and require_contiguous_from > self._cursor()
        ):
            raise ProjectError(
                "resync_required", "Retained history is insufficient; resync."
            )
        return [e for e in self._events if e["seq"] > cursor]
