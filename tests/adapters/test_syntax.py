"""SYNTAX RED — SyntaxAdapter behind the ToolAdapter port (run_syntax).

Valid RED = `rocket_engine.adapters.syntax` does not exist yet, so
every test fails on ImportError. Fixtures are verified against real
slang 12.0.0: clean→rc 0 silent, broken→rc 1 + error diag, trunc→rc 0
+ -Wextra warning. Tests skip (never fake-green) where slang is
unpathed; tool placement on PATH is B10 integration scope.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "syntax"

tools_present = shutil.which("slang") is not None
needs_slang = pytest.mark.skipif(not tools_present, reason="slang not on PATH")


def _job(sources, tmp_path, **over):
    workdir = tmp_path / "work"
    workdir.mkdir(exist_ok=True)
    staged = []
    for name in sources:
        dest = workdir / name
        shutil.copy(FIXTURES / name, dest)
        staged.append(str(dest))
    job = {"operation": "run_syntax", "sources": staged, "workdir": str(workdir)}
    job.update(over)
    return job


def test_syntax_adapter_implements_tool_port():
    from rocket_engine.adapters import ToolAdapter  # live surface
    from rocket_engine.adapters.syntax import SyntaxAdapter  # RED: missing adapter

    assert issubclass(SyntaxAdapter, ToolAdapter)


def test_syntax_capabilities_advertise_run_syntax():
    from rocket_engine.adapters.syntax import SyntaxAdapter  # RED: missing adapter

    caps = SyntaxAdapter().capabilities({"top": "counter"})
    assert "run_syntax" in caps["operations"]
    assert caps["tool"] == "slang"


def test_syntax_preflight_refuses_missing_sources(tmp_path):
    from rocket_engine.adapters.syntax import SyntaxAdapter  # RED: missing adapter

    job = _job(["counter.v"], tmp_path)
    job["sources"] = [str(tmp_path / "work" / "ghost.v")]
    try:
        SyntaxAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_reference"
    else:
        raise AssertionError("expected invalid_reference for missing sources")


def test_syntax_preflight_refuses_missing_tools(tmp_path):
    from rocket_engine.adapters.syntax import SyntaxAdapter  # RED: missing adapter

    job = _job(["counter.v"], tmp_path)
    job["tool_dir"] = "/nonexistent-dir-for-syntax-tests"
    try:
        SyntaxAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "missing_dependency"
    else:
        raise AssertionError("expected missing_dependency for bad tool_dir")


def test_syntax_preflight_refuses_bad_timeout(tmp_path):
    from rocket_engine.adapters.syntax import SyntaxAdapter  # RED: missing adapter

    job = _job(["counter.v"], tmp_path, timeout_s=0)
    try:
        SyntaxAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_command"
    else:
        raise AssertionError("expected invalid_command for zero timeout")


@needs_slang
def test_syntax_clean_reports_zero(tmp_path):
    from rocket_engine.adapters.syntax import SyntaxAdapter  # RED: missing adapter

    adapter = SyntaxAdapter()
    result = adapter.parse(adapter.execute(_job(["counter.v"], tmp_path)))
    assert result["total"] == 0
    assert result["violations"] == []


@needs_slang
def test_syntax_broken_reports_error_with_span(tmp_path):
    from rocket_engine.adapters.syntax import SyntaxAdapter  # RED: missing adapter

    adapter = SyntaxAdapter()
    result = adapter.parse(adapter.execute(_job(["counter_broken.v"], tmp_path)))
    assert result["total"] >= 1
    assert all(v["severity"] == "error" for v in result["violations"])
    first = result["violations"][0]
    assert first["file"].endswith("counter_broken.v")
    assert isinstance(first["line"], int) and isinstance(first["col"], int)


@needs_slang
def test_syntax_warning_stays_warning_with_exit_zero(tmp_path):
    from rocket_engine.adapters.syntax import SyntaxAdapter  # RED: missing adapter

    adapter = SyntaxAdapter()
    native = adapter.execute(_job(["trunc.v"], tmp_path))
    assert native["exit_code"] == 0
    result = adapter.parse(native)
    assert result["total"] >= 1
    assert all(v["severity"] == "warning" for v in result["violations"])
    assert any("width" in v["rule"] for v in result["violations"])


@needs_slang
def test_syntax_proves_labels_against_real_slang(tmp_path):
    # Oracle check: fixture labels verified against slang directly,
    # not against the adapter under test.
    from rocket_engine.adapters.syntax import (  # RED: missing adapter  # noqa: F401
        SyntaxAdapter,
    )

    cases = [
        (["counter.v"], 0, ["Build succeeded: 0 errors, 0 warnings"]),
        (["counter_broken.v"], 1, ["error: expected ';'", "Build failed: 1 error"]),
        (["trunc.v"], 0, ["warning:", "Wwidth-trunc", "0 errors, 1 warning"]),
    ]
    for sources, want_rc, want_text in cases:
        proc = subprocess.run(
            ["slang", "--lint-only", "-Wextra", *[str(FIXTURES / s) for s in sources]],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=tmp_path,
        )
        assert proc.returncode == want_rc, (sources, proc.returncode)
        combined = proc.stdout + proc.stderr
        for text in want_text:
            assert text in combined, (sources, text)


def test_syntax_parse_synthesizes_violation_on_bare_failure():
    from rocket_engine.adapters.syntax import SyntaxAdapter  # RED: missing adapter

    native = {
        "exit_code": 1,
        "stdout": "Build failed: 2 errors, 0 warnings\n",
        "stderr": "",
    }
    result = SyntaxAdapter().parse(native)
    assert result["total"] == 1
    assert result["violations"][0]["severity"] == "error"


def test_syntax_parse_rejects_native_without_summary():
    from rocket_engine.adapters.syntax import SyntaxAdapter  # RED: missing adapter

    native = {"exit_code": 0, "stdout": "definitely not slang output\n", "stderr": ""}
    try:
        SyntaxAdapter().parse(native)
    except Exception as exc:
        assert getattr(exc, "code", None) == "runner_unavailable"
    else:
        raise AssertionError("expected runner_unavailable for a missing summary")
