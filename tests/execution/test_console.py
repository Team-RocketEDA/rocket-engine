"""B8 RED — I15 approval binding, I17 console lifecycle, I18 help-is-data.

Tests assume `rocket_engine.execution.ConsoleSession` (open, approve,
admit, execute, reset) and `rocket_engine.execution.get_help`. Valid
RED = each import fails: the console surface does not exist yet.

Deliberately absent: I16/I23/I24 need a real sandbox/worker, and any
RED written without one would be invalid. They land with the console
substrate, not here.
"""

import pytest

CODE = "result = project.snapshot()\n"


def _code(excinfo):
    return getattr(excinfo.value, "code", None)


def _session():
    from rocket_engine.execution import ConsoleSession  # RED: missing surface

    return ConsoleSession(project_id="analog_demo", actor={"kind": "user"})


def _approve(session):
    return session.request_cell_approval(
        code=CODE, history_cursor=3, env_digest="env-abc", expected_revision="p12"
    )


def test_identical_binding_admits():
    session = _session()
    approval = _approve(session)
    assert approval["state"] == "pending_approval"
    admitted = session.admit_cell(
        approval["approval_id"], code=CODE, history_cursor=3,
        env_digest="env-abc", expected_revision="p12",
    )
    assert admitted["state"] == "approved"


@pytest.mark.parametrize(
    "field,value",
    [
        ("code", CODE + "# sneaky\n"),
        ("history_cursor", 4),
        ("env_digest", "env-xyz"),
        ("expected_revision", "p13"),
    ],
)
def test_binding_mismatch_invalidates(field, value):
    session = _session()
    approval = _approve(session)
    admit = {"code": CODE, "history_cursor": 3, "env_digest": "env-abc",
             "expected_revision": "p12"}
    admit[field] = value
    with pytest.raises(Exception) as excinfo:
        session.admit_cell(approval["approval_id"], **admit)
    assert _code(excinfo) == "approval_invalid"


def test_cells_advance_history_cursor():
    session = _session()
    first = session.execute_cell(_approve(session)["approval_id"], code=CODE)
    second = session.execute_cell(_approve(session)["approval_id"], code=CODE)
    assert second["cursor"] > first["cursor"] >= 1


def test_reset_renews_generation_and_kills_approvals():
    session = _session()
    before = session.generation
    approval = _approve(session)
    session.reset()
    assert session.generation != before
    with pytest.raises(Exception) as excinfo:
        session.admit_cell(
            approval["approval_id"], code=CODE, history_cursor=3,
            env_digest="env-abc", expected_revision="p12",
        )
    assert _code(excinfo) == "approval_invalid"


def test_help_returns_versioned_metadata_without_execution():
    from rocket_engine.execution import get_help  # RED: missing surface

    entry = get_help("run_drc")
    assert entry["topic"] == "run_drc"
    assert entry["version"].startswith("rocketeda/")
    assert "signature" in entry and "example" in entry
    assert "import os" not in entry["example"]


def test_help_unknown_topic_errors():
    from rocket_engine.execution import get_help  # RED: missing surface

    with pytest.raises(Exception) as excinfo:
        get_help("no_such_operation")
    assert _code(excinfo) == "unknown_topic"
