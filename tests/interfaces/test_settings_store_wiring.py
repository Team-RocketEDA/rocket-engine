"""SETTINGS-STORE wiring tests — CRUD/query exposure (integrator-run).

Run AFTER the integrator applies docs/work/SETTINGS-STORE/wiring.patch
and reinstalls the package. Before that the whole module skips: the
names are unwired and the installed package lacks the store.

Wired surface under test:
  - OPERATIONS carries write_settings (immediate, CRUD precedent:
    revision gate + idempotent request ids + ledger event, persisted
    as settings/<kind>.yaml documents).
  - QUERIES carries read_settings + get_resolved_config.
  - Reads treat absent files as defaults (absent-default-is-clean);
    writes validate, refuse future on-disk files, merge onto the
    stored bytes, and skip unchanged bytes without a new revision.
"""

import importlib.util

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("rocket_engine.interfaces.settings_store")
    is None,
    reason="SETTINGS-STORE wiring not applied yet",
)

PROJECT = "settings_demo"


def _submit(engine, operation, arguments, request_id):
    return engine.submit(
        {
            "project_id": PROJECT,
            "operation": operation,
            "arguments": arguments,
            "request_id": request_id,
        }
    )


def _head(engine):
    return _submit(
        engine, "get_project_snapshot", {}, "req-ss-head"
    )["current_revision"]


def _write(engine, kind, settings, request_id):
    return _submit(
        engine, "write_settings",
        {"kind": kind, "settings": settings,
         "expected_revision": _head(engine)},
        request_id,
    )


def _code(excinfo):
    return getattr(excinfo.value, "code", None)


def test_vocabulary_contains_settings_names():
    from rocket_engine.interfaces.vocabulary import OPERATIONS, QUERIES

    assert "write_settings" in OPERATIONS
    assert {"read_settings", "get_resolved_config"} <= set(QUERIES)


def test_write_and_read_settings_round_trip():
    from rocket_engine.composition import Engine
    from rocket_engine.interfaces import settings_store

    engine = Engine(PROJECT, actor="human")
    manifest = settings_store.default_settings("chip.manifest")
    manifest["name"] = "wired"
    manifest["pdk"] = {"ref": "sky130A", "version": "v1.0"}
    written = _write(engine, "chip.manifest", manifest, "req-ss-001")
    assert written["written"] is True
    assert written["settings_version"] == 1
    read = _submit(
        engine, "read_settings", {"kind": "chip.manifest"}, "req-ss-002"
    )
    assert read["settings"]["name"] == "wired"
    assert read["stored"] is True
    assert read["current_revision"] == written["current_revision"]


def test_read_settings_serves_defaults_for_absent_files():
    from rocket_engine.composition import Engine

    engine = Engine(PROJECT, actor="human")
    read = _submit(engine, "read_settings", {"kind": "net.classes"}, "req-ss-010")
    assert read["stored"] is False
    assert read["settings"]["default"] in read["settings"]["classes"]


def test_write_settings_rejects_unknown_kind_and_shape():
    from rocket_engine.composition import Engine
    from rocket_engine.interfaces import settings_store

    engine = Engine(PROJECT, actor="human")
    with pytest.raises(Exception) as excinfo:
        _submit(
            engine, "write_settings",
            {"kind": "board.view", "settings": {},
             "expected_revision": _head(engine)},
            "req-ss-020",
        )
    assert _code(excinfo) == "invalid_command"
    bad = settings_store.default_settings("text.vars")
    bad["vars"] = {"NOPE": [1]}
    with pytest.raises(Exception) as excinfo:
        _submit(
            engine, "write_settings",
            {"kind": "text.vars", "settings": bad,
             "expected_revision": _head(engine)},
            "req-ss-021",
        )
    assert _code(excinfo) == "invalid_command"


def test_text_vars_deletes_propagate_through_engine():
    from rocket_engine.composition import Engine

    engine = Engine(PROJECT, actor="human")
    _write(
        engine, "text.vars",
        {"meta": {"version": 1}, "vars": {"KEEP": "1", "DROP": "2"}},
        "req-ss-030",
    )
    _write(
        engine, "text.vars",
        {"meta": {"version": 1}, "vars": {"KEEP": "1"}},
        "req-ss-031",
    )
    read = _submit(engine, "read_settings", {"kind": "text.vars"}, "req-ss-032")
    assert read["settings"]["vars"] == {"KEEP": "1"}


def test_unknown_keys_survive_engine_round_trip():
    from rocket_engine.composition import Engine
    from rocket_engine.interfaces import settings_store

    engine = Engine(PROJECT, actor="human")
    rules = settings_store.default_settings("design.rules")
    rules["foreign_key"] = {"nested": True}
    _write(engine, "design.rules", rules, "req-ss-040")
    trimmed = settings_store.default_settings("design.rules")
    trimmed["erc"]["default"] = False
    _write(engine, "design.rules", trimmed, "req-ss-041")
    read = _submit(engine, "read_settings", {"kind": "design.rules"}, "req-ss-042")
    assert read["settings"]["erc"]["default"] is False
    assert read["settings"]["foreign_key"] == {"nested": True}


def test_future_file_refuses_engine_write():
    from rocket_engine.composition import Engine
    from rocket_engine.interfaces import settings_store

    engine = Engine(PROJECT, actor="human")
    future = settings_store.default_settings("net.classes")
    future["meta"] = {"version": 99}
    _submit(
        engine, "write_doc",
        {
            "path": "settings/net.classes.yaml",
            "content": settings_store.dump_settings_text(future),
            "expected_revision": _head(engine),
        },
        "req-ss-050",
    )
    with pytest.raises(Exception) as excinfo:
        _write(
            engine, "net.classes",
            settings_store.default_settings("net.classes"),
            "req-ss-051",
        )
    assert _code(excinfo) == "future_format"


def test_write_settings_advances_revision_and_gates_stale():
    from rocket_engine.composition import Engine
    from rocket_engine.interfaces import settings_store

    engine = Engine(PROJECT, actor="human")
    first = _write(
        engine, "chip.manifest",
        settings_store.default_settings("chip.manifest"),
        "req-ss-060",
    )
    renamed = settings_store.default_settings("chip.manifest")
    renamed["name"] = "rev-two"
    second = _submit(
        engine, "write_settings",
        {"kind": "chip.manifest", "settings": renamed,
         "expected_revision": first["current_revision"]},
        "req-ss-061",
    )
    assert second["current_revision"] != first["current_revision"]
    with pytest.raises(Exception) as excinfo:
        _submit(
            engine, "write_settings",
            {"kind": "chip.manifest",
             "settings": settings_store.default_settings("chip.manifest"),
             "expected_revision": first["current_revision"]},
            "req-ss-062",
        )
    assert _code(excinfo) == "revision_conflict"


def test_unchanged_write_skips_revision_bump():
    from rocket_engine.composition import Engine
    from rocket_engine.interfaces import settings_store

    engine = Engine(PROJECT, actor="human")
    first = _write(
        engine, "chip.manifest",
        settings_store.default_settings("chip.manifest"),
        "req-ss-070",
    )
    assert first["written"] is True
    again = _write(
        engine, "chip.manifest",
        settings_store.default_settings("chip.manifest"),
        "req-ss-071",
    )
    assert again["written"] is False
    assert again["current_revision"] == first["current_revision"]
    assert again["events"] == []


def test_resolved_config_snapshot_per_session(tmp_path):
    from rocket_engine.composition import Engine

    engine = Engine(PROJECT, actor="human", engine_root=tmp_path / "root")
    snap = _submit(
        engine, "get_resolved_config",
        {"session_id": "s-1", "run_id": "r-1"}, "req-ss-080",
    )
    assert snap["session_id"] == "s-1"
    assert snap["run_id"] == "r-1"
    assert set(snap["settings"]) == {
        "chip.manifest", "design.rules", "net.classes",
        "text.vars", "lib.tables",
    }
    assert snap["settings"]["chip.manifest"]["name"] == "untitled"
