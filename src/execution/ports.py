"""Shared-engine port bus (Step 7A, ECS-FLOW slices 1-4; Step 7 notify).

One shared Engine per process serves many attached ports (stdio
by default; MCP / loopback-HTTP toggled live). A change through
any port modifies the world once; the bus re-emits the appended
ledger event to the other ports over async per-port queues with
client acks (QoS-1, NATS-JetStream style). Submit/admission stays
synchronous on the writer's path — only notification fans out
async, so a slow port never stalls writers.

Delivery model (ADR-017): at-least-once with acks; ledger
position (the event seq) is the packet id, so duplicates
collapse by position and every port handler applies
idempotently (position check, then apply) through the shared
PositionGuard. Slow consumers degrade to restart-and-resync:
the staged 10/15/20s ladder warns, quarantines (backlog
dropped), then hands a resync directive to the client, which
re-runs its idempotent onboarding ritual from the current
cursor. The engine flags, never kills: quarantine is
engine-side bookkeeping plus a resync flag, never client
state. A queue-depth ceiling beside the time threshold bounds
a port that acks slowly but never trips the ladder.

Port toggles are local-only (LOCAL-SINGLE-USER): enabling or
disabling a port, or swapping the boot profile, requires the
caller to assert a local caller; remote callers are refused
loudly instead of rewired.
"""

import threading
import time

from .errors import ExecutionError

#: Staged no-ack escalation, seconds (ADR-017 D5, tunable per
#: bus): warn, quarantine (drop backlog), resync directive.
WARN_AFTER_S = 10.0
QUARANTINE_AFTER_S = 15.0
RESYNC_AFTER_S = 20.0

#: Boot-time default port profile: stdio alone (ADR-017 D6).
BOOT_PROFILE = ("stdio",)

#: Port states: active delivery, warned past the first rung,
#: quarantined (backlog dropped, resync flag pending).
_PORT_STATES = ("active", "warned", "quarantined")


class PositionGuard:
    """Shared position-check-then-apply guard all ports use.

    QoS-1 redelivers facts; redelivery of one ledger position
    must apply once. Every port handler routes through this one
    helper so per-port hand checks cannot drift.

    Args:
        None.
    """

    def __init__(self):
        """Create a guard with no applied positions.

        Returns:
            Empty guard; every first position applies.
        """
        self._lock = threading.RLock()
        self._applied = {}

    def applies(self, port, seq):
        """Check whether one ledger position still needs applying.

        Args:
            port: Port name the position would apply on.
            seq: Ledger position (event seq) to check.

        Returns:
            True when the position is newer than everything the
                port applied before; False for a duplicate or an
                older position.

        Raises:
            ExecutionError: invalid_command for a non-integer
                position.
        """
        if (not isinstance(seq, int) or
                isinstance(seq, bool)):
            raise ExecutionError(
                "invalid_command",
                f"Position must be an integer seq, got {seq!r}.",
            )
        with self._lock:
            return (port not in self._applied or
                    seq > self._applied[port])

    def record(self, port, seq):
        """Mark one ledger position applied without calling anything.

        Args:
            port: Port name the position applied on.
            seq: Ledger position (event seq) now applied.

        Returns:
            The recorded position.

        Raises:
            ExecutionError: invalid_command for a non-integer
                position.
        """
        if (not isinstance(seq, int) or
                isinstance(seq, bool)):
            raise ExecutionError(
                "invalid_command",
                f"Position must be an integer seq, got {seq!r}.",
            )
        with self._lock:
            if (port not in self._applied or
                    seq > self._applied[port]):
                self._applied[port] = seq
            return self._applied[port]

    def apply_once(self, port, seq, func, *args, **kwargs):
        """Apply one position through func at most once per port.

        Args:
            port: Port name the position applies on.
            seq: Ledger position (event seq) to apply.
            func: Apply callable run only when the position is
                new for the port.
            args: Positional arguments forwarded to func.
            kwargs: Keyword arguments forwarded to func.

        Returns:
            (applied, result) pair: applied True plus the func
                result on first application, (False, None) on a
                duplicate position.

        Raises:
            ExecutionError: invalid_command for a non-integer
                position.
            Exception: Whatever func raises propagates, and the
                position is left unrecorded so redelivery retries.
        """
        if not self.applies(port, seq):
            return False, None
        result = func(*args, **kwargs)
        self.record(port, seq)
        return True, result


class PortBus:
    """Async per-port queues with acks over the ledger event log.

    The bus never executes and never merges: writers append to
    the ledger on their own synchronous path, then hand the
    appended events to ingest (or the Engine syncs them with
    sync_ports). Ingest fans out to every enabled push port
    without blocking — a full or silent port is quarantined,
    never a reason to stall a writer.

    Args:
        clock: Nullary callable returning seconds; time.time
            when omitted. Tests inject a manual clock so the
            ladder stays deterministic.
        warn_after: Seconds of unacked backlog before the warn
            directive (ADR-017 default 10).
        quarantine_after: Seconds of unacked backlog before the
            backlog is dropped and the port quarantines
            (default 15).
        resync_after: Seconds of unacked backlog before the
            resync directive fires (default 20).
        max_depth: Per-port queue ceiling beside the time
            ladder; a port past it quarantines immediately
            (default 1024).
    """

    def __init__(self, clock=None, warn_after=WARN_AFTER_S,
                 quarantine_after=QUARANTINE_AFTER_S,
                 resync_after=RESYNC_AFTER_S, max_depth=1024):
        self._clock = clock or time.time
        self._warn_after = float(warn_after)
        self._quarantine_after = float(quarantine_after)
        self._resync_after = float(resync_after)
        self._max_depth = int(max_depth)
        self._lock = threading.RLock()
        self._ports = {}
        self._guards = {}
        self._head = 0
        self._pumps = {}

    def _now(self):
        """Read the bus clock.

        Returns:
            Current time in seconds.
        """
        return float(self._clock())

    def _require(self, name):
        """Fetch one attached port record or fail loudly.

        Args:
            name: Port name to look up.

        Returns:
            Live port record mapping.

        Raises:
            ExecutionError: unknown_port for a detached name.
        """
        try:
            return self._ports[name]
        except KeyError:
            raise ExecutionError(
                "unknown_port", f"No such attached port: {name}."
            ) from None

    def attach(self, name, push=True, max_depth=None):
        """Attach one port to the shared world.

        Args:
            name: Port name (stdio, mcp, ide, loopback-http).
            push: True for async push delivery; False leaves
                the port pull-only (MCP default per ADR-017 D7:
                it polls the cursor log, never wakes on push).
            max_depth: Per-port queue ceiling; the bus default
                when omitted.

        Returns:
            Attached port descriptor (name, push, enabled,
                state, cursor).

        Raises:
            ExecutionError: invalid_command for a non-text or
                empty name, port_exists for an attached name.
        """
        if (not isinstance(name, str) or not name):
            raise ExecutionError(
                "invalid_command",
                f"Port needs a non-empty text name, got {name!r}.",
            )
        with self._lock:
            if name in self._ports:
                raise ExecutionError(
                    "port_exists",
                    f"Port already attached: {name}.",
                )
            depth = (int(max_depth) if max_depth is not None
                     else self._max_depth)
            record = {"name": name, "push": bool(push),
                      "enabled": True, "state": "active",
                      "resync_required": False, "queue": [],
                      "seen": 0, "acked": 0,
                      "last_ack_at": self._now(),
                      "max_depth": depth}
            self._ports[name] = record
            self._guards[name] = PositionGuard()
            return self._describe_locked(record)

    def detach(self, name):
        """Detach one port; its backlog is dropped with it.

        Args:
            name: Attached port name to remove.

        Returns:
            Detached port descriptor.

        Raises:
            ExecutionError: unknown_port for a detached name.
        """
        with self._lock:
            record = self._require(name)
            self.stop(name)
            del self._ports[name]
            self._guards.pop(name, None)
            return self._describe_locked(record)

    def guard_for(self, name):
        """Fetch one port's bound position guard.

        Args:
            name: Attached port name.

        Returns:
            The port's shared PositionGuard.

        Raises:
            ExecutionError: unknown_port for a detached name.
        """
        with self._lock:
            self._require(name)
            return self._guards[name]

    def _describe_locked(self, record):
        """Render one port record without its queued events.

        Args:
            record: Live port record mapping.

        Returns:
            Descriptor with name, push, enabled, state,
                resync_required, backlog, cursor, acked, and
                max_depth.
        """
        return {"name": record["name"], "push": record["push"],
                "enabled": record["enabled"],
                "state": record["state"],
                "resync_required": record["resync_required"],
                "backlog": len(record["queue"]),
                "cursor": record["seen"],
                "acked": record["acked"],
                "max_depth": record["max_depth"]}

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
        with self._lock:
            return self._describe_locked(self._require(name))

    @property
    def cursor(self):
        """Highest ledger position ingested across all ports.

        Returns:
            Bus head seq; ports resync to this position.
        """
        with self._lock:
            return self._head

    def _quarantine_locked(self, record, reason):
        """Quarantine one port: drop backlog, flag resync.

        The engine flags, never kills: the client process is
        untouched; only delivery stops until the client
        re-runs its onboarding ritual and resyncs.

        Args:
            record: Live port record mapping.
            reason: Why the port quarantined (ladder or depth).

        Returns:
            Quarantine directive mapping.
        """
        record["queue"].clear()
        record["state"] = "quarantined"
        record["resync_required"] = True
        return {"port": record["name"], "directive": reason,
                "resync_required": True}

    def ingest(self, events):
        """Fan appended ledger events out to every push port.

        Never blocks and never raises for port conditions: a
        port past its depth ceiling quarantines (backlog
        dropped, resync flagged) while writers and every other
        port continue. Disabled, pull-only, and quarantined
        ports are skipped — a quarantined port converges only
        through resync, never through catch-up flooding.

        Args:
            events: Ledger event mappings, each with an
                integer seq, oldest first.

        Returns:
            Per-port enqueue counts for the ports that took
                the batch.

        Raises:
            ExecutionError: invalid_command for a non-mapping
                event or a non-integer seq.
        """
        batch = list(events or [])
        for event in batch:
            if not isinstance(event, dict):
                raise ExecutionError(
                    "invalid_command",
                    f"Bus events must be mappings, got {event!r}.",
                )
            seq = event.get("seq")
            if (not isinstance(seq, int) or
                    isinstance(seq, bool)):
                raise ExecutionError(
                    "invalid_command",
                    f"Bus events need an integer seq, got {event!r}.",
                )
        counts = {}
        with self._lock:
            for event in batch:
                seq = event["seq"]
                if seq > self._head:
                    self._head = seq
                for record in self._ports.values():
                    if (not record["enabled"] or
                            not record["push"] or
                            record["state"] == "quarantined"):
                        continue
                    if seq <= record["seen"]:
                        continue
                    record["queue"].append(dict(event))
                    record["seen"] = seq
                    counts[record["name"]] = (
                        counts.get(record["name"], 0) + 1)
                    if (len(record["queue"]) >
                            record["max_depth"]):
                        self._quarantine_locked(record,
                                                "depth_ceiling")
            return counts

    def pending(self, name):
        """Read one port's queued events without consuming them.

        Args:
            name: Attached port name.

        Returns:
            Queued event copies, oldest first.

        Raises:
            ExecutionError: unknown_port for a detached name.
        """
        with self._lock:
            record = self._require(name)
            return [dict(event) for event in record["queue"]]

    def ack(self, name, seq):
        """Acknowledge delivery through one ledger position.

        Any ack — even for an already-dropped position — counts
        as client activity and refreshes the ladder clock.
        Queue entries at or below the position are dropped.

        Args:
            name: Attached port name.
            seq: Ledger position acknowledged.

        Returns:
            Ack record with port, acked position, and backlog.

        Raises:
            ExecutionError: unknown_port for a detached name,
                invalid_command for a non-integer position.
        """
        if (not isinstance(seq, int) or
                isinstance(seq, bool)):
            raise ExecutionError(
                "invalid_command",
                f"Ack needs an integer seq, got {seq!r}.",
            )
        with self._lock:
            record = self._require(name)
            if seq > record["acked"]:
                record["acked"] = seq
            record["queue"] = [event for event in record["queue"]
                               if event["seq"] > record["acked"]]
            record["last_ack_at"] = self._now()
            return {"port": name, "acked": record["acked"],
                    "backlog": len(record["queue"])}

    def port_evaluate(self):
        """Run the staged no-ack ladder over every attached port.

        A port with an unacked backlog escalates: past
        warn_after it is flagged warned, past
        quarantine_after its backlog is dropped and it
        quarantines; past resync_after the engine-side resync
        flag (the resync directive) fires for the drained
        port. Each rung fires once per episode; a port that
        keeps consuming or acking never escalates.

        Args:
            None.

        Returns:
            Directive mappings (port, directive, resync_required
                for the terminal rungs) in attach order.
        """
        directives = []
        with self._lock:
            now = self._now()
            for record in self._ports.values():
                if not record["enabled"]:
                    continue
                age = now - record["last_ack_at"]
                if record["queue"]:
                    if (age > self._warn_after and
                            record["state"] == "active"):
                        record["state"] = "warned"
                        directives.append(
                            {"port": record["name"],
                             "directive": "warn", "age_s": age})
                    if (age > self._quarantine_after and
                            record["state"] == "warned"):
                        record["queue"].clear()
                        record["state"] = "quarantined"
                        record["resync_required"] = True
                        directives.append(
                            {"port": record["name"],
                             "directive": "quarantine",
                             "age_s": age,
                             "resync_required": True})
                if (age > self._resync_after and
                        record["state"] == "quarantined" and
                        record["resync_required"] and
                        not record["queue"]):
                    directives.append(
                        {"port": record["name"],
                         "directive": "resync_required",
                         "age_s": age, "resync_required": True})
            return directives

    def port_resync(self, name, head=None):
        """Converge one port onto the current ledger head.

        The client re-runs its idempotent onboarding ritual
        from this position: the backlog is dropped, the cursor
        jumps to head, flags clear. Quarantine is dodgeable
        only through a fresh port otherwise — reconnects come
        back as new ports with fresh cursors.

        Args:
            name: Attached port name.
            head: Ledger position to converge on; the bus head
                when omitted.

        Returns:
            Resync receipt with port, cursor, state, and the
                cleared resync flag.

        Raises:
            ExecutionError: unknown_port for a detached name,
                invalid_command for a non-integer head.
        """
        if head is not None and (
                not isinstance(head, int) or
                isinstance(head, bool)):
            raise ExecutionError(
                "invalid_command",
                f"Resync head must be an integer seq, got {head!r}.",
            )
        with self._lock:
            record = self._require(name)
            target = self._head if head is None else head
            record["queue"].clear()
            record["seen"] = max(record["seen"], target)
            record["acked"] = max(record["acked"], target)
            record["state"] = "active"
            record["resync_required"] = False
            record["last_ack_at"] = self._now()
            return {"port": name, "cursor": record["seen"],
                    "state": "active",
                    "resync_required": False}

    def set_enabled(self, name, enabled, local=False):
        """Enable or disable one port live (local-only toggle).

        Disabling quarantines like a dead ship: the backlog is
        dropped and the resync flag is set, so a returning
        port must resync before it converges. Enabling never
        clears the flag — the client resyncs explicitly.

        Args:
            name: Attached port name.
            enabled: True to attach the port to live delivery,
                False to park it.
            local: Caller asserts a local (loopback/stdio)
                caller; anything else is refused loudly per
                LOCAL-SINGLE-USER.

        Returns:
            Updated port descriptor.

        Raises:
            ExecutionError: unknown_port for a detached name,
                remote_toggle_denied for a non-local caller.
        """
        if local is not True:
            raise ExecutionError(
                "remote_toggle_denied",
                "Port toggles are local-only; a remote caller "
                f"cannot change port {name}.",
            )
        with self._lock:
            record = self._require(name)
            record["enabled"] = bool(enabled)
            if not enabled:
                record["queue"].clear()
                record["state"] = "quarantined"
                record["resync_required"] = True
            return self._describe_locked(record)

    def set_profile(self, names, local=False):
        """Swap the live port profile (local-only toggle).

        Missing names attach as push ports; every other
        attached port disables like a dead ship (backlog
        dropped, resync flagged). The boot profile is stdio
        alone; MCP attaches when the agent arrives, loopback
        HTTP when the IDE wants network.

        Args:
            names: Port names forming the live profile.
            local: Caller asserts a local (loopback/stdio)
                caller; anything else is refused loudly per
                LOCAL-SINGLE-USER.

        Returns:
            Profile mapping with the enabled names sorted.

        Raises:
            ExecutionError: remote_toggle_denied for a
                non-local caller, invalid_command for a
                non-list or empty profile.
        """
        if local is not True:
            raise ExecutionError(
                "remote_toggle_denied",
                "Port profile swaps are local-only; a remote "
                "caller cannot change the profile.",
            )
        wanted = list(names or [])
        if (not isinstance(names, (list, tuple)) or
                not wanted):
            raise ExecutionError(
                "invalid_command",
                "A port profile needs a non-empty list of names.",
            )
        with self._lock:
            for name in wanted:
                if name not in self._ports:
                    self._ports[name] = {
                        "name": name, "push": True,
                        "enabled": True, "state": "active",
                        "resync_required": False, "queue": [],
                        "seen": 0, "acked": 0,
                        "last_ack_at": self._now(),
                        "max_depth": self._max_depth}
                    self._guards[name] = PositionGuard()
            for name, record in self._ports.items():
                if name in wanted:
                    record["enabled"] = True
                else:
                    record["enabled"] = False
                    record["queue"].clear()
                    record["state"] = "quarantined"
                    record["resync_required"] = True
            return {"profile": sorted(wanted)}

    def drain(self, name, handler, limit=None, guarded=True):
        """Deliver one port's backlog through a handler, then ack.

        Handlers run outside the bus lock; a slow handler never
        blocks writers or other ports. With the port's bound
        guard, a redelivered position is acknowledged but not
        re-applied. A raising handler keeps its event at the
        head of the queue and stops the drain — nothing is
        lost, nothing is acked past the failure.

        Args:
            name: Attached port name.
            handler: Callable taking one event mapping.
            limit: Maximum events to deliver; the whole
                backlog when omitted.
            guarded: True routes every position through the
                port's bound PositionGuard; False applies
                every delivery unconditionally.

        Returns:
            Drain record with port, delivered and applied
                counts, the acked position, and handler
                error messages.

        Raises:
            ExecutionError: unknown_port for a detached name.
        """
        with self._lock:
            record = self._require(name)
            guard = self._guards[name]
            batch = list(record["queue"])
            if limit is not None:
                batch = batch[:max(0, int(limit))]
            del record["queue"][:len(batch)]
        delivered = 0
        applied = 0
        errors = []
        last_seq = None
        for index, event in enumerate(batch):
            seq = event["seq"]
            try:
                if guarded:
                    did, _ = guard.apply_once(
                        name, seq, handler, event)
                else:
                    handler(event)
                    did = True
            except Exception as exc:
                with self._lock:
                    live = self._ports.get(name)
                    if live is not None:
                        live["queue"][0:0] = batch[index:]
                errors.append(f"{type(exc).__name__}: {exc}")
                break
            delivered += 1
            if did:
                applied += 1
            last_seq = seq
        if last_seq is not None:
            self.ack(name, last_seq)
        with self._lock:
            acked = self._require(name)["acked"]
        return {"port": name, "delivered": delivered,
                "applied": applied, "acked": acked,
                "errors": errors}

    def start(self, name, handler, interval=0.01):
        """Pump one port on a daemon thread until stopped.

        Args:
            name: Attached port name.
            handler: Callable taking one event mapping; its
                exceptions are contained per drain and
                retried on the next pass.
            interval: Idle seconds between passes when the
                backlog is empty.

        Returns:
            True once the pump runs.

        Raises:
            ExecutionError: unknown_port for a detached name,
                delivery_running for an already-pumped port.
        """
        with self._lock:
            self._require(name)
            if name in self._pumps:
                raise ExecutionError(
                    "delivery_running",
                    f"Port pump already runs: {name}.",
                )
            halt = threading.Event()
            worker = threading.Thread(
                target=self._pump, args=(name, handler,
                                        float(interval), halt),
                daemon=True, name=f"port-pump-{name}")
            self._pumps[name] = (worker, halt)
            worker.start()
            return True

    def _pump(self, name, handler, interval, halt):
        """Run one port pump until its halt event is set.

        Args:
            name: Attached port name.
            handler: Callable taking one event mapping.
            interval: Idle seconds between empty passes.
            halt: Threading event stopping the pump.

        Returns:
            None.
        """
        while not halt.is_set():
            try:
                out = self.drain(name, handler)
            except ExecutionError:
                return
            if not out["delivered"]:
                halt.wait(interval)

    def stop(self, name):
        """Stop one port's background pump, if any.

        Args:
            name: Attached port name.

        Returns:
            True when a pump stopped, False when the port had
                none running.
        """
        with self._lock:
            entry = self._pumps.pop(name, None)
        if entry is None:
            return False
        worker, halt = entry
        halt.set()
        if threading.current_thread() is not worker:
            worker.join(timeout=5)
        return True
