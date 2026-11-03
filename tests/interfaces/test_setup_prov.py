"""Prov-env tool resolution: provisioned root wins, ambient decides otherwise.

Covers setup.prov_bin_dirs + the _detect_binaries fallback order
(docs/provision-sources.md "Engine path pointing"). Hermetic:
tmp TOOLS_DIR + stub PATH, never the real ~/tools.
"""

import os
import stat

import rocket_engine.interfaces.setup as setup


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _stub_bin(path):
    _write(path, "#!/bin/sh\necho stub\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def test_prov_bin_dirs_missing_file_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("TOOLS_DIR", str(tmp_path))
    assert setup.prov_bin_dirs() == []


def test_prov_bin_dirs_parses_prefix_and_exe_paths(tmp_path, monkeypatch):
    pref = tmp_path / "opensta-abc"
    (pref / "bin").mkdir(parents=True)
    app = tmp_path / "librelane-3.0.17"
    app.mkdir()
    _write(
        tmp_path / "prov-phase1.env",
        "# comment\n"
        'OPENSTA_PREFIX="%s"\n' % pref
        + 'LIBRELANE_APPIMAGE="%s"\n' % (app / "x.AppImage")
        + "EMPTY=\n"
        "garbage-line\n",
    )
    monkeypatch.setenv("TOOLS_DIR", str(tmp_path))
    dirs = setup.prov_bin_dirs()
    assert str(pref / "bin") in dirs
    assert str(app) in dirs


def test_detect_prefers_provisioned_over_path(tmp_path, monkeypatch):
    pref = tmp_path / "magic-abc"
    (pref / "bin").mkdir(parents=True)
    _stub_bin(pref / "bin" / "magic")
    pathdir = tmp_path / "pathbin"
    pathdir.mkdir()
    _stub_bin(pathdir / "magic")
    _write(tmp_path / "prov-phase1.env", 'MAGIC_PREFIX="%s"\n' % pref)
    monkeypatch.setenv("TOOLS_DIR", str(tmp_path))
    monkeypatch.setenv("PATH", str(pathdir))
    found, missing = setup._detect_binaries(["magic"])
    assert found == {"magic": str(pref / "bin" / "magic")}
    assert missing == []


def test_detect_falls_back_to_path_without_env(tmp_path, monkeypatch):
    pathdir = tmp_path / "pathbin"
    pathdir.mkdir()
    _stub_bin(pathdir / "faketool")
    monkeypatch.setenv("TOOLS_DIR", str(tmp_path))
    monkeypatch.setenv("PATH", str(pathdir))
    found, missing = setup._detect_binaries(["faketool"])
    assert found == {"faketool": str(pathdir / "faketool")}
    assert missing == []


def test_detect_missing_everywhere(tmp_path, monkeypatch):
    monkeypatch.setenv("TOOLS_DIR", str(tmp_path))
    monkeypatch.setenv("PATH", str(tmp_path))
    found, missing = setup._detect_binaries(["no-such-tool-xyz"])
    assert found == {}
    assert missing == ["no-such-tool-xyz"]
