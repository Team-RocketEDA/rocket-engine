"""APPROVAL-SWEEP RED — the live approval index stays bounded.

Terminal (denied/expired) approvals accumulate forever: nothing
ever reaps them, so a long IDE session grows the ledger without
bound. Approved and pending approvals are live references and
must never reap.

Valid RED = no eviction happens past any bound; the oldest
terminal approvals stay readable forever.
"""

import pytest


def _mod():
    from rocket_engine.execution import python_exec

    return python_exec


def _service(tmp_path, mod=None, **kwargs):
    mod = mod or _mod()
    from rocket_engine.execution.service import ExecutionService

    kwargs.setdefault("execution", ExecutionService("sweep-probe"))
    return mod.PythonExecService(
        "sweep-probe", actor="probe-agent", root=str(tmp_path / "pyexec"),
        **kwargs,
    )


def _deny(service, tag):
    handle = service.request_execution("lines", lines=f"{tag}=1\n")
    service.resolve_approval(handle["approval_id"], "denied", via="ui")
    return handle["approval_id"]


def test_terminal_approvals_evict_oldest_beyond_cap(tmp_path, monkeypatch):
    mod = _mod()
    monkeypatch.setattr(mod, "MAX_TERMINAL_APPROVALS", 3)
    service = _service(tmp_path)
    ids = [_deny(service, f"v{i}") for i in range(5)]
    from rocket_engine.execution.errors import ExecutionError

    with pytest.raises(ExecutionError) as exc:
        service.approval_status(ids[0])
    assert exc.value.code == "approval_invalid"
    with pytest.raises(ExecutionError):
        service.approval_status(ids[1])
    for alive in ids[2:]:
        assert service.approval_status(alive)["approval_state"] == "denied"


def test_expired_counts_toward_terminal_cap(tmp_path, monkeypatch):
    mod = _mod()
    monkeypatch.setattr(mod, "MAX_TERMINAL_APPROVALS", 2)
    clock = [1000.0]
    service = _service(
        tmp_path, approval_ttl_s=10, clock=lambda: clock[0],
    )
    first = service.request_execution("lines", lines="a=1\n")["approval_id"]
    second = service.request_execution("lines", lines="b=2\n")["approval_id"]
    third = service.request_execution("lines", lines="c=3\n")["approval_id"]
    clock[0] += 11.0
    service.console_view()  # flips all three; oldest reaps past cap
    from rocket_engine.execution.errors import ExecutionError

    with pytest.raises(ExecutionError) as exc:
        service.approval_status(first)
    assert exc.value.code == "approval_invalid"
    assert service.approval_status(second)["approval_state"] == "expired"
    assert service.approval_status(third)["approval_state"] == "expired"


def test_approved_and_pending_never_reaped(tmp_path, monkeypatch):
    mod = _mod()
    monkeypatch.setattr(mod, "MAX_TERMINAL_APPROVALS", 2)
    service = _service(tmp_path)
    approved = []
    for i in range(4):
        handle = service.request_execution("lines", lines=f"v{i}=1\n")
        out = service.resolve_approval(
            handle["approval_id"], "approved", via="ui",
        )
        approved.append(out["approval_id"])
    pending = service.request_execution("lines", lines="p=1\n")["approval_id"]
    for alive in approved:
        assert service.approval_status(alive)["approval_state"] == "approved"
    assert service.approval_status(pending)["approval_state"] == "pending_approval"


def test_evicted_approval_keeps_audit_yaml(tmp_path, monkeypatch):
    mod = _mod()
    monkeypatch.setattr(mod, "MAX_TERMINAL_APPROVALS", 1)
    service = _service(tmp_path)
    first = _deny(service, "old")
    _deny(service, "new")
    from rocket_engine.execution.errors import ExecutionError

    with pytest.raises(ExecutionError):
        service.approval_status(first)
    audit = tmp_path / "pyexec" / "approvals" / f"{first}.yaml"
    assert audit.is_file()
