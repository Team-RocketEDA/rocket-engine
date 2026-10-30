"""HTML correctness-gate report — RED.

Proves scripts/correctness_report.py renders gate counts,
intended-vs-actual columns, and case artifact links from a small
fixture report.json. Fails until the generator script exists.
"""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GEN = ROOT / "scripts" / "correctness_report.py"


def load_gen():
    spec = importlib.util.spec_from_file_location(
        "correctness_report_under_test", GEN
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fixture(tmp_path):
    cases_dir = tmp_path / "cases"
    bad = cases_dir / "serv_reset_break-0"
    bad.mkdir(parents=True)
    (bad / "verdict.json").write_text(
        json.dumps({"verdict": {"status": "FAIL"}}) + "\n"
    )
    (bad / "native.log").write_text(
        "=== compile stdout ===\nMONITOR TIMEOUT: reset stuck low\n"
    )
    report = {
        "verdict": "FAIL",
        "flows": {
            "digital": {
                "verdict": "FAIL",
                "cases": [
                    {
                        "case": "serv-good",
                        "flow": "digital",
                        "design": "serv",
                        "kind": "good",
                        "status": "pass",
                    },
                    {
                        "case": "serv_reset_break-0",
                        "flow": "digital",
                        "design": "serv",
                        "kind": "mutant",
                        "status": "fail",
                        "expected": "FAIL(sim_fail)",
                        "got": "PASS",
                        "artifacts": str(bad),
                    },
                ],
            },
            "photonic": {
                "verdict": "FAIL:blocked-env",
                "cases": [
                    {
                        "case": "mzi-optical-good",
                        "flow": "photonic",
                        "design": "mzi",
                        "kind": "good",
                        "status": "quarantined",
                        "reason": "sax not installed",
                        "ref": "B10-owned tooling",
                    },
                ],
            },
        },
        "totals": {
            "flows": 2,
            "flows_pass": 0,
            "cases": 3,
            "cases_pass": 1,
            "cases_fail": 1,
            "cases_quarantined": 1,
        },
        "failed_cases": [
            {
                "case": "serv_reset_break-0",
                "flow": "digital",
                "design": "serv",
                "kind": "mutant",
                "status": "fail",
                "expected": "FAIL(sim_fail)",
                "got": "PASS",
                "artifacts": str(bad),
            },
        ],
        "quarantines": [],
        "artifacts_dir": str(cases_dir),
    }
    report_json = tmp_path / "report.json"
    report_json.write_text(json.dumps(report, indent=2) + "\n")
    return report_json


def test_report_renders_counts_banner(tmp_path):
    mod = load_gen()
    report_json = _fixture(tmp_path)
    html = mod.render_html(
        json.loads(report_json.read_text()), tmp_path / "cases"
    )
    assert "GATE FAIL" in html
    assert "serv-good" in html
    # Suite counts are visible as text, not color alone.
    assert "1 pass" in html and "1 fail" in html and "1 quarantined" in html


def test_report_renders_intended_vs_actual_columns(tmp_path):
    mod = load_gen()
    report_json = _fixture(tmp_path)
    html = mod.render_html(
        json.loads(report_json.read_text()), tmp_path / "cases"
    )
    assert "Intended" in html and "Actual" in html
    # Good case intends PASS; broken mutant intends FAIL but got PASS.
    assert "FAIL(sim_fail)" in html
    assert "<td>PASS</td>" in html


def test_report_links_case_artifacts_and_failure_excerpt(tmp_path):
    mod = load_gen()
    report_json = _fixture(tmp_path)
    out = tmp_path / "report.html"
    mod.write_html_report(report_json, out)
    html = out.read_text()
    assert "serv_reset_break-0/verdict.json" in html
    assert "serv_reset_break-0/native.log" in html
    assert "MONITOR TIMEOUT" in html
    # Accessible table wiring survives: caption + scoped headers.
    assert "<caption>" in html and 'scope="col"' in html
