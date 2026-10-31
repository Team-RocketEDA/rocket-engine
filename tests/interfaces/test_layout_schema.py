"""LAYOUT-SCHEMA RED — machine-readable folder schema.

Tests assume `rocket_engine.interfaces.layout` with:
  SCHEMA_VERSION, LayoutError, load_schema, validate_tree,
  derive_gitignore, verify_gitignore, template_defaults, validate_policy.
Valid RED = the import itself fails: the surface does not exist yet.
"""

import io
from pathlib import Path

import pytest
from ruamel.yaml import YAML

EXPECTED_DEFAULTS = {
    "timeout_s": 120,
    "preflight_timeout_s": 30,
    "threads": 4,
    "slang_flags": ["-Wextra"],
    "tools": {
        "run_drc": "magic",
        "run_hdl_test": "icarus",
        "run_optical": "sax",
        "run_syntax": "slang",
    },
    "decks": {"run_drc": "sky130A"},
    "seeds": [0],
}

EXPECTED_GITIGNORE = (
    "# Engine exhaust (derived from layout_schema.yaml v1; do not edit by hand).\n"
    ".rocket/\n"
    "cache/\n"
    "projects/*/runs/\n"
)


def _dump(data):
    buf = io.StringIO()
    YAML(typ="safe").dump(data, buf)
    return buf.getvalue()


def _write_version(path):
    path.write_text(_dump({"schema_version": 1}))


def _write_policy(path, overrides=None):
    policy = {k: (list(v) if isinstance(v, list) else dict(v) if isinstance(v, dict) else v) for k, v in EXPECTED_DEFAULTS.items()}
    # Deep-copy nested dicts one level (tools/decks are flat).
    policy["tools"] = dict(EXPECTED_DEFAULTS["tools"])
    policy["decks"] = dict(EXPECTED_DEFAULTS["decks"])
    policy["slang_flags"] = list(EXPECTED_DEFAULTS["slang_flags"])
    policy["seeds"] = list(EXPECTED_DEFAULTS["seeds"])
    if overrides:
        policy.update(overrides)
    path.write_text(_dump(policy))


def _make_engine_root(base):
    base.mkdir(parents=True, exist_ok=True)
    _write_version(base / "layout.version")
    _write_policy(base / "policy.yaml")
    (base / "pdks").mkdir(parents=True)
    (base / "cache").mkdir(parents=True)
    (base / "projects" / "demo" / "runs").mkdir(parents=True)
    return base


def _make_linked_project(base):
    (base / ".rocket" / "runs").mkdir(parents=True)
    _write_version(base / ".rocket" / "layout.version")
    (base / "design.v").write_text("// caller-owned source\n")
    return base


def _code(excinfo):
    return getattr(excinfo.value, "code", None)


def test_valid_engine_root_passes(tmp_path):
    from rocket_engine.interfaces.layout import validate_tree  # RED: missing surface

    result = validate_tree(_make_engine_root(tmp_path / "root"))
    assert result["ok"] is True


def test_missing_required_entry_fails(tmp_path):
    from rocket_engine.interfaces.layout import validate_tree  # RED: missing surface

    root = _make_engine_root(tmp_path / "root")
    # cache/ is required; remove it.
    (root / "cache").rmdir()
    with pytest.raises(Exception) as excinfo:
        validate_tree(root)
    assert _code(excinfo) == "missing_entry"


def test_present_but_empty_required_entry_fails(tmp_path):
    from rocket_engine.interfaces.layout import validate_tree  # RED: missing surface

    root = _make_engine_root(tmp_path / "root")
    (root / "policy.yaml").write_text("")
    with pytest.raises(Exception) as excinfo:
        validate_tree(root)
    assert _code(excinfo) == "empty_entry"


def test_present_but_empty_policy_value_fails(tmp_path):
    from rocket_engine.interfaces.layout import validate_tree  # RED: missing surface

    root = _make_engine_root(tmp_path / "root")
    _write_policy(root / "policy.yaml", {"tools": {}})
    with pytest.raises(Exception) as excinfo:
        validate_tree(root)
    assert _code(excinfo) == "empty_policy"


def test_newer_version_folder_refuses(tmp_path):
    from rocket_engine.interfaces.layout import validate_tree  # RED: missing surface

    root = _make_engine_root(tmp_path / "root")
    (root / "layout.version").write_text(_dump({"schema_version": 999}))
    with pytest.raises(Exception) as excinfo:
        validate_tree(root)
    assert _code(excinfo) == "unsupported_version"
    message = str(excinfo.value)
    assert "999" in message and "1" in message


def test_derived_gitignore_matches_expected():
    from rocket_engine.interfaces.layout import (  # RED: missing surface
        derive_gitignore,
        verify_gitignore,
    )

    assert derive_gitignore() == EXPECTED_GITIGNORE
    assert verify_gitignore(EXPECTED_GITIGNORE)["ok"] is True
    with pytest.raises(Exception) as excinfo:
        verify_gitignore("# empty\n")
    assert _code(excinfo) == "gitignore_mismatch"


def test_template_ships_defaults_and_validates():
    from rocket_engine.interfaces.layout import (  # RED: missing surface
        template_defaults,
        validate_policy,
    )

    defaults = template_defaults()
    assert defaults == EXPECTED_DEFAULTS
    assert validate_policy(defaults)["ok"] is True
    with pytest.raises(Exception) as excinfo:
        validate_policy({})
    assert _code(excinfo) == "missing_policy"
    bad = dict(defaults)
    bad["seeds"] = []
    with pytest.raises(Exception) as excinfo:
        validate_policy(bad)
    assert _code(excinfo) == "empty_policy"


def test_linked_project_carve_out(tmp_path):
    from rocket_engine.interfaces.layout import validate_tree  # RED: missing surface

    root = _make_linked_project(tmp_path / "proj")
    assert validate_tree(root, kind="linked_project")["ok"] is True
    # runs/ under .rocket/ is required; remove it.
    (root / ".rocket" / "runs").rmdir()
    with pytest.raises(Exception) as excinfo:
        validate_tree(root, kind="linked_project")
    assert _code(excinfo) == "missing_entry"


# --- LEDGER-DURABLE: the durable event log fits the folder schema ---


def _project_children():
    from rocket_engine.interfaces.layout import load_schema  # RED: no ledger entries

    for section in ("engine_root",):
        for entry in load_schema()[section]:
            if entry["name"] == "projects":
                for child in entry["children"]:
                    if child["name"] == "<id>":
                        return {node["name"]: node for node in child["children"]}
    raise AssertionError("projects/<id> missing from schema")


def test_ledger_files_are_schematized_under_managed_projects():
    children = _project_children()  # RED: entries missing
    for name in ("events.yaml", "ledger.yaml"):
        assert name in children, f"{name} not schematized"
        assert children[name]["type"] == "file"
        assert children[name]["required"] is False
        assert children[name]["tracked"] is True
        assert children[name]["created_by"] == "engine"


def test_present_but_empty_events_file_fails(tmp_path):
    from rocket_engine.interfaces.layout import validate_tree  # RED: file ignored

    root = _make_engine_root(tmp_path / "root")
    (root / "projects" / "demo" / "events.yaml").write_text("")
    with pytest.raises(Exception) as excinfo:
        validate_tree(root)
    assert _code(excinfo) == "empty_entry"


def test_ledger_files_do_not_pollute_the_gitignore():
    from rocket_engine.interfaces.layout import (  # RED: entries missing
        derive_gitignore,
    )

    _project_children()
    assert derive_gitignore() == EXPECTED_GITIGNORE
