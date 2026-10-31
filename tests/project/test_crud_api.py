"""CRUD-API RED — uniform document CRUD over the project tree (I31).

Tests assume the CRUD-API contract:
  - Vocabulary: QUERIES carry list_projects/list_docs/read_doc;
    OPERATIONS carry create_project/write_doc/delete_doc/
    apply_mutations. delete_project, run_script, and per-content
    verbs (create_component, ...) are explicitly out of scope.
  - list_docs/read_doc are wired queries; write/delete/apply are
    immediate OPERATIONS inside submit() (run_job precedent: no
    queue), each returning new revision + events.
  - apply_mutations is all-or-nothing: any validation failure
    lands nothing and names the document.
  - Mutation responses carry actor, diff summary, revision
    transition, and rewind handle.
Valid RED = these fail on the pre-slice engine (unwired names).
"""

import json

import pytest

PROJECT = "analog_demo"


def _code(excinfo):
    return getattr(excinfo.value, "code", None)


def test_vocabulary_contains_crud_names_and_no_per_content_verbs():
    from rocket_engine.interfaces.vocabulary import OPERATIONS, QUERIES

    assert {"list_projects", "list_docs", "read_doc"} <= set(QUERIES)
    assert {
        "create_project",
        "write_doc",
        "delete_doc",
        "apply_mutations",
    } <= set(OPERATIONS)
    for banned in (
        "delete_project",
        "run_script",
        "create_component",
        "create_script",
        "list_components",
    ):
        assert banned not in OPERATIONS
        assert banned not in QUERIES


def test_list_projects_in_memory_returns_bound():
    from rocket_engine.composition import Engine

    engine = Engine(PROJECT, actor="human")
    out = engine.submit(
        {
            "project_id": PROJECT,
            "operation": "list_projects",
            "arguments": {},
            "request_id": "req-lp-001",
        }
    )
    ids = [p["project_id"] for p in out["projects"]]
    assert PROJECT in ids


def test_create_and_list_projects_durable(tmp_path):
    from rocket_engine.composition import Engine

    root = tmp_path / "engine-root"
    engine = Engine(PROJECT, actor="human", engine_root=root)
    created = engine.submit(
        {
            "project_id": PROJECT,
            "operation": "create_project",
            "arguments": {"new_project_id": "demo2"},
            "request_id": "req-cp-001",
        }
    )
    assert created["project_id"] == "demo2"
    assert created["current_revision"] == "p12"
    assert created["actor"] == "human"
    assert "demo2" in created["diff_summary"]
    assert created["revision_transition"] == {"from": None, "to": "p12"}
    assert created["rewind_handle"]["project_id"] == "demo2"
    listed = engine.submit(
        {
            "project_id": PROJECT,
            "operation": "list_projects",
            "arguments": {},
            "request_id": "req-lp-002",
        }
    )
    ids = [p["project_id"] for p in listed["projects"]]
    assert "demo2" in ids
    with pytest.raises(Exception) as excinfo:
        engine.submit(
            {
                "project_id": PROJECT,
                "operation": "create_project",
                "arguments": {"new_project_id": "demo2"},
                "request_id": "req-cp-002",
            }
        )
    assert _code(excinfo) == "project_exists"
    with pytest.raises(Exception) as excinfo:
        engine.submit(
            {
                "project_id": PROJECT,
                "operation": "create_project",
                "arguments": {"new_project_id": "Bad Name!"},
                "request_id": "req-cp-003",
            }
        )
    assert _code(excinfo) == "invalid_project"


def test_write_doc_returns_revision_and_events(tmp_path):
    from rocket_engine.composition import Engine

    root = tmp_path / "engine-root"
    engine = Engine(PROJECT, actor="rocket-fuel", engine_root=root)
    out = engine.submit(
        {
            "project_id": PROJECT,
            "operation": "write_doc",
            "arguments": {
                "path": "schematic.yaml",
                "content": "top: amp\n",
                "expected_revision": "p12",
            },
            "request_id": "req-w-001",
        }
    )
    assert out["previous_revision"] == "p12"
    assert out["current_revision"] == "p13"
    assert out["revision_transition"] == {"from": "p12", "to": "p13"}
    assert out["actor"] == "rocket-fuel"
    assert "schematic.yaml" in out["diff_summary"]
    assert out["rewind_handle"] == {
        "project_id": PROJECT,
        "revision": "p12",
        "request_id": "req-w-001",
    }
    assert len(out["events"]) == 1
    assert out["events"][0]["event"] == "doc_written"
    assert out["events"][0]["actor"] == "rocket-fuel"
    assert out["events"][0]["data"]["revision"] == "p13"
    read = engine.submit(
        {
            "project_id": PROJECT,
            "operation": "read_doc",
            "arguments": {"path": "schematic.yaml"},
            "request_id": "req-r-001",
        }
    )
    assert read["content"] == "top: amp\n"
    assert read["current_revision"] == "p13"
    listed = engine.submit(
        {
            "project_id": PROJECT,
            "operation": "list_docs",
            "arguments": {},
            "request_id": "req-ld-001",
        }
    )
    paths = [d["path"] for d in listed["documents"]]
    assert "schematic.yaml" in paths


def test_write_doc_stale_rejected_without_effects(tmp_path):
    from rocket_engine.composition import Engine

    root = tmp_path / "engine-root"
    engine = Engine(PROJECT, actor="human", engine_root=root)
    engine.submit(
        {
            "project_id": PROJECT,
            "operation": "write_doc",
            "arguments": {
                "path": "a.txt",
                "content": "one\n",
                "expected_revision": "p12",
            },
            "request_id": "req-ws-001",
        }
    )
    before = engine.snapshot()["event_cursor"]
    with pytest.raises(Exception) as excinfo:
        engine.submit(
            {
                "project_id": PROJECT,
                "operation": "write_doc",
                "arguments": {
                    "path": "b.txt",
                    "content": "two\n",
                    "expected_revision": "p12",
                },
                "request_id": "req-ws-002",
            }
        )
    assert _code(excinfo) == "revision_conflict"
    assert engine.snapshot()["current_revision"] == "p13"
    assert engine.snapshot()["event_cursor"] == before
    with pytest.raises(Exception) as excinfo:
        engine.submit(
            {
                "project_id": PROJECT,
                "operation": "read_doc",
                "arguments": {"path": "b.txt"},
                "request_id": "req-ws-003",
            }
        )
    assert _code(excinfo) == "unknown_document"


def test_write_doc_idempotent_replay(tmp_path):
    from rocket_engine.composition import Engine

    root = tmp_path / "engine-root"
    engine = Engine(PROJECT, actor="human", engine_root=root)
    command = {
        "project_id": PROJECT,
        "operation": "write_doc",
        "arguments": {
            "path": "note.txt",
            "content": "hi\n",
            "expected_revision": "p12",
        },
        "request_id": "req-replay-1",
    }
    first = engine.submit(command)
    retry = engine.submit(dict(command))
    assert retry == first
    assert engine.snapshot()["current_revision"] == "p13"
    assert engine.snapshot()["event_cursor"] == 1


def test_delete_doc(tmp_path):
    from rocket_engine.composition import Engine

    root = tmp_path / "engine-root"
    engine = Engine(PROJECT, actor="human", engine_root=root)
    engine.submit(
        {
            "project_id": PROJECT,
            "operation": "write_doc",
            "arguments": {
                "path": "gone.txt",
                "content": "bye\n",
                "expected_revision": "p12",
            },
            "request_id": "req-d-001",
        }
    )
    out = engine.submit(
        {
            "project_id": PROJECT,
            "operation": "delete_doc",
            "arguments": {"path": "gone.txt", "expected_revision": "p13"},
            "request_id": "req-d-002",
        }
    )
    assert out["previous_revision"] == "p13"
    assert out["current_revision"] == "p14"
    assert out["events"][0]["event"] == "doc_deleted"
    assert "gone.txt" in out["diff_summary"]
    with pytest.raises(Exception) as excinfo:
        engine.submit(
            {
                "project_id": PROJECT,
                "operation": "read_doc",
                "arguments": {"path": "gone.txt"},
                "request_id": "req-d-003",
            }
        )
    assert _code(excinfo) == "unknown_document"
    with pytest.raises(Exception) as excinfo:
        engine.submit(
            {
                "project_id": PROJECT,
                "operation": "delete_doc",
                "arguments": {"path": "missing.txt", "expected_revision": "p14"},
                "request_id": "req-d-004",
            }
        )
    assert _code(excinfo) == "unknown_document"


def test_apply_mutations_atomic_single_revision(tmp_path):
    from rocket_engine.composition import Engine

    root = tmp_path / "engine-root"
    engine = Engine(PROJECT, actor="human", engine_root=root)
    out = engine.submit(
        {
            "project_id": PROJECT,
            "operation": "apply_mutations",
            "arguments": {
                "mutations": [
                    {"op": "write", "path": "a.txt", "content": "a\n"},
                    {"op": "write", "path": "b.txt", "content": "b\n"},
                ],
                "expected_revision": "p12",
            },
            "request_id": "req-batch-001",
        }
    )
    assert out["previous_revision"] == "p12"
    assert out["current_revision"] == "p13"
    assert len(out["events"]) == 1
    assert out["events"][0]["event"] == "mutations_applied"
    assert "a.txt" in out["diff_summary"]
    assert "b.txt" in out["diff_summary"]
    for path, want in (("a.txt", "a\n"), ("b.txt", "b\n")):
        read = engine.submit(
            {
                "project_id": PROJECT,
                "operation": "read_doc",
                "arguments": {"path": path},
                "request_id": f"req-batch-r-{path}",
            }
        )
        assert read["content"] == want


def test_apply_mutations_partial_failure_lands_nothing_naming_doc(tmp_path):
    from rocket_engine.composition import Engine

    root = tmp_path / "engine-root"
    engine = Engine(PROJECT, actor="human", engine_root=root)
    with pytest.raises(Exception) as excinfo:
        engine.submit(
            {
                "project_id": PROJECT,
                "operation": "apply_mutations",
                "arguments": {
                    "mutations": [
                        {"op": "write", "path": "good.txt", "content": "g\n"},
                        {"op": "delete", "path": "nope-missing.txt"},
                    ],
                    "expected_revision": "p12",
                },
                "request_id": "req-batch-fail-001",
            }
        )
    assert "nope-missing.txt" in str(excinfo.value)
    assert engine.snapshot()["current_revision"] == "p12"
    assert engine.snapshot()["event_cursor"] == 0
    with pytest.raises(Exception) as excinfo:
        engine.submit(
            {
                "project_id": PROJECT,
                "operation": "read_doc",
                "arguments": {"path": "good.txt"},
                "request_id": "req-batch-fail-002",
            }
        )
    assert _code(excinfo) == "unknown_document"


def test_apply_mutations_stale_rejected(tmp_path):
    from rocket_engine.composition import Engine

    root = tmp_path / "engine-root"
    engine = Engine(PROJECT, actor="human", engine_root=root)
    engine.submit(
        {
            "project_id": PROJECT,
            "operation": "write_doc",
            "arguments": {
                "path": "a.txt",
                "content": "a\n",
                "expected_revision": "p12",
            },
            "request_id": "req-bs-001",
        }
    )
    with pytest.raises(Exception) as excinfo:
        engine.submit(
            {
                "project_id": PROJECT,
                "operation": "apply_mutations",
                "arguments": {
                    "mutations": [
                        {"op": "write", "path": "b.txt", "content": "b\n"},
                    ],
                    "expected_revision": "p12",
                },
                "request_id": "req-bs-002",
            }
        )
    assert _code(excinfo) == "revision_conflict"
    assert engine.snapshot()["current_revision"] == "p13"


def test_reserved_and_escape_paths_rejected(tmp_path):
    from rocket_engine.composition import Engine

    root = tmp_path / "engine-root"
    engine = Engine(PROJECT, actor="human", engine_root=root)
    for bad in ("ledger.yaml", "events.yaml", "runs/evil.txt", "../escape.txt", "/abs.txt"):
        with pytest.raises(Exception) as excinfo:
            engine.submit(
                {
                    "project_id": PROJECT,
                    "operation": "write_doc",
                    "arguments": {
                        "path": bad,
                        "content": "x\n",
                        "expected_revision": "p12",
                    },
                    "request_id": f"req-bad-{abs(hash(bad)) % 10**8}",
                }
            )
        assert _code(excinfo) in ("invalid_path", "path_escape")
    assert engine.snapshot()["current_revision"] == "p12"
    assert engine.snapshot()["event_cursor"] == 0


def test_components_scripts_are_conventional_paths(tmp_path):
    from rocket_engine.composition import Engine

    root = tmp_path / "engine-root"
    engine = Engine(PROJECT, actor="human", engine_root=root)
    engine.submit(
        {
            "project_id": PROJECT,
            "operation": "write_doc",
            "arguments": {
                "path": "components/amp.yaml",
                "content": "kind: amp\n",
                "expected_revision": "p12",
            },
            "request_id": "req-conv-001",
        }
    )
    engine.submit(
        {
            "project_id": PROJECT,
            "operation": "write_doc",
            "arguments": {
                "path": "scripts/sim.py",
                "content": "print('sim')\n",
                "expected_revision": "p13",
            },
            "request_id": "req-conv-002",
        }
    )
    listed = engine.submit(
        {
            "project_id": PROJECT,
            "operation": "list_docs",
            "arguments": {},
            "request_id": "req-conv-003",
        }
    )
    paths = [d["path"] for d in listed["documents"]]
    assert "components/amp.yaml" in paths
    assert "scripts/sim.py" in paths


def test_mcp_crud_round_trip(tmp_path):
    from rocket_engine.adapters.mcp import McpTransport
    from rocket_engine.composition import Engine

    root = tmp_path / "engine-root"
    engine = Engine(PROJECT, actor="human", engine_root=root)
    transport = McpTransport(engine, project_id=PROJECT)

    def _call(name, arguments, call_id):
        return json.dumps(
            {
                "jsonrpc": "2.0",
                "id": call_id,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
        )

    written = transport.handle(
        _call(
            "write_doc",
            {
                "project_id": PROJECT,
                "path": "mcp.txt",
                "content": "via-mcp\n",
                "expected_revision": "p12",
            },
            "req-mcp-001",
        )
    )
    assert written["current_revision"] == "p13"
    read = transport.handle(
        _call("read_doc", {"project_id": PROJECT, "path": "mcp.txt"}, "req-mcp-002")
    )
    assert read["content"] == "via-mcp\n"


def test_delete_project_and_run_script_out_of_scope():
    from rocket_engine.composition import Engine

    engine = Engine(PROJECT, actor="human")
    for name in ("delete_project", "run_script"):
        with pytest.raises(Exception) as excinfo:
            engine.submit(
                {
                    "project_id": PROJECT,
                    "operation": name,
                    "arguments": {},
                    "request_id": f"req-oos-{name}",
                }
            )
        assert _code(excinfo) == "unsupported_operation"
