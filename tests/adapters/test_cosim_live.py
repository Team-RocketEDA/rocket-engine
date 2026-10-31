"""SEAM-COSIM live suite — coupled tran-to-RTL runs plus post-patch wiring.

Valid RED = `rocket_engine.adapters.cosim` does not exist yet, so
every adapter-importing test fails on ImportError (PEX-tier tests
skip loudly without their COSIM_PEX_* gates, wiring tests skip
until the patch lands). Tier-1 (behavioral, model-free,
seconds per run) carries the full live matrix by default: good
joint PASS in the documented tier-1 band, every sdm_* seed flipping
the JOINT verdict with only assert_fatal, analog faults flipping
with only measurement, 3x determinism, and kept artifacts with I28
ingredient closure for both halves. PEX-tier proofs run behind
COSIM_PEX_LIVE=1 (good, ~11 min) and COSIM_PEX_MATRIX=1 (sdtop_*
matrix plus 3x, ~1.5 h); without the gates they skip LOUDLY naming
the gate. Engine-wiring tests skip until the wiring patch lands.

Live tools resolve through PATH plus the oss-cad-suite bins (B10
scope); xschem generates the tier-1 body from the vendored
schematic at staging time, so the .sch stays the source of truth.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from .cosim_staging import (
    GATE_DB,
    ONES_MAX,
    ONES_MIN,
    PEX_NBITS,
    PEX_NSETTLE,
    PEX_SIG_BIN,
    TIER1_NBITS,
    TIER1_NSETTLE,
    TIER1_SIG_BIN,
    pex_job,
    stage_cosim_digital,
    stage_pex_wrapper,
    stage_tier1_body,
    tier1_job,
)

ROOT = Path(__file__).resolve().parent.parent.parent
SIGMA = ROOT / "fixtures" / "upstream" / "ttsky-sigma-delta"
SDM_RX = SIGMA / "rtl" / "sdm_rx.v"
PEX = SIGMA / "spice" / "sd_top_pex.spice"
TIER1_SCH = SIGMA / "xschem" / "tier1_sdm.sch"
ARTIFACTS = ROOT / "tmp" / "validate-cosim"

OSR_FAST = 25
OSR_PREC = 250
SNDR_TIER1_LO = 36.4
SNDR_TIER1_HI = 38.0
SNDR_PEX_LO = 38.3
SNDR_PEX_HI = 40.7

SDM_OP_SEEDS = {
    "sdm_reset_break": [0, 1],
    "sdm_truncation": [0, 1, 2],
    "sdm_unconnected_port": [0, 1],
}
SDTOP_OP_SEEDS = {
    "sdtop_sizing_out_of_spec": [0, 1, 2],
    "sdtop_open_net": [0, 1],
}
TIER1_ANALOG_FAULTS = ["mute", "rin_hi", "rin_lo", "rin_open"]


def _sinc3_model(bits, osr):
    """Golden model with the RTL's exact sampling convention (copied
    verbatim from the vendored cocotb TB test_sdm_rx.py via
    tests/validate/test_mixed.py — the independent oracle)."""
    i1 = i2 = i3 = 0
    z1 = z2 = z3 = 0
    cnt = 0
    out = []
    for b in bits:
        d = 1 if b else -1
        i3_old, c1 = i3, i3 - z1
        c2 = c1 - z2
        c3 = c2 - z3
        i1, i2, i3 = i1 + d, i2 + i1, i3 + i2
        if cnt == osr - 1:
            cnt = 0
            z1, z2, z3 = i3_old, c1, c2
            out.append(_sign32(c3))
        else:
            cnt += 1
    return out


def _sign32(v):
    v &= 0xFFFFFFFF
    return v - (1 << 32) if v & 0x80000000 else v


def _require_fixture(*paths):
    missing = [p for p in paths if not p.is_file()]
    if missing:
        pytest.skip(
            "SEAM-COSIM live: ttsky-sigma-delta fixture not fetched "
            "(scripts/fetch_fixtures.py)"
        )


def _require_ngspice():
    if shutil.which("ngspice") is None:
        pytest.skip("SEAM-COSIM live: ngspice not on PATH (B10 tooling)")


def _require_icarus():
    if shutil.which("iverilog") is None or shutil.which("vvp") is None:
        pytest.skip(
            "SEAM-COSIM live: iverilog/vvp not on PATH "
            "(PATH=$HOME/tools/oss-cad-suite/bin:$HOME/tools/bin:$PATH)"
        )


def _require_xschem():
    if shutil.which("xschem") is None:
        pytest.skip("SEAM-COSIM live: xschem not on PATH (B10 tooling)")


def _require_pex_live():
    _require_ngspice()
    _require_icarus()
    if os.environ.get("COSIM_PEX_LIVE") != "1":
        pytest.skip(
            "SEAM-COSIM PEX-tier: set COSIM_PEX_LIVE=1 to run the ~11 min "
            "extracted-top joint proof (see docs/work/SEAM-COSIM/report.md)"
        )


def _require_pex_matrix():
    _require_pex_live()
    if os.environ.get("COSIM_PEX_MATRIX") != "1":
        pytest.skip(
            "SEAM-COSIM PEX matrix: set COSIM_PEX_MATRIX=1 to run the "
            "~1.5 h sdtop_* joint-flip matrix (report § PEX-tier evidence)"
        )


def _require_wiring():
    from rocket_engine.composition import Engine  # RED-adjacent: unwired tree

    engine = Engine("cosim_wiring_probe", actor="cosim")
    if "run_cosim" not in engine._solvers:
        pytest.skip("SEAM-COSIM wiring not applied yet")


def _require_pdk():
    try:
        from rocket_engine.interfaces.paths import slugify
        from rocket_engine.interfaces.pdks import list_pdks, resolve_deck
    except Exception as exc:
        pytest.skip(f"SEAM-COSIM PEX live: pdk store unavailable ({exc})")
    try:
        entries = list_pdks()
    except Exception as exc:
        pytest.skip(f"SEAM-COSIM PEX live: PDK store unreadable ({exc})")
    cands = [e for e in entries
             if slugify(e.get("id") or "") == "sky130a"]
    if not cands:
        pytest.skip(
            "SEAM-COSIM PEX live: sky130 PDK not registered "
            "(scripts/install.sh --install registers it)"
        )
    entry = sorted(cands, key=lambda e: e["revision"])[0]
    try:
        resolve_deck(
            entry["id"], entry["revision"], "libs.tech/combined/sky130.lib.spice"
        )
    except Exception as exc:
        pytest.skip(f"SEAM-COSIM PEX live: sky130 model lib unresolvable ({exc})")
    return entry


def _tool_versions():
    versions = {}
    for binary in ("ngspice", "iverilog", "vvp", "xschem"):
        found = shutil.which(binary)
        versions[binary] = found or "absent"
        if found:
            flag = "--version" if binary == "ngspice" else "-V"
            if binary == "xschem":
                flag = "-v"
            try:
                proc = subprocess.run(
                    [binary, flag], capture_output=True, text=True, timeout=30
                )
                versions[binary] = (proc.stdout + proc.stderr).splitlines()[0][:120]
            except Exception:
                pass
    return versions


def _verdict_of(parsed):
    return "FAIL" if any(v.get("severity") == "error"
                         for v in parsed.get("violations", [])) else "PASS"


def _canon_findings(findings):
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


def _fixture_pin():
    note = ROOT / "fixtures" / "upstream" / "ttsky-sigma-delta.md"
    rev = None
    if note.is_file():
        for line in note.read_text().splitlines():
            if "pinned rev:" in line:
                rev = line.split("`")[1]
    head = None
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=SIGMA,
    )
    if proc.returncode == 0:
        head = proc.stdout.strip()
    return rev, head


def _write_artifacts(case, job, native, parsed, mutation):
    from rocket_engine.adapters.cosim import build_run_record  # RED: missing

    case_dir = ARTIFACTS / case
    case_dir.mkdir(parents=True, exist_ok=True)
    verdict = {"status": _verdict_of(parsed),
               "finding_counts": {"error": parsed["total"]}}
    (case_dir / "verdict.json").write_text(
        json.dumps({"verdict": verdict, "findings": parsed["violations"]},
                   indent=2, sort_keys=True) + "\n"
    )
    analog = native.get("analog") or {}
    digital = native.get("digital") or {}
    compile_block = digital.get("compile") or {}
    run_block = digital.get("run") or {}
    (case_dir / "native.log").write_text(
        "=== analog deck ===\n" + (analog.get("deck") or "")
        + "\n=== analog stdout ===\n" + (analog.get("stdout") or "")
        + "\n=== analog stderr ===\n" + (analog.get("stderr") or "")
        + "\n=== analog log ===\n" + (analog.get("log") or "")
        + "\n=== digital compile stdout ===\n"
        + compile_block.get("stdout", "")
        + "\n=== digital compile stderr ===\n"
        + compile_block.get("stderr", "")
        + "\n=== digital run stdout ===\n" + run_block.get("stdout", "")
        + "\n=== digital run stderr ===\n" + run_block.get("stderr", "")
    )
    pinned, head = _fixture_pin()
    record = build_run_record(
        case, "sd_top+sdm_rx", job, native, parsed, mutation=mutation,
        versions=_tool_versions(),
        extra={"fixture": {"pinned_rev": pinned, "actual_head": head}})
    (case_dir / "run_record.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n"
    )
    return case_dir


def _tier1_case(tmp_path, name, operator=None, seed=0, fault=None):
    """Stage and run one tier-1 joint case; return (job, native, parsed)."""
    from rocket_engine.adapters.cosim import CosimAdapter  # RED: missing

    _require_fixture(SDM_RX, TIER1_SCH)
    _require_ngspice()
    _require_icarus()
    _require_xschem()
    workdir = tmp_path / name
    stage_dir = workdir / "stage"
    overrides = None
    lift_rin = False
    if fault == "mute":
        overrides = {"AMP": 0}
    elif fault == "rin_hi":
        overrides = {"RIN": 38280}
    elif fault == "rin_lo":
        overrides = {"RIN": 514800}
    elif fault == "rin_open":
        lift_rin = True
    body = stage_tier1_body(stage_dir, SIGMA, workdir,
                            param_overrides=overrides, lift_rin=lift_rin)
    digital = stage_cosim_digital(workdir / "dith", ROOT, operator, seed)
    if fault is not None and operator is not None:
        raise AssertionError("one half mutates at a time")
    job = tier1_job(workdir, body, digital)
    assert job["analog"]["nbits"] == TIER1_NBITS
    assert job["analog"]["nsettle"] == TIER1_NSETTLE
    assert job["analog"]["sig_bin"] == TIER1_SIG_BIN
    native = CosimAdapter().execute(job)
    parsed = CosimAdapter().parse(native)
    return job, native, parsed


def _pex_case(tmp_path, name, operator=None, seed=0):
    """Stage and run one PEX-tier joint case; return (job, native, parsed)."""
    from rocket_engine.adapters.cosim import CosimAdapter  # RED: missing
    from rocket_engine.mutate import (OPERATORS, apply_operator,
                                      copy_base_files, stage_design_extras)

    _require_fixture(SDM_RX, PEX)
    _require_pex_live()
    pdk_entry = _require_pdk()
    workdir = tmp_path / name
    stage_dir = workdir / "stage"
    if operator is None:
        entry = next(item for item in OPERATORS.values()
                     if item.get("design") == "sd_top")
        copy_base_files(entry, ROOT / entry["base"], stage_dir)
    else:
        entry = OPERATORS[operator]
        apply_operator(operator, stage_dir, seed, ROOT / entry["base"])
    # Shipped sd_top extras clamp the X99 startup FET on the staged
    # copy; the DC wrapper it also stages stays off the source list —
    # the cosim wrapper below carries the top_tb.py sine stimuli.
    stage_design_extras("sd_top", stage_dir, ROOT)
    wrapper = stage_pex_wrapper(stage_dir, PEX_NBITS, PEX_SIG_BIN)
    analog_sources = [str(stage_dir / "sd_top_pex.spice"), wrapper]
    digital = stage_cosim_digital(workdir / "dith", ROOT)
    job = pex_job(workdir, analog_sources, digital, pdk_entry)
    assert job["analog"]["nbits"] == PEX_NBITS
    assert job["analog"]["nsettle"] == PEX_NSETTLE
    assert job["analog"]["sig_bin"] == PEX_SIG_BIN
    native = CosimAdapter().execute(job)
    parsed = CosimAdapter().parse(native)
    return job, native, parsed


def _op_params(table):
    return [(op, seed) for op, seeds in table.items() for seed in seeds]


def test_tier1_good_joint_passes_in_documented_band(tmp_path):
    _require_fixture(SDM_RX, TIER1_SCH)
    job, native, parsed = _tier1_case(tmp_path, "good")
    assert _verdict_of(parsed) == "PASS", parsed["violations"]
    assert SNDR_TIER1_LO <= native["sndr_db"] <= SNDR_TIER1_HI, native["sndr_db"]
    assert ONES_MIN <= native["ones_density"] <= ONES_MAX
    assert len(native["bits"]) == TIER1_NBITS
    assert len(job["analog_sources"]) == 1
    by_name = {m["name"]: m for m in parsed["measurements"]}
    assert by_name["sndr_fast_db"]["margin"] > 0
    text = native["digital"]["run"]["stdout"]
    assert "COSIM_PASS" in text
    assert f"COSIM_BITS {TIER1_NBITS} {sum(native['bits'])}" in text
    assert f"COSIM_COUNT_FAST {TIER1_NBITS // OSR_FAST}" in text
    assert f"COSIM_COUNT_PREC {TIER1_NBITS // OSR_PREC}" in text
    model_fast = _sinc3_model(native["bits"], OSR_FAST)[-1]
    model_prec = _sinc3_model(native["bits"], OSR_PREC)[-1]
    assert f"COSIM_DATA_FAST {model_fast}" in text
    assert f"COSIM_DATA_PREC {model_prec}" in text


@pytest.mark.parametrize("operator,seed", _op_params(SDM_OP_SEEDS))
def test_tier1_sdm_mutant_flips_only_assert_fatal(operator, seed, tmp_path):
    _, _, parsed = _tier1_case(tmp_path, f"{operator}-{seed}", operator, seed)
    assert _verdict_of(parsed) == "FAIL", (operator, seed)
    errors = [v for v in parsed["violations"] if v["severity"] == "error"]
    assert errors, (operator, seed)
    assert {v["rule"] for v in errors} == {"assert_fatal"}, (operator, seed)


def test_tier1_mute_flips_only_measurement(tmp_path):
    _, native, parsed = _tier1_case(tmp_path, "mute", fault="mute")
    assert _verdict_of(parsed) == "FAIL", native["sndr_db"]
    errors = [v for v in parsed["violations"] if v["severity"] == "error"]
    assert {v["rule"] for v in errors} == {"measurement"}
    assert any("sndr_fast_db" in v["message"] for v in errors)
    assert ONES_MIN <= native["ones_density"] <= ONES_MAX


@pytest.mark.parametrize("fault", ["rin_hi", "rin_lo", "rin_open"])
def test_tier1_rin_fault_class_flips_only_measurement(fault, tmp_path):
    _, native, parsed = _tier1_case(tmp_path, fault, fault=fault)
    assert _verdict_of(parsed) == "FAIL", (fault, native["sndr_db"])
    errors = [v for v in parsed["violations"] if v["severity"] == "error"]
    assert {v["rule"] for v in errors} == {"measurement"}, (fault, errors)


def test_tier1_determinism_3x(tmp_path):
    cases = [("good", None, None, None)]
    cases += [(op, op, seed, None) for op, seed in _op_params(SDM_OP_SEEDS)]
    cases += [("mute", None, None, "mute")]
    for name, operator, seed, fault in cases:
        seen = []
        for rep in range(3):
            _, native, parsed = _tier1_case(
                tmp_path, f"{name}-{seed}-{rep}",
                operator, seed or 0, fault)
            seen.append((_verdict_of(parsed),
                         _canon_findings(parsed["violations"]),
                         native["sndr_db"], list(native["bits"])))
        assert seen[0] == seen[1] == seen[2], (name, seed, fault)
        want = "PASS" if operator is None and fault is None else "FAIL"
        assert seen[0][0] == want, (name, seed, fault)


def test_tier1_failure_artifacts_keep_i28_both_halves(tmp_path):
    from rocket_engine.adapters.cosim import build_run_record  # RED: missing

    digital_probe = stage_cosim_digital(tmp_path / "probe", ROOT)
    assert digital_probe["mutation"] is None
    job, native, parsed = _tier1_case(tmp_path, "art", fault="mute")
    assert _verdict_of(parsed) == "FAIL"
    mutation = {"operator": "tier1_mute", "domain": "analog",
                "operation": "run_cosim", "seed": 0,
                "target_file": "tier1_cosim.spice",
                "expected_verdict": "FAIL",
                "expected_rules": ["measurement"]}
    case_dir = _write_artifacts("tier1_mute-0", job, native, parsed, mutation)
    for name in ("verdict.json", "native.log", "run_record.json"):
        path = case_dir / name
        assert path.is_file(), name
        assert path.stat().st_size > 0, name
    record = json.loads((case_dir / "run_record.json").read_text())
    ingredients = record["ingredients"]
    assert ingredients["analog"]["solver"] == "ngspice"
    assert ingredients["digital"]["solver"] == "icarus"
    assert ingredients["analog"]["pdk"] is None
    assert len(ingredients["analog"]["sources"]) == 1
    assert len(ingredients["digital"]["sources"]) == 2
    assert ingredients["vector"]["name"] == "cosim_bits.txt"
    assert len(ingredients["sampled_bits"]["sha256"]) == 64
    assert ingredients["mutation"]["operator"] == "tier1_mute"
    assert record["results"]["total"] == 1
    assert build_run_record is not None


def test_pex_good_joint_passes_in_extracted_band(tmp_path):
    _require_fixture(SDM_RX, PEX)
    job, native, parsed = _pex_case(tmp_path, "good")
    assert _verdict_of(parsed) == "PASS", parsed["violations"]
    assert SNDR_PEX_LO <= native["sndr_db"] <= SNDR_PEX_HI, native["sndr_db"]
    assert ONES_MIN <= native["ones_density"] <= ONES_MAX
    assert len(native["bits"]) == PEX_NBITS
    text = native["digital"]["run"]["stdout"]
    assert "COSIM_PASS" in text
    assert f"COSIM_BITS {PEX_NBITS} {sum(native['bits'])}" in text
    model_fast = _sinc3_model(native["bits"], OSR_FAST)[-1]
    model_prec = _sinc3_model(native["bits"], OSR_PREC)[-1]
    assert f"COSIM_DATA_FAST {model_fast}" in text
    assert f"COSIM_DATA_PREC {model_prec}" in text
    case_dir = _write_artifacts("pex_good", job, native, parsed, None)
    assert (case_dir / "run_record.json").is_file()


@pytest.mark.parametrize("operator,seed", _op_params(SDTOP_OP_SEEDS))
def test_pex_sdtop_mutant_flips_only_measurement(operator, seed, tmp_path):
    _require_pex_matrix()
    _, _, parsed = _pex_case(tmp_path, f"{operator}-{seed}", operator, seed)
    assert _verdict_of(parsed) == "FAIL", (operator, seed)
    errors = [v for v in parsed["violations"] if v["severity"] == "error"]
    assert errors, (operator, seed)
    assert {v["rule"] for v in errors} == {"measurement"}, (operator, seed)


def test_pex_determinism_3x_good(tmp_path):
    _require_pex_matrix()
    seen = []
    for rep in range(3):
        _, native, parsed = _pex_case(tmp_path, f"good-{rep}")
        seen.append((_verdict_of(parsed),
                     _canon_findings(parsed["violations"]),
                     native["sndr_db"], list(native["bits"])))
    assert seen[0] == seen[1] == seen[2]
    assert seen[0][0] == "PASS"


def test_wired_run_cosim_through_engine_tier1(tmp_path):
    from rocket_engine.adapters.cosim import CosimAdapter  # RED: missing
    from rocket_engine.composition import Engine

    _require_wiring()
    _require_fixture(SDM_RX, TIER1_SCH)
    _require_ngspice()
    _require_icarus()
    _require_xschem()
    assert CosimAdapter is not None
    workdir = tmp_path / "wired"
    body = stage_tier1_body(workdir / "stage", SIGMA, workdir)
    digital = stage_cosim_digital(workdir / "dith", ROOT)
    job = tier1_job(workdir, body, digital)
    engine = Engine("cosim_wired", actor="cosim")
    out = engine.run({"project_id": "cosim_wired", "operation": "run_cosim",
                      "arguments": job})
    assert out["verdict"]["status"] == "PASS", out["verdict"]
    assert engine.findings(out["run_id"])["findings"] == []
    names = {m["name"] for m in out["verdict"]["measurements"]}
    assert {"sndr_fast_db", "ones_density"} <= names


def test_wired_capabilities_report_cosim_ready():
    from rocket_engine.composition import Engine

    _require_wiring()
    report = Engine("cosim_caps", actor="cosim").capabilities()
    state = report["operations"]["run_cosim"]["readiness"]
    assert state in ("ready", "blocked")
    if shutil.which("ngspice") is not None and shutil.which("iverilog") is not None:
        assert state == "ready", report["operations"]["run_cosim"]


def test_wired_job_kinds_list_cosim_tool():
    from rocket_engine.composition import Engine

    _require_wiring()
    kinds = {entry["operation"]: entry["tools"]
             for entry in Engine("cosim_kinds", actor="cosim").job_kinds()["job_kinds"]}
    assert kinds["run_cosim"] == ["cosim"]
