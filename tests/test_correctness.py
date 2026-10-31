"""ENGINE-CORRECTNESS RED — single-command MVP gate, all flows.

Valid RED = `scripts/correctness.py` does not exist yet, so every
test below fails on FileNotFoundError/ImportError. The gate runs all
four flows (good + all mutations) through the engine, collects
verdicts, writes the correctness report (totals, failed cases with
artifacts, quarantined flakes with refs), and exits 0 iff 4/4 flows
green. Skip = FAIL with reason + ref (blocked-env, never hidden,
never fake-green) — the gate tells the truth about what is proven
HERE. DEMO-PATH runs this gate as its centerpiece.

Correct = per-flow good→documented PASS, mutations→expected FAIL
(validate D/A/P/M precedent); environment-blocked flows surface as
FAIL blocked-env with a ticket ref (NGSPICE-LIVE for ngspice/PKD,
B10-owned tooling for PATH/sax).
"""

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GATE = ROOT / "scripts" / "correctness.py"


def load_gate():
    # RED: scripts/correctness.py does not exist yet.
    spec = importlib.util.spec_from_file_location(
        "correctness_under_test", GATE
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


tools_present = shutil.which("iverilog") is not None and shutil.which("vvp") is not None
needs_icarus = pytest.mark.skipif(
    not tools_present,
    reason="ENGINE-CORRECTNESS live: iverilog/vvp not on PATH (B10-owned tooling)",
)


def test_gate_lists_four_flows():
    mod = load_gate()
    assert set(mod.FLOWS) == {"digital", "analog", "photonic", "mixed"}
    for flow in ("digital", "analog", "photonic", "mixed"):
        assert mod.FLOWS[flow]["designs"], flow
    assert callable(mod.main)
    assert callable(mod.run_gate)


def test_gate_exit_zero_iff_pass_unit():
    mod = load_gate()
    assert mod._gate_verdict({"digital": "PASS", "analog": "PASS",
                              "photonic": "PASS", "mixed": "PASS"}) == "PASS"
    assert mod._gate_verdict({"digital": "PASS", "analog": "FAIL",
                              "photonic": "PASS", "mixed": "PASS"}) == "FAIL"
    assert mod._gate_verdict({"digital": "PASS", "analog": "FAIL:blocked-env",
                              "photonic": "PASS", "mixed": "PASS"}) == "FAIL"


def test_gate_report_shape_on_quarantined_flow(tmp_path):
    # Analog needs ngspice + sky130 store (absent here per
    # NGSPICE-LIVE): the gate must record quarantines with refs and
    # FAIL blocked-env, never fake-green, never silently skip.
    mod = load_gate()
    report_dir = tmp_path / "correctness"
    if shutil.which("ngspice") is not None:
        pytest.skip(
            "ENGINE-CORRECTNESS quarantine: ngspice present, live path "
            "covers analog (see docs/tickets/NGSPICE-LIVE.md)"
        )
    report = mod.run_gate(ROOT, report_dir, flow="analog")
    assert report["verdict"] == "FAIL"
    assert report["flows"]["analog"]["verdict"] == "FAIL:blocked-env"
    assert (report_dir / "report.json").is_file()
    assert (report_dir / "report.md").is_file()
    totals = report["totals"]
    assert totals["flows"] == 1 and totals["flows_pass"] == 0
    assert totals["cases_quarantined"] >= 1
    assert report["failed_cases"] == []
    assert len(report["quarantines"]) == totals["cases_quarantined"]
    for entry in report["quarantines"]:
        assert entry["reason"].strip(), entry
        assert entry["ref"].strip(), entry
        assert "NGSPICE-LIVE" in entry["ref"], entry


def test_gate_quarantine_exit_code_is_one(tmp_path):
    mod = load_gate()
    if shutil.which("ngspice") is not None:
        pytest.skip(
            "ENGINE-CORRECTNESS quarantine: ngspice present (NGSPICE-LIVE)"
        )
    code = mod.main(["--flow", "analog", "--report", str(tmp_path / "rep")])
    assert code == 1


def test_gate_photonic_circuit_cases_live_or_loud(tmp_path):
    # SAX-LIVE acceptance: photonic circuit cases execute live
    # (not skipped, not quarantined) with 0 failures where sax +
    # the cspdk fixture exist; quarantined LOUDLY (reason + ref)
    # where sax is absent. Never silently skipped either way.
    mod = load_gate()
    marker = (
        ROOT / "fixtures" / "upstream" / "cspdk"
        / "tests" / "gds_ref_si340" / "mzi.gds"
    )
    if not marker.is_file():
        pytest.skip(
            "SAX-LIVE gate: cspdk fixture not fetched "
            "(scripts/fetch_fixtures.py --only cspdk)"
        )
    report = mod.run_gate(ROOT, tmp_path / "correctness", flow="photonic")
    optical = [
        case for case in report["flows"]["photonic"]["cases"]
        if "optical" in case["case"]
    ]
    assert optical, "photonic flow must enumerate optical cases"
    if importlib.util.find_spec("sax") is None:
        assert all(c["status"] == "quarantined" for c in optical), optical
        for case in optical:
            assert "sax not installed" in case["reason"], case
            assert case["ref"].strip(), case
    else:
        assert all(c["status"] == "pass" for c in optical), json.dumps(
            report, indent=2)[:2000]
        assert report["totals"]["cases_fail"] == 0


@needs_icarus
def test_gate_digital_picorv32_good_passes_tools_path(tmp_path):
    # The one flow provable HERE: picorv32 good through the engine
    # must PASS with exit 0 (subset for speed; full gate runs all).
    mod = load_gate()
    report_dir = tmp_path / "correctness"
    report = mod.run_gate(ROOT, report_dir, flow="digital",
                          design="picorv32", only_good=True)
    assert report["verdict"] == "PASS", json.dumps(report, indent=2)[:2000]
    assert report["flows"]["digital"]["verdict"] == "PASS"
    assert report["totals"]["cases_fail"] == 0
    assert report["totals"]["cases_quarantined"] == 0
    code = mod.main(["--flow", "digital", "--design", "picorv32",
                     "--only-good", "--report", str(tmp_path / "rep2")])
    assert code == 0


@needs_icarus
def test_gate_fails_on_broken_flow_fixture(tmp_path):
    # Deliberately-broken flow fixture: picorv32 good with reset
    # stuck must FAIL the gate with artifacts, exit 1.
    mod = load_gate()
    pico = ROOT / "fixtures" / "upstream" / "picorv32"
    if not (pico / "picorv32.v").is_file():
        pytest.skip(
            "ENGINE-CORRECTNESS live: picorv32 fixture not fetched "
            "(scripts/fetch_fixtures.py; docs/tickets/VALIDATE-D.md)"
        )
    broken_root = tmp_path / "root"
    dest = broken_root / "fixtures" / "upstream" / "picorv32"
    shutil.copytree(pico, dest, ignore=shutil.ignore_patterns(".git"))
    bench = dest / "testbench_ez.v"
    text = bench.read_text()
    assert "reg resetn" in text or "resetn" in text
    # Stick reset low: CPU never fetches, monitor $fatal fires.
    broken = text.replace("resetn <= 1;", "resetn <= 0; // BROKEN")
    assert broken != text
    bench.write_text(broken)
    # Gate resolves harness/monitor from --root: link the rest.
    for rel in ("tests/adapters/fixtures/hdl",
                "fixtures/upstream/serv"):
        src = ROOT / rel
        link = broken_root / rel
        link.parent.mkdir(parents=True, exist_ok=True)
        if not link.exists():
            link.symlink_to(src, target_is_directory=True)
    report_dir = tmp_path / "correctness"
    report = mod.run_gate(broken_root, report_dir, flow="digital",
                          design="picorv32", only_good=True)
    assert report["verdict"] == "FAIL"
    assert report["flows"]["digital"]["verdict"] == "FAIL"
    assert len(report["failed_cases"]) == 1
    failed = report["failed_cases"][0]
    assert failed["case"].startswith("picorv32-good"), failed
    artifacts = Path(failed["artifacts"])
    assert (artifacts / "verdict.json").is_file()
    assert (artifacts / "native.log").is_file()
    assert (artifacts / "run_record.json").is_file()
    assert (artifacts / "verdict.json").stat().st_size > 0
    code = mod.main(["--flow", "digital", "--design", "picorv32",
                     "--only-good", "--report", str(tmp_path / "rep2"),
                     "--root", str(broken_root)])
    assert code == 1
