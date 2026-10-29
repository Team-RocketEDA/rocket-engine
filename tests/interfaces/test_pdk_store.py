"""PDK-STORE RED — register/verify/list PDK against the user tree.

Tests assume `rocket_engine.interfaces.pdks` with:
  PdkError, resolve_engine_root, ensure_engine_root,
  register_pdk, verify_pdk, list_pdks, resolve_deck, pdk_ingredient.
Valid RED = the import itself fails: the surface does not exist yet.

Policy under test (docs/tickets/PDK-STORE.md + docs/storage-policy.md):
  local-dir adoption into pdks/ (sole shared store) via copy +
  manifest + verify; re-register re-verifies, never duplicates;
  drift fails loudly naming the file; unknown id/rev raises (never
  silent substitute); decks resolve to manifest-hashed paths.

Committed tests use a tiny synthetic PDK tree only. The 12G
user tree (/home/alrida-ismail/.local/share/pdk/sky130A) is proven
once by hand, never copied in the suite.
"""

import pytest

TINY_PDK_FILES = {
    "libs.tech/klayout/drc/sky130A.lydrc": "// DRC deck v1\n",
    "libs.tech/magic/sky130A.tech": "# magic tech v1\n",
    "libs.tech/ngspice/sky130.lib.spice": "* spice models v1\n",
    "libs.ref/sky130_fd_sc_hd/cells.v": "// cells v1\n",
}


def _make_tiny_pdk(base):
    for rel, text in TINY_PDK_FILES.items():
        target = base / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    (base / "libs.tech" / "netgen").mkdir(parents=True, exist_ok=True)
    (base / "libs.tech" / "netgen" / "sky130A_setup.tcl").write_text("# setup\n")
    (base / "libs.tech" / "netgen" / "setup.tcl").symlink_to("sky130A_setup.tcl")
    return base


def _code(excinfo):
    return getattr(excinfo.value, "code", None)


def test_register_adopts_local_dir(tmp_path):
    from rocket_engine.interfaces.pdks import register_pdk  # RED: missing surface

    engine_root = tmp_path / "root"
    source = _make_tiny_pdk(tmp_path / "tiny_pdk")
    record = register_pdk(source, "tiny130A", "v1", engine_root=engine_root)
    assert record["id"] == "tiny130a"
    assert record["revision"] == "v1"
    assert record["file_count"] == len(TINY_PDK_FILES) + 1
    dest = engine_root / "pdks" / "tiny130a" / "v1"
    assert record["path"] == str(dest.resolve()) or record["path"] == str(dest)
    manifest = dest / "manifest.yaml"
    assert manifest.is_file() and manifest.stat().st_size > 0
    assert (dest / "libs.tech" / "klayout" / "drc" / "sky130A.lydrc").is_file()
    assert (dest / "libs.tech" / "netgen" / "setup.tcl").is_symlink()
    assert record["manifest_hash"]
    assert record["tree_hash"]
    assert record["verified"] is True


def test_manifest_excludes_itself_and_is_canonical(tmp_path):
    from rocket_engine.interfaces.pdks import register_pdk  # RED: missing surface
    from ruamel.yaml import YAML

    engine_root = tmp_path / "root"
    register_pdk(_make_tiny_pdk(tmp_path / "tiny_pdk"), "tiny130A", "v1",
                 engine_root=engine_root)
    manifest = YAML(typ="safe").load(
        (engine_root / "pdks" / "tiny130a" / "v1" / "manifest.yaml").read_text()
    )
    assert "manifest.yaml" not in manifest["files"]
    assert list(manifest["files"]) == sorted(manifest["files"])
    assert manifest["symlinks"] == {"libs.tech/netgen/setup.tcl": "sky130A_setup.tcl"}
    assert manifest["id"] == "tiny130a"
    assert manifest["revision"] == "v1"


def test_reregister_reverifies_never_duplicates(tmp_path):
    from rocket_engine.interfaces.pdks import (  # RED: missing surface
        list_pdks,
        register_pdk,
    )

    engine_root = tmp_path / "root"
    source = _make_tiny_pdk(tmp_path / "tiny_pdk")
    first = register_pdk(source, "tiny130A", "v1", engine_root=engine_root)
    second = register_pdk(source, "tiny130A", "v1", engine_root=engine_root)
    assert second["manifest_hash"] == first["manifest_hash"]
    assert second["tree_hash"] == first["tree_hash"]
    assert second["verified"] is True
    assert list_pdks(engine_root=engine_root) and len(
        list_pdks(engine_root=engine_root)
    ) == 1
    assert sorted(p.name for p in (engine_root / "pdks" / "tiny130a").iterdir()) == ["v1"]


def test_verify_passes_clean(tmp_path):
    from rocket_engine.interfaces.pdks import (  # RED: missing surface
        register_pdk,
        verify_pdk,
    )

    engine_root = tmp_path / "root"
    source = _make_tiny_pdk(tmp_path / "tiny_pdk")
    record = register_pdk(source, "tiny130A", "v1", engine_root=engine_root)
    result = verify_pdk("tiny130A", "v1", engine_root=engine_root)
    assert result["ok"] is True
    assert result["manifest_hash"] == record["manifest_hash"]


def test_tampered_deck_fails_verify_naming_file(tmp_path):
    from rocket_engine.interfaces.pdks import (  # RED: missing surface
        register_pdk,
        verify_pdk,
    )

    engine_root = tmp_path / "root"
    register_pdk(_make_tiny_pdk(tmp_path / "tiny_pdk"), "tiny130A", "v1",
                 engine_root=engine_root)
    victim = "libs.tech/klayout/drc/sky130A.lydrc"
    (engine_root / "pdks" / "tiny130a" / "v1" / victim).write_text("// EVIL\n")
    with pytest.raises(Exception) as excinfo:
        verify_pdk("tiny130a", "v1", engine_root=engine_root)
    assert _code(excinfo) == "pdk_drift"
    assert victim in str(excinfo.value)


def test_unknown_pdk_id_or_rev_raises(tmp_path):
    from rocket_engine.interfaces.pdks import (  # RED: missing surface
        register_pdk,
        resolve_deck,
        verify_pdk,
    )

    engine_root = tmp_path / "root"
    register_pdk(_make_tiny_pdk(tmp_path / "tiny_pdk"), "tiny130A", "v1",
                 engine_root=engine_root)
    with pytest.raises(Exception) as excinfo:
        verify_pdk("no-such-pdk", "v1", engine_root=engine_root)
    assert _code(excinfo) == "unknown_pdk"
    with pytest.raises(Exception) as excinfo:
        verify_pdk("tiny130a", "v9", engine_root=engine_root)
    assert _code(excinfo) == "unknown_pdk"
    with pytest.raises(Exception) as excinfo:
        resolve_deck("no-such-pdk", "v1", "libs.tech/magic/sky130A.tech",
                     engine_root=engine_root)
    assert _code(excinfo) == "unknown_pdk"


def test_resolve_deck_returns_manifest_hashed_path(tmp_path):
    from rocket_engine.interfaces.pdks import (  # RED: missing surface
        register_pdk,
        resolve_deck,
    )

    engine_root = tmp_path / "root"
    register_pdk(_make_tiny_pdk(tmp_path / "tiny_pdk"), "tiny130A", "v1",
                 engine_root=engine_root)
    for deck in (
        "libs.tech/klayout/drc/sky130A.lydrc",  # DRC slice
        "libs.tech/magic/sky130A.tech",  # EXTRACT slice
        "libs.tech/ngspice/sky130.lib.spice",  # SIM slice
    ):
        hit = resolve_deck("tiny130a", "v1", deck, engine_root=engine_root)
        assert hit["path"] == str(
            engine_root / "pdks" / "tiny130a" / "v1" / deck
        ) or hit["path"] == str(
            (engine_root / "pdks" / "tiny130a" / "v1" / deck).resolve()
        )
        assert hit["sha256"]


def test_resolve_deck_rejects_drift_unknown_and_escape(tmp_path):
    from rocket_engine.interfaces.pdks import (  # RED: missing surface
        register_pdk,
        resolve_deck,
    )

    engine_root = tmp_path / "root"
    register_pdk(_make_tiny_pdk(tmp_path / "tiny_pdk"), "tiny130A", "v1",
                 engine_root=engine_root)
    victim = "libs.tech/magic/sky130A.tech"
    (engine_root / "pdks" / "tiny130a" / "v1" / victim).write_text("# EVIL\n")
    with pytest.raises(Exception) as excinfo:
        resolve_deck("tiny130a", "v1", victim, engine_root=engine_root)
    assert _code(excinfo) == "pdk_drift"
    assert victim in str(excinfo.value)
    with pytest.raises(Exception) as excinfo:
        resolve_deck("tiny130a", "v1", "libs.tech/magic/nope.tech",
                     engine_root=engine_root)
    assert _code(excinfo) == "unknown_pdk"
    with pytest.raises(Exception) as excinfo:
        resolve_deck("tiny130a", "v1", "../../escape.tech", engine_root=engine_root)
    assert _code(excinfo) == "path_escape"


def test_list_pdks_sorted_and_empty_ok(tmp_path):
    from rocket_engine.interfaces.pdks import (  # RED: missing surface
        ensure_engine_root,
        list_pdks,
        register_pdk,
    )

    engine_root = tmp_path / "root"
    ensure_engine_root(engine_root)
    assert list_pdks(engine_root=engine_root) == []
    register_pdk(_make_tiny_pdk(tmp_path / "b"), "b-pdk", "v2", engine_root=engine_root)
    register_pdk(_make_tiny_pdk(tmp_path / "a"), "a-pdk", "v1", engine_root=engine_root)
    assert [(e["id"], e["revision"]) for e in list_pdks(engine_root=engine_root)] == [
        ("a-pdk", "v1"),
        ("b-pdk", "v2"),
    ]


def test_engine_root_resolution_chain(tmp_path, monkeypatch):
    from rocket_engine.interfaces.pdks import (  # RED: missing surface
        resolve_engine_root,
    )

    explicit = tmp_path / "explicit"
    env_home = tmp_path / "envhome"
    monkeypatch.setenv("ROCKETEDA_HOME", str(env_home))
    assert resolve_engine_root(explicit) == explicit
    assert resolve_engine_root() == env_home
    monkeypatch.delenv("ROCKETEDA_HOME")
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    assert resolve_engine_root() == fake_home / ".local" / "share" / "rocketeda"


def test_pdk_ingredient_closure_for_runs(tmp_path):
    from rocket_engine.interfaces.pdks import (  # RED: missing surface
        pdk_ingredient,
        register_pdk,
    )

    engine_root = tmp_path / "root"
    record = register_pdk(
        _make_tiny_pdk(tmp_path / "tiny_pdk"), "tiny130A", "v1",
        engine_root=engine_root,
    )
    assert pdk_ingredient("tiny130a", "v1", engine_root=engine_root) == {
        "pdk_id": "tiny130a",
        "pdk_revision": "v1",
        "pdk_manifest_hash": record["manifest_hash"],
    }


def test_register_rejects_bad_source_and_bad_revision(tmp_path):
    from rocket_engine.interfaces.pdks import register_pdk  # RED: missing surface

    engine_root = tmp_path / "root"
    with pytest.raises(Exception) as excinfo:
        register_pdk(tmp_path / "missing", "tiny130a", "v1", engine_root=engine_root)
    assert _code(excinfo) == "invalid_pdk"
    (tmp_path / "afile").write_text("not a dir\n")
    with pytest.raises(Exception) as excinfo:
        register_pdk(tmp_path / "afile", "tiny130a", "v1", engine_root=engine_root)
    assert _code(excinfo) == "invalid_pdk"
    source = _make_tiny_pdk(tmp_path / "tiny_pdk")
    with pytest.raises(Exception) as excinfo:
        register_pdk(source, "tiny130a", "../evil", engine_root=engine_root)
    assert _code(excinfo) in ("invalid_pdk", "path_escape")
