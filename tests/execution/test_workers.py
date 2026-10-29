"""WORKERS RED — isolated worker substrate (I23/I24).

CellRunner spawns one sandboxed worker per approved cell under
BwrapRunner confinement, issues execution-scoped IPC credentials,
confirms revocation + tree-kill before any terminal state, and
persists reusable results only as approved artifacts. Runner
profiles gain env-unset support so workers start scrubbed (the
netgen DISPLAY forcing function).

Valid RED = every import fails: the substrate does not exist yet.
Live tests use the `cell_runner` fixture, which skips loudly unless
a provable bwrap + in-sandbox python3 admit workers — a shadowed
bwrap skips, never fake-greens (I16 rule).
"""

import os
import threading
from pathlib import Path

import pytest

CODE = "print('cell-ok')\n"


def _code(excinfo):
    return getattr(excinfo.value, "code", None)


def _session_and_approval(code=CODE):
    from rocket_engine.execution import ConsoleSession

    session = ConsoleSession(project_id="workers_probe", actor={"kind": "user"})
    approval = session.request_cell_approval(
        code=code, history_cursor=7, env_digest="env-probe",
        expected_revision="p1",
    )
    return session, approval["approval_id"]


def _run(host, code=CODE, **kwargs):
    session, approval_id = _session_and_approval(code)
    return host.run_cell(
        session, approval_id, code, history_cursor=7,
        env_digest="env-probe", expected_revision="p1", **kwargs
    )


@pytest.fixture
def cell_runner(tmp_path):
    from rocket_engine.execution.worker import CellRunner  # RED: missing

    host = CellRunner(artifacts_root=str(tmp_path / "artifacts"))
    if not host.admission["admitted"]:
        pytest.skip(
            f"no provable worker isolation: {host.admission.get('reason')}"
        )
    return host


def _broken_host(tmp_path):
    from rocket_engine.execution.worker import CellRunner  # RED: missing

    return CellRunner(
        binary="/nonexistent-bwrap-for-workers",
        artifacts_root=str(tmp_path / "artifacts"),
    )


# --- Substrate shape (no isolation needed) ---

def test_worker_module_exists():
    from rocket_engine.execution.worker import (  # RED: missing module
        CellRunner,
        CredentialGate,
        worker_profile,
    )

    assert callable(CellRunner)
    assert callable(CredentialGate)
    assert callable(worker_profile)


def test_worker_profile_scrubs_display_by_default():
    from rocket_engine.execution.runner import default_profile
    from rocket_engine.execution.worker import worker_profile  # RED: missing

    assert "DISPLAY" in default_profile()["env_unset"]
    assert "DISPLAY" in worker_profile()["env_unset"]
    assert worker_profile()["namespaces"] == ["user"]


def test_runner_argv_emits_unsetenv(tmp_path):
    from rocket_engine.execution.runner import BwrapRunner

    profile = {"namespaces": ["user"], "env_unset": ["DISPLAY"]}
    argv = BwrapRunner(profile).argv_for(str(tmp_path), ["/bin/true"])  # RED
    assert argv.count("--unsetenv") == 1
    assert argv[argv.index("--unsetenv") + 1] == "DISPLAY"


def test_runner_argv_supports_per_run_extra_env(tmp_path):
    from rocket_engine.execution.runner import BwrapRunner

    argv = BwrapRunner({"namespaces": ["user"]}).argv_for(  # RED
        str(tmp_path), ["/bin/true"], extra_env={"ROCKETEDA_RUN_ID": "r1"}
    )
    at = argv.index("--setenv")
    assert argv[at + 1] == "ROCKETEDA_RUN_ID" and argv[at + 2] == "r1"


def test_runner_unsetenv_scrubs_display_live(tmp_path, monkeypatch):
    from rocket_engine.execution.runner import BwrapRunner, default_profile

    monkeypatch.setenv("DISPLAY", ":99-unreachable-for-workers")
    runner = BwrapRunner(default_profile())
    try:
        runner.preflight()
    except Exception:
        pytest.skip("no provable bwrap on PATH")
    proc = runner.run(
        ["/bin/sh", "-c", "echo DISPLAY-is-$DISPLAY"],
        str(tmp_path), timeout_s=30,
    )
    assert proc.stdout.strip() == "DISPLAY-is-"


# --- Admission without isolation (no host fallback; runs everywhere) ---

def test_unavailable_isolation_disables_admission_with_reason(tmp_path):
    host = _broken_host(tmp_path)
    admission = host.admission
    assert admission["admitted"] is False
    assert admission["reason"]
    session, approval_id = _session_and_approval()
    with pytest.raises(Exception) as excinfo:
        host.run_cell(
            session, approval_id, CODE, history_cursor=7,
            env_digest="env-probe", expected_revision="p1",
        )
    assert _code(excinfo) == "isolation_unavailable"


def test_no_host_fallback_without_isolation(tmp_path):
    canary = tmp_path / "host_canary.txt"
    code = f"open({str(canary)!r}, 'w').write('ESCAPED')\n"
    host = _broken_host(tmp_path)
    session, approval_id = _session_and_approval(code)
    with pytest.raises(Exception) as excinfo:
        host.run_cell(
            session, approval_id, code, history_cursor=7,
            env_digest="env-probe", expected_revision="p1",
        )
    assert _code(excinfo) == "isolation_unavailable"
    assert not canary.exists()


def test_run_cell_reuses_approval_binding(tmp_path):
    host = _broken_host(tmp_path)
    session, approval_id = _session_and_approval(CODE)
    with pytest.raises(Exception) as excinfo:
        host.run_cell(
            session, approval_id, CODE + "# sneaky\n", history_cursor=7,
            env_digest="env-probe", expected_revision="p1",
        )
    assert _code(excinfo) == "approval_invalid"


@pytest.mark.parametrize("bad", ["../escape.txt", "/abs/path.txt", "sub/../../x"])
def test_artifact_escape_rejected_before_spawn(tmp_path, bad):
    host = _broken_host(tmp_path)
    session, approval_id = _session_and_approval()
    with pytest.raises(Exception) as excinfo:
        host.run_cell(
            session, approval_id, CODE, history_cursor=7,
            env_digest="env-probe", expected_revision="p1",
            artifacts=(bad,),
        )
    assert _code(excinfo) == "invalid_reference"


def test_strict_network_mode_admits_only_when_provably_isolated(tmp_path):
    from rocket_engine.execution.worker import CellRunner  # RED: missing

    host = CellRunner(
        binary="bwrap", require_net=True,
        artifacts_root=str(tmp_path / "artifacts"),
    )
    admission = host.admission
    assert admission["admitted"] == bool(admission.get("network_isolated"))
    if not admission["admitted"]:
        assert admission["reason"]


def test_credential_gate_threaded_lifecycle():
    from rocket_engine.execution.worker import CredentialGate  # RED: missing

    gate = CredentialGate()
    token = gate.issue("run-1")
    errors = []

    def caller(n):
        try:
            out = gate.invoke(token, {"op": "ping", "n": n})
            assert out["accepted"] is True
            assert out["run_id"] == "run-1"
        except Exception as exc:  # pragma: no cover - failure path
            errors.append(exc)

    threads = [threading.Thread(target=caller, args=(i,)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
    assert not errors
    assert gate.revoke("run-1")["revoked"] is True
    with pytest.raises(Exception) as excinfo:
        gate.invoke(token, {"op": "late"})
    assert _code(excinfo) == "credential_revoked"
    with pytest.raises(Exception) as excinfo:
        gate.invoke("never-issued-token", {"op": "ping"})
    assert _code(excinfo) == "credential_unknown"


# --- Live worker behavior (skips loudly without provable isolation) ---

def test_cell_completes_under_confinement(cell_runner):
    seen = {}

    def on_live(run_id, token):
        seen.update(run_id=run_id, token=token)

    code = (
        "import os\n"
        "print('TOKEN=' + os.environ.get('ROCKETEDA_CELL_TOKEN', ''))\n"
        "print('RUN=' + os.environ.get('ROCKETEDA_RUN_ID', ''))\n"
    )
    result = _run(cell_runner, code, timeout_s=30, on_live=on_live)
    assert result["state"] == "completed"
    assert result["ok"] is True
    assert result["exit_code"] == 0
    assert result["partial"] is False
    assert f"TOKEN={seen['token']}" in result["stdout"]
    assert f"RUN={seen['run_id']}" in result["stdout"]
    assert result["run_id"] == seen["run_id"]
    assert result["credential_revoked"] is True
    assert result["tree_killed"] is True
    assert isinstance(result["network_isolated"], bool)
    assert not Path(result["scratch"]).exists()


def test_host_access_denied(cell_runner, tmp_path):
    host_canary = tmp_path / "host_secret.txt"
    host_canary.write_text("HOST-SECRET")
    code = (
        "import os\n"
        f"host = {str(host_canary)!r}\n"
        "probes = []\n"
        "try:\n    open(host).read()\n    probes.append('HOST_GRANTED')\n"
        "except Exception:\n    probes.append('HOST_DENIED')\n"
        "try:\n    open('/usr/nope_workers_probe', 'w').write('x')\n"
        "    probes.append('WRITE_GRANTED')\n"
        "except Exception:\n    probes.append('WRITE_DENIED')\n"
        "print(' '.join(probes))\n"
    )
    result = _run(cell_runner, code, timeout_s=30)
    assert result["state"] == "completed"
    assert "HOST_DENIED" in result["stdout"]
    assert "WRITE_DENIED" in result["stdout"]
    assert "GRANTED" not in result["stdout"]
    assert not Path("/usr/nope_workers_probe").exists()


def test_evidence_access_denied(cell_runner, tmp_path):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "prior_run.json").write_text('{"verdict": "PASS"}')
    code = (
        f"evidence = {str(evidence / 'prior_run.json')!r}\n"
        "try:\n    open(evidence).read()\n    print('EVIDENCE_GRANTED')\n"
        "except Exception:\n    print('EVIDENCE_DENIED')\n"
    )
    result = _run(cell_runner, code, timeout_s=30)
    assert result["state"] == "completed"
    assert "EVIDENCE_DENIED" in result["stdout"]
    assert "GRANTED" not in result["stdout"]


def test_network_egress_denied_where_provably_isolated(cell_runner):
    probe = _run(cell_runner, "print('probe')\n", timeout_s=30)
    if not probe["network_isolated"]:
        pytest.skip("net namespace unprovable here; re-prove on target (B10)")
    import socket

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    code = (
        "import socket\n"
        "sock = socket.socket()\n"
        "sock.settimeout(3)\n"
        "try:\n"
        f"    sock.connect(('127.0.0.1', {port}))\n"
        "    print('NET_GRANTED')\n"
        "except Exception:\n    print('NET_DENIED')\n"
    )
    try:
        result = _run(cell_runner, code, timeout_s=30)
    finally:
        server.close()
    assert "NET_DENIED" in result["stdout"]
    assert "GRANTED" not in result["stdout"]


def test_post_cell_threaded_callbacks_rejected(cell_runner):
    gate = cell_runner.gate
    captured = {}
    live = threading.Event()

    def on_live(run_id, token):
        captured["token"] = token
        live.set()

    outcome = {}

    def runner_thread():
        outcome["result"] = _run(
            cell_runner, "import time\ntime.sleep(4)\nprint('done')\n",
            timeout_s=30, on_live=on_live,
        )

    worker = threading.Thread(target=runner_thread)
    worker.start()
    try:
        assert live.wait(20)
        errors = []

        def caller(n):
            try:
                out = gate.invoke(captured["token"], {"op": "ping", "n": n})
                assert out["accepted"] is True
            except Exception as exc:  # pragma: no cover - failure path
                errors.append(exc)

        threads = [threading.Thread(target=caller, args=(i,)) for i in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(10)
        assert not errors
    finally:
        worker.join(30)
    assert outcome["result"]["state"] == "completed"
    assert outcome["result"]["credential_revoked"] is True
    for _ in range(3):
        with pytest.raises(Exception) as excinfo:
            gate.invoke(captured["token"], {"op": "late"})
        assert _code(excinfo) == "credential_revoked"


def test_timeout_kills_process_tree(cell_runner):
    code = (
        "import subprocess, time\n"
        "child = subprocess.Popen(['/bin/sleep', '60'])\n"
        "open('child.pid', 'w').write(str(child.pid))\n"
        "print('spawned', flush=True)\n"
        "time.sleep(30)\n"
    )
    result = _run(cell_runner, code, artifacts=("child.pid",), timeout_s=3)
    assert result["state"] == "timeout"
    assert result["ok"] is False
    assert result["tree_killed"] is True
    assert result["credential_revoked"] is True
    assert "spawned" in result["stdout"]
    found = {item["name"]: item for item in result["artifacts"]}
    assert "child.pid" in found
    child_pid = int(Path(found["child.pid"]["path"]).read_text().strip())
    with pytest.raises(ProcessLookupError):
        os.kill(child_pid, 0)


def test_timeout_yields_truthful_state_and_retained_partials(cell_runner):
    code = "import time\nprint('step-1', flush=True)\ntime.sleep(30)\n"
    result = _run(cell_runner, code, timeout_s=3)
    assert result["state"] == "timeout"
    assert result["ok"] is False
    assert result["partial"] is True
    assert result["exit_code"] is None
    assert "timeout" in result["reason"].lower()
    assert "step-1" in result["stdout"]


def test_crash_and_failure_are_truthful_no_fake_pass(cell_runner):
    failed = _run(cell_runner, "raise SystemExit(3)\n", timeout_s=30)
    assert failed["state"] == "failed"
    assert failed["ok"] is False
    assert failed["exit_code"] == 3
    assert failed["partial"] is False
    crashed = _run(
        cell_runner,
        "import os, signal\nos.kill(os.getpid(), signal.SIGTERM)\n",
        timeout_s=30,
    )
    assert crashed["state"] == "crashed"
    assert crashed["ok"] is False
    assert crashed["exit_code"] == -15
    assert crashed["partial"] is True
    assert "signal" in crashed["reason"].lower()


def test_fresh_worker_per_cell_namespace_never_crosses(cell_runner):
    seen = []

    def on_live(run_id, token):
        seen.append(token)

    first = _run(
        cell_runner, "open('marker.txt', 'w').write('A')\nprint('A-done')\n",
        timeout_s=30, on_live=on_live,
    )
    assert first["state"] == "completed"
    second = _run(
        cell_runner,
        "import os\n"
        "print('FRESH_OK' if not os.path.exists('marker.txt') else 'STALE')\n",
        timeout_s=30, on_live=on_live,
    )
    assert "FRESH_OK" in second["stdout"]
    assert "STALE" not in second["stdout"]
    assert seen[0] != seen[1]
    with pytest.raises(Exception) as excinfo:
        cell_runner.gate.invoke(seen[0], {"op": "cross-cell"})
    assert _code(excinfo) == "credential_revoked"


def test_approved_artifacts_persist_undeclared_dies(cell_runner):
    code = (
        "open('approved.txt', 'w').write('keep-me')\n"
        "open('secret.txt', 'w').write('drop-me')\n"
        "print('wrote')\n"
    )
    result = _run(cell_runner, code, artifacts=("approved.txt",), timeout_s=30)
    assert result["state"] == "completed"
    found = {item["name"]: item for item in result["artifacts"]}
    assert set(found) == {"approved.txt"}
    assert Path(found["approved.txt"]["path"]).read_text() == "keep-me"
    assert found["approved.txt"]["bytes"] == len("keep-me")
    assert len(found["approved.txt"]["sha256"]) == 64
    assert not Path(result["scratch"]).exists()


def test_artifact_symlink_escape_rejected(cell_runner, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("TOP-SECRET")
    code = (
        "import os\n"
        f"os.symlink({str(outside)!r}, 'linked.txt')\n"
        "print('linked')\n"
    )
    result = _run(cell_runner, code, artifacts=("linked.txt",), timeout_s=30)
    assert [item["name"] for item in result["artifacts"]] == []
    assert "linked.txt" in result["rejected_artifacts"]


def test_worker_starts_from_scrubbed_env(cell_runner, monkeypatch):
    monkeypatch.setenv("DISPLAY", ":99-unreachable-for-workers")
    code = "import os\nprint('DISPLAY=%r' % os.environ.get('DISPLAY'))\n"
    result = _run(cell_runner, code, timeout_s=30)
    assert result["state"] == "completed"
    assert "unreachable-for-workers" not in result["stdout"]


def test_cell_output_budgets_apply(cell_runner):
    code = "for i in range(200000): print('line-%d' % i)\n"
    result = _run(cell_runner, code, timeout_s=60)
    assert result["state"] == "completed"
    assert "truncated after" in result["stdout"]
