"""Deferred execution runtime (API-V1-CORE, ASYNC-SUBMIT, PUSH-EVENTS).

One EngineRuntime owns the ledger-facing admission state the
composition root will delegate to: durable request identity,
revision-pinned coalescing, advisory capacity, and ordered
lifecycle events. Submit acknowledges promptly with a run id and
no verdict; the deferred handle watches the run to completion
and every lifecycle step is observable through watch plus push
listeners.

Engine.submit integration seam (surface lane owns
composition.py, vocabulary.py, submit.py — this module never
imports them):
- Call: route solver operations to
  `EngineRuntime.submit(operation, arguments, request_id)`
  instead of the inline drain, returning the receipt
  (`admitted`, `run_id`, `request_id`, `snapshot_id`,
  `revision`, `event_cursor`) as the prompt acknowledgement.
- Mapping: merge the terminal completion back with
  `execution.apig.submit.merge_ack_completion(ack, completion)`
  so the ack shape plus verdict keeps the one run id; serve
  `list_survivors`, `resume_run`, `discard_run`, `cancel_job`,
  and `get_events_since` from `boot_report`, `resume`,
  `discard`, `cancel`, and `watch`.

Caution: Runs never execute on acknowledgement — pump
explicitly or construct with auto_dispatch. A disconnect after
acknowledgement never discards the request: the request/run
mapping stays queryable until resume or discard decides it.
"""

import shutil
import threading
import uuid

from .coalesce import Coalescer, content_key
from .errors import ExecutionError
from .ports import PortBus
from .queue import DeferredQueue

#: Operations that never coalesce: mutating scripts and editor
#: transactions execute fresh even with identical content.
NEVER_COALESCE = frozenset({"python_execute", "write_doc",
                            "delete_doc", "apply_mutations",
                            "write_settings", "rewind"})

#: Lifecycle kinds every run emits, in order (frontend-tooling
#: spec prompt-ack plus job_queued/started/progress/finished).
LIFECYCLE_ORDER = ("job_queued", "job_started", "job_progress",
                   "job_finished")

#: Interruptions past this count quarantine the run key until an
#: explicit quarantine override resumes it.
QUARANTINE_AFTER = 2

#: Retained event window: cursors at or below the floor fail
#: with cursor_expired plus the resubscribe path, never gaps.
RETAINED_EVENTS = 4096


def probe_host_tool(name, reason):
    """Probe one host tool without executing anything.

    Args:
        name: Binary to resolve on PATH.
        reason: BLOCKED-needs-host reason stamped when the
            binary is absent.

    Returns:
        Probe with available, name, path when found, else the
            reason and a BLOCKED verdict — loud, never a
            faked PASS.
    """
    path = shutil.which(name)
    if path is not None:
        return {"available": True, "name": name, "path": path}
    return {"available": False, "name": name, "path": None,
            "reason": reason, "verdict": "BLOCKED-needs-host"}


class DeferredHandle:
    """Prompt acknowledgement watching one run to completion.

    Args:
        runtime: EngineRuntime the run was admitted to.
        run_id: Admitted run id shared by every coalesced caller.
        receipt: Prompt acknowledgement (admitted, run_id,
            request_id, snapshot_id, revision, event_cursor —
            no verdict until the run finishes).
    """

    def __init__(self, runtime, run_id, receipt):
        self._runtime = runtime
        self._run_id = run_id
        self._receipt = dict(receipt)

    @property
    def run_id(self):
        """Admitted run id for this handle.

        Returns:
            Run id shared by every coalesced caller.
        """
        return self._run_id

    @property
    def receipt(self):
        """Prompt acknowledgement for this handle.

        Returns:
            Receipt copy (admitted plus identity fields, never
                a verdict before completion).
        """
        return dict(self._receipt)

    def poll(self):
        """Read the current run state without blocking.

        Returns:
            Status with run_id, operation, state, and verdict
                once judged.
        """
        return self._runtime.status(self._run_id)

    def wait(self, timeout=None):
        """Block until the run reaches a terminal state.

        Args:
            timeout: Maximum seconds to wait; waits with the
                run when omitted.

        Returns:
            Terminal completion for the run.

        Raises:
            TimeoutError: The wait lapsed before the run
                finished.
        """
        return self._runtime.wait_for(self._run_id, timeout=timeout)


class EngineRuntime:
    """Deferred execution runtime: prompt ack, capacity, events.

    Args:
        project_id: Project this runtime admits runs for.
        runner: Callable `(operation, arguments, snapshot_id,
            request_id, run_id)` returning a completion mapping.
            Runner exceptions become failed completions, never
            raised, and the drain continues.
        max_inflight: Maximum queued plus running runs;
            admissions past it are refused retryable with
            admitted False, never queued, never dropped
            silently.
        auto_dispatch: Dispatch admitted runs on a daemon
            worker without a client round trip; False leaves
            dispatch to explicit pump (deterministic tests).
        schemas: Optional operation to allowed-argument-names
            mapping for C01 request validation; None checks
            shapes only.
        operations: Optional known-operation names for C01
            validation; None accepts any string name and
            leaves catalog validation to the Engine seam.
    """

    def __init__(self, project_id, runner, max_inflight=64,
                 auto_dispatch=True, schemas=None,
                 operations=None):
        self._project_id = project_id
        self._runner = runner
        self._max_inflight = max_inflight
        self._auto_dispatch = auto_dispatch
        self._schemas = dict(schemas) if schemas else {}
        self._operations = (frozenset(operations)
                            if operations is not None else None)
        self._lock = threading.RLock()
        self._queue = DeferredQueue(max_depth=max_inflight)
        self._coalescer = Coalescer()
        self._ports = PortBus()
        self._requests = {}
        self._runs = {}
        self._events = []
        self._seq_floor = 0
        self._revision = 0
        self._paused = False
        self._listeners = []
        self._interruptions = {}
        self._quarantined = set()
        self._pumping = False

    def submit(self, operation, arguments, request_id=None):
        """Admit one run and acknowledge promptly without verdict.

        Reused request ids replay their stored receipt without
        re-executing (identical content) or fail with
        request_conflict (changed content). Equivalent
        in-flight observational runs share one execution across
        callers; scripts and edits always execute fresh. Past
        capacity the receipt refuses retryable with admitted
        False and no run is queued.

        Args:
            operation: Cataloged operation name.
            arguments: Operation arguments mapping.
            request_id: Client envelope id; minted when omitted.

        Returns:
            DeferredHandle watching the admitted (or shared, or
                refused) run. Refused handles carry admitted
                False, code, retryable, depth, and bound.

        Raises:
            ExecutionError: invalid_command for a malformed
                call, unsupported_operation for an unknown
                name, request_conflict for a reused envelope id
                with new content.
        """
        request_id = str(request_id or uuid.uuid4().hex)
        arguments = dict(arguments or {})
        self.validate_request(operation, arguments)
        with self._lock:
            stored = self._requests.get(request_id)
            if stored is not None:
                if (stored["operation"] != operation or
                        stored["arguments"] != arguments):
                    raise ExecutionError(
                        "request_conflict",
                        f"Request {request_id} reused with new content.",
                    )
                return DeferredHandle(
                    self, stored["run_id"], stored["receipt"])
            key = content_key(operation, arguments)
            if operation not in NEVER_COALESCE:
                with self._coalescer.guard:
                    hit = self._coalescer.lookup(key,
                                                 self._revision)
                    if hit is not None:
                        waiter = self._coalescer.attach(
                            hit["run_id"], request_id)
                        receipt = self._ack(hit["run_id"],
                                            request_id,
                                            coalesced=True)
                        self._record_request(request_id,
                                             operation,
                                             arguments, key,
                                             hit["run_id"],
                                             receipt)
                        return DeferredHandle(self,
                                              hit["run_id"],
                                              receipt)
            if self._inflight_locked() >= self._max_inflight:
                self._paused = True
                self._emit_locked("admission_paused", None,
                                  {"depth": self._inflight_locked(),
                                   "bound": self._max_inflight})
                return DeferredHandle(self, "", {
                    "admitted": False, "code": "pool_full",
                    "retryable": True, "request_id": request_id,
                    "depth": self._inflight_locked(),
                    "bound": self._max_inflight,
                    "message": "Admission saturated: drain before "
                               "submitting more.",
                })
            run_id = uuid.uuid4().hex
            snapshot_id = f"snapshot_{self._revision}"
            record = {
                "run_id": run_id, "operation": operation,
                "arguments": dict(arguments),
                "snapshot_id": snapshot_id,
                "revision": self._revision,
                "ingredients": {"revision": self._revision,
                                "operation": operation,
                                "arguments": dict(arguments)},
                "request_ids": [request_id],
                "state": "queued", "verdict": None,
                "done": threading.Event(),
            }
            self._runs[run_id] = record
            receipt = self._ack(run_id, request_id,
                                snapshot_id=snapshot_id)
            self._record_request(request_id, operation,
                                 arguments, key, run_id,
                                 receipt)
            if operation not in NEVER_COALESCE:
                with self._coalescer.guard:
                    self._coalescer.register(key,
                                             self._revision,
                                             request_id, run_id,
                                             snapshot_id)
            self._queue.put({"run_id": run_id,
                             "request_id": request_id,
                             "operation": operation,
                             "arguments": dict(arguments),
                             "snapshot_id": snapshot_id})
            self._emit_locked("job_queued", run_id, {})
            kick = self._auto_dispatch
        if kick:
            self._kick_worker()
        return DeferredHandle(self, run_id, receipt)

    def validate_request(self, operation, arguments):
        """Validate one call against the C01 request schema.

        Args:
            operation: Cataloged operation name.
            arguments: Operation arguments mapping.

        Returns:
            True when the call is well formed.

        Raises:
            ExecutionError: invalid_command for a non-mapping
                payload or an unknown semantic field,
                unsupported_operation for an unknown name.
        """
        if not isinstance(arguments, dict):
            raise ExecutionError(
                "invalid_command",
                f"Arguments must be a mapping, got {arguments!r}.",
            )
        if (self._operations is not None and
                operation not in self._operations):
            raise ExecutionError(
                "unsupported_operation",
                f"Unsupported operation: {operation}.",
            )
        allowed = self._schemas.get(operation)
        if allowed is not None:
            unknown = [key for key in arguments
                       if key not in allowed]
            if unknown:
                raise ExecutionError(
                    "invalid_command",
                    f"Unknown fields for {operation}: "
                    f"{sorted(unknown)}.",
                    fields=[{"fields": sorted(unknown)}],
                )
        return True

    def pump(self, limit=None):
        """Dispatch queued runs oldest first through the runner.

        Args:
            limit: Maximum entries to drain; the whole backlog
                when omitted.

        Returns:
            Completions in dispatch order.
        """
        entries = self._queue.take_all()
        if limit is not None:
            requeue = entries[max(0, limit):]
            entries = entries[:max(0, limit)]
            for entry in reversed(requeue):
                self._queue.put(entry)
        completions = []
        for entry in entries:
            completions.append(self._drain_one(entry))
        with self._lock:
            if (self._paused and self._inflight_locked() <
                    self._max_inflight):
                self._paused = False
                self._emit_locked("admission_resumed", None,
                                  {"depth":
                                   self._inflight_locked()})
        return completions

    def status(self, run_id):
        """Read one run's state, verdict, and operation.

        Args:
            run_id: Run to inspect.

        Returns:
            Status with run_id, operation, state, and verdict
                once judged.

        Raises:
            ExecutionError: unknown_run for an untracked id.
        """
        with self._lock:
            try:
                record = self._runs[run_id]
            except KeyError:
                raise ExecutionError(
                    "unknown_run", f"Unknown run: {run_id}."
                ) from None
            out = {"run_id": run_id,
                   "operation": record["operation"],
                   "state": record["state"]}
            if record["verdict"] is not None:
                out["verdict"] = dict(record["verdict"])
            return out

    def wait_for(self, run_id, timeout=None):
        """Block until one run reaches a terminal state.

        Args:
            run_id: Run to wait for.
            timeout: Maximum seconds to wait; waits with the
                run when omitted.

        Returns:
            Terminal completion for the run.

        Raises:
            ExecutionError: unknown_run for an untracked id.
            TimeoutError: The wait lapsed before the run
                finished.
        """
        with self._lock:
            try:
                record = self._runs[run_id]
            except KeyError:
                raise ExecutionError(
                    "unknown_run", f"Unknown run: {run_id}."
                ) from None
            done = record["done"]
        if not done.wait(timeout):
            raise TimeoutError(
                f"Run did not finish in time: {run_id}."
            )
        return self._completion_locked(run_id)

    def cancel(self, run_id, actor="unknown"):
        """Cancel one queued or running run with attribution.

        Cancelling a finished run truthfully returns its
        terminal state, never a fake cancelled. Cancellation
        needs no capacity slot: control stays responsive while
        admission is saturated.

        Args:
            run_id: Run to cancel.
            actor: Attribution for the lifecycle event.

        Returns:
            Outcome with run_id, state, actor, and verdict
                when judged.

        Raises:
            ExecutionError: unknown_run for an untracked id.
        """
        with self._lock:
            try:
                record = self._runs[run_id]
            except KeyError:
                raise ExecutionError(
                    "unknown_run", f"Unknown run: {run_id}."
                ) from None
            if record["state"] not in ("queued", "running"):
                out = {"run_id": run_id,
                       "state": record["state"], "actor": actor}
                if record["verdict"] is not None:
                    out["verdict"] = dict(record["verdict"])
                return out
            entry = self._queue.take(run_id)
            record["state"] = "cancelled"
            record["verdict"] = {"status": "NOT_RUN",
                                 "reason": "cancelled"}
            if entry is not None:
                self._coalescer.discard(run_id)
            else:
                record["cancel_requested"] = True
            self._emit_locked("job_cancelled", run_id,
                              {"actor": actor})
            record["done"].set()
            return {"run_id": run_id, "state": "cancelled",
                    "actor": actor,
                    "verdict": dict(record["verdict"])}

    def report_progress(self, run_id, fraction):
        """Report one job_progress step for a live run.

        Progress for a queued run is buffered and flushed in
        order right after job_started, so the log always reads
        queued, started, progress, finished. Progress for a
        terminal run is refused instead of logged as a lie.

        Args:
            run_id: Live run to report progress for.
            fraction: Completion fraction between 0 and 1.

        Returns:
            Emitted (or buffered) progress event.

        Raises:
            ExecutionError: unknown_run for an untracked id,
                already_decided for a terminal run.
        """
        with self._lock:
            try:
                record = self._runs[run_id]
            except KeyError:
                raise ExecutionError(
                    "unknown_run", f"Unknown run: {run_id}."
                ) from None
            if record["state"] not in ("queued", "running"):
                raise ExecutionError(
                    "already_decided",
                    f"Run already {record['state']}: {run_id}.",
                )
            record["progressed"] = True
            if record["state"] == "queued":
                pending = record.setdefault(
                    "pending_progress", [])
                event = {"seq": None, "kind": "job_progress",
                         "run_id": run_id, "fraction": fraction,
                         "buffered": True}
                pending.append(fraction)
                return event
            return self._emit_locked("job_progress", run_id,
                                     {"fraction": fraction})

    def request_ids_for(self, run_id):
        """List the request ids mapped to one run, owner first.

        Args:
            run_id: Run to inspect.

        Returns:
            Mapped request ids; empty once the run is unknown.
        """
        with self._lock:
            record = self._runs.get(run_id)
            if record is None:
                return []
            return list(record["request_ids"])

    def watch(self, cursor):
        """Read ordered lifecycle events after a cursor.

        Args:
            cursor: Opaque position from a previous read; 0
                replays the retained log.

        Returns:
            Events appended after the cursor, oldest first,
                plus the current cursor.

        Raises:
            ExecutionError: cursor_expired when the cursor is
                behind the retained floor or past the head —
                re-read the snapshot and resubscribe.
        """
        with self._lock:
            if not isinstance(cursor, int) or cursor < 0:
                raise ExecutionError(
                    "invalid_command",
                    f"Invalid event cursor: {cursor!r}.",
                )
            head = self._seq_floor + len(self._events)
            if cursor < self._seq_floor or cursor > head:
                raise ExecutionError(
                    "cursor_expired",
                    f"Cursor {cursor} expired: re-read the "
                    f"snapshot and resubscribe from {head}.",
                )
            events = [dict(event) for event in
                      self._events[cursor - self._seq_floor:]]
            return {"events": events, "cursor": head}

    def add_listener(self, callback):
        """Subscribe one push listener to lifecycle events.

        Args:
            callback: Called synchronously with each emitted
                event mapping. Listener exceptions are
                contained so one bad subscriber never breaks
                admission or dispatch.

        Returns:
            Unsubscribe callable removing the listener.
        """
        with self._lock:
            self._listeners.append(callback)

        def unsubscribe():
            """Remove the subscribed push listener.

            Returns:
                True when the listener was still subscribed.
            """
            with self._lock:
                if callback in self._listeners:
                    self._listeners.remove(callback)
                    return True
                return False

        return unsubscribe

    def pause_visible(self):
        """Check whether admission saturation is signalled.

        Returns:
            True while a refusal is outstanding against the
                bound; False once capacity frees.
        """
        with self._lock:
            return self._paused

    def attach_port(self, name, push=True, max_depth=None):
        """Attach one notify port to the lifecycle event log.

        Every appended lifecycle event fans out to the port's
        async queue; the writer's path never waits for it.

        Args:
            name: Port name (stdio, mcp, ide, loopback-http).
            push: True for async push delivery; False leaves
                the port pull-only over watch.
            max_depth: Per-port queue ceiling; the bus default
                when omitted.

        Returns:
            Attached port descriptor.

        Raises:
            ExecutionError: invalid_command for a bad name,
                port_exists for an attached name.
        """
        return self._ports.attach(name, push=push,
                                 max_depth=max_depth)

    def detach_port(self, name):
        """Detach one notify port; its backlog is dropped.

        Args:
            name: Attached port name to remove.

        Returns:
            Detached port descriptor.

        Raises:
            ExecutionError: unknown_port for a detached name.
        """
        return self._ports.detach(name)

    def port_state(self, name):
        """Read one port's engine-side bookkeeping.

        Args:
            name: Attached port name.

        Returns:
            Descriptor with name, push, enabled, state,
                resync_required, backlog, cursor, acked, and
                max_depth.

        Raises:
            ExecutionError: unknown_port for a detached name.
        """
        return self._ports.port_state(name)

    def port_pending(self, name):
        """Read one port's queued lifecycle events.

        Args:
            name: Attached port name.

        Returns:
            Queued event copies, oldest first.

        Raises:
            ExecutionError: unknown_port for a detached name.
        """
        return self._ports.pending(name)

    def port_ack(self, name, seq):
        """Acknowledge delivery through one ledger position.

        Args:
            name: Attached port name.
            seq: Lifecycle position acknowledged.

        Returns:
            Ack record with port, acked position, and backlog.

        Raises:
            ExecutionError: unknown_port for a detached name,
                invalid_command for a non-integer position.
        """
        return self._ports.ack(name, seq)

    def port_drain(self, name, handler, limit=None,
                   guarded=True):
        """Deliver one port's backlog through a handler.

        Args:
            name: Attached port name.
            handler: Callable taking one event mapping.
            limit: Maximum events to deliver; the whole
                backlog when omitted.
            guarded: True applies each position once through
                the port's bound guard.

        Returns:
            Drain record with delivered and applied counts,
                the acked position, and handler errors.

        Raises:
            ExecutionError: unknown_port for a detached name.
        """
        return self._ports.drain(name, handler, limit=limit,
                                guarded=guarded)

    def port_evaluate(self):
        """Run the staged no-ack ladder over every port.

        Args:
            None.

        Returns:
            Directive mappings in attach order.
        """
        return self._ports.port_evaluate()

    def port_resync(self, name, head=None):
        """Converge one port onto the current lifecycle head.

        Args:
            name: Attached port name.
            head: Position to converge on; the bus head when
                omitted.

        Returns:
            Resync receipt with port, cursor, and state.

        Raises:
            ExecutionError: unknown_port for a detached name,
                invalid_command for a non-integer head.
        """
        return self._ports.port_resync(name, head=head)

    def set_port_enabled(self, name, enabled, local=False):
        """Enable or disable one port live (local-only).

        Args:
            name: Attached port name.
            enabled: True for live delivery, False to park
                the port (backlog dropped, resync flagged).
            local: Caller asserts a local caller; anything
                else is refused loudly.

        Returns:
            Updated port descriptor.

        Raises:
            ExecutionError: unknown_port for a detached name,
                remote_toggle_denied for a non-local caller.
        """
        return self._ports.set_enabled(name, enabled,
                                      local=local)

    def set_port_profile(self, names, local=False):
        """Swap the live port profile (local-only toggle).

        Args:
            names: Port names forming the live profile.
            local: Caller asserts a local caller; anything
                else is refused loudly.

        Returns:
            Profile mapping with the enabled names sorted.

        Raises:
            ExecutionError: remote_toggle_denied for a
                non-local caller, invalid_command for a bad
                profile.
        """
        return self._ports.set_profile(names, local=local)

    def apply_edit(self):
        """Advance the revision cursor for one editor commit.

        Editor commits ride their own lane: they never wait
        behind solver capacity and only move the coalescing
        cursor so later submissions execute fresh.

        Returns:
            New revision.
        """
        with self._lock:
            self._revision += 1
            return self._revision

    def boot_report(self):
        """Report unfinished survivors without executing any.

        Returns:
            Survivors (admitted but unfinished run ids),
                interrupted runs, and quarantined runs.
        """
        with self._lock:
            survivors = [run_id for run_id, record in
                         self._runs.items()
                         if record["state"] in ("queued",
                                                "running")]
            return {"survivors": survivors,
                    "interrupted": sorted(
                        run_id for run_id, count in
                        self._interruptions.items() if count),
                    "quarantined": sorted(self._quarantined)}

    def resume(self, run_id, override_quarantine=False):
        """Explicitly resume one survivor through the runner.

        Args:
            run_id: Survivor to execute now.
            override_quarantine: Required to resume a run
                quarantined after repeated interruptions.

        Returns:
            Terminal completion for the run.

        Raises:
            ExecutionError: unknown_run for an untracked id,
                poison_quarantined without an explicit
                override, already_decided for a discarded run.
        """
        with self._lock:
            try:
                record = self._runs[run_id]
            except KeyError:
                raise ExecutionError(
                    "unknown_run", f"Unknown run: {run_id}."
                ) from None
            if record["state"] == "discarded":
                raise ExecutionError(
                    "already_decided",
                    f"Run already discarded: {run_id}.",
                )
            if (run_id in self._quarantined and
                    not override_quarantine):
                raise ExecutionError(
                    "poison_quarantined",
                    f"Run quarantined after repeated "
                    f"interruptions: {run_id}.",
                )
            if record["state"] not in ("queued", "running"):
                return self._completion_locked(run_id)
            entry = self._queue.take(run_id)
            if entry is None:
                entry = {"run_id": run_id,
                         "request_id":
                         record["request_ids"][0],
                         "operation": record["operation"],
                         "arguments": dict(
                             record["arguments"]),
                         "snapshot_id":
                         record["snapshot_id"]}
        return self._drain_one(entry)

    def discard(self, run_id):
        """Explicitly discard one survivor without executing it.

        Args:
            run_id: Survivor to discard.

        Returns:
            Discard record with run_id and discarded state.

        Raises:
            ExecutionError: unknown_run for an untracked id.
        """
        with self._lock:
            try:
                record = self._runs[run_id]
            except KeyError:
                raise ExecutionError(
                    "unknown_run", f"Unknown run: {run_id}."
                ) from None
            self._queue.take(run_id)
            record["state"] = "discarded"
            record["done"].set()
            self._coalescer.discard(run_id)
            self._emit_locked("job_cancelled", run_id,
                              {"reason": "discarded"})
            return {"run_id": run_id, "state": "discarded"}

    def note_interruption(self, run_id):
        """Record one ambiguous interruption toward quarantine.

        Args:
            run_id: Run interrupted before a terminal state.

        Returns:
            Interruption count for the run.
        """
        with self._lock:
            count = self._interruptions.get(run_id, 0) + 1
            self._interruptions[run_id] = count
            if count >= QUARANTINE_AFTER:
                self._quarantined.add(run_id)
            return count

    def check_drift(self, run_id, current):
        """Compare pinned ingredients against current inputs.

        Args:
            run_id: Run whose pinned ingredients to check.
            current: Current input mapping with revision,
                operation, and arguments.

        Returns:
            Drift report with drifted, changed fields, pinned
                snapshot, and current snapshot.

        Raises:
            ExecutionError: unknown_run for an untracked id.
        """
        with self._lock:
            try:
                record = self._runs[run_id]
            except KeyError:
                raise ExecutionError(
                    "unknown_run", f"Unknown run: {run_id}."
                ) from None
            pinned = record["ingredients"]
        changed = sorted(
            key for key in ("revision", "operation",
                            "arguments")
            if pinned.get(key) != current.get(key))
        return {"run_id": run_id, "drifted": bool(changed),
                "changed": changed,
                "pinned": dict(pinned), "current": dict(current)}

    def _inflight_locked(self):
        """Count queued plus running runs under the lock.

        Returns:
            Undrained run count.
        """
        return sum(1 for record in self._runs.values()
                   if record["state"] in ("queued", "running"))

    def _ack(self, run_id, request_id, coalesced=False,
             snapshot_id=None):
        """Build the prompt acknowledgement receipt.

        Args:
            run_id: Admitted run id.
            request_id: Client envelope id.
            coalesced: True when the caller joined a shared run.
            snapshot_id: Evidence snapshot the run pins.

        Returns:
            Receipt with admitted, identity fields, queued
                state, revision, and event cursor — never a
                verdict.
        """
        ack = {"admitted": True, "project_id":
               self._project_id, "run_id": run_id,
               "request_id": request_id,
               "snapshot_id": snapshot_id or
               f"snapshot_{self._revision}",
               "state": "queued", "revision": self._revision,
               "event_cursor": self._seq_floor +
               len(self._events)}
        if coalesced:
            ack["coalesced"] = True
        return ack

    def _record_request(self, request_id, operation, arguments,
                        key, run_id, receipt):
        """Persist the durable request/run identity mapping.

        Args:
            request_id: Client envelope id.
            operation: Admitted operation name.
            arguments: Admitted arguments copy.
            key: Content key for the submission.
            run_id: Admitted run id.
            receipt: Prompt acknowledgement for replays.
        """
        self._requests[request_id] = {
            "run_id": run_id, "operation": operation,
            "arguments": dict(arguments), "key": key,
            "receipt": dict(receipt),
        }
        record = self._runs.get(run_id)
        if (record is not None and request_id not in
                record["request_ids"]):
            record["request_ids"].append(request_id)

    def _emit_locked(self, kind, run_id, data):
        """Append one lifecycle event and push to listeners.

        Args:
            kind: Lifecycle kind (job_queued, job_started,
                job_progress, job_finished, job_cancelled,
                admission_paused, admission_resumed).
            run_id: Run the event belongs to, if any.
            data: Event payload fields.

        Returns:
            Emitted event with seq, kind, run_id, and cursor.
        """
        seq = self._seq_floor + len(self._events) + 1
        event = {"seq": seq, "kind": kind, "run_id": run_id,
                 "cursor": seq}
        event.update(dict(data or {}))
        record = self._runs.get(run_id) if run_id else None
        if record is not None:
            event.setdefault("operation",
                             record["operation"])
            if record["request_ids"]:
                event.setdefault("request_id",
                                 record["request_ids"][0])
        self._events.append(event)
        if len(self._events) > RETAINED_EVENTS:
            overflow = len(self._events) - RETAINED_EVENTS
            del self._events[:overflow]
            self._seq_floor += overflow
        for callback in list(self._listeners):
            try:
                callback(dict(event))
            except Exception:  # noqa: BLE001 — contained
                continue
        # Port fan-out rides the same appended event: ingest is
        # non-blocking and quarantines slow ports instead of
        # stalling the writer, so emission never fails here.
        self._ports.ingest([event])
        return dict(event)

    def _completion_locked(self, run_id):
        """Build the terminal completion for a finished run.

        Args:
            run_id: Run to report.

        Returns:
            Completion with run_id, state, operation, and
                verdict when judged.
        """
        record = self._runs[run_id]
        out = {"run_id": run_id, "state": record["state"],
               "operation": record["operation"]}
        if record["verdict"] is not None:
            out["verdict"] = dict(record["verdict"])
        if record.get("reason") is not None:
            out["reason"] = record["reason"]
        return out

    def _drain_one(self, entry):
        """Run one queued entry through the runner, contained.

        Args:
            entry: Queue entry with run_id, request_id,
                operation, arguments, and snapshot_id.

        Returns:
            Terminal completion for the run.
        """
        run_id = entry["run_id"]
        with self._lock:
            record = self._runs.get(run_id)
            if record is None or record["state"] != "queued":
                return self._completion_locked(run_id)
            record["state"] = "running"
            self._emit_locked("job_started", run_id, {})
            pending = record.pop("pending_progress", [])
            for fraction in pending:
                self._emit_locked("job_progress", run_id,
                                  {"fraction": fraction})
            if not record.get("progressed"):
                self._emit_locked("job_progress", run_id,
                                  {"fraction": 0.0,
                                   "synthetic": True})
            arguments = dict(entry["arguments"])
            snapshot_id = entry["snapshot_id"]
            request_id = entry["request_id"]
            operation = entry["operation"]
        try:
            completion = self._runner(operation, arguments,
                                      snapshot_id, request_id,
                                      run_id)
        except Exception as exc:  # noqa: BLE001 — recorded
            completion = {"run_id": run_id, "state": "failed",
                          "operation": operation,
                          "error": f"{type(exc).__name__}: {exc}",
                          "verdict": {"status": "NOT_RUN",
                                      "reason": str(exc)}}
        with self._lock:
            record = self._runs.get(run_id)
            if record is not None and record["state"] == \
                    "running":
                if record.get("cancel_requested"):
                    record["state"] = "cancelled"
                    record["verdict"] = {"status": "NOT_RUN",
                                         "reason": "cancelled"}
                    self._emit_locked("job_cancelled", run_id,
                                      {})
                else:
                    record["state"] = completion.get(
                        "state", "completed")
                    record["verdict"] = completion.get(
                        "verdict")
                    if completion.get("reason") is not None:
                        record["reason"] = completion[
                            "reason"]
                    self._emit_locked("job_finished", run_id,
                                      {"verdict":
                                       record["verdict"]})
                record["done"].set()
            if run_id in self._runs:
                self._coalescer.complete(
                    run_id, self._completion_locked(run_id))
            if (self._paused and self._inflight_locked() <
                    self._max_inflight):
                self._paused = False
                self._emit_locked("admission_resumed", None,
                                  {"depth":
                                   self._inflight_locked()})
            return self._completion_locked(run_id)

    def _kick_worker(self):
        """Start the background dispatcher when idle.

        Returns:
            True when a worker was started.
        """
        with self._lock:
            if self._pumping or not self._queue.pending():
                return False
            self._pumping = True

        def _work():
            try:
                while self._queue.pending():
                    entries = self._queue.take_all()
                    for entry in entries:
                        self._drain_one(entry)
            finally:
                with self._lock:
                    self._pumping = False
                    if (self._paused and
                            self._inflight_locked() <
                            self._max_inflight):
                        self._paused = False
                        self._emit_locked("admission_resumed",
                                          None, {"depth":
                                                 self._inflight_locked()})

        worker = threading.Thread(target=_work, daemon=True,
                                  name="engine-runtime-drain")
        worker.start()
        return True

