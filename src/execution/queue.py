"""Bounded deferred FIFO for prompt-ack admission (ASYNC-SUBMIT).

The queue owns order only: admission truth (durable request
mapping, coalescing, capacity) lives in `EngineRuntime`. Entries
wait here between the prompt acknowledgement and `pump`.
"""

import threading
from collections import deque


class DeferredQueue:
    """Thread-safe FIFO of admitted-but-undispatched run entries.

    Args:
        max_depth: Maximum entries held; admissions past it are
            refused by the caller, never queued.
    """

    def __init__(self, max_depth=64):
        self._max_depth = max_depth
        self._lock = threading.Lock()
        self._entries = deque()

    @property
    def max_depth(self):
        """Bound refused past, never queued past.

        Returns:
            Maximum entries held.
        """
        return self._max_depth

    def __len__(self):
        with self._lock:
            return len(self._entries)

    def put(self, entry):
        """Append one admitted entry at the tail.

        Args:
            entry: Mapping with at least a run_id key.

        Returns:
            Depth after the append.
        """
        with self._lock:
            self._entries.append(entry)
            return len(self._entries)

    def pending(self):
        """List queued run ids, oldest first.

        Returns:
            Run ids in dispatch order.
        """
        with self._lock:
            return [entry["run_id"] for entry in self._entries]

    def take(self, run_id):
        """Remove and return one queued entry by run id.

        Args:
            run_id: Entry to remove.

        Returns:
            Entry, or None when no queued entry names the id.
        """
        with self._lock:
            for entry in self._entries:
                if entry["run_id"] == run_id:
                    self._entries.remove(entry)
                    return entry
            return None

    def take_all(self):
        """Remove and return every queued entry, oldest first.

        Returns:
            Entries in dispatch order.
        """
        with self._lock:
            entries = list(self._entries)
            self._entries.clear()
            return entries
