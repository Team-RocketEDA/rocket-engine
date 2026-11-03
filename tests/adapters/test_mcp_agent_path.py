"""MCP agent path: an agent can run a job over MCP and read its result.

Consolidated semantic (merge/fuel-mcp): submit admits (queued; the ack
run_id is the execution id), explicit run_job executes, and the job
queries read the result back. Nothing runs implicitly. Uses the real
Engine with a stand-in run_spice solver whose execute() fakes ngspice
output; verdicts come from the real NgspiceAdapter.parse().
"""

import asyncio
import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent

PROJECT = "opamp_demo"
GAIN = {"name": "dc_gain_db", "expr": "vdb(out)[0]", "unit": "dB"}
CONSTRAINTS = {"dc_gain_db": {"min": 60.0, "unit": "dB"}}


class StandInSpice:
    """Fakes only the ngspice process; parsing is the real adapter's."""

    def __init__(self, values):
        self.values = values

    def preflight(self, job):
        return job

    def execute(self, job):
        lines = ["ngspice-44 (stand-in)", "Circuit: opamp"]
        lines += [f"meas_{name} = {value}" for name, value in self.values.items()]
        return {
            "exit_code": 0, "stdout": "", "stderr": "", "log": "\n".join(lines),
            "sources": job.get("sources", []), "measurements": job["measurements"],
        }

    def parse(self, native):
        from rocket_engine.adapters.ngspice import NgspiceAdapter

        return NgspiceAdapter().parse(native)


def _engine(values, constraints=None):
    from rocket_engine.composition import Engine

    engine = Engine(PROJECT, actor="mcp", constraints=constraints)
    engine.register_solver("run_spice", StandInSpice(values), tool="ngspice")
    return engine


def _submit(engine, name, arguments, request_id="r1"):
    return engine.submit({"project_id": PROJECT, "operation": name,
                          "arguments": arguments, "request_id": request_id})


def _query(engine, name, **arguments):
    return engine.submit({"project_id": PROJECT, "operation": name, "arguments": arguments})


def _run_job(engine, run_id):
    return engine.submit({"project_id": PROJECT, "operation": "run_job",
                          "arguments": {"run_id": run_id}})


def test_submitted_job_runs_under_the_same_run_id():
    engine = _engine({"dc_gain_db": 52.0})
    ack = _submit(engine, "run_spice", {"expected_revision": "p12", "measurements": [dict(GAIN, min=60)]})
    assert ack["state"] == "completed"
    assert ack["verdict"]["status"] == "FAIL"

    done = _run_job(engine, ack["run_id"])
    assert done["run_id"] == ack["run_id"]
    assert done["verdict"]["status"] == "FAIL"
    status = _query(engine, "get_job_status", run_id=ack["run_id"])
    assert status["state"] == "completed"
    assert status["verdict"]["status"] == "FAIL"


def test_submit_leaves_job_queued_until_explicit_run_job():
    # Submit-immediate: submit executes inline; queries never execute.
    # (Historical name: submit used to queue until run_job.)
    engine = _engine({"dc_gain_db": 52.0})
    ack = _submit(engine, "run_spice", {"expected_revision": "p12", "measurements": [dict(GAIN, min=60)]})
    assert ack["state"] == "completed"
    status = _query(engine, "get_job_status", run_id=ack["run_id"])
    assert status["state"] == "completed" and status["verdict"]["status"] == "FAIL"
    # An unrelated query in between still runs nothing (same verdict, no re-execution).
    _query(engine, "list_job_kinds")
    again = _query(engine, "get_job_status", run_id=ack["run_id"])
    assert again["state"] == "completed" and again["verdict"] == status["verdict"]


def test_run_job_accepts_envelope_request_id():
    # HEAD compat: run_job by the submit envelope's request_id works too,
    # and executes under the same ack run_id.
    engine = _engine({"dc_gain_db": 52.0})
    ack = _submit(engine, "run_spice", {"expected_revision": "p12", "measurements": [dict(GAIN, min=60)]},
                  request_id="req-9")
    out = engine.submit({"project_id": PROJECT, "operation": "run_job",
                         "arguments": {"request_id": "req-9"}})
    assert out["state"] == "completed" and out["run_id"] == ack["run_id"]
    assert out["verdict"]["status"] == "FAIL"


def test_run_job_unknown_run_id_is_clean():
    from rocket_engine.project.errors import ProjectError

    engine = _engine({})
    with pytest.raises(ProjectError) as err:
        engine.submit({"project_id": PROJECT, "operation": "run_job",
                       "arguments": {"run_id": "nope"}})
    assert err.value.code == "unknown_request"


def test_measurements_survive_a_pass():
    engine = _engine({"dc_gain_db": 62.5})
    ack = _submit(engine, "run_spice", {"expected_revision": "p12", "measurements": [dict(GAIN, min=60)]})
    _run_job(engine, ack["run_id"])
    verdict = _query(engine, "get_job_status", run_id=ack["run_id"])["verdict"]
    assert verdict["status"] == "PASS"
    assert verdict["measurements"] == [{"name": "dc_gain_db", "value": 62.5, "unit": "dB",
                                        "target": {"min": 60}, "margin": 2.5, "status": "pass"}]


def test_check_results_logs_and_job_kinds_are_wired():
    engine = _engine({"dc_gain_db": 52.0})
    ack = _submit(engine, "run_spice", {"expected_revision": "p12", "measurements": [dict(GAIN, min=60)]})
    _run_job(engine, ack["run_id"])

    results = _query(engine, "get_check_results")
    assert results["checks"]["run_spice"]["run_id"] == ack["run_id"]
    assert results["checks"]["run_spice"]["status"] == "FAIL"

    logs = _query(engine, "get_logs", run_id=ack["run_id"], query="meas_")
    assert logs["lines"] == ["3: meas_dc_gain_db = 52.0"]
    assert logs["total_lines"] == 3

    kinds = _query(engine, "list_job_kinds")
    assert {"operation": "run_spice", "tools": ["ngspice"]} in kinds["job_kinds"]


def test_unknown_run_is_a_clean_error():
    from rocket_engine.execution.errors import ExecutionError

    engine = _engine({})
    with pytest.raises(ExecutionError) as err:
        _query(engine, "get_job_status", run_id="nope")
    assert err.value.code == "unknown_run"


def test_targets_come_from_constraints_not_the_caller():
    from rocket_engine.project.errors import ProjectError

    engine = _engine({"dc_gain_db": 52.0}, constraints=CONSTRAINTS)
    with pytest.raises(ProjectError) as err:
        _submit(engine, "run_spice", {"expected_revision": "p12", "measurements": [dict(GAIN, min=40)]})
    assert err.value.code == "invalid_command"
    assert "constraints" in str(err.value)

    ack = _submit(engine, "run_spice", {"expected_revision": "p12", "measurements": [GAIN]}, request_id="r2")
    _run_job(engine, ack["run_id"])
    verdict = _query(engine, "get_job_status", run_id=ack["run_id"])["verdict"]
    assert verdict["status"] == "FAIL"
    assert verdict["measurements"][0]["target"] == {"min": 60.0}


def test_a_crashing_solver_is_not_run_not_a_crash():
    class Boom(StandInSpice):
        def execute(self, job):
            raise RuntimeError("solver exploded")

    from rocket_engine.composition import Engine

    engine = Engine(PROJECT, actor="mcp")
    engine.register_solver("run_spice", Boom({}), tool="ngspice")
    ack = _submit(engine, "run_spice", {"expected_revision": "p12", "measurements": [dict(GAIN, min=60)]})
    _run_job(engine, ack["run_id"])
    verdict = _query(engine, "get_job_status", run_id=ack["run_id"])["verdict"]
    assert verdict["status"] == "NOT_RUN"
    assert "solver exploded" in verdict["reason"]


# --- MCP server: bound project, argument schemas, clean errors ---------------

def _call(handler, name, arguments):
    from mcp.types import CallToolRequestParams

    result = asyncio.run(handler(None, CallToolRequestParams(name=name, arguments=arguments)))
    return result, json.loads(result.content[0].text)


def test_tools_stay_generated_not_handwritten():
    # MCP-SCHEMA: wire schemas come from the api_spec generator
    # (docstrings) — real per-op schemas, still no hand-written copies.
    from rocket_engine.adapters.mcp.server import tool_definitions
    from rocket_engine.interfaces.vocabulary import OPERATIONS, QUERIES

    tools = {tool.name: tool for tool in tool_definitions()}
    assert set(OPERATIONS) <= set(tools) and set(QUERIES) <= set(tools)
    entry = json.loads((ROOT / "docs" / "api-schema.json").read_text())
    entry = entry["operations"]["run_spice"]
    assert tools["run_spice"].input_schema["properties"] == entry["properties"]
    assert tools["run_spice"].input_schema["required"] == entry["required"]


def test_bound_server_fills_project_and_revision_and_returns_results():
    from rocket_engine.adapters.mcp.server import make_handlers

    engine = _engine({"dc_gain_db": 62.5}, constraints=CONSTRAINTS)
    _, call = make_handlers(lambda project_id: engine, project_scope=PROJECT)

    _, ack = _call(call, "run_spice", {"measurements": [GAIN]})
    assert ack["state"] == "completed"
    _, queued = _call(call, "get_job_status", {"run_id": ack["run_id"]})
    assert queued["state"] == "completed"

    _, done = _call(call, "run_job", {"run_id": ack["run_id"]})
    assert done["state"] == "completed" and done["run_id"] == ack["run_id"]
    _, status = _call(call, "get_job_status", {"run_id": ack["run_id"]})
    assert status["state"] == "completed"
    assert status["verdict"]["status"] == "PASS"


def test_engine_errors_come_back_as_json_not_exceptions():
    from rocket_engine.adapters.mcp.server import make_handlers

    engine = _engine({})
    _, call = make_handlers(lambda project_id: engine, project_scope=PROJECT)
    result, body = _call(call, "run_spice", {"expected_revision": "p11", "measurements": [GAIN]})
    assert result.is_error is True
    assert body == {"ok": False, "code": "revision_conflict", "message": body["message"]}

    result, body = _call(call, "get_job_status", {"run_id": "nope"})
    assert result.is_error is True and body["code"] == "unknown_run"


def test_bound_server_rejects_other_projects():
    from rocket_engine.adapters.mcp.server import make_handlers

    engine = _engine({})
    _, call = make_handlers(lambda project_id: engine, project_scope=PROJECT)
    result, body = _call(call, "get_project_snapshot", {"project_id": "someone_else"})
    assert result.is_error is True and body["code"] == "cross_project_denied"


def test_constraints_yaml_becomes_targets(tmp_path):
    from rocket_engine.adapters.mcp.server import load_constraints

    (tmp_path / "constraints.yaml").write_text(
        "checks:\n"
        "  - {id: opamp.dc_gain, metric: dc_gain_db, comparison: '>=', value: 60, unit: dB}\n"
        "  - {id: opamp.power, metric: power_uw, comparison: '<=', value: 500, unit: uW}\n"
        "  - {id: opamp.note, metric: label, comparison: '==', value: 1}\n"
    )
    assert load_constraints(tmp_path) == {
        "dc_gain_db": {"min": 60, "unit": "dB"},
        "power_uw": {"max": 500, "unit": "uW"},
    }
    assert load_constraints(tmp_path / "missing") is None


def test_bound_server_keeps_files_inside_the_project(tmp_path):
    from rocket_engine.adapters.mcp.server import make_handlers

    (tmp_path / "design").mkdir()
    (tmp_path / "design" / "opamp.cir").write_text("* opamp\n")
    seen = []

    class Recording(StandInSpice):
        def execute(self, job):
            seen.append(job)
            return super().execute(job)

    from rocket_engine.composition import Engine

    engine = Engine(PROJECT, actor="mcp")
    engine.register_solver("run_spice", Recording({"dc_gain_db": 61.0}), tool="ngspice")
    _, call = make_handlers(lambda project_id: engine, project_scope=PROJECT, project_dir=tmp_path)

    _, ack = _call(call, "run_spice", {"sources": ["design/opamp.cir"], "measurements": [dict(GAIN, min=60)]})
    assert ack["state"] == "completed" and len(seen) == 1
    _, done = _call(call, "run_job", {"run_id": ack["run_id"]})
    assert done["state"] == "completed"
    assert seen[0]["sources"] == [str(tmp_path / "design" / "opamp.cir")]
    assert seen[0]["workdir"] == str(tmp_path / "results" / "engine-runs")
    assert (tmp_path / "results" / "engine-runs").is_dir()

    result, body = _call(call, "run_spice", {"sources": ["../outside.cir"], "measurements": [dict(GAIN, min=60)]})
    assert result.is_error is True and body["code"] == "invalid_reference"
    assert len(seen) == 1


# --- measurement definitions come from constraints too; live ngspice proof ---

MEASURED = {
    "dc_gain_db": {"min": 60.0, "unit": "dB", "expr": "vdb(out)[0]"},
    "ugbw_mhz": {"min": 10.0, "unit": "MHz", "expr": "ugbw_hz/1e6",
                 "control": ["meas ac ugbw_hz when vdb(out)=0"]},
}


def test_measurement_definition_comes_from_constraints():
    from rocket_engine.project.errors import ProjectError

    seen = []

    class Recording(StandInSpice):
        def execute(self, job):
            seen.append(job)
            return super().execute(job)

    from rocket_engine.composition import Engine

    engine = Engine(PROJECT, actor="mcp", constraints=MEASURED)
    engine.register_solver("run_spice", Recording({"ugbw_mhz": 33.6}), tool="ngspice")
    with pytest.raises(ProjectError) as err:
        _submit(engine, "run_spice", {"expected_revision": "p12", "analyses": ["ac dec 50 1 1e10"],
                                       "measurements": [{"name": "ugbw_mhz", "expr": "100"}]})
    assert "omit expr" in str(err.value)

    ack = _submit(engine, "run_spice", {"expected_revision": "p12", "analyses": ["ac dec 50 1 1e10"],
                                   "measurements": [{"name": "ugbw_mhz"}]}, request_id="r2")
    _run_job(engine, ack["run_id"])
    assert seen[0]["measurements"] == [{"name": "ugbw_mhz", "expr": "ugbw_hz/1e6", "min": 10.0, "unit": "MHz"}]
    assert seen[0]["analyses"] == ["ac dec 50 1 1e10", "meas ac ugbw_hz when vdb(out)=0"]


def test_constraints_yaml_carries_measurement_definitions(tmp_path):
    from rocket_engine.adapters.mcp.server import load_constraints

    (tmp_path / "constraints.yaml").write_text(
        "checks:\n"
        "  - metric: ugbw_mhz\n"
        "    comparison: '>='\n"
        "    value: 10\n"
        "    unit: MHz\n"
        "    expr: ugbw_hz/1e6\n"
        "    control: ['meas ac ugbw_hz when vdb(out)=0']\n"
    )
    assert load_constraints(tmp_path) == {"ugbw_mhz": MEASURED["ugbw_mhz"] | {"min": 10}}


OPAMP = """* Two-stage Miller op-amp, generic 1.8 V level-1 models (demo only, not a foundry PDK)
* L2 = second-stage channel length (um); CC = Miller compensation (pF)
.param L2=0.5
.param CC=1.0
.model nch nmos level=1 vto=0.45 kp=250u lambda=0.2
.model pch pmos level=1 vto=-0.45 kp=100u lambda=0.2
* channel-length modulation falls as L grows, so a longer second stage has higher gain
.model nch2 nmos level=1 vto=0.45 kp=250u lambda={0.08/L2}
.model pch2 pmos level=1 vto=-0.45 kp=100u lambda={0.08/L2}
.subckt opamp inp inn out vdd vss bias
M1 n1 inn tail vss nch W=4u L=1u
M2 n2 inp tail vss nch W=4u L=1u
M3 n1 n1 vdd vdd pch W=8u L=1u
M4 n2 n1 vdd vdd pch W=8u L=1u
M5 tail bias vss vss nch W=4u L=1u
M6 out n2 vdd vdd pch2 W={40*L2*1e-6} L={L2*1e-6}
M7 out bias vss vss nch2 W={20*L2*1e-6} L={L2*1e-6}
CC n2 out {CC*1e-12}
.ends opamp
"""
TESTBENCH = """* Open-loop AC testbench: 1 GOhm / 1 F keeps the DC point closed-loop, AC open-loop
VDD vdd 0 1.8
VBIAS bias 0 0.75
VCM inp 0 0.9 AC 1
RF out inn 1G
CF inn 0 1
CL out 0 2p
XOA inp inn out vdd 0 bias opamp
"""


@pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice not on PATH")
def test_live_ngspice_opamp_over_bound_server(tmp_path):
    from rocket_engine.adapters.mcp.server import make_handlers
    from rocket_engine.composition import Engine

    (tmp_path / "design").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "design" / "opamp.cir").write_text(OPAMP)
    (tmp_path / "tests" / "tb_opamp.cir").write_text(TESTBENCH)
    engine = Engine(PROJECT, actor="mcp", constraints=MEASURED)
    _, call = make_handlers(lambda project_id: engine, project_scope=PROJECT, project_dir=tmp_path)

    _, ack = _call(call, "run_spice", {
        "sources": ["design/opamp.cir", "tests/tb_opamp.cir"], "analyses": ["ac dec 50 1 1e10"],
        "measurements": [{"name": "dc_gain_db"}, {"name": "ugbw_mhz"}],
    })
    _, done = _call(call, "run_job", {"run_id": ack["run_id"]})
    assert done["state"] == "completed"
    _, status = _call(call, "get_job_status", {"run_id": ack["run_id"]})
    verdict = status["verdict"]
    assert verdict["status"] == "FAIL"
    measured = {m["name"]: m for m in verdict["measurements"]}
    assert measured["dc_gain_db"]["status"] == "fail" and 55 < measured["dc_gain_db"]["value"] < 57
    assert measured["ugbw_mhz"]["status"] == "pass" and measured["ugbw_mhz"]["value"] > 10
    _, logs = _call(call, "get_logs", {"run_id": ack["run_id"], "query": "meas_dc_gain_db"})
    assert logs["matched"] >= 1


def test_bound_server_writes_evidence_into_the_project(tmp_path):
    import subprocess

    from rocket_engine.adapters.mcp.server import make_handlers

    (tmp_path / "design").mkdir()
    (tmp_path / "design" / "opamp.cir").write_text("* opamp\n")
    git = ["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "start"], check=True)
    head = subprocess.run([*git, "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()

    engine = _engine({"dc_gain_db": 52.0})
    _, call = make_handlers(lambda project_id: engine, project_scope=PROJECT, project_dir=tmp_path)
    _, ack = _call(call, "run_spice", {"sources": ["design/opamp.cir"], "measurements": [dict(GAIN, min=60)]})

    evidence_path = tmp_path / "results" / "engine-runs" / f"{ack['run_id']}.json"
    assert not evidence_path.is_file()
    _, done = _call(call, "run_job", {"run_id": ack["run_id"]})
    assert done["state"] == "completed"

    evidence = json.loads(evidence_path.read_text())
    assert evidence["run_id"] == ack["run_id"]
    assert evidence["operation"] == "run_spice"
    assert evidence["verdict"]["status"] == "FAIL"
    assert evidence["verdict"]["measurements"][0]["value"] == 52.0
    assert evidence["source_commit"] == head and evidence["source_dirty"] is False
    assert evidence["producer"] == "rocket-engine"
    assert "meas_dc_gain_db = 52.0" in evidence["log"]
    assert evidence["finished_at"].endswith("Z")


@pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice not on PATH")
def test_one_shot_call_runs_a_job_and_writes_evidence(tmp_path, capsys):
    from rocket_engine.adapters.mcp.server import main

    (tmp_path / "design").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "design" / "opamp.cir").write_text(OPAMP)
    (tmp_path / "tests" / "tb_opamp.cir").write_text(TESTBENCH)
    (tmp_path / "constraints.yaml").write_text(
        "checks:\n"
        "  - {metric: dc_gain_db, comparison: '>=', value: 60, unit: dB, expr: 'vdb(out)[0]'}\n"
    )
    code = main(["--project", PROJECT, "--project-dir", str(tmp_path), "--call", "run_spice", "--args",
                 json.dumps({"sources": ["design/opamp.cir", "tests/tb_opamp.cir"],
                             "analyses": ["ac dec 50 1 1e10"], "measurements": [{"name": "dc_gain_db"}]})])
    assert code == 0
    status = json.loads(capsys.readouterr().out)
    assert status["state"] == "completed" and status["verdict"]["status"] == "FAIL"
    assert (tmp_path / "results" / "engine-runs" / f"{status['run_id']}.json").is_file()
    evidence = json.loads((tmp_path / "results" / "engine-runs" / f"{status['run_id']}.json").read_text())
    assert evidence["datasets"] == [
        {"analysis": "ac", "path": f"results/engine-runs/{status['run_id']}-ac.raw"}
    ]
    raw = (tmp_path / evidence["datasets"][0]["path"]).read_text()
    assert "Plotname: AC Analysis" in raw and "v(out)" in raw
    assert not list((tmp_path / "results" / "engine-runs").glob("waveforms-*.raw"))


class _EvidenceEngine:
    """Engine stand-in for write_evidence: one waveform, one spectrum."""

    def __init__(self, raw):
        self.raw = raw

    def log_text(self, run_id):
        return ""

    def datasets(self, run_id):
        return [{"analysis": "ac", "path": str(self.raw)}]

    def spectra(self, run_id):
        return [{"from": "in0", "to": "out1", "wavelength_nm": [1550.0], "transmission_db": [float("-inf")]}]


def _strict_json(text):
    def refuse(constant):
        raise AssertionError(f"not valid JSON: {constant}")

    return json.loads(text, parse_constant=refuse)


def test_evidence_keeps_waveforms_and_spectra_and_survives_a_second_fetch(tmp_path):
    from rocket_engine.adapters.mcp.server import write_evidence

    workdir = tmp_path / "results" / "engine-runs"
    workdir.mkdir(parents=True)
    raw = workdir / "waveforms-1-ac.raw"
    raw.write_text("Plotname: AC Analysis\n")
    engine = _EvidenceEngine(raw)
    outcome = {"run_id": "r1", "operation": "run_optical",
               "verdict": {"status": "PASS", "measurements": [{"name": "null_db", "value": float("-inf")}]}}

    # run_job is an idempotent fetch, so evidence can be written twice for one run.
    for _ in range(2):
        write_evidence(tmp_path, engine, [outcome], {})
        record = _strict_json((workdir / "r1.json").read_text())
        assert record["datasets"] == [
            {"analysis": "ac", "path": "results/engine-runs/r1-ac.raw"},
            {"analysis": "optical", "path": "results/engine-runs/r1-optical.json"},
        ]
    assert record["verdict"]["measurements"][0]["value"] is None
    assert (workdir / "r1-ac.raw").read_text() == "Plotname: AC Analysis\n"
    assert not raw.exists()
    spectra = _strict_json((workdir / "r1-optical.json").read_text())
    assert spectra[0]["transmission_db"] == [None]


def test_tool_replies_stay_valid_json_for_a_perfect_null(tmp_path):
    # The IDE parses the --call reply with JSON.parse, which refuses -Infinity.
    from rocket_engine.adapters.mcp.server import _finite

    assert _finite({"value": float("-inf"), "points": [1.0, float("nan")], "ok": True}) == {
        "value": None, "points": [1.0, None], "ok": True,
    }
    _strict_json(json.dumps(_finite({"a": [float("inf")]}), allow_nan=False))


def test_one_shot_optical_run_keeps_its_spectrum(tmp_path, capsys):
    pytest.importorskip("sax")
    from rocket_engine.adapters.mcp.server import main

    (tmp_path / "design").mkdir()
    spec = Path(__file__).parent / "fixtures" / "sax" / "mzi.yml"
    (tmp_path / "design" / "mzi.yml").write_text(spec.read_text())
    code = main(["--project", PROJECT, "--project-dir", str(tmp_path), "--call", "run_optical", "--args",
                 json.dumps({"sources": ["design/mzi.yml"]})])
    assert code == 0
    status = json.loads(capsys.readouterr().out)
    assert status["verdict"]["status"] == "PASS"
    evidence = json.loads((tmp_path / "results" / "engine-runs" / f"{status['run_id']}.json").read_text())
    assert evidence["datasets"] == [
        {"analysis": "optical", "path": f"results/engine-runs/{status['run_id']}-optical.json"}
    ]
    spectra = json.loads((tmp_path / evidence["datasets"][0]["path"]).read_text())
    assert spectra[0]["wavelength_nm"]
