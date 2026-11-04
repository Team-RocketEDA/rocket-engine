"""CONSOLE-SESSION-MIGRATE RED — approval-bound cells on ApplySession.

The approval-bound cell surface (`ConsoleSession`) now lives on the
atomic apply-context (`ApplySession`): the same request/admit
binding, worker replay through the shared runner contract, and
lifecycle status — but staged worker intents land through
`Engine.apply_batch` instead of a side record. Valid RED: the new
module does not exist yet, so every import below fails.
"""

import json

import pytest

CODE = "result = project.snapshot()\n"


def _code(excinfo):
    return getattr(excinfo.value, "code", None)


def _mod():
    from rocket_engine.execution.console import apply_session  # RED

    return apply_session


def _session(**kwargs):
    mod = _mod()
    params = {"project_id": "migrate_probe", "actor": "tester"}
    params.update(kwargs)
    return mod.ConsoleSession(**params)


def _approve(session, code=CODE):
    return session.request_cell_approval(
        code=code, history_cursor=3, env_digest="env-abc",
        expected_revision="p12",
    )


class FakeRunner:
    """Stand-in worker: real approval binding, canned worker record."""

    def __init__(self, tmp_path, stdout="fake-out\n", log_lines=()):
        self._tmp = tmp_path
        self._stdout = stdout
        self._log_lines = list(log_lines)
        self.calls = []

    @property
    def admission(self):
        return {"admitted": True, "reason": None,
                "network_isolated": False}

    def run_cell(self, session, approval_id, code, history_cursor,
                 env_digest, expected_revision, artifacts=(),
                 timeout_s=None, on_live=None):
        session.admit_cell(  # real binding: tamper raises approval_invalid
            approval_id, code=code, history_cursor=history_cursor,
            env_digest=env_digest, expected_revision=expected_revision,
        )
        harvested = []
        if self._log_lines:
            ops_file = self._tmp / "fake_harvest.jsonl"
            ops_file.write_text(
                "".join(self._log_lines), encoding="utf-8",
            )
            harvested.append({"name": "__console_ops.jsonl",
                              "path": str(ops_file),
                              "bytes": ops_file.stat().st_size,
                              "sha256": "0" * 64})
        return {"run_id": "run_fake", "state": "completed", "ok": True,
                "reason": None, "exit_code": 0, "stdout": self._stdout,
                "stderr": "", "partial": False, "artifacts": harvested,
                "rejected_artifacts": [], "network_isolated": False,
                "credential_revoked": True, "tree_killed": True,
                "scratch": str(self._tmp)}


class FakeApplyEngine:
    """Deterministic engine: queued submits, capturing apply_batch."""

    def __init__(self):
        self.commands = []
        self.batches = []

    def snapshot(self):
        return {"current_revision": "p12"}

    def submit(self, command):
        self.commands.append(("submit", command))
        return {"state": "queued", "run_id": "run_fake_q"}

    def run(self, command):
        self.commands.append(("run", command))
        return {"run_id": "run_fake", "state": "completed",
                "verdict": {"status": "PASS"},
                "operation": command["operation"]}

    def apply_batch(self, batch):
        self.batches.append(batch)
        return {"ok": True, "operation": "apply_batch",
                "label": batch["label"], "revision": "p13",
                "landed": [i["kind"] for i in batch["intents"]],
                "applied": len(batch["intents"])}


# --- Surface: ApplySession subclass with the approval binding ---

def test_session_is_apply_session_with_identity():
    from rocket_engine.execution.pyexec.apply_context import ApplySession

    session = _session()
    assert isinstance(session, ApplySession)
    assert session.generation
    assert session.console_id


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


def test_unknown_approval_invalid():
    session = _session()
    with pytest.raises(Exception) as excinfo:
        session.admit_cell(
            "no-such-approval", code=CODE, history_cursor=3,
            env_digest="env-abc", expected_revision="p12",
        )
    assert _code(excinfo) == "approval_invalid"


def test_execute_cell_advances_cursor_and_binds_code():
    session = _session()
    first = session.execute_cell(_approve(session)["approval_id"],
                                 code=CODE)
    second = session.execute_cell(_approve(session)["approval_id"],
                                  code=CODE)
    assert second["cursor"] > first["cursor"] >= 1
    with pytest.raises(Exception) as excinfo:
        session.execute_cell(_approve(session)["approval_id"],
                             code=CODE + "# drift\n")
    assert _code(excinfo) == "approval_invalid"


def test_reset_rotates_generation_kills_approvals_and_rearms():
    session = _session()
    before = session.generation
    approval = _approve(session)
    out = session.reset()
    assert out["generation"] != before
    assert session.generation == out["generation"]
    with pytest.raises(Exception) as excinfo:
        session.admit_cell(
            approval["approval_id"], code=CODE, history_cursor=3,
            env_digest="env-abc", expected_revision="p12",
        )
    assert _code(excinfo) == "approval_invalid"
    # Rearmed: new approvals admit and new batches carry the new gen.
    admitted = session.admit_cell(
        _approve(session)["approval_id"], code=CODE, history_cursor=3,
        env_digest="env-abc", expected_revision="p12",
    )
    assert admitted["state"] == "approved"
    with session.edit("after-reset"):
        pass
    assert session.last_batch["generation"] == session.generation


def test_batch_envelope_carries_console_and_generation():
    session = _session(console_id="c-bind")
    with session.edit("stage"):
        pass
    (batch,) = session.emitted
    assert batch["console_id"] == "c-bind"
    assert batch["generation"] == session.generation
    assert ("gen=%s" % session.generation) in batch["envelope"]


# --- Landing: worker intents through Engine.apply_batch ---

def test_land_worker_intents_lands_rect_through_apply_batch(tmp_path):
    log = tmp_path / "worker.jsonl"
    log.write_text(
        json.dumps({"operation": "get_project_snapshot",
                    "arguments": {}}) + "\n"
        + "not json at all\n"
        + json.dumps({"apply_intent": {
            "kind": "rect", "layer": [1, 0],
            "bbox": [0, 0, 10, 5], "pdk": "sky130"}}) + "\n",
        encoding="utf-8",
    )
    session = _session()
    engine = FakeApplyEngine()
    landed = session.land_worker_intents(engine, str(log), "cell x")
    assert landed["ok"] is True
    assert landed["intents"] == 1
    assert landed["receipt"]["revision"] == "p13"
    assert landed["receipt"]["landed"] == ["rect"]
    (batch,) = engine.batches
    assert batch["label"] == "cell x"
    assert batch["generation"] == session.generation


def test_land_worker_intents_none_when_no_intents(tmp_path):
    log = tmp_path / "ops-only.jsonl"
    log.write_text(
        json.dumps({"operation": "get_project_snapshot",
                    "arguments": {}}) + "\n",
        encoding="utf-8",
    )
    session = _session()
    engine = FakeApplyEngine()
    assert session.land_worker_intents(engine, str(log), "cell y") is None
    assert engine.batches == []
    assert session.emitted == []


def test_land_worker_intents_none_without_apply_batch(tmp_path):
    log = tmp_path / "intents.jsonl"
    log.write_text(
        json.dumps({"apply_intent": {
            "kind": "rect", "layer": [1, 0],
            "bbox": [0, 0, 1, 1], "pdk": "sky130"}}) + "\n",
        encoding="utf-8",
    )

    class NoApplyEngine:
        def snapshot(self):
            return {"current_revision": "p12"}

    session = _session()
    assert session.land_worker_intents(
        NoApplyEngine(), str(log), "cell z") is None


def test_land_worker_intents_conflict_propagates(tmp_path):
    from rocket_engine.project.errors import ProjectError

    log = tmp_path / "intents.jsonl"
    log.write_text(
        json.dumps({"apply_intent": {
            "kind": "rect", "layer": [1, 0],
            "bbox": [0, 0, 1, 1], "pdk": "sky130"}}) + "\n",
        encoding="utf-8",
    )

    class ConflictEngine:
        def apply_batch(self, batch):
            raise ProjectError("revision_conflict", "head moved")

    session = _session()
    with pytest.raises(Exception) as excinfo:
        session.land_worker_intents(ConflictEngine(), str(log), "cell w")
    assert _code(excinfo) == "revision_conflict"


# --- Worker replay through the console on the migrated session ---

def _open(tmp_path, runner, engine):
    from rocket_engine.adapters import stdio_console

    return stdio_console.StdioConsole(
        engine=engine, root=str(tmp_path), cell_runner=runner,
    )


def test_stdio_submit_lands_worker_intents_and_replays_ops(tmp_path):
    lines = [
        json.dumps({"operation": "get_project_snapshot",
                    "arguments": {}}),
        json.dumps({"apply_intent": {
            "kind": "rect", "layer": [1, 0],
            "bbox": [0, 0, 10, 5], "pdk": "sky130"}}),
    ]
    log_lines = [line + "\n" for line in lines]
    engine = FakeApplyEngine()
    console = _open(tmp_path / "c1",
                     FakeRunner(tmp_path, log_lines=log_lines), engine)
    try:
        record = console.submit("print('cell-ok')\n")
        assert record["state"] == "completed"
        assert record["ops"] == [{"operation": "get_project_snapshot",
                                  "arguments": {}}]
        assert record["ops_ok"] is True
        assert record["apply"]["ok"] is True
        assert record["apply"]["intents"] == 1
        assert record["apply"]["receipt"]["landed"] == ["rect"]
        (batch,) = engine.batches
        assert batch["generation"] == console.generation
    finally:
        console.close()


def test_stdio_submit_without_intents_lands_nothing(tmp_path):
    engine = FakeApplyEngine()
    console = _open(tmp_path / "c2", FakeRunner(tmp_path), engine)
    try:
        record = console.submit("print('plain')\n")
        assert record["state"] == "completed"
        assert record["apply"] is None
        assert engine.batches == []
    finally:
        console.close()


def test_stdio_submit_without_apply_engine_keeps_cell_green(tmp_path):
    class NoApplyEngine:
        def snapshot(self):
            return {"current_revision": "p12"}

        def submit(self, command):
            return {"state": "queued", "run_id": "run_q"}

        def run(self, command):
            return {"run_id": "run_x", "state": "completed",
                    "operation": command["operation"]}

    lines = [json.dumps({"apply_intent": {
        "kind": "rect", "layer": [1, 0],
        "bbox": [0, 0, 1, 1], "pdk": "sky130"}}) + "\n"]
    console = _open(tmp_path / "c3", FakeRunner(tmp_path, log_lines=lines),
                     NoApplyEngine())
    try:
        record = console.submit("print('plain')\n")
        assert record["state"] == "completed"
        assert record["apply"] is None
    finally:
        console.close()


def test_tampered_cell_rejected_by_migrated_binding(tmp_path):
    engine = FakeApplyEngine()
    console = _open(tmp_path / "c4", FakeRunner(tmp_path), engine)
    try:
        approval = console.request_approval("print(1)\n")
        assert approval["state"] == "pending_approval"
        with pytest.raises(Exception) as excinfo:
            console.run_approved(approval["approval_id"], "print(2)\n")
        assert _code(excinfo) == "approval_invalid"
        record = console.run_approved(approval["approval_id"],
                                      "print(1)\n")
        assert record["ok"] is True
    finally:
        console.close()


def test_reset_kills_approvals_and_renews_generation(tmp_path):
    engine = FakeApplyEngine()
    console = _open(tmp_path / "c5", FakeRunner(tmp_path), engine)
    try:
        approval = console.request_approval("print(1)\n")
        before = console.generation
        out = console.reset()
        assert out["generation"] != before
        with pytest.raises(Exception) as excinfo:
            console.run_approved(approval["approval_id"], "print(1)\n")
        assert _code(excinfo) == "approval_invalid"
    finally:
        console.close()


# --- Lifecycle status on the migrated session ---

def test_lifecycle_status_on_apply_session():
    from rocket_engine.execution.console.lifecycle import ConsoleLifecycle
    from rocket_engine.execution.pyexec.apply_context import ApplySession

    service = ConsoleLifecycle()
    opened = service.open_console(project_id="demo", actor="user")
    session = service.session_for(opened["console_id"])
    assert isinstance(session, ApplySession)
    status = service.status(opened["console_id"])
    assert status["generation"] == session.generation
    assert status["generation"] == opened["generation"]
    approval = session.request_cell_approval(
        code=CODE, history_cursor=0, env_digest="env",
        expected_revision="p1",
    )
    reset = service.reset_console(opened["console_id"])
    assert reset["generation"] != opened["generation"]
    assert service.status(
        opened["console_id"])["generation"] == reset["generation"]
    with pytest.raises(Exception) as excinfo:
        session.admit_cell(
            approval["approval_id"], code=CODE, history_cursor=0,
            env_digest="env", expected_revision="p1",
        )
    assert _code(excinfo) == "approval_invalid"


def test_get_help_moved_with_session():
    mod = _mod()
    entry = mod.get_help("run_drc")
    assert entry["topic"] == "run_drc"
    assert entry["version"].startswith("rocketeda/")
    with pytest.raises(Exception) as excinfo:
        mod.get_help("no_such_operation")
    assert _code(excinfo) == "unknown_topic"
