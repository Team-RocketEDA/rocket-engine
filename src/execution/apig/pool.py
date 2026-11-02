"""Worker pool (API-GENERALIZE): in-order drain, backpressure, boot replay.

The durable request log (ProjectService) owns admission truth; the pool
owns execution order around it. `submit_request` delegates admission to
the ledger (same ack bytes, same `request_id` dedupe), then holds the
admitted run in a FIFO backlog until `drain`/`drain_ids` runs it through
the caller-supplied runner. The backlog is bounded: a full pool refuses
new admissions with a typed `pool_full` error BEFORE touching the
ledger, so a refusal never advances the revision and nothing is ever
silently dropped. Replays (same `request_id`, same text) return the
stored ack without re-enqueueing and are never refused, even when full.

Boot replay rebuilds the backlog from ledger events alone: `replay`
takes `job_queued` run ids in seq order, minus every run id with a
`run_completed`/`run_failed` event, resolves each survivor through the
caller, and drains them — so a kill mid-queue still completes every
request exactly once after reboot.
"""

from ruamel.yaml import YAML

try:
    from ..errors import ExecutionError
except ImportError:  # standalone verification before install
    from rocket_engine.execution.errors import ExecutionError

POOL_VERSION = 1
DEFAULT_MAX_DEPTH = 64

_yaml = YAML(typ="safe")


def pending_from_events(events):
    """Order admitted-but-uncompleted requests oldest first.

    Args:
        events: Ledger events with seq, event, request_id, and
            data.run_id entries.

    Returns:
        (request_id, run_id) pairs for every `job_queued` event
            without a later `run_completed`/`run_failed` event for
            the same run id, in seq order.
    """
    queued = {}
    order = []
    completed = set()
    for event in sorted(events, key=lambda e: e.get("seq", 0)):
        data = event.get("data") or {}
        run_id = data.get("run_id")
        if run_id is None:
            continue
        if event.get("event") == "job_queued":
            if run_id not in queued:
                order.append(run_id)
            queued[run_id] = event.get("request_id")
        elif event.get("event") in ("run_completed", "run_failed"):
            completed.add(run_id)
    return [
        (queued[run_id], run_id) for run_id in order if run_id not in completed
    ]


def stored_completion_from_events(events, run_id):
    """Read a run's stored completion from ledger events, if any.

    Args:
        events: Ledger events with event and data entries.
        run_id: Run to look up.

    Returns:
        Completion mapping (run_id, completed state, verdict,
            operation) from the run's `run_completed`/`run_failed`
            event, or None when the run never completed.
    """
    for event in events:
        if event.get("event") not in ("run_completed", "run_failed"):
            continue
        data = event.get("data") or {}
        if data.get("run_id") != run_id:
            continue
        return {
            "run_id": run_id,
            "state": "completed",
            "verdict": data.get("verdict"),
            "operation": data.get("operation"),
        }
    return None


def request_for_run(events, run_id):
    """Find the admitting request id for a run, if any.

    Args:
        events: Ledger events with event, request_id, and
            data.run_id entries.
        run_id: Run to trace back to its admission.

    Returns:
        Request id from the run's `job_queued` event, or None
            when no admission event names the run.
    """
    for event in events:
        if event.get("event") != "job_queued":
            continue
        data = event.get("data") or {}
        if data.get("run_id") == run_id:
            return event.get("request_id")
    return None


class ApigPool:
    """Bounded FIFO execution pool over a durable request ledger.

    Args:
        project: Project port with `submit(command_text,
            request_id, expected_revision)`, `events_since(cursor)`,
            and `command_for(request_id)` (ProjectService serves).
        runner: Callable `(operation, arguments, snapshot_id,
            request_id, run_id)` returning a completion mapping.
            Runner exceptions are recorded as failed completions,
            never raised, and the drain continues.
        max_depth: Maximum undrained backlog; admissions past it
            are refused with `pool_full`, never queued, never
            dropped silently.

    Caution: The bound applies to new admissions only — replay
        re-enqueues crash survivors past the bound rather than
        abandoning admitted work.
    """

    def __init__(self, project, runner, max_depth=DEFAULT_MAX_DEPTH):
        self._project = project
        self._runner = runner
        self._max_depth = max_depth
        self._backlog = []
        self._queued = {}
        self._acks = {}
        self._completions = {}
        self._completed_runs = None

    @property
    def max_depth(self):
        """Backlog bound refused past, not queued past.

        Returns:
            Maximum undrained backlog.
        """
        return self._max_depth

    @property
    def depth(self):
        """Current undrained backlog size.

        Returns:
            Number of admitted runs awaiting drain.
        """
        return len(self._backlog)

    def _seed_completed(self):
        if self._completed_runs is None:
            self._completed_runs = {
                run_id
                for _request_id, run_id in ()
            }
            for event in self._project.events_since(0):
                if event.get("event") in ("run_completed", "run_failed"):
                    data = event.get("data") or {}
                    if data.get("run_id") is not None:
                        self._completed_runs.add(data["run_id"])

    def submit_request(self, command_text, request_id, expected_revision=None):
        """Admit one request through the ledger, then enqueue it.

        Replays return the stored ack without re-enqueueing and are
        never refused. A full pool raises before admission, so the
        ledger never advances for a refused request.

        Args:
            command_text: YAML command mapping with an operation.
            request_id: Client envelope id; resubmitting the
                identical text returns the identical ack.
            expected_revision: Revision the writer read.

        Returns:
            Admission ack with run_id, snapshot_id, queued state,
                current revision, and event cursor.

        Raises:
            ExecutionError: pool_full when the undrained backlog
                is at its bound — names the request, the depth,
                and the bound.
            ProjectError: invalid_yaml, revision_conflict, or
                request_conflict from the ledger, untouched.
        """
        if request_id in self._acks:
            return dict(self._acks[request_id])
        if len(self._backlog) >= self._max_depth:
            raise ExecutionError(
                "pool_full",
                f"Pool saturated: {request_id} refused at "
                f"depth {len(self._backlog)}/{self._max_depth}; "
                "drain before submitting more.",
                fields=[{"depth": len(self._backlog),
                         "max_depth": self._max_depth}],
            )
        ack = self._project.submit(
            command_text, request_id, expected_revision=expected_revision
        )
        self._seed_completed()
        command = _yaml.load(command_text)
        self._acks[request_id] = dict(ack)
        if ack["run_id"] in self._completed_runs:
            return dict(ack)
        self._enqueue(
            request_id, ack["run_id"], command, ack["snapshot_id"]
        )
        return dict(ack)

    def adopt(self, request_id, run_id, command, snapshot_id):
        """Enqueue an already-admitted request without touching the ledger.

        Batch pumping and boot replay admit through this: the
        request was admitted before (its ack lives in the ledger),
        so only the backlog bound and dedupe apply here.

        Args:
            request_id: Admitting envelope id.
            run_id: Admitted run id.
            command: Parsed command mapping with operation and
                arguments.
            snapshot_id: Evidence snapshot the run pins.

        Returns:
            True when the run was enqueued, False when it was
                already queued or drained.

        Raises:
            ExecutionError: pool_full when the undrained backlog
                is at its bound.
        """
        if request_id in self._queued or request_id in self._completions:
            return False
        self._seed_completed()
        if run_id in self._completed_runs:
            return False
        if len(self._backlog) >= self._max_depth:
            raise ExecutionError(
                "pool_full",
                f"Pool saturated: {request_id} refused at "
                f"depth {len(self._backlog)}/{self._max_depth}; "
                "drain before submitting more.",
                fields=[{"depth": len(self._backlog),
                         "max_depth": self._max_depth}],
            )
        self._enqueue(request_id, run_id, command, snapshot_id)
        return True

    def _enqueue(self, request_id, run_id, command, snapshot_id):
        entry = {
            "request_id": request_id,
            "run_id": run_id,
            "operation": command.get("operation"),
            "arguments": dict(command.get("arguments") or {}),
            "snapshot_id": snapshot_id,
        }
        self._backlog.append(entry)
        self._queued[request_id] = entry

    def pending(self):
        """List undrained run ids, oldest first.

        Returns:
            Run ids in drain order.
        """
        return [entry["run_id"] for entry in self._backlog]

    def drain(self, limit=None):
        """Run undrained entries oldest first.

        Args:
            limit: Maximum completions; the whole backlog when
                omitted.

        Returns:
            Completion mappings in drain order. A raising runner
                becomes a failed completion carrying the error,
                and the drain continues past it.
        """
        run_ids = [entry["run_id"] for entry in self._backlog]
        if limit is not None:
            run_ids = run_ids[: max(0, limit)]
        return self.drain_ids(run_ids)

    def drain_ids(self, run_ids):
        """Run named backlog entries in the given order.

        Args:
            run_ids: Backlog run ids to drain, in order.

        Returns:
            Completion mappings in the given order.

        Raises:
            ExecutionError: unknown_request for a run id with no
                backlog entry.
        """
        completions = []
        for run_id in run_ids:
            entry = None
            for candidate in self._backlog:
                if candidate["run_id"] == run_id:
                    entry = candidate
                    break
            if entry is None:
                raise ExecutionError(
                    "unknown_request", f"No queued request: {run_id}."
                )
            self._backlog.remove(entry)
            del self._queued[entry["request_id"]]
            try:
                completion = self._runner(
                    entry["operation"],
                    dict(entry["arguments"]),
                    entry["snapshot_id"],
                    entry["request_id"],
                    entry["run_id"],
                )
            except Exception as exc:  # noqa: BLE001 — recorded, never raised
                code = getattr(exc, "code", type(exc).__name__)
                completion = {
                    "run_id": entry["run_id"],
                    "state": "failed",
                    "error": f"{code}: {exc}",
                    "operation": entry["operation"],
                }
            self._completions[entry["request_id"]] = completion
            self._seed_completed()
            self._completed_runs.add(entry["run_id"])
            completions.append(completion)
        return completions

    def replay(self, events, resolve):
        """Re-enqueue crash survivors from ledger events, then drain them.

        Args:
            events: Ledger events; survivors are `job_queued` run
                ids without a `run_completed`/`run_failed` event.
            resolve: Callable `request_id -> (command, ack)` for
                each survivor (ProjectService.command_for serves).

        Returns:
            Report with replayed run ids (seq order), their
                completions, and skipped entries (each with
                request_id, run_id, and reason) for survivors the
                resolver cannot serve. Skips are reported, never
                silent, and the drain continues past them.
        """
        replayed = []
        skipped = []
        for request_id, run_id in pending_from_events(events):
            if request_id in self._queued or request_id in self._completions:
                continue
            try:
                command, ack = resolve(request_id)
            except Exception as exc:  # noqa: BLE001 — reported per request
                skipped.append({
                    "request_id": request_id,
                    "run_id": run_id,
                    "reason": f"{getattr(exc, 'code', type(exc).__name__)}: {exc}",
                })
                continue
            self._acks[request_id] = dict(ack)
            self._enqueue(request_id, run_id, command, ack["snapshot_id"])
            replayed.append(run_id)
        completions = self.drain_ids(replayed)
        return {
            "replayed": replayed,
            "completions": completions,
            "skipped": skipped,
        }
