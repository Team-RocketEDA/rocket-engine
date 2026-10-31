"""Fuel contract publisher: schemas + envelopes + overlap in, pin out.

FUEL-CONTRACT's engine side: docs/contract.json is the versioned
artifact fuel's mcp-stub pins to — the API-GEN-B schemas (IDE types,
stub shapes), the submit/run_job envelope shapes carrying the shared
request/run ids both audit trails join on, and the stub overlap map
the drift check enforces. Like api_spec, this generator derives its
output from code: schemas from docstrings, envelopes from live
in-memory engine probes (a fake solver, no tools), versions from the
package release. STUB_OVERLAP is the one curated seam (which stub
tool maps to which engine shape — the fuel side cannot be derived
from engine code); its notes explain, its tuples pin.

Pin semantics: contract_version names the tooling line
(rocketeda/tooling/v<major>.<minor>); schema_sha256 pins the exact
checkable bits (schemas, envelopes, overlap tuples). Either half
skewed means a stale stub, and the drift check fails loudly.

Usage: python scripts/contract.py [--write|--check] (default --check).
"""

import argparse
import copy
import hashlib
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import api_spec  # noqa: E402
from check_contract import engine_ref_present  # noqa: E402,F401

ROOT = Path(__file__).resolve().parent.parent


def _tooling_line():
    from rocket_engine import __version__

    major, minor, *_ = __version__.split(".")
    return f"rocketeda/tooling/v{major}.{minor}", __version__


CONTRACT_VERSION, ENGINE_VERSION = _tooling_line()

# Curated seam: which stub tool maps to which engine shape. Tuples
# (stub_tool, stub_side, stub_field, engine_ref) are checkable and
# hashed; notes explain and are not. known_gaps document real
# mismatch both sides accept for now (reported, never enforced);
# fuel_owned names stub tools with no engine counterpart at all.
STUB_OVERLAP = {
    "mappings": [
        {
            "stub_tool": "run_job",
            "stub_side": "response",
            "stub_field": "run_id",
            "engine_ref": "envelopes.run_completion.keys.run_id",
            "note": "Execution id echoed on completion.",
        },
        {
            "stub_tool": "get_job_status",
            "stub_side": "request",
            "stub_field": "run_id",
            "engine_ref": "envelopes.run_completion.keys.run_id",
            "note": "run_id addresses a run on both sides; the "
            "same-name engine query is unwired (GAP-2), so this "
            "pins the shared completion shape, not engine wiring.",
        },
        {
            "stub_tool": "get_job_status",
            "stub_side": "response",
            "stub_field": "run_id",
            "engine_ref": "envelopes.run_completion.keys.run_id",
            "note": "Completion echo of the addressing id (GAP-2 "
            "applies: shared shape, not engine wiring).",
        },
        {
            "stub_tool": "get_logs",
            "stub_side": "request",
            "stub_field": "run_id",
            "engine_ref": "envelopes.run_completion.keys.run_id",
            "note": "Log reads address the execution id (GAP-2 "
            "applies: shared shape, not engine wiring).",
        },
        {
            "stub_tool": "get_logs",
            "stub_side": "response",
            "stub_field": "run_id",
            "engine_ref": "envelopes.run_completion.keys.run_id",
            "note": "Log page echo of the execution id (GAP-2 "
            "applies: shared shape, not engine wiring).",
        },
    ],
    "known_gaps": [
        {
            "id": "GAP-1",
            "summary": "request_id carriage: stub run_job takes "
            "kind/hypothesis (repair-loop bookkeeping), not the "
            "admission request_id; engine run_job takes request_id "
            "only on GREEN-the-tests. Fuel adopts request_id per "
            "docs/fuel-contract.md; until then the check cannot pin "
            "submit-phase calls.",
        },
        {
            "id": "GAP-2",
            "summary": "Job queries unwired engine-side: "
            "get_job_status, get_check_results, get_logs, "
            "list_job_kinds have no engine handler on "
            "GREEN-the-tests (merge/fuel-mcp wires the agent path "
            "including run_job-by-run_id; integration pending). "
            "Mappings pin shared envelope shapes only, never "
            "same-name engine wiring.",
        },
        {
            "id": "GAP-3",
            "summary": "ack/completion run_id duality: on "
            "GREEN-the-tests the submit ack run_id (queue id) "
            "differs from the run_job completion run_id (execution "
            "id); join across phases by request_id. merge/fuel-mcp "
            "decides the ack run_id IS the execution id and run_job "
            "accepts run_id; the stub MUST NOT assume identity "
            "until this contract says so.",
        },
        {
            "id": "GAP-4",
            "summary": "Error shapes unconverged: stub "
            "{error, message} vs engine MCP {ok: false, code, "
            "message}. Join and audit work MUST match on ids, not "
            "error bodies.",
        },
        {
            "id": "GAP-5",
            "summary": "Constraints ownership: caller-supplied "
            "run_spice min/max are accepted on GREEN-the-tests "
            "HEAD; merge/fuel-mcp refuses caller targets in favor "
            "of project constraints. The stub MUST NOT treat "
            "caller targets as engine-accepted.",
        },
    ],
    "fuel_owned": [
        "apply_revision",
        "get_constraints",
        "get_status",
        "ip_get",
        "ip_register",
        "ip_search",
        "propose_constraint_change",
        "propose_revision",
    ],
}


def _checkable_bits(artifact):
    """Pin scope: exactly what the drift check enforces."""
    return {
        "operations": artifact["operations"],
        "queries": artifact["queries"],
        "envelopes": artifact["envelopes"],
        "mappings": [
            {
                "stub_tool": entry["stub_tool"],
                "stub_side": entry["stub_side"],
                "stub_field": entry["stub_field"],
                "engine_ref": entry["engine_ref"],
            }
            for entry in artifact["stub_overlap"]["mappings"]
        ],
    }


def contract_hash(artifact):
    """Schema pin: sha256 over the canonical checkable bits."""
    canonical = json.dumps(
        _checkable_bits(artifact), sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class _PassAdapter:
    """Probe solver: PASS verdict without touching any tool."""

    def preflight(self, job):
        return {"ready": True}

    def execute(self, job):
        return {"exit_code": 0, "stdout": "probe", "stderr": ""}

    def parse(self, native_output):
        return {"total": 0, "violations": []}


class _FailAdapter(_PassAdapter):
    """Probe solver: NOT_RUN verdict via a typed tool failure."""

    def execute(self, job):
        from rocket_engine.adapters.errors import AdapterError

        raise AdapterError("runner_unavailable", "probe tool exploded")


def build_envelopes():
    """Envelope shapes probed from live engine behavior.

    Drives in-memory engines with fake solvers (no tools, no disk)
    and records the exact keys each phase returns, asserting the
    request/run id join as it goes: generation fails loudly when
    the plumbing breaks instead of publishing a fantasy contract.
    """
    from rocket_engine.composition import Engine
    from rocket_engine.project.errors import ProjectError

    engine = Engine("contract-probe", actor="contract-probe")
    engine.register_solver("run_em", _PassAdapter())
    request_id = uuid.uuid4().hex
    ack = engine.submit(
        {
            "project_id": "contract-probe",
            "operation": "run_em",
            "arguments": {"expected_revision": "p12"},
            "request_id": request_id,
        }
    )
    assert ack["request_id"] == request_id, ack
    assert ack["state"] == "completed", ack
    assert ack["operation"] == "run_em", ack
    assert ack["verdict"]["status"] == "PASS", ack
    completion = engine.submit(
        {
            "project_id": "contract-probe",
            "operation": "run_job",
            "arguments": {"request_id": request_id},
        }
    )
    assert completion["state"] == "completed", completion
    assert completion["operation"] == "run_em", completion
    page = engine.submit(
        {
            "project_id": "contract-probe",
            "operation": "get_events_since",
            "arguments": {"cursor": 0},
        }
    )
    by_event = {event["event"]: event for event in page["events"]}
    assert by_event["job_queued"]["request_id"] == request_id
    assert by_event["job_queued"]["data"]["run_id"] == ack["run_id"]
    assert by_event["run_completed"]["request_id"] == request_id
    assert (
        by_event["run_completed"]["data"]["run_id"]
        == completion["run_id"]
    )

    failing = Engine("contract-probe-fail", actor="contract-probe")
    failing.register_solver("run_em", _FailAdapter())
    failed_id = uuid.uuid4().hex
    failing.submit(
        {
            "project_id": "contract-probe-fail",
            "operation": "run_em",
            "arguments": {"expected_revision": "p12"},
            "request_id": failed_id,
        }
    )
    failing.submit(
        {
            "project_id": "contract-probe-fail",
            "operation": "run_job",
            "arguments": {"request_id": failed_id},
        }
    )
    failed_page = failing.submit(
        {
            "project_id": "contract-probe-fail",
            "operation": "get_events_since",
            "arguments": {"cursor": 0},
        }
    )
    failed_events = {
        event["event"]: event for event in failed_page["events"]
    }
    assert failed_events["run_failed"]["request_id"] == failed_id

    defaulted = []
    try:
        anonymous = engine.submit(
            {
                "project_id": "contract-probe",
                "operation": "run_em",
                "arguments": {
                    "expected_revision": ack["current_revision"]
                },
            }
        )
    except ProjectError:
        anonymous = {}
    if anonymous.get("request_id"):
        defaulted.append("request_id")
    try:
        engine.submit(
            {"project_id": "contract-probe", "operation": "list_projects"}
        )
    except ProjectError:
        pass
    else:
        defaulted.append("arguments")

    data_by_event = {
        name: sorted(record["data"])
        for name, record in sorted(by_event.items())
    }
    data_by_event["run_failed"] = sorted(
        failed_events["run_failed"]["data"]
    )
    return {
        "submit_envelope": {
            "required_by_contract": sorted(
                ["project_id", "operation", "arguments", "request_id"]
            ),
            "engine_defaulted_when_absent": sorted(defaulted),
        },
        "ack": {"keys": sorted(ack)},
        "run_completion": {"keys": sorted(completion)},
        "ledger_event": {
            "keys": sorted(page["events"][0]),
            "data_by_event": data_by_event,
        },
    }


def build_contract(root=None):
    """Full contract artifact, derived from code and behavior."""
    schemas = api_spec.build_schemas(
        root=root if root is not None else api_spec.SRC
    )
    artifact = {
        "contract_version": CONTRACT_VERSION,
        "engine_version": ENGINE_VERSION,
        "schema_sha256": "",
        "operations": schemas["operations"],
        "queries": schemas["queries"],
        "envelopes": build_envelopes(),
        "stub_overlap": copy.deepcopy(STUB_OVERLAP),
    }
    artifact["schema_sha256"] = contract_hash(artifact)
    return artifact


def _dumps(payload):
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def main(argv):
    """Regenerate (--write) or freshness-check (--check, default)."""
    parser = argparse.ArgumentParser(description="Fuel contract publisher.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--write", action="store_true")
    group.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    path = ROOT / "docs" / "contract.json"
    text = _dumps(build_contract())
    if args.write:
        path.write_text(text, encoding="utf-8")
        return 0
    if not path.is_file() or path.read_text(encoding="utf-8") != text:
        print(f"stale generated output: {path} (run --write)")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
