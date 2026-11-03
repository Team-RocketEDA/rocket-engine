"""COALESCE-I33 unit RED — request coalescing substrate.

Tests assume `rocket_engine.execution.coalesce`: content keys
(operation + normalized arguments incl. deck hash + run.request),
revision-pinned join/register/complete fan-out over overlapping
lifetime (queued/running), and completion-then-evict (completed
results serve via idempotent fetch, never coalescing). Valid RED =
the import itself fails.
"""

import threading

import pytest


def _mod():
    from rocket_engine.execution import coalesce  # RED: missing module

    return coalesce


def _args(**overrides):
    base = {
        "cell": "amp",
        "deck": {"tool": "magic", "rules": "sky130"},
        "request": {"netlist_type": "spice", "timeout_s": 30},
        "expected_revision": "p12",
    }
    base.update(overrides)
    return base


# content keys ---------------------------------------------------------


def test_content_key_shape_names_operation_and_digest():
    key = _mod().content_key("run_drc", _args())
    assert key.startswith("i33:run_drc:")
    assert len(key.split(":")[-1]) == 64


def test_content_key_stable_across_key_order():
    first = {"b": 2, "a": [1, {"z": None, "y": True}]}
    second = {"a": [1, {"y": True, "z": None}], "b": 2}
    assert _mod().content_key("op", first) == _mod().content_key("op", second)


def test_content_key_differs_by_operation():
    args = _args()
    assert _mod().content_key("run_drc", args) != _mod().content_key(
        "run_lvs", args
    )


def test_content_key_includes_run_request_knobs():
    plain = _args()
    tweaked = _args(request={"netlist_type": "spice", "timeout_s": 60})
    assert _mod().content_key("run_drc", plain) != _mod().content_key(
        "run_drc", tweaked
    )


def test_content_key_ignores_envelope_keys():
    first = _args(expected_revision="p12")
    second = _args(expected_revision="p13")
    second["request_id"] = "stale-envelope"
    assert _mod().content_key("run_drc", first) == _mod().content_key(
        "run_drc", second
    )


def test_content_key_deck_reorder_stable_content_change_breaks():
    mod = _mod()
    base = _args()
    reordered = _args(deck={"rules": "sky130", "tool": "magic"})
    changed = _args(deck={"tool": "magic", "rules": "gf180"})
    assert mod.content_key("run_drc", base) == mod.content_key(
        "run_drc", reordered
    )
    assert mod.content_key("run_drc", base) != mod.content_key(
        "run_drc", changed
    )


def test_content_key_distinguishes_types_that_str_would_collapse():
    mod = _mod()
    assert mod.content_key("op", {"v": ("a",)}) != mod.content_key(
        "op", {"v": ["a"]}
    )
    assert mod.content_key("op", {"v": b"a"}) != mod.content_key(
        "op", {"v": "a"}
    )
    assert mod.content_key("op", {1: "a"}) != mod.content_key(
        "op", {"1": "a"}
    )
    assert mod.content_key("op", {"v": {2, 1}}) == mod.content_key(
        "op", {"v": {1, 2}}
    )


def test_deck_hash_is_content_addressed_hex():
    mod = _mod()
    digest = mod.deck_hash({"tool": "magic", "rules": ["a", "b"]})
    assert len(digest) == 64
    assert digest == mod.deck_hash({"rules": ["a", "b"], "tool": "magic"})
    assert digest != mod.deck_hash({"tool": "klayout"})


def test_normalize_arguments_pins_deck_hash_and_drops_envelope():
    mod = _mod()
    args = _args()
    normalized = mod.normalize_arguments(args)
    assert normalized["deck"] == {"deck_hash": mod.deck_hash(args["deck"])}
    assert "expected_revision" not in normalized
    assert normalized["request"] == args["request"]
    assert normalized["cell"] == "amp"
    # The caller's mapping is never mutated or aliased.
    assert args["deck"] == {"tool": "magic", "rules": "sky130"}
    normalized["request"]["timeout_s"] = 999
    assert args["request"]["timeout_s"] == 30


def test_normalize_arguments_rejects_non_mapping():
    with pytest.raises(Exception) as excinfo:
        _mod().normalize_arguments(["not", "a", "mapping"])
    assert getattr(excinfo.value, "code", None) == "invalid_arguments"


# join / register / complete --------------------------------------------


def _owned(mod=None):
    mod = mod or _mod()
    lane = mod.Coalescer()
    key = mod.content_key("run_drc", _args())
    run_id = lane.register(key, "p13", "req-owner", "run-1", "snap-1")
    assert run_id == "run-1"
    return lane, key


def test_lookup_is_pure_and_revision_pinned():
    lane, key = _owned()
    assert lane.lookup(key, "p13") == {"run_id": "run-1", "snapshot_id": "snap-1"}
    assert lane.lookup(key, "p14") is None
    assert lane.lookup("i33:run_drc:deadbeef", "p13") is None
    assert lane.requests_for("run-1") == ["req-owner"]


def test_join_fans_out_one_run_id_to_every_caller():
    lane, key = _owned()
    first = lane.join(key, "p13", "req-a")
    second = lane.join(key, "p13", "req-b")
    assert first["run_id"] == "run-1"
    assert second["run_id"] == "run-1"
    assert first["snapshot_id"] == "snap-1"
    assert lane.requests_for("run-1") == ["req-owner", "req-a", "req-b"]


def test_join_misses_when_revision_moved():
    lane, key = _owned()
    assert lane.join(key, "p14", "req-late") is None
    assert lane.requests_for("run-1") == ["req-owner"]


def test_join_and_attach_dedupe_replayed_envelopes():
    lane, key = _owned()
    lane.join(key, "p13", "req-owner")
    assert lane.requests_for("run-1") == ["req-owner"]
    waiter = lane.attach("run-1", "req-owner")
    assert waiter is not None
    assert lane.requests_for("run-1") == ["req-owner"]
    assert lane.attach("run-gone", "req-x") is None


def test_complete_delivers_completion_to_waiters_then_evicts():
    lane, key = _owned()
    joined = lane.join(key, "p13", "req-a")
    completion = {"run_id": "run-1", "state": "completed", "verdict": {"ok": 1}}
    fanned = lane.complete("run-1", completion)
    assert fanned == ["req-owner", "req-a"]
    assert lane.await_completion(joined["waiter"]) == completion
    # Completed results never coalesce: later joins miss.
    assert lane.lookup(key, "p13") is None
    assert lane.join(key, "p13", "req-late") is None
    assert lane.requests_for("run-1") == []
    assert lane.pending() == []


def test_complete_copies_so_callers_cannot_alias_state():
    lane, key = _owned()
    joined = lane.join(key, "p13", "req-a")
    completion = {"run_id": "run-1", "verdict": {"ok": 1}}
    lane.complete("run-1", completion)
    completion["verdict"]["ok"] = 999
    assert lane.await_completion(joined["waiter"]) == {
        "run_id": "run-1",
        "verdict": {"ok": 1},
    }


def test_complete_unknown_run_is_silent_noop():
    assert _mod().Coalescer().complete("run-gone", {}) == []


def test_discard_wakes_waiters_with_none_and_evicts():
    lane, key = _owned()
    joined = lane.join(key, "p13", "req-a")
    assert lane.discard("run-1") == ["req-owner", "req-a"]
    assert lane.await_completion(joined["waiter"]) is None
    assert lane.join(key, "p13", "req-late") is None
    assert lane.discard("run-1") == []


def test_await_completion_times_out_loudly():
    lane, key = _owned()
    joined = lane.join(key, "p13", "req-a")
    with pytest.raises(TimeoutError):
        lane.await_completion(joined["waiter"], timeout=0.01)


def test_register_replaces_stale_revision_without_stranding_waiters():
    lane, key = _owned()
    owner_wait = lane.join(key, "p13", "req-a")["waiter"]
    assert lane.register(key, "p15", "req-b", "run-2", "snap-2") == "run-2"
    assert lane.lookup(key, "p15")["run_id"] == "run-2"
    assert lane.lookup(key, "p13") is None
    # The displaced run still completes to its own waiters.
    lane.complete("run-1", {"run_id": "run-1", "state": "completed"})
    assert lane.await_completion(owner_wait)["run_id"] == "run-1"
    assert lane.lookup(key, "p15")["run_id"] == "run-2"


def test_register_first_wins_on_same_slot():
    lane, key = _owned()
    assert lane.register(key, "p13", "req-b", "run-2", "snap-2") == "run-1"
    assert lane.lookup(key, "p13") == {"run_id": "run-1", "snapshot_id": "snap-1"}


def test_pending_lists_joinable_runs_oldest_first():
    mod = _mod()
    lane = mod.Coalescer()
    key_a = mod.content_key("run_drc", _args())
    key_b = mod.content_key("run_lvs", _args())
    lane.register(key_b, "p13", "req-b", "run-b", "snap-b")
    lane.register(key_a, "p13", "req-a", "run-a", "snap-a")
    assert lane.pending() == ["run-b", "run-a"]


def test_concurrent_joins_share_one_owner():
    mod = _mod()
    lane = mod.Coalescer()
    key = mod.content_key("run_drc", _args())
    lane.register(key, "p13", "req-owner", "run-1", "snap-1")
    seen = []
    lock = threading.Lock()

    def _join(index):
        joined = lane.join(key, "p13", f"req-{index}")
        with lock:
            seen.append(joined["run_id"])

    threads = [threading.Thread(target=_join, args=(n,)) for n in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive()
    assert seen == ["run-1"] * 4
    assert sorted(lane.requests_for("run-1")) == sorted(
        ["req-owner"] + [f"req-{n}" for n in range(4)]
    )


def test_guard_serializes_admission_sections():
    mod = _mod()
    lane = mod.Coalescer()
    key = mod.content_key("run_drc", _args())
    # The wiring pattern: entry methods run under the guard, so
    # the guard must be reentrant — this test deadlocks otherwise.
    with lane.guard:
        assert lane.lookup(key, "p13") is None
        lane.register(key, "p13", "req-owner", "run-1", "snap-1")
        assert lane.join(key, "p13", "req-a")["run_id"] == "run-1"
        assert lane.pending() == ["run-1"]
