"""I28 replay-reproduces-verdicts (INVARIANT-PARTIALS, F4).

Replaying a recorded run must reproduce verdicts, findings, and
measurements; native output bytes may differ (run-replay law).
"""

from rocket_engine.adapters.cosim import build_run_record
from rocket_engine.execution.service import ExecutionService

PASS_FINDINGS = (
    "findings:\n"
    "  - {rule: snr_floor, severity: warning, detail: margin 2 dB}\n"
    "  - {rule: lint_clean, severity: info}\n"
)
FAIL_FINDINGS = (
    "findings:\n"
    "  - {rule: snr_floor, severity: error, detail: below floor}\n"
    "  - {rule: lint_clean, severity: info}\n"
)


def _evaluated(findings_text, exit_code, run_id):
    service = ExecutionService("replay_probe")
    service.dispatch("run_syntax", "top", "snap-1", run_id=run_id)
    verdict = service.evaluate(run_id, exit_code, findings_text)
    return service, verdict


def test_replay_reproduces_verdict_and_findings():
    for findings_text, status in (
        (PASS_FINDINGS, "PASS"),
        (FAIL_FINDINGS, "FAIL"),
    ):
        original, verdict = _evaluated(findings_text, 0, "run-orig")
        assert verdict["status"] == status
        replayed, replay_verdict = _evaluated(findings_text, 137, "run-replay")
        assert replay_verdict == verdict
        assert replayed.findings("run-replay") == original.findings("run-orig")


def test_replay_detects_changed_findings():
    original, verdict = _evaluated(PASS_FINDINGS, 0, "run-orig")
    assert verdict["status"] == "PASS"
    replayed, replay_verdict = _evaluated(FAIL_FINDINGS, 0, "run-replay")
    assert replay_verdict["status"] == "FAIL"
    assert replay_verdict != verdict
    assert (
        replayed.findings("run-replay")["total_counts"]
        != original.findings("run-orig")["total_counts"]
    )


def test_run_record_replay_reproduces_results(tmp_path):
    analog = tmp_path / "bench.spice"
    analog.write_text("* bench\n")
    digital = tmp_path / "rx.v"
    digital.write_text("module rx; endmodule\n")
    job = {
        "analog_sources": [str(analog)],
        "digital_sources": [str(digital)],
        "analog": {"clock_hz": 1000000.0},
    }
    native = {
        "analog": {"deck": "* deck\n"},
        "bits": [0, 1, 1, 0],
        "vector_name": "vector.txt",
    }
    parsed = {
        "violations": [{"rule": "snr", "severity": "warning"}],
        "total": 1,
        "measurements": [{"name": "sndr_db", "value": 37.1}],
    }
    versions = {"ngspice": "ngspice-42", "iverilog": "iv-12", "vvp": "vvp-12"}
    first = build_run_record("case", "design", job, native, parsed,
                             versions=versions)
    replay = build_run_record("case", "design", job, native, parsed,
                              versions=versions)
    assert replay["results"] == first["results"]
    assert replay["ingredients"] == first["ingredients"]
    mutated = build_run_record(
        "case", "design", job, native,
        {"violations": [{"rule": "snr", "severity": "error"}],
         "total": 1,
         "measurements": [{"name": "sndr_db", "value": 12.0}]},
        versions=versions,
    )
    assert mutated["results"]["verdict"] == "FAIL"
    assert mutated["results"] != first["results"]
