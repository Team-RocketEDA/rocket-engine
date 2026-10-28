"""RUNNER tests — BwrapRunner behind a small isolation contract (I16).

Profiles and recipes come from the verified bubblewrap probe (see
docs/probe-bwrap-isolation.md): userns sandbox, merged-/usr binds, ro
tools, rw workdir. The bwrap-backed tests use the `runner` fixture,
which skips unless the PATH-resolved bwrap passes preflight — another
PATH entry may shadow bwrap with an unprovable build, and that must
skip loudly, never fake-green or mystery-fail.
"""

import shutil
from pathlib import Path

import pytest

tools_present = shutil.which("bwrap") is not None
needs_bwrap = pytest.mark.skipif(not tools_present, reason="bwrap not on PATH")

PROFILE = {
    "namespaces": ["user"],
    "binds_ro": [("/usr", "/usr")],
    "symlinks": [("usr/bin", "/bin"), ("usr/lib", "/lib"), ("usr/lib64", "/lib64")],
    "tmpfs": ["/tmp"],
    "env": {"PATH": "/usr/bin:/bin"},
}


@pytest.fixture
def runner():
    from rocket_engine.execution.runner import BwrapRunner

    candidate = BwrapRunner(PROFILE)
    try:
        candidate.preflight()
    except Exception:
        pytest.skip("no provable bwrap on PATH")
    return candidate


def test_runner_module_exists():
    from rocket_engine.execution.runner import BwrapRunner

    assert callable(BwrapRunner)


def test_runner_preflight_refuses_missing_binary(tmp_path):
    from rocket_engine.execution.runner import BwrapRunner

    runner = BwrapRunner(PROFILE, binary="/nonexistent-bwrap-for-tests")
    try:
        runner.preflight()
    except Exception as exc:
        assert getattr(exc, "code", None) == "missing_dependency"
    else:
        raise AssertionError("expected missing_dependency for a missing bwrap")


@needs_bwrap
def test_runner_preflight_passes_for_provable_profile(runner):
    out = runner.preflight()
    assert out["ready"] is True


@needs_bwrap
def test_runner_preflight_refuses_unprovable_namespaces():
    from rocket_engine.execution.runner import BwrapRunner

    profile = dict(PROFILE)
    profile["namespaces"] = ["user", "nosuchns"]
    try:
        BwrapRunner(profile).preflight()
    except Exception as exc:
        assert getattr(exc, "code", None) == "runner_unavailable"
    else:
        raise AssertionError("expected runner_unavailable for a bogus namespace")


@needs_bwrap
def test_runner_executes_inside_sandbox(runner, tmp_path):
    proc = runner.run(["/bin/echo", "hi"], str(tmp_path), timeout_s=30)
    assert proc.returncode == 0
    assert proc.stdout.strip() == "hi"


@needs_bwrap
def test_runner_confines_writes_to_workdir(runner, tmp_path):
    proc = runner.run(
        ["/bin/sh", "-c", "touch /usr/nope_for_tests && echo BAD || echo CONFINED"],
        str(tmp_path),
        timeout_s=30,
    )
    assert "CONFINED" in proc.stdout
    assert not Path("/usr/nope_for_tests").exists()


@needs_bwrap
def test_runner_kills_overruns(runner, tmp_path):
    try:
        runner.run(["/bin/sleep", "30"], str(tmp_path), timeout_s=2)
    except Exception as exc:
        assert getattr(exc, "code", None) == "runner_unavailable"
    else:
        raise AssertionError("expected runner_unavailable for an overrun")
