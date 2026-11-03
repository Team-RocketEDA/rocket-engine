"""BLOCK-RUNS wiring — Engine submit→preflight→snapshot→verdict.

The integrator runs this AFTER applying the docs/work/BLOCK-RUNS
wiring patch: block targets flow through Engine.submit/run_job with
closure narrowing and scope cited on verdicts + run events. Every
test skips until the patch lands (Engine takes no `blocks` yet).
"""

import inspect
from pathlib import Path

import pytest

from rocket_engine.composition import Engine
from rocket_engine.interfaces import ToolAdapter


def _wired():
    try:
        inspect.signature(Engine.__init__).parameters["blocks"]
    except KeyError:
        return False
    return True


needs_wiring = pytest.mark.skipif(not _wired(), reason="BLOCK-RUNS wiring patch not applied")


class _FakeLint(ToolAdapter):
    """Minimal run_syntax solver: BREAK markers fail, else clean."""

    def capabilities(self, target):
        return {"operations": ["run_syntax"], "tool": "fake"}

    def preflight(self, job):
        missing = [s for s in job.get("sources", []) if not Path(s).is_file()]
        if not job.get("sources") or missing:
            from rocket_engine.adapters.errors import AdapterError

            raise AdapterError("invalid_reference", f"Sources not found: {missing}.")
        return {"sources": list(job["sources"])}

    def execute(self, job):
        self.preflight(job)
        return {"exit_code": 0, "sources": list(job["sources"])}

    def parse(self, native_output):
        violations = []
        for source in native_output["sources"]:
            if "BREAK" in Path(source).read_text(encoding="utf-8"):
                violations.append(
                    {"rule": "syntax", "severity": "error",
                     "message": "broken", "file": source}
                )
        return {"total": len(violations), "violations": violations}


def _blocks(tmp_path):
    amp = tmp_path / "amp.sv"
    bias = tmp_path / "bias.sv"
    amp.write_text("module amp; endmodule\n", encoding="utf-8")
    bias.write_text("module bias; endmodule\n", encoding="utf-8")
    return {
        "amp": {"id": "amp", "sources": [str(amp)], "params": {"w": "2u"}},
        "bias": {"id": "bias", "sources": [str(bias)]},
    }


def _engine(tmp_path):
    engine = Engine("block_demo", actor="tester", blocks=_blocks(tmp_path))
    engine.register_solver("run_syntax", _FakeLint(), tool="fake")
    return engine


def _submit(engine, block_id, **over):
    arguments = {
        "target": {"scope": "block", "id": block_id},
        "sources": ["should-never-run.sv"],
        "deck": {"tool": "fake"},
        "workdir": ".",
        "expected_revision": engine.snapshot()["current_revision"],
    }
    arguments.update(over)
    return engine.submit(
        {"project_id": "block_demo", "operation": "run_syntax",
         "arguments": arguments, "request_id": f"req-{block_id}-{arguments['expected_revision']}"}
    )


@needs_wiring
def test_block_submit_runs_narrowed_closure(tmp_path):
    engine = _engine(tmp_path)
    ack = _submit(engine, "amp")
    out = engine.run(
        {"project_id": "block_demo", "operation": "run_job",
         "arguments": {"run_id": ack["run_id"]}}
    )
    assert out["verdict"]["status"] == "PASS"
    assert out["verdict"]["scope"] == {
        "run_id": ack["run_id"],
        "revision": engine.snapshot()["current_revision"],
        "block_id": "amp",
        "deck": {"tool": "fake"},
    }


@needs_wiring
def test_block_verdict_provenance_lands_on_run_event(tmp_path):
    engine = _engine(tmp_path)
    ack = _submit(engine, "amp")
    engine.run(
        {"project_id": "block_demo", "operation": "run_job",
         "arguments": {"run_id": ack["run_id"]}}
    )
    events = engine.events_since(0)
    completions = [e for e in events if e["event"] == "run_completed"]
    assert completions
    assert completions[-1]["data"]["verdict"]["scope"]["block_id"] == "amp"


@needs_wiring
def test_sibling_breakage_leaves_wired_block_green(tmp_path):
    blocks = _blocks(tmp_path)
    engine = Engine("block_demo", actor="tester", blocks=blocks)
    engine.register_solver("run_syntax", _FakeLint(), tool="fake")
    Path(blocks["bias"]["sources"][0]).write_text(
        "module bias BREAK; endmodule\n", encoding="utf-8"
    )
    ack = _submit(engine, "amp")
    out = engine.run(
        {"project_id": "block_demo", "operation": "run_job",
         "arguments": {"run_id": ack["run_id"]}}
    )
    assert out["verdict"]["status"] == "PASS"
    bias_ack = _submit(engine, "bias")
    bias_out = engine.run(
        {"project_id": "block_demo", "operation": "run_job",
         "arguments": {"run_id": bias_ack["run_id"]}}
    )
    assert bias_out["verdict"]["status"] == "FAIL"
    assert bias_out["verdict"]["scope"]["block_id"] == "bias"


@needs_wiring
def test_unknown_block_fails_submit_with_named_reason(tmp_path):
    from rocket_engine.project.errors import ProjectError

    engine = _engine(tmp_path)
    with pytest.raises(ProjectError) as exc:
        _submit(engine, "ghost")
    assert exc.value.code == "unknown_block"


@needs_wiring
def test_project_runs_unaffected_by_wiring(tmp_path):
    engine = _engine(tmp_path)
    out = engine.run(
        {"project_id": "block_demo", "operation": "run_syntax",
         "arguments": {"sources": [f for b in _blocks(tmp_path).values()
                                   for f in b["sources"]],
                       "deck": {"tool": "fake"}, "workdir": "."}}
    )
    assert out["verdict"]["status"] == "PASS"
    assert "scope" not in out["verdict"]
