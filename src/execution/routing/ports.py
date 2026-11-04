"""Port handler seam: position-checked apply plus ack, shared by ports.

Every port handler honors position-check-then-apply: one
ledger position applies once per port, and every delivery —
first or duplicate — advances the ack. Handlers bind to the
port's own bus guard, so the check cannot drift per port.
"""

from ..ports import PositionGuard


class PortHandler:
    """One port's apply path: guard, apply, ack.

    Args:
        bus: PortBus the port is attached to.
        port: Attached port name this handler serves.
        guard: PositionGuard to check positions against; the
            port's bound bus guard when omitted.
    """

    def __init__(self, bus, port, guard=None):
        """Bind one handler to one port's guard and ack flow.

        Args:
            bus: PortBus the port is attached to.
            port: Attached port name this handler serves.
            guard: PositionGuard to check positions against;
                the port's bound bus guard when omitted.

        Returns:
            Bound handler.
        """
        self._bus = bus
        self._port = port
        self._guard = (guard if guard is not None
                       else bus.guard_for(port))

    @property
    def port(self):
        """Port name this handler serves.

        Returns:
            Attached port name.
        """
        return self._port

    @property
    def guard(self):
        """Position guard this handler checks against.

        Returns:
            The bound PositionGuard.
        """
        return self._guard

    def handle(self, event, apply):
        """Apply one event once, then ack its position.

        Args:
            event: Ledger event mapping with an integer seq.
            apply: Callable taking the event, run only when
                its position is new for the port.

        Returns:
            (applied, result) pair: applied True plus the
                apply result on first application, (False,
                None) on a duplicate position. Either way the
                position is acked.

        Raises:
            ExecutionError: invalid_command for an event
                without an integer seq, unknown_port for a
                detached port.
            Exception: Whatever apply raises propagates, and
                the position stays unapplied for redelivery.
        """
        seq = event.get("seq") if isinstance(event, dict) else None
        applied, result = self._guard.apply_once(
            self._port, seq, apply, event)
        self._bus.ack(self._port, seq)
        return applied, result

    def drain(self, apply, limit=None):
        """Drain the port backlog through one apply callable.

        Args:
            apply: Callable taking one event mapping, run
                once per ledger position.
            limit: Maximum events to deliver; the whole
                backlog when omitted.

        Returns:
            Drain record with port, delivered and applied
                counts, the acked position, and handler
                error messages.

        Raises:
            ExecutionError: unknown_port for a detached port.
        """
        return self._bus.drain(self._port, apply,
                               limit=limit, guarded=True)
