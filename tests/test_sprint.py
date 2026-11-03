"""sprint.py description support: bodies live in docs/tickets/<ID>.md."""

import importlib.util
from argparse import Namespace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def load_sprint(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "sprint_under_test", ROOT / "scripts" / "sprint.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    board = tmp_path / "board.md"
    board.write_text(
        "# Board\n\n## Backlog\n\n- [T1] First ticket\n\n## Done\n\n(empty)\n"
    )
    monkeypatch.setattr(mod, "BOARD", board)
    monkeypatch.setattr(mod, "TICKETS_DIR", tmp_path / "tickets")
    return mod


def test_add_body_attaches_description(tmp_path, monkeypatch):
    mod = load_sprint(tmp_path, monkeypatch)
    body = tmp_path / "why.md"
    body.write_text("## Why\nBecause reasons.\n")
    out = mod.cmd_add(Namespace(title="Second", id="T2", status="backlog",
                                body=str(body)))
    assert "added [T2]" in out
    assert (tmp_path / "tickets" / "T2.md").read_text() == body.read_text()


def test_add_body_missing_file_changes_nothing(tmp_path, monkeypatch):
    mod = load_sprint(tmp_path, monkeypatch)
    out = mod.cmd_add(Namespace(title="Second", id="T2", status="backlog",
                                body=str(tmp_path / "nope.md")))
    assert "no such body file" in out
    assert "T2" not in mod.load()[1]


def test_describe_and_show_roundtrip(tmp_path, monkeypatch):
    mod = load_sprint(tmp_path, monkeypatch)
    body = tmp_path / "why.md"
    body.write_text("## Why\nBecause reasons.\n")
    assert "described [T1]" in mod.cmd_describe(
        Namespace(id="T1", file=str(body)))
    shown = mod.cmd_show(Namespace(id="T1"))
    assert "[T1] First ticket" in shown
    assert "Because reasons." in shown


def test_describe_unknown_ticket_or_file(tmp_path, monkeypatch):
    mod = load_sprint(tmp_path, monkeypatch)
    body = tmp_path / "why.md"
    body.write_text("x\n")
    assert "unknown ticket" in mod.cmd_describe(
        Namespace(id="NOPE", file=str(body)))
    assert "no such body file" in mod.cmd_describe(
        Namespace(id="T1", file=str(tmp_path / "nope.md")))


def test_undescribe_removes_only_body(tmp_path, monkeypatch):
    mod = load_sprint(tmp_path, monkeypatch)
    (tmp_path / "tickets").mkdir()
    (tmp_path / "tickets" / "T1.md").write_text("body\n")
    assert "undescribed [T1]" in mod.cmd_undescribe(Namespace(id="T1"))
    assert not (tmp_path / "tickets" / "T1.md").exists()
    assert "T1" in mod.load()[1]  # ticket itself stays
    assert "no description" in mod.cmd_undescribe(Namespace(id="T1"))


def test_remove_drops_body_too(tmp_path, monkeypatch):
    mod = load_sprint(tmp_path, monkeypatch)
    (tmp_path / "tickets").mkdir()
    (tmp_path / "tickets" / "T1.md").write_text("body\n")
    out = mod.cmd_remove(Namespace(id="T1"))
    assert "removed [T1]" in out
    assert "description" in out
    assert not (tmp_path / "tickets" / "T1.md").exists()


def test_show_without_body_notes_absence(tmp_path, monkeypatch):
    mod = load_sprint(tmp_path, monkeypatch)
    shown = mod.cmd_show(Namespace(id="T1")).splitlines()
    assert shown[0] == "[T1] First ticket"
    assert shown[1] == "status: Backlog"
    assert "no description" in shown[-1]
