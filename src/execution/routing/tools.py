"""Worker-side console op recorder in prelude shape."""

from .calls import tool_call


class ConsoleTools:
    """Worker-side console namespace: tier-2 verbs as op records.

    The recording twin of ConsoleNamespace: one explicit wrapper
    per tier-2 verb plus a generic fallback for every other op,
    each appending a canonical op-call record in the prelude shape
    (operation plus verbatim keyword arguments) and answering the
    recorded receipt. Recording never validates semantics and
    never executes — the host replays each record through shared
    dispatch after the worker exits, where admission judges it.

    Args:
        sink: Optional callable receiving every recorded entry
            besides the calls list (a JSONL writer serves).
    """

    def __init__(self, sink=None):
        self.calls = []
        self._sink = sink
        self._index = 0

    def _record(self, operation, args, kwargs):
        """Append one op record; positional args fail prelude-loud."""
        if args:
            raise TypeError(
                "op calls take keyword arguments only: %s." % operation
            )
        entry = tool_call(operation, kwargs)
        self.calls.append(entry)
        if self._sink is not None:
            self._sink(entry)
        self._index += 1
        return {"state": "recorded", "operation": operation,
                "index": self._index}

    def __getattr__(self, operation):
        """Record one call to any op by name (generic fallback)."""
        def call(*args, **kwargs):
            return self._record(operation, args, kwargs)

        return call

    def write_doc(self, *args, **kwargs):
        """Record one write_doc op call.

        Args:
            args: Rejected positionally, prelude parity.
            kwargs: Keyword op arguments recorded verbatim.

        Returns:
            Recorded receipt with state, operation, and index.

        Raises:
            TypeError: When positional args arrive (keyword-only).
        """
        return self._record("write_doc", args, kwargs)

    def delete_doc(self, *args, **kwargs):
        """Record one delete_doc op call.

        Args:
            args: Rejected positionally, prelude parity.
            kwargs: Keyword op arguments recorded verbatim.

        Returns:
            Recorded receipt with state, operation, and index.

        Raises:
            TypeError: When positional args arrive (keyword-only).
        """
        return self._record("delete_doc", args, kwargs)

    def apply_mutations(self, *args, **kwargs):
        """Record one apply_mutations op call.

        Args:
            args: Rejected positionally, prelude parity.
            kwargs: Keyword op arguments recorded verbatim.

        Returns:
            Recorded receipt with state, operation, and index.

        Raises:
            TypeError: When positional args arrive (keyword-only).
        """
        return self._record("apply_mutations", args, kwargs)

    def place_cell(self, *args, **kwargs):
        """Record one place_cell op call.

        Args:
            args: Rejected positionally, prelude parity.
            kwargs: Keyword op arguments recorded verbatim.

        Returns:
            Recorded receipt with state, operation, and index.

        Raises:
            TypeError: When positional args arrive (keyword-only).
        """
        return self._record("place_cell", args, kwargs)

    def create_entity(self, *args, **kwargs):
        """Record one create_entity op call.

        Args:
            args: Rejected positionally, prelude parity.
            kwargs: Keyword op arguments recorded verbatim.

        Returns:
            Recorded receipt with state, operation, and index.

        Raises:
            TypeError: When positional args arrive (keyword-only).
        """
        return self._record("create_entity", args, kwargs)

    def set_component(self, *args, **kwargs):
        """Record one set_component op call.

        Args:
            args: Rejected positionally, prelude parity.
            kwargs: Keyword op arguments recorded verbatim.

        Returns:
            Recorded receipt with state, operation, and index.

        Raises:
            TypeError: When positional args arrive (keyword-only).
        """
        return self._record("set_component", args, kwargs)

    def attach_component(self, *args, **kwargs):
        """Record one attach_component op call.

        Args:
            args: Rejected positionally, prelude parity.
            kwargs: Keyword op arguments recorded verbatim.

        Returns:
            Recorded receipt with state, operation, and index.

        Raises:
            TypeError: When positional args arrive (keyword-only).
        """
        return self._record("attach_component", args, kwargs)

    def detach_component(self, *args, **kwargs):
        """Record one detach_component op call.

        Args:
            args: Rejected positionally, prelude parity.
            kwargs: Keyword op arguments recorded verbatim.

        Returns:
            Recorded receipt with state, operation, and index.

        Raises:
            TypeError: When positional args arrive (keyword-only).
        """
        return self._record("detach_component", args, kwargs)

    def delete_entity(self, *args, **kwargs):
        """Record one delete_entity op call.

        Args:
            args: Rejected positionally, prelude parity.
            kwargs: Keyword op arguments recorded verbatim.

        Returns:
            Recorded receipt with state, operation, and index.

        Raises:
            TypeError: When positional args arrive (keyword-only).
        """
        return self._record("delete_entity", args, kwargs)

    def place_wire(self, *args, **kwargs):
        """Record one place_wire op call.

        Args:
            args: Rejected positionally, prelude parity.
            kwargs: Keyword op arguments recorded verbatim.

        Returns:
            Recorded receipt with state, operation, and index.

        Raises:
            TypeError: When positional args arrive (keyword-only).
        """
        return self._record("place_wire", args, kwargs)

    def place_junction(self, *args, **kwargs):
        """Record one place_junction op call.

        Args:
            args: Rejected positionally, prelude parity.
            kwargs: Keyword op arguments recorded verbatim.

        Returns:
            Recorded receipt with state, operation, and index.

        Raises:
            TypeError: When positional args arrive (keyword-only).
        """
        return self._record("place_junction", args, kwargs)

    def connect_endpoint(self, *args, **kwargs):
        """Record one connect_endpoint op call.

        Args:
            args: Rejected positionally, prelude parity.
            kwargs: Keyword op arguments recorded verbatim.

        Returns:
            Recorded receipt with state, operation, and index.

        Raises:
            TypeError: When positional args arrive (keyword-only).
        """
        return self._record("connect_endpoint", args, kwargs)

    def move_wire(self, *args, **kwargs):
        """Record one move_wire op call.

        Args:
            args: Rejected positionally, prelude parity.
            kwargs: Keyword op arguments recorded verbatim.

        Returns:
            Recorded receipt with state, operation, and index.

        Raises:
            TypeError: When positional args arrive (keyword-only).
        """
        return self._record("move_wire", args, kwargs)

    def split_wire(self, *args, **kwargs):
        """Record one split_wire op call.

        Args:
            args: Rejected positionally, prelude parity.
            kwargs: Keyword op arguments recorded verbatim.

        Returns:
            Recorded receipt with state, operation, and index.

        Raises:
            TypeError: When positional args arrive (keyword-only).
        """
        return self._record("split_wire", args, kwargs)

    def delete_wire(self, *args, **kwargs):
        """Record one delete_wire op call.

        Args:
            args: Rejected positionally, prelude parity.
            kwargs: Keyword op arguments recorded verbatim.

        Returns:
            Recorded receipt with state, operation, and index.

        Raises:
            TypeError: When positional args arrive (keyword-only).
        """
        return self._record("delete_wire", args, kwargs)

    def delete_junction(self, *args, **kwargs):
        """Record one delete_junction op call.

        Args:
            args: Rejected positionally, prelude parity.
            kwargs: Keyword op arguments recorded verbatim.

        Returns:
            Recorded receipt with state, operation, and index.

        Raises:
            TypeError: When positional args arrive (keyword-only).
        """
        return self._record("delete_junction", args, kwargs)

    def materialize_nets(self, *args, **kwargs):
        """Record one materialize_nets op call.

        Args:
            args: Rejected positionally, prelude parity.
            kwargs: Keyword op arguments recorded verbatim.

        Returns:
            Recorded receipt with state, operation, and index.

        Raises:
            TypeError: When positional args arrive (keyword-only).
        """
        return self._record("materialize_nets", args, kwargs)

    def create_project(self, *args, **kwargs):
        """Record one create_project op call.

        Args:
            args: Rejected positionally, prelude parity.
            kwargs: Keyword op arguments recorded verbatim.

        Returns:
            Recorded receipt with state, operation, and index.

        Raises:
            TypeError: When positional args arrive (keyword-only).
        """
        return self._record("create_project", args, kwargs)

    def rewind(self, *args, **kwargs):
        """Record one rewind op call.

        Args:
            args: Rejected positionally, prelude parity.
            kwargs: Keyword op arguments recorded verbatim.

        Returns:
            Recorded receipt with state, operation, and index.

        Raises:
            TypeError: When positional args arrive (keyword-only).
        """
        return self._record("rewind", args, kwargs)

    def write_settings(self, *args, **kwargs):
        """Record one write_settings op call.

        Args:
            args: Rejected positionally, prelude parity.
            kwargs: Keyword op arguments recorded verbatim.

        Returns:
            Recorded receipt with state, operation, and index.

        Raises:
            TypeError: When positional args arrive (keyword-only).
        """
        return self._record("write_settings", args, kwargs)
