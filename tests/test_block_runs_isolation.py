"""BLOCK-RUNS isolation RED — sibling breakage never leaks across blocks.

A fake solver harness runs narrowed block jobs over tmp sources: the
amp block greens against its golden while the bias sibling's breakage
leaves it untouched. Valid RED = the block_runs_scope import fails.
"""

from pathlib import Path

GOLDEN_AMP_OUTPUT = "PASS amp findings=0\n"


def _mod():
    from rocket_engine.execution import block_runs_scope  # RED: missing module

    return block_runs_scope


def _write(path, text):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8")
    return str(path)


def _layout(tmp_path):
    amp_src = _write(tmp_path / "blocks" / "amp" / "amp.sv", "module amp; endmodule\n")
    bias_src = _write(
        tmp_path / "blocks" / "bias" / "bias.sv", "module bias; endmodule\n"
    )
    blocks = {
        "amp": {"id": "amp", "sources": [amp_src], "params": {"w": "2u"}},
        "bias": {"id": "bias", "sources": [bias_src], "params": {"w": "1u"}},
    }
    return blocks, amp_src, bias_src


def _lint(job):
    """Fake syntax solver: FAIL names only the files it was given."""
    findings = []
    for source in job["sources"]:
        text = Path(source).read_text(encoding="utf-8")
        if "BREAK" in text:
            findings.append({"rule": "syntax", "file": source})
    status = "FAIL" if findings else "PASS"
    block = job.get("block_scope", {}).get("block_id", "?")
    return {
        "status": status,
        "findings": findings,
        "output": f"{status} {block} findings={len(findings)}\n",
    }


def _run_block(mod, blocks, block_id, revision="p12", deck=None, run_id="r1"):
    block = mod.resolve_block(block_id, blocks)
    closure = mod.snapshot_closure(block)
    job = mod.narrow_job_for_block({"operation": "run_syntax"}, closure)
    result = _lint(job)
    verdict = {"status": result["status"], "finding_counts": {}}
    scope = mod.scope_provenance(
        run_id=run_id, revision=revision, block_id=block_id, deck=deck or {}
    )
    return mod.stamp_verdict(verdict, scope), result, closure


def test_block_run_greens_against_golden(tmp_path):
    mod = _mod()
    blocks, _, _ = _layout(tmp_path)
    verdict, result, _ = _run_block(mod, blocks, "amp", deck={"tool": "slang"})
    assert verdict["status"] == "PASS"
    assert result["output"] == GOLDEN_AMP_OUTPUT
    assert verdict["scope"] == {
        "run_id": "r1",
        "revision": "p12",
        "block_id": "amp",
        "deck": {"tool": "slang"},
    }


def test_sibling_breakage_leaves_block_untouched(tmp_path):
    mod = _mod()
    blocks, _, bias_src = _layout(tmp_path)
    _, _, before = _run_block(mod, blocks, "amp")
    hash_before = mod.closure_hash(before)
    _write(bias_src, "module bias BREAK; endmodule\n")
    verdict, result, after = _run_block(mod, blocks, "amp", run_id="r2")
    assert verdict["status"] == "PASS"
    assert result["output"] == GOLDEN_AMP_OUTPUT.replace("amp", "amp")
    assert mod.closure_hash(after) == hash_before
    assert verdict["scope"]["block_id"] == "amp"
    assert verdict["scope"]["run_id"] == "r2"


def test_broken_sibling_fails_on_its_own_sources_only(tmp_path):
    mod = _mod()
    blocks, amp_src, bias_src = _layout(tmp_path)
    _write(bias_src, "module bias BREAK; endmodule\n")
    verdict, result, _ = _run_block(mod, blocks, "bias")
    assert verdict["status"] == "FAIL"
    assert [f["file"] for f in result["findings"]] == [bias_src]
    assert all(amp_src not in f["file"] for f in result["findings"])
    assert verdict["scope"]["block_id"] == "bias"


def test_block_narrowing_never_sees_project_sources(tmp_path):
    mod = _mod()
    blocks, _, _ = _layout(tmp_path)
    closure = mod.snapshot_closure(mod.resolve_block("amp", blocks))
    job = mod.narrow_job_for_block(
        {"operation": "run_syntax", "sources": ["top.sv", "other.sv"]}, closure
    )
    assert job["sources"] == blocks["amp"]["sources"]
    assert "top.sv" not in job["sources"]
