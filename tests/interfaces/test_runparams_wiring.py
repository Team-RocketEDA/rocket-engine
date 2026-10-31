"""RUN-PARAMS wiring tests: submit validation + snapshot freeze.

The integrator runs this file AFTER applying the wiring patch (see
docs/work/RUN-PARAMS/report.md): Engine.submit and Engine.run must
validate the run.request shape through
`rocket_engine.interfaces.runparams` and freeze the normalized knobs
into the stored command. Before the patch these tests skip — the
probe below admits nothing when the schema is unwired.
"""

import uuid

import pytest

from rocket_engine.composition import Engine
from rocket_engine.interfaces.runparams import (
    RUN_REQUEST_DEFAULTS,
    freeze_run_request,
)


def _engine():
    return Engine(f"runparams-wiring-{uuid.uuid4().hex[:8]}", actor="test")


def _submit(engine, operation, arguments):
    arguments = dict(arguments)
    arguments.setdefault(
        "expected_revision", engine.snapshot()["current_revision"]
    )
    return engine.submit(
        {
            "project_id": engine.snapshot()["project_id"],
            "operation": operation,
            "arguments": arguments,
            "request_id": uuid.uuid4().hex,
        }
    )


def _wiring_present():
    probe = _engine()
    try:
        _submit(probe, "run_drc", {"request": {"bogus_knob": True}})
    except Exception as exc:
        return getattr(exc, "code", None) == "unknown_run_param"
    return False


needs_wiring = pytest.mark.skipif(
    not _wiring_present(), reason="needs RUN-PARAMS wiring patch"
)


@needs_wiring
def test_submit_rejects_unknown_field_with_named_reason():
    engine = _engine()
    with pytest.raises(Exception) as excinfo:
        _submit(engine, "run_drc", {"request": {"flatten": True}})
    assert getattr(excinfo.value, "code", None) == "unknown_run_param"
    assert "flatten" in str(excinfo.value)


@needs_wiring
def test_submit_rejects_bad_value_with_named_reason():
    engine = _engine()
    with pytest.raises(Exception) as excinfo:
        _submit(engine, "run_drc", {"request": {"netlist_type": "hspice"}})
    assert getattr(excinfo.value, "code", None) == "invalid_run_param"
    assert "netlist_type" in str(excinfo.value)


@needs_wiring
def test_submit_freezes_every_knob():
    engine = _engine()
    request_id = uuid.uuid4().hex
    engine.submit(
        {
            "project_id": engine.snapshot()["project_id"],
            "operation": "run_drc",
            "arguments": {
                "expected_revision": engine.snapshot()["current_revision"],
                "request": {"flat_netlist": True},
            },
            "request_id": request_id,
        }
    )
    stored, _ack = engine._project.command_for(request_id)
    assert stored["arguments"]["request"] == {
        **RUN_REQUEST_DEFAULTS,
        "flat_netlist": True,
    }


@needs_wiring
def test_submit_freezes_defaults_when_request_absent():
    engine = _engine()
    request_id = uuid.uuid4().hex
    engine.submit(
        {
            "project_id": engine.snapshot()["project_id"],
            "operation": "run_drc",
            "arguments": {
                "expected_revision": engine.snapshot()["current_revision"],
            },
            "request_id": request_id,
        }
    )
    stored, _ack = engine._project.command_for(request_id)
    assert stored["arguments"]["request"] == RUN_REQUEST_DEFAULTS


@needs_wiring
def test_same_request_replays_byte_identical_inputs():
    engine = _engine()
    ids = []
    shapes = [
        {"top_is_subckt": True, "netlist_type": "spectre"},
        {"netlist_type": "spectre", "top_is_subckt": True},
    ]
    for shape in shapes:
        request_id = uuid.uuid4().hex
        ids.append(request_id)
        engine.submit(
            {
                "project_id": engine.snapshot()["project_id"],
                "operation": "run_drc",
                "arguments": {
                    "expected_revision": engine.snapshot()["current_revision"],
                    "request": shape,
                },
                "request_id": request_id,
            }
        )
    frozen = [
        freeze_run_request(
            engine._project.command_for(request_id)[0]["arguments"]["request"]
        )
        for request_id in ids
    ]
    assert frozen[0] == frozen[1]


@needs_wiring
def test_run_path_validates_identically_to_submit():
    engine = _engine()
    with pytest.raises(Exception) as excinfo:
        engine.run(
            {
                "project_id": engine.snapshot()["project_id"],
                "operation": "run_drc",
                "arguments": {"request": {"bogus_knob": True}},
            }
        )
    assert getattr(excinfo.value, "code", None) == "unknown_run_param"


@needs_wiring
def test_mcp_shape_validates_identically_to_submit():
    import json

    from rocket_engine.adapters.mcp import McpTransport

    engine = _engine()
    transport = McpTransport(engine)
    project_id = engine.snapshot()["project_id"]
    with pytest.raises(Exception) as excinfo:
        transport.handle(
            json.dumps(
                {
                    "method": "tools/call",
                    "params": {
                        "name": "run_drc",
                        "arguments": {
                            "project_id": project_id,
                            "expected_revision": engine.snapshot()[
                                "current_revision"
                            ],
                            "request": {"bogus_knob": True},
                        },
                    },
                    "id": uuid.uuid4().hex,
                }
            )
        )
    assert getattr(excinfo.value, "code", None) == "unknown_run_param"


def test_dispatch_shape_carries_request_through():
    from rocket_engine.execution.dispatch import parse_op_tokens

    operation, arguments = parse_op_tokens(
        ["run_drc", "request={flat_netlist: true}"]
    )
    assert operation == "run_drc"
    assert arguments["request"] == {"flat_netlist": True}
