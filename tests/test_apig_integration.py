"""API-GENERALIZE integration: integrator runs AFTER applying the wiring patch.

Default (unpatched tree): every test skips with a named reason, so the
shared branch stays green. Forced probe (`APIG_PROBE_WIRING=1`): skips
lift and each test fails on the missing surface — that failure IS the
RED evidence the patch must turn green. Patched tree: the probe sees
the wired vocabulary + Engine methods and every test runs for real.
"""

import base64
import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

from rocket_engine.composition import Engine
from rocket_engine.interfaces.vocabulary import OPERATIONS, QUERIES

PROBE_FORCED = os.environ.get("APIG_PROBE_WIRING") == "1"
WIRED = PROBE_FORCED or (
    "place_cell" in OPERATIONS
    and {"list_cells", "serve_asset", "list_assets"} <= set(QUERIES)
    and hasattr(Engine, "catalog_cells")
    and hasattr(Engine, "replay_pending")
)
needs_wiring = pytest.mark.skipif(
    not WIRED, reason="needs APIG wiring patch (docs/work/API-GENERALIZE/report.md)"
)

SYM_BYTES = (
    b"v {xschem version=3.4.4 file_version=1.2}\n"
    b"K {type=subcircuit\nformat=\"@name @pinlist @model\"\n}\n"
)
SEED_CELLS = [
    {
        "cell": "nand2",
        "pdk": "demopdk",
        "pdk_revision": "r1",
        "ports": ["A", "B", "Y"],
        "default_params": {"drive": 2},
    },
    {
        "cell": "inv",
        "pdk": "demopdk",
        "pdk_revision": "r1",
        "ports": ["A", "Y"],
        "default_params": {"drive": 1},
    },
]


class _StubAdapter:
    def __init__(self):
        self.runs = 0

    def preflight(self, job):
        return {"ok": True}

    def execute(self, job):
        self.runs += 1
        return {"exit_code": 0, "log": "stub ok"}

    def parse(self, native):
        return {"violations": []}


def _engine(project_id="apigint", **kwargs):
    engine = Engine(project_id, actor="test", **kwargs)
    stub = _StubAdapter()
    engine.register_solver("run_syntax", stub, tool="apig_stub")
    engine.register_cells(SEED_CELLS)
    return engine, stub


def _op(engine, operation, arguments, request_id):
    return engine.submit({
        "project_id": engine.snapshot()["project_id"],
        "operation": operation,
        "arguments": arguments,
        "request_id": request_id,
    })


@needs_wiring
def test_submit_executes_inline_with_ack_shape_and_verdict():
    engine, stub = _engine()
    head = engine.snapshot()["current_revision"]
    merged = _op(engine, "run_syntax", {
        "cell": "x", "expected_revision": head,
        "deck": {"tool": "apig_stub"},
    }, "req-inline-1")
    assert merged["state"] == "completed"
    assert merged["verdict"]["status"] == "PASS"
    for key in ("request_id", "project_id", "run_id", "snapshot_id",
                "current_revision", "event_cursor"):
        assert key in merged
    assert stub.runs == 1


@needs_wiring
def test_run_job_is_idempotent_fetch_after_inline_submit():
    engine, stub = _engine()
    head = engine.snapshot()["current_revision"]
    merged = _op(engine, "run_syntax", {
        "cell": "x", "expected_revision": head,
        "deck": {"tool": "apig_stub"},
    }, "req-fetch-1")
    first = _op(engine, "run_job", {"run_id": merged["run_id"]}, "req-fetch-2")
    second = _op(engine, "run_job", {"run_id": merged["run_id"]}, "req-fetch-3")
    assert first == second
    assert first["verdict"] == merged["verdict"]
    assert stub.runs == 1


@needs_wiring
def test_run_job_batch_pumps_in_order_with_loud_refusal():
    engine, stub = _engine(pool_max_depth=2)
    head = engine.snapshot()["current_revision"]
    # Consume the lazy boot replay with one inline submit, so the
    # staged backlog below reaches the batch pump itself (replay
    # would otherwise — correctly — drain it first).
    _op(engine, "run_syntax", {
        "cell": "warmup", "expected_revision": head,
        "deck": {"tool": "apig_stub"},
    }, "req-batch-warmup")
    assert stub.runs == 1
    # Stage backlog the way a crash would: admit to the ledger
    # without draining (bypasses the pool bound, like survivors
    # from a dead process the fresh pool never saw).
    head = engine.snapshot()["current_revision"]
    staged = []
    for index in range(3):
        ack = engine._project.submit(
            _dump(head, index), f"req-batch-{index}",
            expected_revision=head,
        )
        head = ack["current_revision"]
        staged.append(ack)
    batch = _op(engine, "run_job",
                {"run_ids": [ack["run_id"] for ack in staged]},
                "req-batch-pump")
    assert [c["run_id"] for c in batch["completions"]] == [
        staged[0]["run_id"], staged[1]["run_id"]]
    assert all(c["verdict"]["status"] == "PASS" for c in batch["completions"])
    assert len(batch["refused"]) == 1
    assert batch["refused"][0]["run_id"] == staged[2]["run_id"]
    assert batch["refused"][0]["code"] == "pool_full"
    assert stub.runs == 3


def _dump(head, index):
    import io

    from ruamel.yaml import YAML

    buf = io.StringIO()
    YAML(typ="safe").dump(
        {"operation": "run_syntax",
         "arguments": {"cell": f"b{index}", "deck": {"tool": "apig_stub"}}},
        buf,
    )
    return buf.getvalue()


@needs_wiring
def test_spam_place_cell_all_acked_exactly_once():
    engine, _ = _engine()
    start = engine.snapshot()["current_revision"]
    for index in range(25):
        head = engine.snapshot()["current_revision"]
        mapping = _op(engine, "place_cell", {
            "cell": "inv", "pdk": "demopdk", "instance_id": f"u{index}",
            "expected_revision": head,
        }, f"req-spam-{index}")
        assert mapping["current_revision"] != head
    docs = _op(engine, "list_docs", {"prefix": "components"}, "req-list-1")
    assert len(docs["documents"]) == 25
    assert engine.snapshot()["current_revision"] != start
    # No frontend gdsfactory import: the query serves plain data and
    # triggers no gdsfactory import itself, whatever the solver
    # adapters pulled in at engine construction.
    before = set(sys.modules)
    listing = _op(engine, "list_cells", {"pdk": "demopdk"}, "req-spam-cat")
    json.dumps(listing)
    assert "gdsfactory" not in set(sys.modules) - before


@needs_wiring
def test_catalogue_round_trip_list_place_simulate_verdict():
    engine, stub = _engine()
    listing = _op(engine, "list_cells", {"pdk": "demopdk"}, "req-cat-1")
    assert listing["catalog_version"] >= 1
    assert {e["cell"] for e in listing["cells"]} == {"inv", "nand2"}
    json.dumps(listing)
    head = engine.snapshot()["current_revision"]
    mapping = _op(engine, "place_cell", {
        "cell": "nand2", "pdk": "demopdk", "instance_id": "u_nand",
        "params": {"drive": 3}, "expected_revision": head,
    }, "req-cat-2")
    assert mapping["current_revision"] != head
    head = engine.snapshot()["current_revision"]
    merged = _op(engine, "run_syntax", {
        "cell": "u_nand", "expected_revision": head,
        "deck": {"tool": "apig_stub"},
    }, "req-cat-3")
    assert merged["verdict"]["status"] == "PASS"
    assert stub.runs == 1


@needs_wiring
def test_kill_reboot_replays_through_engine(tmp_path):
    root = tmp_path / "eng"
    engine_a, _ = _engine("apigkill", engine_root=root)
    head = engine_a.snapshot()["current_revision"]
    first = _op(engine_a, "run_syntax", {
        "cell": "a", "expected_revision": head,
        "deck": {"tool": "apig_stub"},
    }, "req-kill-1")
    assert first["verdict"]["status"] == "PASS"
    # Crash between admit and drain: backlog survives in the ledger only.
    head = engine_a.snapshot()["current_revision"]
    staged = engine_a._pool.submit_request(
        _dump(head, 7), "req-kill-2", expected_revision=head
    )
    del engine_a
    engine_b, stub_b = _engine("apigkill", engine_root=root)
    report = engine_b.replay_pending()
    assert report["replayed"] == [staged["run_id"]]
    assert report["completions"][0]["verdict"]["status"] == "PASS"
    assert stub_b.runs == 1
    assert engine_b.replay_pending()["replayed"] == []


@needs_wiring
def test_raw_asset_serving_through_engine(tmp_path):
    root = tmp_path / "eng"
    base = root / "pdks" / "demopdk" / "r1"
    (base / "xschem").mkdir(parents=True)
    (base / "inv.sym").write_bytes(SYM_BYTES)
    engine, _ = _engine()
    served = _op(engine, "serve_asset", {
        "pdk_id": "demopdk", "revision": "r1", "path": "inv.sym",
        "engine_root": str(root),
    }, "req-asset-1")
    assert base64.b64decode(served["content_b64"]) == SYM_BYTES
    assert served["sha256"] == hashlib.sha256(SYM_BYTES).hexdigest()
    listing = _op(engine, "list_assets", {
        "pdk_id": "demopdk", "revision": "r1", "engine_root": str(root),
    }, "req-asset-2")
    assert "inv.sym" in [entry["path"] for entry in listing["files"]]
