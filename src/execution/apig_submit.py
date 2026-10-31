"""Submit-immediate (API-GENERALIZE field note 2026-11-01): run by default.

Queue-by-default is rejected: `submit()` executes the job inline and
returns the same `run_id` ack shape plus the verdict payload, while
`run_job` stays for explicit/deferred/batch pumping plus idempotent
result fetch. This module is the reference implementation of that
contract over the public engine port (`submit`/`run`): it behaves
identically against a queueing engine (submit, then pump once) and a
wired immediate engine (the ack already carries the verdict, so no
second call is made). Replay and fetch paths execute at most once per
run id: the ack's run id keys a completion cache, and `fetch` reads
back through it.
"""

import uuid

try:
    from .errors import ExecutionError  # noqa: F401 — re-exported for callers
except ImportError:  # standalone verification before install
    from rocket_engine.execution.errors import ExecutionError  # noqa: F401

SUBMIT_VERSION = 1


def merge_ack_completion(ack, completion):
    """Merge an admission ack with its completion (ack shape wins on identity).

    Args:
        ack: Admission ack with run_id, snapshot_id, state, and
            revision/cursor fields.
        completion: Completion with run_id, state, verdict, and
            operation for the same run.

    Returns:
        Merged mapping: every ack identity field (request_id,
            project_id, run_id, snapshot_id, current_revision,
            event_cursor) plus the completion's state, verdict,
            and operation.
    """
    return {
        **ack,
        "state": completion["state"],
        "verdict": completion.get("verdict"),
        "operation": completion.get("operation"),
    }


class SubmitImmediate:
    """Submit-then-pump-once over the public engine port.

    Args:
        engine: Duck-typed engine port with `submit(command)` and
            `run(command)` (Engine serves).
        project_id: Project id stamped on every command.

    Caution: The completion cache is per-instance: share one
        instance per engine port when replays must not re-execute.
    """

    def __init__(self, engine, project_id):
        self._engine = engine
        self._project_id = project_id
        self._completed = {}

    def submit(self, operation, arguments, request_id=None):
        """Submit an operation and return its completion inline.

        The ack's run id is the execution id: against a queueing
        engine the job is pumped exactly once via `run_job`; against
        an immediate engine the ack already carries the verdict and
        no second call is made. Replaying a request id returns the
        stored completion without re-executing.

        Args:
            operation: Cataloged operation name.
            arguments: Operation arguments.
            request_id: Envelope id; generated when omitted.

        Returns:
            Merged ack-plus-completion mapping with run_id, queued
                revision fields, completed state, verdict, and
                operation.
        """
        request_id = request_id or uuid.uuid4().hex
        ack = self._engine.submit({
            "project_id": self._project_id,
            "operation": operation,
            "arguments": dict(arguments),
            "request_id": request_id,
        })
        if ack.get("verdict") is not None and ack.get("state") != "queued":
            self._completed[ack["run_id"]] = dict(ack)
            return dict(ack)
        if ack["run_id"] in self._completed:
            return dict(self._completed[ack["run_id"]])
        completion = self._engine.run({
            "project_id": self._project_id,
            "operation": "run_job",
            "arguments": {"run_id": ack["run_id"]},
            "request_id": f"{request_id}:pump",
        })
        merged = merge_ack_completion(ack, completion)
        self._completed[ack["run_id"]] = merged
        return dict(merged)

    def fetch(self, run_id):
        """Fetch a run's completion idempotently.

        Args:
            run_id: Run submitted through this instance.

        Returns:
            Stored completion for the run; repeated fetches return
                the identical mapping without re-executing.

        Raises:
            ExecutionError: unknown_run for an id this instance
                never completed.
        """
        try:
            return dict(self._completed[run_id])
        except KeyError:
            raise ExecutionError(
                "unknown_run", f"Unknown run: {run_id}."
            ) from None
