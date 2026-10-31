"""Fuel contract artifact: versioned schemas + id plumbing (FUEL-CONTRACT).

scripts/contract.py publishes docs/contract.json — the API-GEN-B
schemas plus the submit/run_job envelope shapes and the stub overlap
map fuel's mcp-stub pins to. Like api_spec, the artifact is generated
output (freshness-pinned here, never hand-edited); the envelopes are
probed from live engine behavior, and the E2E round trip below proves
the request/run id join both audit trails share.
"""

import copy
import importlib.util
import json
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_contract():
    # RED: scripts/contract.py does not exist yet.
    spec = importlib.util.spec_from_file_location(
        "contract", ROOT / "scripts" / "contract.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_artifact():
    # RED: docs/contract.json does not exist yet.
    return json.loads((ROOT / "docs" / "contract.json").read_text())


class _FakeAdapter:
    """Solver double: PASS verdict without touching any tool."""

    def preflight(self, job):
        return {"ready": True}

    def execute(self, job):
        return {"exit_code": 0, "stdout": "fake", "stderr": ""}

    def parse(self, native_output):
        return {"total": 0, "violations": []}


def _probe_shapes():
    """Ack/completion/event key sets from live behavior (oracle).

    Independent of the generator: drives an in-memory engine with a
    fake solver and records the exact keys each phase returns, so the
    artifact's envelopes pin behavior, not a copy of the code.
    """
    from rocket_engine.composition import Engine

    engine = Engine("contract-probe", actor="contract-probe")
    engine.register_solver("run_em", _FakeAdapter())
    request_id = uuid.uuid4().hex
    ack = engine.submit(
        {
            "project_id": "contract-probe",
            "operation": "run_em",
            "arguments": {"expected_revision": "p12"},
            "request_id": request_id,
        }
    )
    completion = engine.submit(
        {
            "project_id": "contract-probe",
            "operation": "run_job",
            "arguments": {"request_id": request_id},
        }
    )
    page = engine.submit(
        {
            "project_id": "contract-probe",
            "operation": "get_events_since",
            "arguments": {"cursor": 0},
        }
    )
    by_event = {}
    for event in page["events"]:
        by_event.setdefault(event["event"], event)
    return ack, completion, page["events"][0], by_event


def test_contract_versions_pin_engine_release():
    from rocket_engine import __version__

    contract = _load_contract()
    artifact = _read_artifact()
    major, minor, *_ = __version__.split(".")
    assert artifact["contract_version"] == f"rocketeda/tooling/v{major}.{minor}"
    assert artifact["contract_version"] == contract.CONTRACT_VERSION
    assert artifact["engine_version"] == __version__
    assert artifact["schema_sha256"] == contract.contract_hash(artifact)


def test_contract_embeds_api_gen_b_schemas():
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import api_spec
    finally:
        sys.path.pop(0)

    artifact = _read_artifact()
    assert artifact["operations"] == api_spec.build_schemas()["operations"]
    assert artifact["queries"] == api_spec.build_schemas()["queries"]
    assert artifact["operations"]["run_job"]["wired"] is True


def test_contract_envelopes_match_live_behavior():
    artifact = _read_artifact()
    ack, completion, event, by_event = _probe_shapes()
    envelopes = artifact["envelopes"]
    assert sorted(ack) == sorted(envelopes["ack"]["keys"])
    assert sorted(completion) == sorted(envelopes["run_completion"]["keys"])
    assert sorted(event) == sorted(envelopes["ledger_event"]["keys"])
    for name, record in by_event.items():
        assert sorted(record["data"]) == sorted(
            envelopes["ledger_event"]["data_by_event"][name]
        ), name


def test_contract_json_is_current():
    contract = _load_contract()
    assert contract.build_contract() == _read_artifact()


def test_stub_overlap_refs_resolve_inside_contract():
    contract = _load_contract()
    artifact = _read_artifact()
    assert artifact["stub_overlap"] == contract.STUB_OVERLAP
    mappings = artifact["stub_overlap"]["mappings"]
    assert mappings != []
    for entry in mappings:
        assert contract.engine_ref_present(artifact, entry["engine_ref"]), entry
        assert entry["stub_side"] in ("request", "response"), entry
    assert artifact["stub_overlap"]["known_gaps"] != []
    assert artifact["stub_overlap"]["fuel_owned"] != []


def test_submit_run_job_round_trip_joins_request_and_run_ids():
    """E2E: stub-shaped submit->run_job matches engine behavior.

    Fuel-shaped calls (client-minted request id, canonical submit then
    run_job) round-trip with the join intact: the ack echoes the
    request, the completion judges the operation, and both ledger
    events carry the request id plus their run id so fuel's audit log
    and the engine log join on (request_id, run_id).
    """
    from rocket_engine.composition import Engine

    artifact = _read_artifact()
    engine = Engine("fuel-contract-e2e", actor="rocket-fuel")
    engine.register_solver("run_em", _FakeAdapter())
    request_id = f"fuel-{uuid.uuid4().hex}"
    ack = engine.submit(
        {
            "project_id": "fuel-contract-e2e",
            "operation": "run_em",
            "arguments": {"expected_revision": "p12"},
            "request_id": request_id,
        }
    )
    assert ack["state"] == "completed"
    assert ack["request_id"] == request_id
    assert ack["current_revision"] == "p13"
    assert ack["operation"] == "run_em"
    assert ack["verdict"]["status"] == "PASS"
    assert sorted(ack) == sorted(artifact["envelopes"]["ack"]["keys"])

    completion = engine.submit(
        {
            "project_id": "fuel-contract-e2e",
            "operation": "run_job",
            "arguments": {"request_id": request_id},
        }
    )
    assert completion["state"] == "completed"
    assert completion["operation"] == "run_em"
    assert completion["verdict"]["status"] == "PASS"
    assert sorted(completion) == sorted(
        artifact["envelopes"]["run_completion"]["keys"]
    )

    page = engine.submit(
        {
            "project_id": "fuel-contract-e2e",
            "operation": "get_events_since",
            "arguments": {"cursor": 0},
        }
    )
    by_event = {event["event"]: event for event in page["events"]}
    queued = by_event["job_queued"]
    assert queued["request_id"] == request_id
    assert queued["data"]["run_id"] == ack["run_id"]
    assert queued["actor"] == "rocket-fuel"
    done = by_event["run_completed"]
    assert done["request_id"] == request_id
    assert done["data"]["run_id"] == completion["run_id"]
    assert done["data"]["verdict"]["status"] == "PASS"


def test_handshake_doc_names_pin_and_check():
    doc = (ROOT / "docs" / "fuel-contract.md").read_text()
    assert "docs/contract.json" in doc
    assert "scripts/check_contract.py" in doc
    assert "contract.pin" in doc


def test_contract_hash_covers_checkable_bits_only():
    contract = _load_contract()
    artifact = _read_artifact()
    retitled = copy.deepcopy(artifact)
    retitled["stub_overlap"]["known_gaps"].append(
        {"id": "GAP-X", "summary": "prose must not invalidate pins"}
    )
    assert contract.contract_hash(retitled) == artifact["schema_sha256"]
    reschemed = copy.deepcopy(artifact)
    reschemed["envelopes"]["ack"]["keys"].append("bogus_key")
    assert contract.contract_hash(reschemed) != artifact["schema_sha256"]
