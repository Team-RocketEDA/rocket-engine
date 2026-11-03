"""VALIDATE-D RED — digital correctness end-to-end (SERV, picorv32).

Valid RED = the vendored digital operators do not exist yet in
`rocket_engine.mutate` (KeyError), the shared staging helpers are
missing (ImportError), the committed picorv32 monitor fixture is
absent (FileNotFoundError), and HdlSimAdapter ignores `defines` —
so every live test below fails while the toolchain-quarantine test
skips loudly.

Correct = the designers' documented outcomes. SERV (olofk/serv):
the hello_uart firmware prints "Hi, I'm Servant!" (sw/hello_uart.S)
and HALTs through the servile HALT trap, which prints "Test
complete" (servile/servile_mux.v). picorv32 (YosysHQ/picorv32): the
vendor `make test_ez` flow (testbench_ez.v + picorv32.v, no firmware
toolchain needed per README) finishes clean with 182 ifetch / 45
write / 45 read transactions. Each vendored mutation must flip its
e2e to FAIL with assert_fatal and only it.
"""

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SERV = ROOT / "fixtures" / "upstream" / "serv"
PICO = ROOT / "fixtures" / "upstream" / "picorv32"
ARTIFACTS = ROOT / "tmp" / "validate-d"

SERV_OP_SEEDS = {
    "serv_reset_break": [0, 1],
    "serv_truncation": [0, 1, 2],
    "serv_unconnected_port": [0, 1],
}
PICO_OP_SEEDS = {
    "picorv32_reset_break": [0, 1],
    "picorv32_truncation": [0, 1, 2],
    "picorv32_unconnected_port": [0, 1],
}

# Vendor test_ez traffic, observed with oss-cad-suite iverilog 14.0.
# The committed monitor is silent on good runs, so the engine run
# must reproduce these counts exactly.
PICO_IFETCH = 182
PICO_WRITE = 45
PICO_READ = 45

tools_present = shutil.which("iverilog") is not None and shutil.which("vvp") is not None
needs_icarus = pytest.mark.skipif(
    not tools_present,
    reason="VALIDATE-D live: iverilog/vvp not on PATH (B10-owned tooling)",
)


def _require_serv():
    if not (SERV / "rtl" / "serv_top.v").is_file():
        pytest.skip(
            "VALIDATE-D live: serv fixture not fetched "
            "(scripts/fetch_fixtures.py; docs/tickets/VALIDATE-D.md)"
        )


def _require_pico():
    if not (PICO / "picorv32.v").is_file() or not (PICO / "testbench_ez.v").is_file():
        pytest.skip(
            "VALIDATE-D live: picorv32 fixture not fetched "
            "(scripts/fetch_fixtures.py; docs/tickets/VALIDATE-D.md)"
        )


def _engine_run(project, operation, arguments):
    from rocket_engine.composition import Engine

    engine = Engine(project, actor="validate-d")
    out = engine.run({"project_id": project, "operation": operation, "arguments": arguments})
    return engine, out


def _stage_good(design, dest):
    # RED: stage_good_design does not exist yet.
    from rocket_engine.mutate import stage_good_design

    return stage_good_design(design, dest, ROOT)


def _stage_mut(operator, dest, seed):
    # RED: vendored operators are not in the registry yet.
    from rocket_engine.mutate import OPERATORS, apply_operator, stage_design_extras

    entry = OPERATORS[operator]
    apply_operator(operator, dest, seed, ROOT / entry["base"])
    return stage_design_extras(entry["design"], dest, ROOT)


def _job(staged):
    # "operation" serves direct-adapter calls; Engine.run passes it
    # through identically (same value, harmless duplicate).
    return {
        "operation": "run_hdl_test",
        "sources": staged["sources"],
        "workdir": staged["workdir"],
        "request": {"timeout_s": staged["timeout_s"]},
        "defines": staged["defines"],
        "deck": {"tool": "icarus"},
    }


def _native_text(native):
    run = native.get("run") or {}
    return run.get("stdout", "") + "\n" + run.get("stderr", "")


def _canon_findings(findings):
    # Results-not-bytes: absolute tmp paths legitimately differ
    # across runs; compare rule/severity/message + basenames.
    canon = []
    for finding in findings:
        location = dict(finding.get("location") or {})
        if "file" in location:
            location["file"] = Path(location["file"]).name
        canon.append(
            (
                finding.get("rule"),
                finding.get("severity"),
                finding.get("message"),
                sorted(location.items()),
            )
        )
    return sorted(canon)


def _fixture_pin(design):
    note = ROOT / "fixtures" / "upstream" / f"{design}.md"
    rev = None
    if note.is_file():
        for line in note.read_text().splitlines():
            if "pinned rev:" in line:
                rev = line.split("`")[1]
    head = None
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        cwd=ROOT / "fixtures" / "upstream" / design,
    )
    if proc.returncode == 0:
        head = proc.stdout.strip()
    return rev, head


def _tool_versions():
    versions = {}
    for binary in ("iverilog", "vvp"):
        found = shutil.which(binary)
        versions[binary] = found or "absent"
        if found:
            flag = "-V" if binary == "iverilog" else "-V"
            try:
                proc = subprocess.run(
                    [binary, flag], capture_output=True, text=True, timeout=30
                )
                versions[binary] = (proc.stdout + proc.stderr).splitlines()[0][:120]
            except Exception:
                pass
    return versions


def _write_artifacts(case, *, verdict, findings, native, staged, design, mutation):
    case_dir = ARTIFACTS / case
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "verdict.json").write_text(
        json.dumps(
            {"verdict": verdict, "findings": findings}, indent=2, sort_keys=True
        )
        + "\n"
    )
    compile_block = native.get("compile") or {}
    run_block = native.get("run") or {}
    (case_dir / "native.log").write_text(
        "=== compile stdout ===\n"
        + compile_block.get("stdout", "")
        + "\n=== compile stderr ===\n"
        + compile_block.get("stderr", "")
        + "\n=== run stdout ===\n"
        + run_block.get("stdout", "")
        + "\n=== run stderr ===\n"
        + run_block.get("stderr", "")
    )
    pinned, head = _fixture_pin(design)
    sources = []
    for path in staged["sources"]:
        digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        sources.append({"name": Path(path).name, "sha256": digest})
    record = {
        "case": case,
        "design": design,
        "engine": {"operation": "run_hdl_test", "project_id": "validate-d"},
        "ingredients": {
            "fixture": {"pinned_rev": pinned, "actual_head": head},
            "sources": sorted(sources, key=lambda s: s["name"]),
            "defines": list(staged["defines"]),
            "timeout_s": staged["timeout_s"],
            "watchdog_units": staged.get("watchdog_units"),
            "solver": {"tool": "icarus", **_tool_versions()},
            "mutation": mutation,
        },
        "results": {"verdict": verdict, "findings": findings},
    }
    (case_dir / "run_record.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n"
    )
    return case_dir


# Good-matches-documented: SERV hello through the engine.


@needs_icarus
def test_serv_good_matches_documented_outcome(tmp_path):
    from rocket_engine.adapters.hdl_sim import HdlSimAdapter

    _require_serv()
    staged = _stage_good("serv", tmp_path / "good")
    engine, out = _engine_run("validate_d_serv_good", "run_hdl_test", _job(staged))
    assert out["verdict"]["status"] == "PASS", out["verdict"]
    assert engine.findings(out["run_id"])["findings"] == []
    native = HdlSimAdapter().execute(_job(staged))
    result = HdlSimAdapter().parse(native)
    assert result["total"] == 0, result["violations"]
    text = _native_text(native)
    # Documented: sw/hello_uart.S prints the greeting; the HALT
    # store hits servile_mux.v which prints "Test complete".
    assert "Hi, I'm Servant!" in text
    assert "Test complete" in text


@needs_icarus
def test_serv_good_passes_at_staging_watchdog(tmp_path):
    # The staging watchdog must clear the good hello finish with
    # margin: hello completes below 4M units (bisected), staging
    # uses 5M, so a mutant watchdog fire always means a real hang.
    _require_serv()
    staged = _stage_good("serv", tmp_path / "good")
    assert staged["watchdog_units"] == 5000000
    _, out = _engine_run("validate_d_serv_wd", "run_hdl_test", _job(staged))
    assert out["verdict"]["status"] == "PASS", out["verdict"]


# Good-matches-documented: picorv32 test_ez through the engine.


@needs_icarus
def test_picorv32_good_matches_documented_outcome(tmp_path):
    from rocket_engine.adapters.hdl_sim import HdlSimAdapter

    _require_pico()
    staged = _stage_good("picorv32", tmp_path / "good")
    assert staged["defines"] == ["COMPRESSED_ISA"]
    engine, out = _engine_run("validate_d_pico_good", "run_hdl_test", _job(staged))
    assert out["verdict"]["status"] == "PASS", out["verdict"]
    assert engine.findings(out["run_id"])["findings"] == []
    native = HdlSimAdapter().execute(_job(staged))
    result = HdlSimAdapter().parse(native)
    assert result["total"] == 0, result["violations"]
    text = _native_text(native)
    assert "$finish called at 11000000 (1ps)" in text
    assert text.count("ifetch ") == PICO_IFETCH, text.count("ifetch ")
    assert text.count("write  ") == PICO_WRITE, text.count("write  ")
    assert text.count("read   ") == PICO_READ, text.count("read   ")


@needs_icarus
def test_picorv32_matches_vendor_make_oracle(tmp_path):
    # Oracle check: the vendor's own `make test_ez` in a scratch
    # copy of the fixture must agree with the engine run on
    # verdict-relevant results (exit + traffic + finish).
    if shutil.which("make") is None:
        pytest.skip("VALIDATE-D oracle: make not on PATH (B10-owned tooling)")
    _require_pico()
    clone = tmp_path / "upstream-copy"
    shutil.copytree(PICO, clone, ignore=shutil.ignore_patterns(".git"))
    proc = subprocess.run(
        ["make", "test_ez"],
        capture_output=True,
        text=True,
        timeout=280,
        cwd=clone,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    vendor_text = proc.stdout + proc.stderr
    assert "$finish called at 11000000 (1ps)" in vendor_text
    assert vendor_text.count("ifetch ") == PICO_IFETCH
    assert vendor_text.count("write  ") == PICO_WRITE
    assert vendor_text.count("read   ") == PICO_READ
    staged = _stage_good("picorv32", tmp_path / "good")
    _, out = _engine_run("validate_d_pico_oracle", "run_hdl_test", _job(staged))
    assert out["verdict"]["status"] == "PASS", out["verdict"]


def test_picorv32_full_firmware_bench_quarantined_without_toolchain():
    # The full `make test` bench needs firmware/firmware.hex built
    # by a RISC-V GCC toolchain, which no PATH provides; the vendor
    # README names test_ez as the no-toolchain bench, and that is
    # what VALIDATE-D covers. If a toolchain ever appears this
    # tripwire fails loudly so the full bench gets covered instead
    # of silently staying out of the gate.
    prefixes = (
        "riscv32-unknown-elf-gcc",
        "riscv64-unknown-elf-gcc",
        "riscv32-unknown-linux-gnu-gcc",
    )
    found = [p for p in prefixes if shutil.which(p) is not None]
    if not found:
        pytest.skip(
            "VALIDATE-D full-bench: no RISC-V GCC on PATH (B10-owned "
            "tooling; vendor test_ez covers the no-firmware bench)"
        )
    raise AssertionError(
        f"RISC-V toolchain present ({found}): VALIDATE-D must now cover "
        "the full `make test` firmware bench (ALL TESTS PASSED.), not "
        "just test_ez."
    )


# Mutation-flips-only-target: file level (no tool needed).


def _op_params(table):
    return [(op, seed) for op, seeds in table.items() for seed in seeds]


@pytest.mark.parametrize("operator,seed", _op_params(SERV_OP_SEEDS))
def test_serv_mutation_targets_vendored_site(operator, seed, tmp_path):
    from rocket_engine.mutate import OPERATORS, apply_operator

    _require_serv()
    assert OPERATORS[operator]["operation"] == "run_hdl_test"
    assert OPERATORS[operator]["expected_verdict"] == "FAIL"
    assert OPERATORS[operator]["expected_rules"] == ["assert_fatal"]
    dest = tmp_path / "mut"
    evidence = apply_operator(operator, dest, seed, SERV)
    assert evidence["operator"] == operator
    assert evidence["seed"] == seed
    staged = dest / evidence["target_file"]
    assert staged.is_file()
    # Scratch copies mutated, vendored tree pristine.
    assert evidence["target_file"] in ("servant/servant.v", "rtl/serv_bufreg.v")
    base = SERV / evidence["target_file"]
    assert staged.read_bytes() != base.read_bytes()


@pytest.mark.parametrize("operator,seed", _op_params(PICO_OP_SEEDS))
def test_picorv32_mutation_targets_vendored_site(operator, seed, tmp_path):
    from rocket_engine.mutate import OPERATORS, apply_operator

    _require_pico()
    assert OPERATORS[operator]["operation"] == "run_hdl_test"
    assert OPERATORS[operator]["expected_verdict"] == "FAIL"
    assert OPERATORS[operator]["expected_rules"] == ["assert_fatal"]
    evidence = apply_operator(operator, tmp_path / "mut", seed, PICO)
    assert evidence["operator"] == operator
    assert evidence["seed"] == seed
    staged = (tmp_path / "mut") / evidence["target_file"]
    assert staged.is_file()
    assert evidence["target_file"] in ("picorv32.v", "testbench_ez.v")
    base = PICO / evidence["target_file"]
    assert staged.read_bytes() != base.read_bytes()


def test_serv_operator_files_match_manifest():
    from rocket_engine.mutate import OPERATORS

    manifest = ROOT / "tests" / "adapters" / "fixtures" / "hdl" / "serv_sources.txt"
    rels = sorted(
        line.strip()
        for line in manifest.read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    )
    for operator in SERV_OP_SEEDS:
        assert sorted(OPERATORS[operator]["files"]) == rels, operator


def test_picorv32_operator_files_match_manifest():
    from rocket_engine.mutate import OPERATORS

    manifest = ROOT / "tests" / "adapters" / "fixtures" / "hdl" / "picorv32_sources.txt"
    rels = sorted(
        line.strip()
        for line in manifest.read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    )
    assert rels == ["picorv32.v", "testbench_ez.v"]
    for operator in PICO_OP_SEEDS:
        assert sorted(OPERATORS[operator]["files"]) == rels, operator


# Mutation-flips-only-target: live rechecks.


@needs_icarus
@pytest.mark.parametrize("operator,seed", _op_params(SERV_OP_SEEDS))
def test_serv_mutated_fails_only_target(operator, seed, tmp_path):
    _require_serv()
    staged = _stage_mut(operator, tmp_path / "mut", seed)
    engine, out = _engine_run(f"validate_d_serv_{seed}", "run_hdl_test", _job(staged))
    assert out["verdict"]["status"] == "FAIL", (operator, seed, out["verdict"])
    found = engine.findings(out["run_id"])["findings"]
    errors = [f for f in found if f["severity"] == "error"]
    assert errors, (operator, seed)
    assert {f["rule"] for f in errors} == {"assert_fatal"}, (operator, seed, found)


@needs_icarus
@pytest.mark.parametrize("operator,seed", _op_params(PICO_OP_SEEDS))
def test_picorv32_mutated_fails_only_target(operator, seed, tmp_path):
    _require_pico()
    staged = _stage_mut(operator, tmp_path / "mut", seed)
    engine, out = _engine_run(f"validate_d_pico_{seed}", "run_hdl_test", _job(staged))
    assert out["verdict"]["status"] == "FAIL", (operator, seed, out["verdict"])
    found = engine.findings(out["run_id"])["findings"]
    errors = [f for f in found if f["severity"] == "error"]
    assert errors, (operator, seed)
    assert {f["rule"] for f in errors} == {"assert_fatal"}, (operator, seed, found)


# Determinism-3x: identical verdicts across repeat runs.


@needs_icarus
def test_serv_determinism_3x(tmp_path):
    _require_serv()
    cases = [("good", None, None)]
    cases += [(op, op, seed) for op, seed in _op_params(SERV_OP_SEEDS)]
    for name, operator, seed in cases:
        seen = []
        for rep in range(3):
            dest = tmp_path / f"{name}-{seed}-{rep}"
            if operator is None:
                staged = _stage_good("serv", dest)
            else:
                staged = _stage_mut(operator, dest, seed)
            engine, out = _engine_run(
                f"validate_d_serv_det_{rep}", "run_hdl_test", _job(staged)
            )
            found = engine.findings(out["run_id"])["findings"]
            seen.append((out["verdict"]["status"], _canon_findings(found)))
        assert seen[0] == seen[1] == seen[2], (name, seed, seen)
        want = "PASS" if operator is None else "FAIL"
        assert seen[0][0] == want, (name, seed, seen)


@needs_icarus
def test_picorv32_determinism_3x(tmp_path):
    _require_pico()
    cases = [("good", None, None)]
    cases += [(op, op, seed) for op, seed in _op_params(PICO_OP_SEEDS)]
    for name, operator, seed in cases:
        seen = []
        for rep in range(3):
            dest = tmp_path / f"{name}-{seed}-{rep}"
            if operator is None:
                staged = _stage_good("picorv32", dest)
            else:
                staged = _stage_mut(operator, dest, seed)
            engine, out = _engine_run(
                f"validate_d_pico_det_{rep}", "run_hdl_test", _job(staged)
            )
            found = engine.findings(out["run_id"])["findings"]
            seen.append((out["verdict"]["status"], _canon_findings(found)))
        assert seen[0] == seen[1] == seen[2], (name, seed, seen)
        want = "PASS" if operator is None else "FAIL"
        assert seen[0][0] == want, (name, seed, seen)


# Artifacts-kept: verdict JSON + native logs + run record.


@needs_icarus
def test_serv_failure_artifacts_kept(tmp_path):
    from rocket_engine.adapters.hdl_sim import HdlSimAdapter
    from rocket_engine.mutate import OPERATORS, apply_operator, stage_design_extras

    _require_serv()
    operator, seed = "serv_truncation", 0
    dest = tmp_path / "mut"
    evidence = apply_operator(operator, dest, seed, SERV)
    staged = stage_design_extras(OPERATORS[operator]["design"], dest, ROOT)
    job = _job(staged)
    engine, out = _engine_run("validate_d_serv_art", "run_hdl_test", job)
    assert out["verdict"]["status"] == "FAIL"
    native = HdlSimAdapter().execute(job)
    assert HdlSimAdapter().parse(native)["total"] >= 1
    found = engine.findings(out["run_id"])["findings"]
    case_dir = _write_artifacts(
        "serv_truncation-0",
        verdict=out["verdict"],
        findings=found,
        native=native,
        staged=staged,
        design="serv",
        mutation=evidence,
    )
    for name in ("verdict.json", "native.log", "run_record.json"):
        path = case_dir / name
        assert path.is_file(), name
        assert path.stat().st_size > 0, name
    record = json.loads((case_dir / "run_record.json").read_text())
    assert record["ingredients"]["mutation"]["operator"] == operator
    assert record["ingredients"]["solver"]["tool"] == "icarus"
    assert len(record["ingredients"]["sources"]) == len(staged["sources"])
    assert "watchdog expired" in (case_dir / "native.log").read_text()


@needs_icarus
def test_picorv32_failure_artifacts_kept(tmp_path):
    from rocket_engine.adapters.hdl_sim import HdlSimAdapter
    from rocket_engine.mutate import OPERATORS, apply_operator, stage_design_extras

    _require_pico()
    operator, seed = "picorv32_truncation", 0
    dest = tmp_path / "mut"
    evidence = apply_operator(operator, dest, seed, PICO)
    staged = stage_design_extras(OPERATORS[operator]["design"], dest, ROOT)
    job = _job(staged)
    engine, out = _engine_run("validate_d_pico_art", "run_hdl_test", job)
    assert out["verdict"]["status"] == "FAIL"
    native = HdlSimAdapter().execute(job)
    assert HdlSimAdapter().parse(native)["total"] >= 1
    found = engine.findings(out["run_id"])["findings"]
    case_dir = _write_artifacts(
        "picorv32_truncation-0",
        verdict=out["verdict"],
        findings=found,
        native=native,
        staged=staged,
        design="picorv32",
        mutation=evidence,
    )
    for name in ("verdict.json", "native.log", "run_record.json"):
        path = case_dir / name
        assert path.is_file(), name
        assert path.stat().st_size > 0, name
    record = json.loads((case_dir / "run_record.json").read_text())
    assert record["ingredients"]["mutation"]["operator"] == operator
    assert record["ingredients"]["defines"] == ["COMPRESSED_ISA"]
    assert "no progress" in (case_dir / "native.log").read_text()


# Staging guards: unknown designs and missing/drifted pieces fail
# loudly (no tool needed).


def test_stage_unknown_design_raises_key_error(tmp_path):
    from rocket_engine.mutate import stage_design_extras, stage_good_design

    for fn in (stage_good_design, stage_design_extras):
        try:
            fn("no_such_design", tmp_path, ROOT)
        except KeyError:
            continue
        raise AssertionError(f"expected KeyError from {fn.__name__}")


def test_stage_picorv32_missing_monitor_raises(tmp_path):
    from rocket_engine.mutate import stage_design_extras

    dest = tmp_path / "mut"
    dest.mkdir()
    (dest / "picorv32.v").write_text("module picorv32; endmodule\n")
    (dest / "testbench_ez.v").write_text("module testbench; endmodule\n")
    empty_root = tmp_path / "empty-root"
    empty_root.mkdir()
    try:
        stage_design_extras("picorv32", dest, empty_root)
    except FileNotFoundError as exc:
        assert "monitor" in str(exc)
    else:
        raise AssertionError("expected FileNotFoundError for missing monitor")


def test_stage_picorv32_missing_base_raises(tmp_path):
    from rocket_engine.mutate import stage_design_extras

    dest = tmp_path / "mut"
    dest.mkdir()
    try:
        stage_design_extras("picorv32", dest, ROOT)
    except FileNotFoundError as exc:
        assert "base file missing" in str(exc)
    else:
        raise AssertionError("expected FileNotFoundError for missing base")


def test_stage_serv_drifted_watchdog_raises(tmp_path):
    from rocket_engine.mutate import MutationError, stage_design_extras

    fake_root = tmp_path / "fake-root"
    harness_dir = fake_root / "tests" / "adapters" / "fixtures" / "hdl"
    harness_dir.mkdir(parents=True)
    real = (ROOT / "tests" / "adapters" / "fixtures" / "hdl" / "serv_harness.v").read_text()
    (harness_dir / "serv_harness.v").write_text(
        real.replace("parameter watchdog_units = 200000000", "parameter watchdog_units = 1")
    )
    dest = tmp_path / "mut"
    try:
        stage_design_extras("serv", dest, fake_root)
    except MutationError as exc:
        assert "watchdog" in str(exc)
    else:
        raise AssertionError("expected MutationError for drifted watchdog")


def test_stage_serv_missing_pieces_raise(tmp_path):
    from rocket_engine.mutate import stage_design_extras

    fake_root = tmp_path / "fake-root"
    fake_root.mkdir()
    dest = tmp_path / "mut"
    try:
        stage_design_extras("serv", dest, fake_root)
    except FileNotFoundError as exc:
        assert "harness" in str(exc)
    else:
        raise AssertionError("expected FileNotFoundError for missing harness")
    harness_dir = fake_root / "tests" / "adapters" / "fixtures" / "hdl"
    harness_dir.mkdir(parents=True)
    shutil.copy(
        ROOT / "tests" / "adapters" / "fixtures" / "hdl" / "serv_harness.v",
        harness_dir / "serv_harness.v",
    )
    try:
        stage_design_extras("serv", dest, fake_root)
    except FileNotFoundError as exc:
        assert "firmware" in str(exc)
    else:
        raise AssertionError("expected FileNotFoundError for missing firmware")


# CLI rechecks prove the scripts/mutate.py path on vendored designs.


@needs_icarus
@pytest.mark.parametrize("operator", ["serv_truncation", "picorv32_truncation"])
def test_cli_recheck_proves_vendored_flip(operator, tmp_path):
    if operator.startswith("serv_"):
        _require_serv()
    else:
        _require_pico()
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "mutate.py"), "recheck",
         "--operator", operator, "--seed", "0",
         "--dest", str(tmp_path / "recheck")],
        capture_output=True,
        text=True,
        timeout=280,
        cwd=ROOT,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    report = json.loads(proc.stdout)
    assert report["proven"] is True, report
    assert report["good"] == "PASS", report
    assert report["mutated"] == "FAIL", report
