"""Project-bound MCP server: the PDK pin comes from constraints.yaml.

A project names its PDK once (`pdk: sky130A`, or `pdk: {id, revision}`)
and every run_spice the bound server admits carries that pin, whether
the IDE's Run checks or the agent sent it. A name resolves to its one
registered revision; anything else fails before admission, never a
silent fallback to generic models.
"""

import asyncio
import json

import pytest

PROJECT = "opamp_demo"
GAIN = {"name": "dc_gain_db", "expr": "vdb(out)[0]", "unit": "dB", "min": 60}
TINY_PDK_FILES = {
    "libs.tech/combined/sky130.lib.spice": "* spice models v1\n",
    "libs.tech/klayout/drc/sky130A.lydrc": "// DRC deck v1\n",
}


@pytest.fixture
def store(tmp_path, monkeypatch):
    root = tmp_path / "rocketeda"
    monkeypatch.setenv("ROCKETEDA_HOME", str(root))
    return root


def _register(root, source, revision, pdk_id="tiny130A"):
    from rocket_engine.interfaces.pdks import register_pdk

    for rel, text in TINY_PDK_FILES.items():
        target = source / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    return register_pdk(source, pdk_id, revision, engine_root=root)


def _project(tmp_path, pdk_yaml):
    project = tmp_path / "project"
    (project / "design").mkdir(parents=True)
    (project / "design" / "opamp.cir").write_text("* opamp\n")
    (project / "constraints.yaml").write_text(pdk_yaml + "checks: []\n")
    return project


def _code(excinfo):
    return getattr(excinfo.value, "code", None)


def test_a_pdk_name_pins_its_registered_revision(tmp_path, store):
    from rocket_engine.adapters.mcp.server import load_pdk_pin

    _register(store, tmp_path / "src", "v1")
    project = _project(tmp_path, "pdk: tiny130A\n")
    assert load_pdk_pin(project) == {"id": "tiny130A", "revision": "v1"}


@pytest.mark.parametrize("pdk_yaml", ["", "pdk: none\n", "pdk: None\n", "pdk:\n", "pdk: ''\n"])
def test_no_pdk_means_generic_models(tmp_path, store, pdk_yaml):
    from rocket_engine.adapters.mcp.server import load_pdk_pin

    assert load_pdk_pin(_project(tmp_path, pdk_yaml)) is None
    assert not store.exists()  # no store lookup when nothing is named


def test_a_project_without_constraints_has_no_pin(tmp_path, store):
    from rocket_engine.adapters.mcp.server import load_pdk_pin

    assert load_pdk_pin(tmp_path / "missing") is None


def test_a_pinned_mapping_is_taken_as_written(tmp_path, store):
    # The solver verifies id/revision against the store when it runs.
    from rocket_engine.adapters.mcp.server import load_pdk_pin

    project = _project(tmp_path, "pdk: {id: tiny130A, revision: v2}\n")
    assert load_pdk_pin(project) == {"id": "tiny130A", "revision": "v2"}


@pytest.mark.parametrize("pdk_yaml", ["pdk: {id: tiny130A}\n", "pdk: 130\n", "pdk: [tiny130A]\n"])
def test_a_malformed_pdk_is_refused(tmp_path, store, pdk_yaml):
    from rocket_engine.adapters.errors import AdapterError
    from rocket_engine.adapters.mcp.server import load_pdk_pin

    with pytest.raises(AdapterError) as excinfo:
        load_pdk_pin(_project(tmp_path, pdk_yaml))
    assert _code(excinfo) == "invalid_command"


def test_an_unregistered_pdk_fails_loudly(tmp_path, store):
    from rocket_engine.adapters.errors import AdapterError
    from rocket_engine.adapters.mcp.server import load_pdk_pin

    project = _project(tmp_path, "pdk: tiny130A\n")
    with pytest.raises(AdapterError) as excinfo:
        load_pdk_pin(project)  # no store on this machine at all
    assert _code(excinfo) == "unknown_pdk"
    assert "tiny130A" in str(excinfo.value) and "registered: none" in str(excinfo.value)

    _register(store, tmp_path / "other", "v1", pdk_id="other130A")
    with pytest.raises(AdapterError) as excinfo:
        load_pdk_pin(project)
    assert _code(excinfo) == "unknown_pdk"
    assert "other130A v1" in str(excinfo.value)


def test_a_name_with_several_revisions_needs_one_pinned(tmp_path, store):
    from rocket_engine.adapters.errors import AdapterError
    from rocket_engine.adapters.mcp.server import load_pdk_pin

    _register(store, tmp_path / "src_a", "v1")
    _register(store, tmp_path / "src_b", "v2")
    with pytest.raises(AdapterError) as excinfo:
        load_pdk_pin(_project(tmp_path, "pdk: tiny130A\n"))
    assert _code(excinfo) == "invalid_command"
    assert "v1, v2" in str(excinfo.value) and "revision" in str(excinfo.value)


# --- the bound server puts the pin on every run_spice it admits ---


class Recording:
    """Stand-in ngspice that records each job and measures a fixed gain."""

    def __init__(self):
        self.jobs = []

    def preflight(self, job):
        return job

    def execute(self, job):
        self.jobs.append(job)
        return {
            "exit_code": 0, "stdout": "", "stderr": "",
            "log": "ngspice-44 (stand-in)\nmeas_dc_gain_db = 61.0",
            "sources": job.get("sources", []), "measurements": job["measurements"],
        }

    def parse(self, native):
        from rocket_engine.adapters.ngspice import NgspiceAdapter

        return NgspiceAdapter().parse(native)


def _bound(project):
    from rocket_engine.adapters.mcp.server import make_handlers
    from rocket_engine.composition import Engine

    solver = Recording()
    engine = Engine(PROJECT, actor="mcp")
    engine.register_solver("run_spice", solver, tool="ngspice")
    _, call = make_handlers(lambda project_id: engine, project_scope=PROJECT, project_dir=project)
    return solver, call


def _call(handler, name, arguments):
    from mcp.types import CallToolRequestParams

    result = asyncio.run(handler(None, CallToolRequestParams(name=name, arguments=arguments)))
    return result, json.loads(result.content[0].text)


def test_bound_server_pins_run_spice_to_the_project_pdk(tmp_path, store):
    _register(store, tmp_path / "src", "v1")
    solver, call = _bound(_project(tmp_path, "pdk: tiny130A\n"))

    result, _ = _call(call, "run_spice", {"sources": ["design/opamp.cir"], "measurements": [GAIN]})
    assert result.is_error is False
    assert solver.jobs[0]["pdk"] == {"id": "tiny130A", "revision": "v1"}

    # The project decides the PDK, like its targets: a caller's own pin is replaced.
    _call(call, "run_spice", {"sources": ["design/opamp.cir"], "measurements": [GAIN],
                              "pdk": {"id": "elsewhere", "revision": "x"}})
    assert solver.jobs[1]["pdk"] == {"id": "tiny130A", "revision": "v1"}


def test_bound_server_refuses_a_pdk_it_cannot_pin(tmp_path, store):
    solver, call = _bound(_project(tmp_path, "pdk: tiny130A\n"))

    result, body = _call(call, "run_spice", {"sources": ["design/opamp.cir"], "measurements": [GAIN]})
    assert result.is_error is True and body["code"] == "unknown_pdk"
    assert solver.jobs == []


def test_a_project_without_a_pdk_leaves_the_run_alone(tmp_path, store):
    solver, call = _bound(_project(tmp_path, "pdk: none\n"))

    result, _ = _call(call, "run_spice", {"sources": ["design/opamp.cir"], "measurements": [GAIN]})
    assert result.is_error is False
    assert "pdk" not in solver.jobs[0]
