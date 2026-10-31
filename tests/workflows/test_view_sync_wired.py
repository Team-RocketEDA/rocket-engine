"""VIEW-SYNC wired integration — run AFTER the integrator applies the patch.

These tests prove the wiring patch, not the modules: a stock Engine
must serve run_view_sync through the connectgraph solver with
FAIL-on-diff and PASS-with-coverage verdicts. They FAIL on an unwired
tree (unsupported_operation) and PASS once the integrator registers
the solver in composition.py, adds the SOLVER_DEPS row, regenerates
the API spec + contract, and reinstalls.
"""

import copy
import json
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "view_sync_mzi.json"
PROJECT = "view-sync-probe"


def _mzi():
    return json.loads(FIXTURE.read_text())


def _engine():
    from rocket_engine.composition import Engine

    return Engine(PROJECT, actor="probe")


def _submit(engine, arguments, request_id):
    arguments = dict(arguments)
    arguments["expected_revision"] = engine.snapshot()["current_revision"]
    return engine.submit(
        {
            "project_id": PROJECT,
            "operation": "run_view_sync",
            "arguments": arguments,
            "request_id": request_id,
        }
    )


def _run(engine, ack, request_id):
    return engine.run(
        {
            "project_id": PROJECT,
            "operation": "run_job",
            "arguments": {"run_id": ack["run_id"]},
            "request_id": request_id,
        }
    )


def test_run_view_sync_reports_planted_diffs():
    engine = _engine()
    mzi = _mzi()
    ack = _submit(
        engine,
        {"intended": mzi["intended"], "extracted": mzi["extracted"], "links": mzi["links"]},
        "vs-wired-1",
    )
    done = _run(engine, ack, "vs-wired-1-run")
    assert done["state"] == "completed"
    assert done["verdict"]["status"] == "FAIL"
    assert "5 findings" in done["verdict"]["measurements"]["coverage"]["statement"]
    found = engine.findings(done["run_id"])["findings"]
    assert len(found) == 5
    assert sorted(f["rule"] for f in found) == [
        "view_sync.extra_port",
        "view_sync.missing_port",
        "view_sync.unexpected_connection",
        "view_sync.unmapped",
        "view_sync.wrong_port",
    ]


def test_run_view_sync_clean_passes_with_coverage():
    engine = _engine()
    mzi = _mzi()
    clean = copy.deepcopy(mzi["intended"])
    renames = {("S1", "out1"): "o1", ("S2", "in1"): "i1"}
    for pin in clean["pins"]:
        key = (pin["instance"], pin["pin"])
        if key in renames:
            pin["pin"] = renames[key]
    ack = _submit(
        engine,
        {"intended": mzi["intended"], "extracted": clean, "links": mzi["links"]},
        "vs-wired-2",
    )
    done = _run(engine, ack, "vs-wired-2-run")
    assert done["state"] == "completed"
    assert done["verdict"]["status"] == "PASS"
    assert "in sync" in done["verdict"]["measurements"]["coverage"]["statement"]


def test_job_kinds_lists_view_sync_tool():
    kinds = {entry["operation"]: entry["tools"] for entry in _engine().job_kinds()["job_kinds"]}
    assert kinds["run_view_sync"] == ["connectgraph"]
