"""Request coalescing (COALESCE-I33): identical concurrent runs execute once.

Concurrent run-submits with identical normalized content — operation
plus arguments including the deck hash plus run.request — against
the SAME project revision execute once: all callers share the run_id
and the fanned-out result, and every request_id is logged mapping to
it. Any revision move between requests forces separate executions,
because a stale verdict must never serve as fresh; ledger law (every
mutation advances the revision) makes the revision pin the whole
no-intervening-mutation check, with no second mechanism to drift.

Coalescing covers overlapping lifetime (queued/running) only:
completing a run evicts its entry, so later duplicates execute fresh
while completed results keep serving through idempotent fetch.
Forced re-runs bypass the lane entirely — the wiring never looks
them up and never registers them, so they neither join nor serve.
Direct `run()` calls (no request_id, no ledger admission) likewise
never touch the lane.

Threading: one Engine shares one Coalescer across submit threads.
`guard` serializes the lookup-admit-register admission section so
two identical submits cannot both miss; waiters park on per-entry
events outside the guard, so a 20-minute owner never blocks
admission. The guard is a reentrant leaf lock: entry methods take it
themselves and may be called while the wiring holds it, but only
short dict operations ever run under it — never event waits,
drains, or completion callbacks — so admission sections stay brief
and cannot deadlock.
"""

import copy
import hashlib
import json
import threading
from collections.abc import Mapping

try:
    from .errors import ExecutionError
except ImportError:  # standalone verification before install
    from rocket_engine.execution.errors import ExecutionError

COALESCE_VERSION = 1

# Envelope metadata, never content: two callers submitting identical
# work with different gate tokens or envelope ids still coalesce.
_ENVELOPE_KEYS = frozenset({"request_id", "expected_revision"})


def _sort_key(frozen):
    """Ordering key for frozen values: their canonical JSON bytes."""
    return json.dumps(frozen, sort_keys=True, separators=(",", ":"))


def _freeze(value):
    """Freeze any value into JSON-safe canonical parts.

    Mappings sort by frozen key (keys keep their types, so `1` and
    `"1"` never collide); sequences keep order but keep their kind
    (tuple and list stay distinct); sets sort; bytes hex-encode; and
    anything else pins its type name beside its string, so `str()`
    collisions across types cannot coalesce distinct content.
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Mapping):
        frozen = [(_freeze(key), _freeze(val)) for key, val in value.items()]
        frozen.sort(key=lambda pair: _sort_key(pair[0]))
        return {"$map": frozen}
    if isinstance(value, (list, tuple)):
        items = [_freeze(item) for item in value]
        if isinstance(value, tuple):
            return {"$tuple": items}
        return items
    if isinstance(value, (set, frozenset)):
        return {"$set": sorted((_freeze(item) for item in value), key=_sort_key)}
    if isinstance(value, (bytes, bytearray)):
        return {"$bytes": bytes(value).hex()}
    return {"$repr": [type(value).__name__, str(value)]}


def _canonical(value):
    """Canonical JSON text for frozen-safe values (see `_freeze`)."""
    return json.dumps(
        _freeze(value), sort_keys=True, separators=(",", ":"),
        ensure_ascii=True,
    )


def deck_hash(deck):
    """Hash a deck argument for content addressing.

    The hash is key-order stable and content-addressed: equal decks
    hash equally whatever their key order, and any content change
    breaks the hash — so a deck edit between submits forces a
    separate execution.

    Args:
        deck: Deck argument as submitted (usually a mapping with
            a tool key; any value hashes).

    Returns:
        Hex sha256 over the canonical encoding of the deck.
    """
    return hashlib.sha256(_canonical(deck).encode("utf-8")).hexdigest()


def normalize_arguments(arguments):
    """Normalize submitted arguments for content-key comparison.

    Envelope keys (`request_id`, `expected_revision`) are dropped —
    they steer admission, they are not work — and the deck pins to
    its content hash, so deck bytes never ride the key while deck
    edits still break it. The frozen `request` knobs (RUN-PARAMS)
    ride verbatim: callers differing in one knob submit different
    content.

    Args:
        arguments: Submitted operation arguments.

    Returns:
        Normalized copy: every argument but the envelope keys,
            with `deck` replaced by its `deck_hash` mapping when
            present. The caller's mapping is never mutated.

    Raises:
        ExecutionError: invalid_arguments for a non-mapping.
    """
    if not isinstance(arguments, Mapping):
        raise ExecutionError(
            "invalid_arguments",
            f"Arguments must be a mapping, got {arguments!r}.",
        )
    normalized = copy.deepcopy(dict(arguments))
    for key in _ENVELOPE_KEYS:
        normalized.pop(key, None)
    if "deck" in normalized:
        normalized["deck"] = {"deck_hash": deck_hash(normalized["deck"])}
    return normalized


def content_key(operation, arguments):
    """Build the I33 content key for one run-submit.

    Args:
        operation: Cataloged operation name.
        arguments: Submitted arguments (post-freeze: `request`
            already carries every knob, so an omitted `request`
            and an explicit all-defaults `request` key alike).

    Returns:
        Key text `i33:<operation>:<digest>` with hex sha256 over
            the canonical encoding of the normalized arguments.

    Raises:
        ExecutionError: invalid_arguments for a non-mapping.
    """
    digest = hashlib.sha256(
        _canonical([operation, normalize_arguments(arguments)]).encode("utf-8")
    ).hexdigest()
    return f"i33:{operation}:{digest}"


class _Waiter:
    """Parked joiner: an event plus the cell it guards.

    Args:
        event: Set once the shared run reaches a terminal state.
        cell: Completion mapping on success, None when the run was
            discarded before completing.
    """

    def __init__(self):
        self.event = threading.Event()
        self.cell = None


class Coalescer:
    """Revision-pinned registry of live shared runs, one per project.

    Entries join by (content key, revision): a duplicate submit at
    the same head attaches to the owner's run_id, while any revision
    move misses and executes fresh. Completion evicts, so finished
    runs never coalesce. All entry operations are atomic under one
    lock; `await_completion` waits outside it.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._by_key = {}
        self._by_run = {}

    @property
    def guard(self):
        """Admission lock serializing lookup-admit-register.

        Returns:
            The coalescer's reentrant lock, for the wiring to
                hold across the submit admission section
                (lookup, ledger admit, register) so identical
                concurrent submits cannot both miss. Entry
                methods take it themselves, so calling them
                under the guard is safe. Never held across
                drains or completion waits.

        Caution: A leaf — never wait on a waiter event while
            holding it, or the owner cannot complete.
        """
        return self._lock

    def lookup(self, key, revision):
        """Find the live run sharing one key at one revision, purely.

        Args:
            key: Content key from `content_key`.
            revision: Current project head; only an entry pinned
                at this exact revision hits.

        Returns:
            Mapping with run_id and snapshot_id for the shared
                run, or None on a miss (unknown key, moved
                revision, or finished run). Never attaches.
        """
        with self._lock:
            entry = self._by_key.get(key)
            if entry is None or entry["revision"] != revision:
                return None
            return {
                "run_id": entry["run_id"],
                "snapshot_id": entry["snapshot_id"],
            }

    def join(self, key, revision, request_id):
        """Attach one request to the live shared run, if any.

        Lookup and attach are atomic: a hit guarantees the waiter
        resolves (completion or discard), never a lost wakeup.

        Args:
            key: Content key from `content_key`.
            revision: Current project head; a moved revision
                misses unconditionally.
            request_id: Joining envelope id, recorded once (a
                replayed envelope re-joins without duplicating).

        Returns:
            Mapping with run_id, snapshot_id, and the opaque
                waiter for `await_completion`, or None on a miss.
        """
        with self._lock:
            entry = self._by_key.get(key)
            if entry is None or entry["revision"] != revision:
                return None
            if request_id not in entry["request_ids"]:
                entry["request_ids"].append(request_id)
            return {
                "run_id": entry["run_id"],
                "snapshot_id": entry["snapshot_id"],
                "waiter": entry["waiter"],
            }

    def attach(self, run_id, request_id):
        """Attach one request to a live run by id.

        The wiring uses this after logging the coalesced request:
        a run evicted between lookup and attach answers None, and
        the caller falls back to the stored completion (the run
        event precedes eviction, so fetch cannot miss).

        Args:
            run_id: Live shared run id from `lookup`.
            request_id: Joining envelope id, recorded once.

        Returns:
            Opaque waiter for `await_completion`, or None when
                the run already finished.
        """
        with self._lock:
            entry = self._by_run.get(run_id)
            if entry is None:
                return None
            if request_id not in entry["request_ids"]:
                entry["request_ids"].append(request_id)
            return entry["waiter"]

    def register(self, key, revision, request_id, run_id, snapshot_id):
        """Register a fresh execution as the join target for its key.

        A same-slot collision (impossible under the guard) keeps
        the first run; a re-registration at a new revision replaces
        the join target while the displaced run keeps its own entry
        until it completes, so its waiters are never stranded.

        Args:
            key: Content key from `content_key`.
            revision: Post-admission project head the run pins.
            request_id: Owning envelope id.
            run_id: Fresh execution id.
            snapshot_id: Ack snapshot the run drains under.

        Returns:
            Run id now serving the key (the existing one on a
                same-slot collision, else the fresh one).
        """
        with self._lock:
            live = self._by_key.get(key)
            if live is not None and live["revision"] == revision:
                # Same slot, second owner: the first run keeps
                # serving; the newcomer drains its own admission
                # unshared, so its envelope stays out of the
                # fan-out mapping.
                return live["run_id"]
            entry = {
                "key": key,
                "revision": revision,
                "request_ids": [request_id],
                "run_id": run_id,
                "snapshot_id": snapshot_id,
                "waiter": _Waiter(),
            }
            self._by_key[key] = entry
            self._by_run[run_id] = entry
            return run_id

    def complete(self, run_id, completion):
        """Evict a finished run and deliver its completion to waiters.

        Args:
            run_id: Run that reached a terminal state.
            completion: Completion mapping fanned out to every
                joined waiter (a copy is stored; the caller's
                mapping is never aliased).

        Returns:
            Fanned-out request ids, owner first; empty when the
                run was never registered or already finished.
        """
        with self._lock:
            entry = self._by_run.pop(run_id, None)
            if entry is None:
                return []
            if self._by_key.get(entry["key"]) is entry:
                del self._by_key[entry["key"]]
            entry["waiter"].cell = copy.deepcopy(completion)
            entry["waiter"].event.set()
            return list(entry["request_ids"])

    def discard(self, run_id):
        """Evict a run with no completion, waking waiters empty.

        The wiring calls this only when the owner cannot complete
        (its drain raised despite containment): waiters then fall
        back to the stored completion, or fail loudly when the run
        truly finished with nothing stored.

        Args:
            run_id: Run to drop without completing.

        Returns:
            Woken request ids, owner first; empty when the run
                was never registered or already finished.
        """
        with self._lock:
            entry = self._by_run.pop(run_id, None)
            if entry is None:
                return []
            if self._by_key.get(entry["key"]) is entry:
                del self._by_key[entry["key"]]
            entry["waiter"].event.set()
            return list(entry["request_ids"])

    def await_completion(self, waiter, timeout=None):
        """Wait for a joined run's completion.

        Args:
            waiter: Opaque waiter from `join` or `attach`.
            timeout: Maximum seconds to wait; waits as long as
                the owner lives when omitted (its terminal path
                always wakes its waiters).

        Returns:
            Completion mapping, or None when the run was
                discarded before completing.

        Raises:
            TimeoutError: The wait lapsed before the run finished.
        """
        if not waiter.event.wait(timeout):
            raise TimeoutError("Shared run did not finish in time.")
        return copy.deepcopy(waiter.cell)

    def requests_for(self, run_id):
        """List the request ids mapped to one live run.

        Args:
            run_id: Run to inspect.

        Returns:
            Mapped request ids, owner first; empty once the run
                finishes (its mapping lives on in the ledger).
        """
        with self._lock:
            entry = self._by_run.get(run_id)
            if entry is None:
                return []
            return list(entry["request_ids"])

    def pending(self):
        """List joinable shared runs, oldest first.

        Returns:
            Run ids with a live join target.
        """
        with self._lock:
            return [entry["run_id"] for entry in self._by_key.values()]
