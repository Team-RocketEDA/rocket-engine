"""SETTINGS-STORE unit tests — engine-owned design-truth settings store.

Tests assume `src/interfaces/settings_store.py` with:
  CURRENT_VERSIONS, SettingsError, register_migration, migrate,
  default_settings, fresh_project_settings, validate_settings,
  apply_update, merge_writer_maps, load_settings_file,
  save_settings_file, SettingsStore (file + in-memory modes),
  resolve_library.

Valid RED = the load itself fails: the module does not exist yet.

Policy under test (docs/tickets/SETTINGS-STORE.md):
  five versioned design-truth schemas (chip.manifest, design.rules,
  net.classes, text.vars, lib.tables), meta.version per file, chained
  migrators, additive-params-first, merge-onto-original preserving
  unknown keys, future-format blocks autosave, byte-compare skip,
  atomic write, one writer per key with unset-fill merge, and a
  resolved-config snapshot per session/run.
"""

import importlib.util
import os
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent


def _load_store():
    # RED: src/interfaces/settings_store.py does not exist yet.
    location = ROOT / "src" / "interfaces" / "settings_store.py"
    spec = importlib.util.spec_from_file_location(
        "settings_store_under_test", location
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


store = _load_store()

KINDS = (
    "chip.manifest",
    "design.rules",
    "net.classes",
    "text.vars",
    "lib.tables",
)


@pytest.fixture(autouse=True)
def _clean_registry():
    store.clear_migrations()
    yield
    store.clear_migrations()


def _code(excinfo):
    return getattr(excinfo.value, "code", None)


def test_current_versions_cover_all_five_kinds():
    assert set(store.CURRENT_VERSIONS) == set(KINDS)
    for kind in KINDS:
        assert store.CURRENT_VERSIONS[kind] >= 1


def test_fresh_project_manifest_carries_name_pdk_and_canvases():
    fresh = store.fresh_project_settings(
        "demo", "sky130A", "v1.0",
        canvases=[{"name": "top"}, {"name": "power"}],
    )
    manifest = fresh["chip.manifest"]
    assert manifest["name"] == "demo"
    assert manifest["pdk"] == {"ref": "sky130A", "version": "v1.0"}
    assert [c["name"] for c in manifest["canvases"]] == ["top", "power"]
    assert manifest["meta"]["version"] == store.CURRENT_VERSIONS["chip.manifest"]


def test_fresh_project_defaults_validate_for_every_kind():
    fresh = store.fresh_project_settings("demo", "sky130A", "v1.0")
    assert set(fresh) == set(KINDS)
    for kind in KINDS:
        assert store.validate_settings(kind, fresh[kind]) == fresh[kind]


def test_design_rules_defaults_are_nested():
    rules = store.default_settings("design.rules")
    assert rules["erc"]["default"] in (True, False)
    assert rules["erc"]["checks"] != {}
    assert all(isinstance(v, bool) for v in rules["erc"]["checks"].values())
    assert rules["drc"]["deck"]["ref"] != ""
    assert isinstance(rules["lvs"], dict) and rules["lvs"] != {}


def test_net_classes_default_and_per_net_split():
    classes = store.default_settings("net.classes")
    assert classes["default"] in classes["classes"]
    entry = classes["classes"][classes["default"]]
    assert "color" in entry and "visible" in entry
    assert classes["nets"] != {}
    for net, class_name in classes["nets"].items():
        assert class_name in classes["classes"], net


def test_text_vars_rejects_non_scalars():
    bad = store.default_settings("text.vars")
    bad["vars"] = {"BAD": {"nested": True}}
    with pytest.raises(store.SettingsError) as excinfo:
        store.validate_settings("text.vars", bad)
    assert _code(excinfo) == "invalid_settings"


def test_unknown_kind_rejected():
    with pytest.raises(store.SettingsError) as excinfo:
        store.default_settings("board.view")
    assert _code(excinfo) == "unknown_kind"
    with pytest.raises(store.SettingsError) as excinfo:
        store.validate_settings("board.view", {})
    assert _code(excinfo) == "unknown_kind"


def test_manifest_validation_rejects_missing_name():
    bad = store.default_settings("chip.manifest")
    del bad["name"]
    with pytest.raises(store.SettingsError) as excinfo:
        store.validate_settings("chip.manifest", bad)
    assert _code(excinfo) == "invalid_settings"


def test_settings_version_reads_meta():
    data = store.default_settings("chip.manifest")
    assert store.settings_version("chip.manifest", data) == 1
    data["meta"] = {"version": "1"}
    with pytest.raises(store.SettingsError) as excinfo:
        store.settings_version("chip.manifest", data)
    assert _code(excinfo) == "invalid_settings"


def test_migrations_chain_in_order_additive_first():
    seen = []

    def one_to_two(data):
        seen.append("1->2")
        data = dict(data)
        data["added_v2"] = "from-migrator"
        return data

    def two_to_three(data):
        seen.append("2->3")
        data = dict(data)
        data["added_v3"] = "from-migrator"
        return data

    store.register_migration("design.rules", 1, 2, one_to_two)
    store.register_migration("design.rules", 2, 3, two_to_three)
    old = store.default_settings("design.rules")
    old["meta"] = {"version": 1}
    out = store.migrate("design.rules", old)
    assert seen == ["1->2", "2->3"]
    assert out["meta"]["version"] == 3
    # Additive-params-first: migrator keys land on top of defaults,
    # and defaults survive even where the migrator says nothing.
    assert out["added_v2"] == "from-migrator"
    assert out["added_v3"] == "from-migrator"
    assert out["erc"]["default"] == old["erc"]["default"]


def test_register_migration_rejects_skips_and_duplicates():
    store.register_migration("text.vars", 1, 2, lambda data: data)
    with pytest.raises(store.SettingsError) as excinfo:
        store.register_migration("text.vars", 1, 3, lambda data: data)
    assert _code(excinfo) == "invalid_migration"
    with pytest.raises(store.SettingsError) as excinfo:
        store.register_migration("text.vars", 1, 2, lambda data: data)
    assert _code(excinfo) == "migration_conflict"


def test_migrate_rejects_future_format():
    future = store.default_settings("net.classes")
    future["meta"] = {"version": 99}
    with pytest.raises(store.SettingsError) as excinfo:
        store.migrate("net.classes", future)
    assert _code(excinfo) == "future_format"


def test_migrate_reports_a_missing_link():
    store.register_migration("text.vars", 2, 3, lambda data: data)
    old = store.default_settings("text.vars")
    old["meta"] = {"version": 1}
    with pytest.raises(store.SettingsError) as excinfo:
        store.migrate("text.vars", old)
    assert _code(excinfo) == "missing_migration"


def test_file_round_trip_preserves_unknown_keys(tmp_path):
    path = tmp_path / "settings" / "design.rules.yaml"
    first = store.SettingsStore(root=tmp_path)
    first.ensure_fresh("demo", "sky130A", "v1.0")
    assert path.exists()
    second = store.SettingsStore(root=tmp_path)
    # A newer/foreign writer left keys this engine does not know.
    raw = second.load("design.rules")
    raw["future_flag"] = True
    raw["erc"]["unknown_check"] = True
    second.write("design.rules", raw)
    third = store.SettingsStore(root=tmp_path)
    reread = third.load("design.rules")
    assert reread["future_flag"] is True
    assert reread["erc"]["unknown_check"] is True


def test_future_file_blocks_autosave_and_keeps_bytes(tmp_path):
    path = tmp_path / "settings" / "net.classes.yaml"
    path.parent.mkdir(parents=True)
    data = store.default_settings("net.classes")
    data["meta"] = {"version": 99}
    handle = store.SettingsStore(root=tmp_path)
    path.write_text(store.dump_settings_text(data), encoding="utf-8")
    before = path.read_bytes()
    loaded = store.load_settings_file(path)
    assert loaded.future is True
    with pytest.raises(store.SettingsError) as excinfo:
        store.save_settings_file(loaded)
    assert _code(excinfo) == "future_format"
    with pytest.raises(store.SettingsError):
        handle.load("net.classes")
    assert path.read_bytes() == before


def test_byte_compare_skips_unchanged_write(tmp_path):
    handle = store.SettingsStore(root=tmp_path)
    handle.ensure_fresh("demo", "sky130A", "v1.0")
    path = tmp_path / "settings" / "chip.manifest.yaml"
    before = path.stat().st_mtime_ns
    time.sleep(0.01)
    out = handle.write("chip.manifest", handle.load("chip.manifest"))
    assert out["written"] is False
    assert path.stat().st_mtime_ns == before


def test_save_writes_atomically_with_no_tmp_leftovers(tmp_path):
    handle = store.SettingsStore(root=tmp_path)
    handle.ensure_fresh("demo", "sky130A", "v1.0")
    manifest = handle.load("chip.manifest")
    manifest["name"] = "renamed"
    out = handle.write("chip.manifest", manifest)
    assert out["written"] is True
    leftovers = [
        p for p in (tmp_path / "settings").iterdir() if p.suffix == ".tmp"
    ]
    assert leftovers == []
    reread = store.SettingsStore(root=tmp_path).load("chip.manifest")
    assert reread["name"] == "renamed"


def test_text_vars_clear_unknown_keys_deletes():
    current = store.default_settings("text.vars")
    current["vars"] = {"KEEP": "1", "DROP": "2"}
    out = store.apply_update(
        "text.vars", current, {"vars": {"KEEP": "1", "NEW": "3"}}
    )
    assert out["vars"] == {"KEEP": "1", "NEW": "3"}


def test_text_vars_deletes_propagate_through_store(tmp_path):
    handle = store.SettingsStore(root=tmp_path)
    handle.ensure_fresh("demo", "sky130A", "v1.0")
    handle.write(
        "text.vars",
        {**store.default_settings("text.vars"),
         "vars": {"KEEP": "1", "DROP": "2"}},
    )
    handle.update("text.vars", {"vars": {"KEEP": "1"}})
    reread = store.SettingsStore(root=tmp_path).load("text.vars")
    assert reread["vars"] == {"KEEP": "1"}


def test_update_merges_structured_kinds(tmp_path):
    handle = store.SettingsStore(root=tmp_path)
    handle.ensure_fresh("demo", "sky130A", "v1.0")
    handle.update("design.rules", {"erc": {"default": False}})
    reread = handle.load("design.rules")
    assert reread["erc"]["default"] is False
    assert reread["erc"]["checks"] != {}
    assert reread["drc"]["deck"]["ref"] != ""


def test_write_validates_before_touching_disk(tmp_path):
    handle = store.SettingsStore(root=tmp_path)
    handle.ensure_fresh("demo", "sky130A", "v1.0")
    path = tmp_path / "settings" / "chip.manifest.yaml"
    before = path.read_bytes()
    bad = handle.load("chip.manifest")
    bad["pdk"] = "not-a-mapping"
    with pytest.raises(store.SettingsError) as excinfo:
        handle.write("chip.manifest", bad)
    assert _code(excinfo) == "invalid_settings"
    assert path.read_bytes() == before


def test_lib_tables_resolve_only(tmp_path):
    libdir = tmp_path / "libs"
    (libdir / "sky130").mkdir(parents=True)
    (libdir / "sky130" / "cells.spice").write_text("* cells\n")
    tables = store.default_settings("lib.tables")
    tables["tables"] = {
        "cells": {"ref": "sky130/cells.spice"},
        "missing": {"ref": "sky130/nope.spice"},
    }
    resolved = store.resolve_library(tables, "cells", [libdir])
    assert resolved == libdir / "sky130" / "cells.spice"
    with pytest.raises(store.SettingsError) as excinfo:
        store.resolve_library(tables, "missing", [libdir])
    assert _code(excinfo) == "unknown_library"
    # Resolve-only: resolving never writes beside the referent.
    assert sorted(p.name for p in (libdir / "sky130").iterdir()) == [
        "cells.spice"
    ]


def test_merge_writer_maps_one_writer_per_key():
    base = {"a": 1, "b": 2, "c": 3}
    out = store.merge_writer_maps(
        base, {"front": {"a": 10}, "back": {"b": 20}}
    )
    assert out == {"a": 10, "b": 20, "c": 3}
    with pytest.raises(store.SettingsError) as excinfo:
        store.merge_writer_maps(
            base, {"front": {"a": 10}, "back": {"a": 20}}
        )
    assert _code(excinfo) == "writer_conflict"


def test_snapshot_bundles_resolved_config_per_session_run(tmp_path):
    handle = store.SettingsStore(root=tmp_path)
    handle.ensure_fresh("demo", "sky130A", "v1.0")
    snap = handle.snapshot(session_id="s-1", run_id="r-2")
    assert snap["session_id"] == "s-1"
    assert snap["run_id"] == "r-2"
    assert set(snap["settings"]) == set(KINDS)
    assert set(snap["versions"]) == set(KINDS)
    assert snap["settings"]["chip.manifest"]["name"] == "demo"


def test_snapshot_settings_needs_all_five_kinds():
    fresh = store.fresh_project_settings("demo", "sky130A", "v1.0")
    snap = store.snapshot_settings(fresh, session_id="s", run_id="r")
    assert snap["versions"] == {kind: 1 for kind in KINDS}
    assert snap["settings"] == fresh
    assert snap["settings"] is not fresh
    partial = dict(fresh)
    del partial["lib.tables"]
    with pytest.raises(store.SettingsError) as excinfo:
        store.snapshot_settings(partial)
    assert _code(excinfo) == "invalid_settings"


def test_store_memory_mode_needs_no_root():
    handle = store.SettingsStore()
    created = handle.ensure_fresh("demo", "sky130A", "v1.0")
    assert set(created) == set(KINDS)
    handle.update("text.vars", {"vars": {"HELLO": "world"}})
    assert handle.load("text.vars")["vars"] == {"HELLO": "world"}
    snap = handle.snapshot(session_id="s-9")
    assert snap["settings"]["text.vars"]["vars"] == {"HELLO": "world"}


def test_ensure_fresh_never_clobbers(tmp_path):
    handle = store.SettingsStore(root=tmp_path)
    handle.ensure_fresh("demo", "sky130A", "v1.0")
    manifest = handle.load("chip.manifest")
    manifest["name"] = "custom"
    handle.write("chip.manifest", manifest)
    assert handle.ensure_fresh("other", "gf180", "v9") == []
    assert handle.load("chip.manifest")["name"] == "custom"


def test_merge_settings_seam_for_crud_persistence():
    original = store.default_settings("design.rules")
    original["foreign_key"] = {"nested": [1, 2]}
    new = store.default_settings("design.rules")
    new["erc"]["default"] = False
    merged = store.merge_settings("design.rules", original, new)
    assert merged["erc"]["default"] is False
    assert merged["foreign_key"] == {"nested": [1, 2]}
    first_write = store.merge_settings(
        "text.vars", None, {"meta": {"version": 1}, "vars": {}}
    )
    assert first_write["vars"] == {}
    with pytest.raises(store.SettingsError) as excinfo:
        store.merge_settings("board.view", None, {})
    assert _code(excinfo) == "unknown_kind"


def test_dump_settings_text_round_trips():
    from ruamel.yaml import YAML

    data = store.default_settings("chip.manifest")
    assert dict(YAML(typ="safe").load(store.dump_settings_text(data))) == data


def test_memory_files_stay_isolated_per_store():
    first = store.SettingsStore()
    second = store.SettingsStore()
    first.ensure_fresh("demo", "sky130A", "v1.0")
    second.ensure_fresh("demo", "sky130A", "v1.0")
    first.update("text.vars", {"vars": {"ONLY": "first"}})
    assert second.load("text.vars")["vars"] == {}
