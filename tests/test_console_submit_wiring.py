"""CONSOLE-SUBMIT RED — python_open/python_reset through Engine.submit.

The lifecycle registry (`ConsoleLifecycle`) and the envelope shape
(`console_envelope`/`parse_console_envelope`) already exist and are
covered by `tests/test_console_lifecycle_open_reset.py`. What is
missing is the adapt lane: the two operations are not vocabulary,
submit does not serve them, and no Engine surface owns a console
registry. Valid RED = these fail on the pre-slice engine.
"""

import pytest

PROJECT = "console_demo"


def _code(excinfo):
    return getattr(excinfo.value, "code", None)


def _engine():
    from rocket_engine.composition import Engine

    return Engine(PROJECT, actor="human")


def _submit(engine, operation, arguments, request_id):
    return engine.submit(
        {
            "project_id": PROJECT,
            "operation": operation,
            "arguments": arguments,
            "request_id": request_id,
        }
    )


def test_vocabulary_carries_console_lifecycle_ops():
    from rocket_engine.interfaces.vocabulary import OPERATIONS

    assert {"python_open", "python_reset"} <= set(OPERATIONS)


def test_submit_open_mints_console():
    engine = _engine()
    out = _submit(engine, "python_open", {}, "req-open-001")
    assert out["console_id"]
    assert out["generation"]
    assert out["project_id"] == PROJECT


def test_submit_open_reuses_workspace_root(tmp_path):
    engine = _engine()
    root = str(tmp_path)
    first = _submit(
        engine, "python_open", {"workspace_root": root},
        "req-open-root-1")
    second = _submit(
        engine, "python_open", {"workspace_root": root},
        "req-open-root-2")
    assert second["console_id"] == first["console_id"]
    third = _submit(
        engine, "python_open",
        {"workspace_root": root + "-other"},
        "req-open-root-3")
    assert third["console_id"] != first["console_id"]


def test_submit_reset_advances_generation():
    engine = _engine()
    opened = _submit(engine, "python_open", {}, "req-open-reset")
    first = opened["generation"]
    out = _submit(
        engine, "python_reset",
        {"console_id": opened["console_id"]},
        "req-reset-001")
    assert out["console_id"] == opened["console_id"]
    assert out["generation"] != first


def test_submit_reset_unknown_console_fails_loudly():
    engine = _engine()
    with pytest.raises(Exception) as excinfo:
        _submit(
            engine, "python_reset",
            {"console_id": "no-such-console"},
            "req-reset-unknown")
    assert _code(excinfo) == "unknown_console"


def test_submit_open_needs_no_revision_gate():
    engine = _engine()
    out = _submit(
        engine, "python_open", {"workspace_root": None},
        "req-open-nogate")
    assert out["console_id"]
