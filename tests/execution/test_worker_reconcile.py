"""Worker reconcile without a sandbox: CellRunner vs stub binaries.

The live worker tests (test_workers.py) skip loudly without a
provable bwrap, which leaves the reconcile core — exit mapping,
timeout kill, crash reading, harvest gating, revocation ordering —
unexercised on machines where the sandbox cannot be proved. These
tests drive the SAME CellRunner.run_cell public path with stub
binaries (`/bin/true` plus tiny arg-sniffing sh scripts), so the
reconcile logic is pinned deterministically with no isolation at
all. What they do NOT prove is confinement itself — that stays
with the live bwrap tests.

RED state for this file: it did not exist, and the suite sat at
79.41% against the 80% floor (coverage FAIL was the red).
"""

import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest


def _session_and_approval(code):
    from rocket_engine.execution import ConsoleSession

    session = ConsoleSession(project_id="reconcile_probe", actor={"kind": "user"})
    approval = session.request_cell_approval(
        code=code, history_cursor=3, env_digest="env-reconcile",
        expected_revision="p1",
    )
    return session, approval["approval_id"]


def _run(host, code="print('reconciled')\n", **kwargs):
    session, approval_id = _session_and_approval(code)
    return host.run_cell(
        session, approval_id, code, history_cursor=3,
        env_digest="env-reconcile", expected_revision="p1", **kwargs
    )


def _stub(tmp_path, name, marker=None, action="exit 0"):
    """An executable sh stub: `action` when argv contains marker.

    Cell argv always ends with `/usr/bin/python3 cell.py`; probe
    argv never mentions cell.py — so marker "cell.py" cleanly splits
    the probe path (exit 0, admit) from the run path (action).
    """
    path = tmp_path / name
    body = "#!/bin/sh\n"
    if marker is not None:
        body += (
            f'case " $* " in *"{marker}"*) {action};; esac\n'
            'exec /bin/true "$@"\n'
        )
    else:
        body += action + "\n"
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)
    return str(path)


def _true_host(tmp_path, **kwargs):
    from rocket_engine.execution.worker import CellRunner

    return CellRunner(
        binary="/bin/true",
        artifacts_root=str(tmp_path / "artifacts"),
        **kwargs,
    )


# --- Tree-kill confirmation: pure process-group logic, no sandbox ---

def test_confirm_tree_dead_true_once_group_exits():
    from rocket_engine.execution.worker import _confirm_tree_dead

    proc = subprocess.Popen(
        ["sleep", "30"], stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, start_new_session=True,
    )
    try:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()
        assert _confirm_tree_dead(proc.pid) is True
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()


def test_confirm_tree_dead_false_while_members_live():
    from rocket_engine.execution.worker import _confirm_tree_dead

    proc = subprocess.Popen(
        ["sleep", "30"], stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, start_new_session=True,
    )
    try:
        assert _confirm_tree_dead(proc.pid, grace_s=0) is False
        assert _confirm_tree_dead(proc.pid, grace_s=0.25) is False
    finally:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()
        assert _confirm_tree_dead(proc.pid) is True


# --- Admission probing through stub binaries ---

def test_true_binary_admits_with_net_probe_passing(tmp_path):
    host = _true_host(tmp_path)
    assert host.admission["admitted"] is True
    # /bin/true ignores --unshare-net, so the probe "passes":
    # the stamp is honest about what the probe proved.
    assert host.admission["network_isolated"] is True


def test_net_probe_failure_degrades_loudly_unless_required(tmp_path):
    from rocket_engine.execution.worker import CellRunner

    binary = _stub(tmp_path, "nonet.sh", marker="--unshare-net", action="exit 1")
    degraded = CellRunner(
        binary=binary, artifacts_root=str(tmp_path / "artifacts"),
    )
    assert degraded.admission["admitted"] is True
    assert degraded.admission["network_isolated"] is False

    strict = CellRunner(
        binary=binary, artifacts_root=str(tmp_path / "artifacts"),
        require_net=True,
    )
    assert strict.admission["admitted"] is False
    assert "net namespace" in strict.admission["reason"]


def test_cell_python_probe_failure_denies_admission(tmp_path):
    from rocket_engine.execution.worker import CellRunner

    binary = _stub(tmp_path, "nopy.sh", marker=" -c ", action="exit 1")
    host = CellRunner(
        binary=binary, artifacts_root=str(tmp_path / "artifacts"),
    )
    assert host.admission["admitted"] is False
    assert "python3" in host.admission["reason"]


def test_gate_property_exposes_live_credential_ledger(tmp_path):
    from rocket_engine.execution.worker import CredentialGate

    host = _true_host(tmp_path)
    assert isinstance(host.gate, CredentialGate)
    token = host.gate.issue("run-probe")
    assert host.gate.invoke(token, call="ping")["accepted"] is True


# --- Reconcile: completed / failed / crashed / timeout ---

def test_completed_exit_zero_is_the_only_ok(tmp_path):
    record = _run(_true_host(tmp_path))
    assert record["state"] == "completed"
    assert record["ok"] is True
    assert record["exit_code"] == 0
    assert record["reason"] is None
    assert record["partial"] is False
    assert record["credential_revoked"] is True
    assert record["tree_killed"] is True
    assert record["network_isolated"] is True


def test_nonzero_exit_is_failed_never_ok(tmp_path):
    from rocket_engine.execution.worker import CellRunner

    binary = _stub(tmp_path, "fail3.sh", marker="cell.py", action="exit 3")
    host = CellRunner(
        binary=binary, artifacts_root=str(tmp_path / "artifacts"),
    )
    assert host.admission["admitted"] is True
    record = _run(host)
    assert record["state"] == "failed"
    assert record["ok"] is False
    assert record["exit_code"] == 3
    assert record["reason"] == "exit 3."
    assert record["partial"] is False
    assert record["credential_revoked"] is True


def test_signal_death_reads_as_crashed(tmp_path):
    from rocket_engine.execution.worker import CellRunner

    binary = _stub(
        tmp_path, "die.sh", marker="cell.py", action="kill -KILL $$"
    )
    host = CellRunner(
        binary=binary, artifacts_root=str(tmp_path / "artifacts"),
    )
    record = _run(host)
    assert record["state"] == "crashed"
    assert record["ok"] is False
    assert record["reason"] == "death by signal 9."
    assert record["partial"] is True


def test_timeout_kills_tree_and_keeps_partials(tmp_path):
    from rocket_engine.execution.worker import CellRunner

    binary = _stub(
        tmp_path, "hang.sh", marker="cell.py", action="exec sleep 30"
    )
    host = CellRunner(
        binary=binary, artifacts_root=str(tmp_path / "artifacts"),
    )
    record = _run(host, timeout_s=1)
    assert record["state"] == "timeout"
    assert record["ok"] is False
    assert record["exit_code"] is None
    assert "timeout after 1s" in record["reason"]
    assert record["partial"] is True
    assert record["tree_killed"] is True
    assert record["credential_revoked"] is True


def test_on_live_failure_still_reaps_the_worker(tmp_path):
    def _boom(run_id, token):
        raise RuntimeError("callback blew up")

    with pytest.raises(RuntimeError, match="callback blew up"):
        _run(_true_host(tmp_path), on_live=_boom)


# --- Harvest gating through the public run path + escape unit ---

def test_declared_cell_script_harvests_with_digest(tmp_path):
    host = _true_host(tmp_path)
    record = _run(host, artifacts=("cell.py",))
    assert record["ok"] is True
    assert [entry["name"] for entry in record["artifacts"]] == ["cell.py"]
    entry = record["artifacts"][0]
    assert len(entry["sha256"]) == 64
    assert Path(entry["path"]).is_file()
    assert record["rejected_artifacts"] == []


def test_missing_artifact_rejects_without_failing_cell(tmp_path):
    record = _run(_true_host(tmp_path), artifacts=("nope.txt",))
    assert record["ok"] is True
    assert record["artifacts"] == []
    assert record["rejected_artifacts"] == ["nope.txt"]


def test_harvest_rejects_symlink_escape(tmp_path):
    from rocket_engine.execution.worker import CellRunner

    host = _true_host(tmp_path)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("do not harvest", encoding="utf-8")
    (scratch / "evil.txt").symlink_to(outside)
    (scratch / "real.txt").write_text("harvest me", encoding="utf-8")

    harvested, rejected = host._harvest(
        "run-escape", str(scratch), ["evil.txt", "real.txt", "gone.txt"]
    )
    assert [entry["name"] for entry in harvested] == ["real.txt"]
    assert sorted(rejected) == ["evil.txt", "gone.txt"]
