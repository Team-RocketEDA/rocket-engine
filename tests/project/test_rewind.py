"""REWIND RED — restorable project snapshots (management-plane).

Tests assume the REWIND contract:
  - Vocabulary: OPERATIONS carries rewind (immediate mutation, no
    queue, no solver — CRUD precedent).
  - Every revision is restorable: mutate → rewind(target) →
    byte-identical managed tree at the target, with the rewind
    itself appended as a new event (history append-only, revision
    advances from the live head, never rewritten back).
  - Linked caller trees: rewind restores engine-tracked state
    only; caller files outside .rocket/ are reported in the
    response and never touched (ADR-001 boundary).
Valid RED = these fail on the pre-slice engine (unwired rewind,
no snapshots, no linked_root).
"""

import json

import pytest

PROJECT = "analog_demo"


def _code(excinfo):
    return getattr(excinfo.value, "code", None)


def _write(engine, path, content, revision, request_id):
    return engine.submit(
        {
            "project_id": PROJECT,
            "operation": "write_doc",
            "arguments": {
                "path": path,
                "content": content,
                "expected_revision": revision,
            },
            "request_id": request_id,
        }
    )


def _rewind(engine, target, revision, request_id):
    return engine.submit(
        {
            "project_id": PROJECT,
            "operation": "rewind",
            "arguments": {
                "target_revision": target,
                "expected_revision": revision,
            },
            "request_id": request_id,
        }
    )


def _tree_bytes(project_dir):
    """Managed bytes: every file except ledger/events/runs/snapshots."""
    found = {}
    for target in sorted(project_dir.rglob("*")):
        if not target.is_file():
            continue
        rel = target.relative_to(project_dir).as_posix()
        if rel in ("ledger.yaml", "events.yaml"):
            continue
        if rel == "runs" or rel.startswith("runs/"):
            continue
        if rel == "snapshots" or rel.startswith("snapshots/"):
            continue
        found[rel] = target.read_bytes()
    return found


def test_vocabulary_contains_rewind_operation():
    from rocket_engine.interfaces.vocabulary import OPERATIONS, QUERIES

    assert "rewind" in OPERATIONS
    assert "rewind" not in QUERIES


def test_mutate_rewind_byte_identical_durable(tmp_path):
    from rocket_engine.composition import Engine

    root = tmp_path / "engine-root"
    engine = Engine(PROJECT, actor="human", engine_root=root)
    _write(engine, "a.txt", "v1\n", "p12", "req-rw-001")
    _write(engine, "b.txt", "b1\n", "p13", "req-rw-002")
    project_dir = root / "projects" / PROJECT
    # Runs exhaust must survive the rewind untouched.
    (project_dir / "runs").mkdir(parents=True, exist_ok=True)
    (project_dir / "runs" / "keep.txt").write_text("evidence\n")
    want = _tree_bytes(project_dir)
    assert want == {"a.txt": b"v1\n", "b.txt": b"b1\n"}
    _write(engine, "a.txt", "v2\n", "p14", "req-rw-003")
    engine.submit(
        {
            "project_id": PROJECT,
            "operation": "delete_doc",
            "arguments": {"path": "b.txt", "expected_revision": "p15"},
            "request_id": "req-rw-004",
        }
    )
    assert engine.snapshot()["current_revision"] == "p16"
    assert _tree_bytes(project_dir) == {"a.txt": b"v2\n"}

    out = _rewind(engine, "p14", "p16", "req-rw-005")

    assert out["previous_revision"] == "p16"
    assert out["current_revision"] == "p17"
    assert out["revision_transition"] == {"from": "p16", "to": "p17"}
    assert out["target_revision"] == "p14"
    assert out["actor"] == "human"
    assert "p14" in out["diff_summary"]
    assert out["rewind_handle"] == {
        "project_id": PROJECT,
        "revision": "p16",
        "request_id": "req-rw-005",
    }
    assert _tree_bytes(project_dir) == want
    read = engine.submit(
        {
            "project_id": PROJECT,
            "operation": "read_doc",
            "arguments": {"path": "a.txt"},
            "request_id": "req-rw-006",
        }
    )
    assert read["content"] == "v1\n"
    assert (project_dir / "runs" / "keep.txt").read_text() == "evidence\n"


def test_rewind_appends_event_history_append_only(tmp_path):
    from rocket_engine.composition import Engine

    root = tmp_path / "engine-root"
    engine = Engine(PROJECT, actor="rocket-fuel", engine_root=root)
    _write(engine, "a.txt", "one\n", "p12", "req-rwe-001")
    _write(engine, "a.txt", "two\n", "p13", "req-rwe-002")
    before = engine.events_since(0)
    assert [e["event"] for e in before] == ["doc_written", "doc_written"]

    out = _rewind(engine, "p13", "p14", "req-rwe-003")

    assert len(out["events"]) == 1
    record = out["events"][0]
    assert record["event"] == "project_rewound"
    assert record["actor"] == "rocket-fuel"
    assert record["request_id"] == "req-rwe-003"
    assert record["data"]["target_revision"] == "p13"
    assert record["data"]["revision"] == "p15"
    after = engine.events_since(0)
    assert [e["event"] for e in after] == [
        "doc_written",
        "doc_written",
        "project_rewound",
    ]
    assert [e["seq"] for e in after] == [1, 2, 3]
    assert after[:2] == before
    assert engine.snapshot()["current_revision"] == "p15"
    assert engine.snapshot()["event_cursor"] == 3
    page = engine.submit(
        {
            "project_id": PROJECT,
            "operation": "get_events_since",
            "arguments": {"cursor": 2},
            "request_id": "req-rwe-004",
        }
    )
    assert [e["event"] for e in page["events"]] == ["project_rewound"]


def test_rewind_linked_external_reported_untouched(tmp_path):
    from rocket_engine.composition import Engine

    root = tmp_path / "engine-root"
    caller = tmp_path / "caller"
    (caller / "src").mkdir(parents=True)
    (caller / "src" / "main.py").write_text("print(1)\n")
    (caller / "README.md").write_text("hello\n")
    (caller / ".rocket" / "runs").mkdir(parents=True)
    (caller / ".rocket" / "runs" / "ev.txt").write_text("exhaust\n")
    engine = Engine(
        PROJECT, actor="human", engine_root=root, linked_root=caller
    )
    _write(engine, "a.txt", "v1\n", "p12", "req-rwl-001")
    _write(engine, "a.txt", "v2\n", "p13", "req-rwl-002")
    caller_before = {
        p.relative_to(caller).as_posix(): p.read_bytes()
        for p in sorted(caller.rglob("*"))
        if p.is_file()
    }

    out = _rewind(engine, "p13", "p14", "req-rwl-003")

    caller_after = {
        p.relative_to(caller).as_posix(): p.read_bytes()
        for p in sorted(caller.rglob("*"))
        if p.is_file()
    }
    assert caller_after == caller_before
    external = sorted(e["path"] for e in out["external_files"])
    assert external == ["README.md", "src/main.py"]
    read = engine.submit(
        {
            "project_id": PROJECT,
            "operation": "read_doc",
            "arguments": {"path": "a.txt"},
            "request_id": "req-rwl-004",
        }
    )
    assert read["content"] == "v1\n"


def test_rewind_stale_rejected_without_effects(tmp_path):
    from rocket_engine.composition import Engine

    root = tmp_path / "engine-root"
    engine = Engine(PROJECT, actor="human", engine_root=root)
    _write(engine, "a.txt", "v1\n", "p12", "req-rws-001")
    before = engine.snapshot()["event_cursor"]
    with pytest.raises(Exception) as excinfo:
        _rewind(engine, "p12", "p12", "req-rws-002")
    assert _code(excinfo) == "revision_conflict"
    assert engine.snapshot()["current_revision"] == "p13"
    assert engine.snapshot()["event_cursor"] == before
    read = engine.submit(
        {
            "project_id": PROJECT,
            "operation": "read_doc",
            "arguments": {"path": "a.txt"},
            "request_id": "req-rws-003",
        }
    )
    assert read["content"] == "v1\n"


def test_rewind_idempotent_replay(tmp_path):
    from rocket_engine.composition import Engine

    root = tmp_path / "engine-root"
    engine = Engine(PROJECT, actor="human", engine_root=root)
    _write(engine, "a.txt", "v1\n", "p12", "req-rwr-001")
    _write(engine, "a.txt", "v2\n", "p13", "req-rwr-002")
    command = {
        "project_id": PROJECT,
        "operation": "rewind",
        "arguments": {"target_revision": "p13", "expected_revision": "p14"},
        "request_id": "req-rwr-003",
    }
    first = engine.submit(command)
    retry = engine.submit(dict(command))
    assert retry == first
    assert engine.snapshot()["current_revision"] == "p15"
    assert engine.snapshot()["event_cursor"] == 3


def test_rewind_unknown_revision(tmp_path):
    from rocket_engine.composition import Engine

    root = tmp_path / "engine-root"
    engine = Engine(PROJECT, actor="human", engine_root=root)
    _write(engine, "a.txt", "v1\n", "p12", "req-rwu-001")
    with pytest.raises(Exception) as excinfo:
        _rewind(engine, "p999", "p13", "req-rwu-002")
    assert _code(excinfo) == "unknown_revision"
    assert engine.snapshot()["current_revision"] == "p13"
    assert engine.snapshot()["event_cursor"] == 1


def test_rewind_to_current_rejected(tmp_path):
    from rocket_engine.composition import Engine

    root = tmp_path / "engine-root"
    engine = Engine(PROJECT, actor="human", engine_root=root)
    _write(engine, "a.txt", "v1\n", "p12", "req-rwcur-001")
    with pytest.raises(Exception) as excinfo:
        _rewind(engine, "p13", "p13", "req-rwcur-002")
    assert _code(excinfo) == "invalid_command"
    assert engine.snapshot()["current_revision"] == "p13"
    assert engine.snapshot()["event_cursor"] == 1


def test_rewind_survives_restart(tmp_path):
    from rocket_engine.composition import Engine

    root = tmp_path / "engine-root"
    engine = Engine(PROJECT, actor="human", engine_root=root)
    _write(engine, "a.txt", "v1\n", "p12", "req-rwrs-001")
    _write(engine, "a.txt", "v2\n", "p13", "req-rwrs-002")
    assert (root / "projects" / PROJECT / "snapshots" / "p13").is_dir()
    assert (root / "projects" / PROJECT / "snapshots" / "p14").is_dir()

    fresh = Engine(PROJECT, actor="human", engine_root=root)
    out = _rewind(fresh, "p13", "p14", "req-rwrs-003")

    assert out["current_revision"] == "p15"
    read = fresh.submit(
        {
            "project_id": PROJECT,
            "operation": "read_doc",
            "arguments": {"path": "a.txt"},
            "request_id": "req-rwrs-004",
        }
    )
    assert read["content"] == "v1\n"


def test_snapshots_excluded_from_docs(tmp_path):
    from rocket_engine.composition import Engine

    root = tmp_path / "engine-root"
    engine = Engine(PROJECT, actor="human", engine_root=root)
    _write(engine, "a.txt", "v1\n", "p12", "req-rwex-001")
    listed = engine.submit(
        {
            "project_id": PROJECT,
            "operation": "list_docs",
            "arguments": {},
            "request_id": "req-rwex-002",
        }
    )
    paths = [d["path"] for d in listed["documents"]]
    assert paths == ["a.txt"]
    with pytest.raises(Exception) as excinfo:
        engine.submit(
            {
                "project_id": PROJECT,
                "operation": "write_doc",
                "arguments": {
                    "path": "snapshots/evil.txt",
                    "content": "x\n",
                    "expected_revision": "p13",
                },
                "request_id": "req-rwex-003",
            }
        )
    assert _code(excinfo) in ("invalid_path", "path_escape")


def test_rewind_via_run_delegates_to_submit(tmp_path):
    from rocket_engine.composition import Engine

    root = tmp_path / "engine-root"
    engine = Engine(PROJECT, actor="human", engine_root=root)
    _write(engine, "a.txt", "v1\n", "p12", "req-rwd-001")
    _write(engine, "a.txt", "v2\n", "p13", "req-rwd-002")
    out = engine.run(
        {
            "project_id": PROJECT,
            "operation": "rewind",
            "arguments": {"target_revision": "p13", "expected_revision": "p14"},
            "request_id": "req-rwd-003",
        }
    )
    assert out["current_revision"] == "p15"
    assert out["events"][0]["event"] == "project_rewound"


def test_mcp_rewind_round_trip(tmp_path):
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

    transport.handle(
        _call(
            "write_doc",
            {
                "project_id": PROJECT,
                "path": "mcp.txt",
                "content": "v1\n",
                "expected_revision": "p12",
            },
            "req-mcp-rw-001",
        )
    )
    transport.handle(
        _call(
            "write_doc",
            {
                "project_id": PROJECT,
                "path": "mcp.txt",
                "content": "v2\n",
                "expected_revision": "p13",
            },
            "req-mcp-rw-002",
        )
    )
    out = transport.handle(
        _call(
            "rewind",
            {
                "project_id": PROJECT,
                "target_revision": "p13",
                "expected_revision": "p14",
            },
            "req-mcp-rw-003",
        )
    )
    assert out["current_revision"] == "p15"
    read = transport.handle(
        _call(
            "read_doc",
            {"project_id": PROJECT, "path": "mcp.txt"},
            "req-mcp-rw-004",
        )
    )
    assert read["content"] == "v1\n"
