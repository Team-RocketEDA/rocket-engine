"""GENERATE-VIEWS RED — GdsfactoryViewsAdapter behind generate_views.

Valid RED = `src/adapters/gdsfactory/adapter.py` does not exist yet, so
the loader below fails on FileNotFoundError. Project view specs and
project GDS files in; identity mappings + diagnostics out — never the
hardcoded MZI smoke (`run_layout_smoke` stays the qualification
fixture; this op generalizes it to any spec cells/params/recipes, and
one live test pins op-vs-smoke agreement). Registered recipes:
import_gds, build_cells, export_gds, export_oasis. Macro
pin/obstruction mappings publish as artifacts with provenance. Live
tests skip (never fake-green) where gdsfactory/cspdk are uninstalled;
unit tests use canned driver envelopes and FakeRunners.
"""

import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURES = Path(__file__).parent / "fixtures" / "generate_views"

gf_present = importlib.util.find_spec("gdsfactory") is not None
needs_gf = pytest.mark.skipif(
    not gf_present,
    reason="gdsfactory not installed (uv sync)",
)

REPO_ROOT = ROOT
VENDORED_CSPDK = REPO_ROOT / "fixtures" / "upstream" / "cspdk"
cspdk_present = (
    importlib.util.find_spec("cspdk") is not None
    or (VENDORED_CSPDK / "cspdk" / "si340" / "__init__.py").exists()
)
needs_cspdk = pytest.mark.skipif(
    not (gf_present and cspdk_present),
    reason="cspdk si340 unavailable (scripts/fetch_fixtures.py --only cspdk)",
)

GF_PIN = "9.51.0"
CSPDK_PIN = "2.1.0"


def _load_adapter():
    # RED: src/adapters/gdsfactory/adapter.py does not exist yet.
    path = ROOT / "src" / "adapters" / "gdsfactory" / "adapter.py"
    spec = importlib.util.spec_from_file_location(
        "generate_views_adapter", path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _job(sources, tmp_path, recipe="build_cells", **over):
    workdir = tmp_path / "work"
    workdir.mkdir(exist_ok=True)
    staged = []
    for name in sources:
        dest = workdir / name
        shutil.copy(FIXTURES / name, dest)
        staged.append(str(dest))
    job = {
        "operation": "generate_views",
        "recipe": recipe,
        "sources": staged,
        "workdir": str(workdir),
    }
    job.update(over)
    return job


def _mapping(**over):
    mapping = {
        "source": "mzi",
        "component": "mzi",
        "ports": ["o1", "o2", "o3"],
        "n_polygons": 42,
        "bbox_um": [[0.0, 0.0], [10.0, 5.0]],
    }
    mapping.update(over)
    return mapping


def _ok_envelope(mappings, recipe="build_cells", **over):
    result = {
        "recipe": recipe,
        "active_pdk": "cornerstone_si340",
        "cspdk_version": "2.1.0-canned",
        "mappings": mappings,
        "artifacts": [
            {
                "kind": "pins",
                "cell": "mzi",
                "path": "/tmp/work/mzi.pins.json",
            },
            {
                "kind": "obstructions",
                "cell": "mzi",
                "path": "/tmp/work/mzi.obstructions.json",
            },
        ],
        "diagnostics": {"roundtrip_match": None, "notes": []},
    }
    result.update(over)
    return json.dumps(
        {
            "ok": True,
            "gdsfactory_version": "9.51.0-canned",
            "result": result,
        }
    )


def _good_native(tmp_path=None, **over):
    spec = str(FIXTURES / "mzi_views.yml")
    native = {
        "exit_code": 0,
        "stdout": _ok_envelope([_mapping()]),
        "stderr": "",
        "recipe": "build_cells",
        "spec": spec,
        "spec_text": (FIXTURES / "mzi_views.yml").read_text(),
        "sources": [spec],
    }
    native.update(over)
    return native


class FakeRunner:
    def __init__(self, stdout, exit_code=0):
        self._stdout = stdout
        self._exit_code = exit_code
        self.seen = {}

    def preflight(self):
        return {"ready": True}

    def run(self, command, workdir, timeout_s=120, extra_binds=()):
        self.seen["command"] = command
        self.seen["workdir"] = workdir
        self.seen["timeout_s"] = timeout_s
        self.seen["extra_binds"] = extra_binds
        return subprocess.CompletedProcess(
            command, self._exit_code, self._stdout, ""
        )


def test_generate_views_adapter_exists():
    mod = _load_adapter()  # RED: missing module
    assert mod.OPERATION == "generate_views"
    assert set(mod.RECIPES) == {
        "import_gds", "build_cells", "export_gds", "export_oasis",
    }
    assert callable(mod.GdsfactoryViewsAdapter)


def test_generate_views_implements_tool_port():
    from rocket_engine.adapters import ToolAdapter  # live surface

    mod = _load_adapter()  # RED: missing module
    assert issubclass(mod.GdsfactoryViewsAdapter, ToolAdapter)


def test_generate_views_capabilities_advertise_recipes():
    mod = _load_adapter()  # RED: missing module
    caps = mod.GdsfactoryViewsAdapter().capabilities({"cell": "mzi"})
    assert caps["operations"] == ["generate_views"]
    assert caps["tool"] == "gdsfactory"
    assert sorted(caps["recipes"]) == [
        "build_cells", "export_gds", "export_oasis", "import_gds",
    ]


def test_generate_views_preflight_refuses_bad_operation(tmp_path):
    mod = _load_adapter()  # RED: missing module
    job = _job(["mzi_views.yml"], tmp_path, operation="run_spice")
    try:
        mod.GdsfactoryViewsAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "unsupported_operation"
    else:
        raise AssertionError("expected unsupported_operation for run_spice")


def test_generate_views_preflight_refuses_unknown_recipe(tmp_path):
    mod = _load_adapter()  # RED: missing module
    job = _job(["mzi_views.yml"], tmp_path, recipe="run_drc")
    try:
        mod.GdsfactoryViewsAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_command"
    else:
        raise AssertionError("expected invalid_command for run_drc recipe")


def test_generate_views_preflight_refuses_missing_sources(tmp_path):
    mod = _load_adapter()  # RED: missing module
    job = _job(["mzi_views.yml"], tmp_path)
    job["sources"] = [str(tmp_path / "work" / "ghost.yml")]
    try:
        mod.GdsfactoryViewsAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_reference"
    else:
        raise AssertionError("expected invalid_reference for missing sources")


def test_generate_views_preflight_refuses_bad_timeout(tmp_path):
    mod = _load_adapter()  # RED: missing module
    job = _job(["mzi_views.yml"], tmp_path, timeout_s=0)
    try:
        mod.GdsfactoryViewsAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_command"
    else:
        raise AssertionError("expected invalid_command for timeout 0")


def test_generate_views_preflight_refuses_unknown_pdk(tmp_path):
    mod = _load_adapter()  # RED: missing module
    job = _job(["mzi_views.yml"], tmp_path)
    bad = Path(job["sources"][0])
    bad.write_text(bad.read_text().replace("cspdk.si340", "sky130"))
    try:
        mod.GdsfactoryViewsAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_command"
    else:
        raise AssertionError("expected invalid_command for sky130 pdk")


def test_generate_views_preflight_refuses_empty_cells(tmp_path):
    mod = _load_adapter()  # RED: missing module
    job = _job(["mzi_views.yml"], tmp_path)
    bad = Path(job["sources"][0])
    bad.write_text("views: empty\npdk: generic\ncells: []\n")
    try:
        mod.GdsfactoryViewsAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_command"
    else:
        raise AssertionError("expected invalid_command for empty cells")


def test_generate_views_preflight_refuses_bad_params(tmp_path):
    mod = _load_adapter()  # RED: missing module
    job = _job(["mzi_views.yml"], tmp_path)
    bad = Path(job["sources"][0])
    bad.write_text(
        "views: bad\npdk: generic\ncells:\n"
        "  - cell: straight\n    params: 42\n"
    )
    try:
        mod.GdsfactoryViewsAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_command"
    else:
        raise AssertionError("expected invalid_command for scalar params")


def test_generate_views_preflight_refuses_export_extension(tmp_path):
    mod = _load_adapter()  # RED: missing module
    job = _job(["mzi_views.yml"], tmp_path, recipe="export_oasis")
    try:
        mod.GdsfactoryViewsAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_command"
    else:
        raise AssertionError("expected invalid_command for .gds under oasis")


def test_generate_views_preflight_refuses_import_without_gds(tmp_path):
    mod = _load_adapter()  # RED: missing module
    job = _job(["mzi_views.yml"], tmp_path, recipe="import_gds")
    try:
        mod.GdsfactoryViewsAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_command"
    else:
        raise AssertionError("expected invalid_command for .yml import")


def test_generate_views_preflight_accepts_import_gds(tmp_path):
    mod = _load_adapter()  # RED: missing module
    workdir = tmp_path / "work"
    workdir.mkdir(exist_ok=True)
    gds = workdir / "macro.gds"
    gds.write_bytes(b"GDSII-project-input")
    pin_map = workdir / "macro_pin_map.yml"
    shutil.copy(FIXTURES / "macro_pin_map.yml", pin_map)
    job = {
        "operation": "generate_views",
        "recipe": "import_gds",
        "sources": [str(gds)],
        "pin_map": str(pin_map),
        "workdir": str(workdir),
    }
    checked = mod.GdsfactoryViewsAdapter().preflight(job)
    assert checked["gds_sources"] == [str(gds)]
    assert checked["pin_map_doc"]["pin_map"] == "macro-binding"
    assert checked["timeout_s"] == 120


def test_generate_views_preflight_refuses_stray_pin_map(tmp_path):
    mod = _load_adapter()  # RED: missing module
    job = _job(["mzi_views.yml"], tmp_path)
    pin_map = tmp_path / "work" / "macro_pin_map.yml"
    shutil.copy(FIXTURES / "macro_pin_map.yml", pin_map)
    job["pin_map"] = str(pin_map)
    try:
        mod.GdsfactoryViewsAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_command"
    else:
        raise AssertionError("expected invalid_command for stray pin_map")


def test_generate_views_preflight_accepts_op_fixture(tmp_path):
    mod = _load_adapter()  # RED: missing module
    checked = mod.GdsfactoryViewsAdapter().preflight(
        _job(["mzi_views.yml"], tmp_path)
    )
    assert checked["spec"].endswith("mzi_views.yml")
    assert checked["doc"]["views"] == "mzi-project"
    assert checked["doc"]["cells"] == [{"cell": "mzi"}]
    assert checked["timeout_s"] == 120


def test_generate_views_parse_reports_mappings_and_diagnostics():
    mod = _load_adapter()  # RED: missing module
    got = mod.GdsfactoryViewsAdapter().parse(_good_native())
    assert got["total"] == 0
    assert got["violations"] == []
    assert got["mappings"] == [_mapping()]
    assert got["diagnostics"]["active_pdk"] == "cornerstone_si340"
    assert got["gdsfactory_version"] == "9.51.0-canned"
    kinds = {(a["kind"], a["cell"]) for a in got["artifacts"]}
    assert kinds == {("pins", "mzi"), ("obstructions", "mzi")}
    names = {m["name"]: m["value"] for m in got["measurements"]}
    assert names["polygons(mzi)"] == 42
    assert names["ports(mzi)"] == 3
    assert names["bbox_area_um2(mzi)"] == pytest.approx(50.0)


def test_generate_views_parse_export_carries_layout_artifact():
    mod = _load_adapter()  # RED: missing module
    native = _good_native(
        recipe="export_gds",
        stdout=_ok_envelope(
            [_mapping()],
            recipe="export_gds",
            artifacts=[
                {
                    "kind": "layout",
                    "cell": "mzi",
                    "path": "/tmp/work/mzi.gds",
                },
                {
                    "kind": "pins",
                    "cell": "mzi",
                    "path": "/tmp/work/mzi.pins.json",
                },
                {
                    "kind": "obstructions",
                    "cell": "mzi",
                    "path": "/tmp/work/mzi.obstructions.json",
                },
            ],
            diagnostics={"roundtrip_match": True, "notes": []},
        ),
    )
    got = mod.GdsfactoryViewsAdapter().parse(native)
    assert got["total"] == 0
    assert got["diagnostics"]["roundtrip_match"] is True
    layouts = [a for a in got["artifacts"] if a["kind"] == "layout"]
    assert layouts == [
        {"kind": "layout", "cell": "mzi", "path": "/tmp/work/mzi.gds"}
    ]


def test_generate_views_parse_unknown_cell_synthesizes_violation():
    mod = _load_adapter()  # RED: missing module
    native = _good_native(
        stdout=json.dumps(
            {
                "ok": False,
                "error": {
                    "code": "invalid_cell",
                    "message": "Unknown cell 'ghost' in PDK 'generic'.",
                    "token": "ghost",
                    "line": 4,
                },
            }
        )
    )
    got = mod.GdsfactoryViewsAdapter().parse(native)
    assert got["total"] == 1
    assert got["measurements"] == []
    violation = got["violations"][0]
    assert violation["rule"] == "views.unknown_cell"
    assert violation["severity"] == "error"
    assert violation["file"] == native["spec"]
    assert violation["line"] == 4


def test_generate_views_parse_missing_dependency_raises():
    mod = _load_adapter()  # RED: missing module
    native = _good_native(
        stdout=json.dumps(
            {
                "ok": False,
                "error": {
                    "code": "missing_dependency",
                    "message": "gdsfactory is not importable",
                    "token": None,
                    "line": None,
                },
            }
        )
    )
    try:
        mod.GdsfactoryViewsAdapter().parse(native)
    except Exception as exc:
        assert getattr(exc, "code", None) == "missing_dependency"
    else:
        raise AssertionError("expected missing_dependency")


def test_generate_views_parse_no_envelope_raises():
    mod = _load_adapter()  # RED: missing module
    native = _good_native(stdout="Traceback (most recent call last): boom\n")
    try:
        mod.GdsfactoryViewsAdapter().parse(native)
    except Exception as exc:
        assert getattr(exc, "code", None) == "runner_unavailable"
    else:
        raise AssertionError("expected runner_unavailable")


def test_generate_views_execute_stages_driver_and_job(tmp_path):
    mod = _load_adapter()  # RED: missing module
    runner = FakeRunner(_ok_envelope([_mapping()]))
    job = _job(["mzi_views.yml"], tmp_path)
    native = mod.GdsfactoryViewsAdapter(runner=runner).execute(job)
    assert native["exit_code"] == 0
    assert native["recipe"] == "build_cells"
    assert native["spec"].endswith("mzi_views.yml")
    assert (Path(job["workdir"]) / "gf_views_driver.py").is_file()
    assert (Path(job["workdir"]) / "gf_views_job.json").is_file()
    assert runner.seen["command"][1:] == [
        "gf_views_driver.py", "gf_views_job.json"]


def test_generate_views_driver_consumes_project_inputs():
    # Generalization law: the staged driver must build from the job —
    # cells, params, GDS paths, and the pin map all ride the spec.
    # A hardcoded MZI would re-qualify the smoke, not generalize it.
    text = (
        ROOT / "src" / "adapters" / "gdsfactory" / "_driver.py"
    ).read_text()
    assert 'doc["cells"]' in text
    assert "import_gds" in text
    assert "write_gds" in text
    assert "write_oas" in text
    assert "pin_map" in text
    assert "mzi" not in text


def test_generate_views_driver_reports_missing_solver_loudly(tmp_path):
    # No gdsfactory here by lane rule (install.sh owns the env, and it
    # ships no layout group) — the real staged driver must fail loud
    # with a missing_dependency envelope, never fake-green.
    if gf_present:  # pragma: no cover — solver present, nothing to prove
        pytest.skip("gdsfactory installed; loud-missing needs it absent")
    driver = ROOT / "src" / "adapters" / "gdsfactory" / "_driver.py"
    job_path = tmp_path / "gf_views_job.json"
    job_path.write_text(json.dumps(
        {
            "recipe": "build_cells",
            "spec": str(FIXTURES / "straight_views.yml"),
            "text": (FIXTURES / "straight_views.yml").read_text(),
            "doc": {
                "views": "straight-project",
                "pdk": "generic",
                "cells": [{"cell": "straight"}],
            },
            "gds_sources": [],
            "pin_map_doc": None,
            "cspdk_path": None,
        }
    ))
    proc = subprocess.run(
        ["python3", str(driver), str(job_path)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=120,
    )
    from rocket_engine.adapters.envelope import extract_envelope

    assert proc.returncode == 3
    envelope = extract_envelope(proc.stdout, tool="views")
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "missing_dependency"


def test_generate_views_dispatches_as_engine_run(tmp_path):
    from rocket_engine.composition import Engine

    mod = _load_adapter()  # RED: missing module
    engine = Engine("generate-views", actor="tester")
    engine.register_solver(
        "generate_views",
        mod.GdsfactoryViewsAdapter(
            runner=FakeRunner(_ok_envelope([_mapping()]))),
        tool="gdsfactory")
    job = _job(["mzi_views.yml"], tmp_path)
    out = engine.run(
        {
            "project_id": "generate-views",
            "operation": "generate_views",
            "arguments": {
                "recipe": "build_cells",
                "sources": job["sources"],
                "workdir": job["workdir"],
                "deck": {"tool": "gdsfactory"},
            },
        }
    )
    assert out["operation"] == "generate_views"
    assert out["run_id"]
    assert out["verdict"]["status"] == "PASS"
    assert out["verdict"]["measurements"]
    events = engine.events_since(0)
    assert any(
        e.get("event") == "run_completed" and e.get("data", {}).get(
            "run_id") == out["run_id"] for e in events
    ), events


def test_generate_views_dispatch_fail_carries_run_id(tmp_path):
    from rocket_engine.composition import Engine

    mod = _load_adapter()  # RED: missing module
    engine = Engine("generate-views", actor="tester")
    engine.register_solver(
        "generate_views",
        mod.GdsfactoryViewsAdapter(runner=FakeRunner(json.dumps(
            {
                "ok": False,
                "error": {
                    "code": "invalid_cell",
                    "message": "Unknown cell 'ghost' in PDK 'generic'.",
                    "token": "ghost",
                    "line": 4,
                },
            }
        ))),
        tool="gdsfactory")
    job = _job(["mzi_views.yml"], tmp_path)
    out = engine.run(
        {
            "project_id": "generate-views",
            "operation": "generate_views",
            "arguments": {
                "recipe": "build_cells",
                "sources": job["sources"],
                "workdir": job["workdir"],
                "deck": {"tool": "gdsfactory"},
            },
        }
    )
    assert out["run_id"]
    assert out["verdict"]["status"] == "FAIL"
    found = engine.findings(out["run_id"])["findings"]
    assert any(f["rule"] == "views.unknown_cell" for f in found)


@needs_gf
def test_generate_views_live_generic_straight(tmp_path):
    mod = _load_adapter()  # RED: missing module
    adapter = mod.GdsfactoryViewsAdapter()
    job = _job(["straight_views.yml"], tmp_path)
    got = adapter.parse(adapter.execute(job))
    assert got["total"] == 0
    assert got["gdsfactory_version"] == GF_PIN
    assert got["mappings"][0]["source"] == "straight"
    assert got["mappings"][0]["ports"]
    assert got["mappings"][0]["n_polygons"] > 0


@needs_cspdk
def test_generate_views_live_cspdk_mzi_identity(tmp_path):
    mod = _load_adapter()  # RED: missing module
    adapter = mod.GdsfactoryViewsAdapter()
    job = _job(["mzi_views.yml"], tmp_path,
               cspdk_path=str(VENDORED_CSPDK))
    got = adapter.parse(adapter.execute(job))
    assert got["total"] == 0
    assert got["gdsfactory_version"] == GF_PIN
    assert got["diagnostics"]["cspdk_version"] == CSPDK_PIN
    mapping = got["mappings"][0]
    assert mapping["source"] == "mzi"
    # gdsfactory names built cells <cell>_<settings>_<hash>; the
    # adapter reports the real name, so pin the prefix, not equality.
    assert mapping["component"].startswith("mzi")
    assert sorted(mapping["ports"]) == ["o1", "o2", "o3"]
    assert mapping["n_polygons"] > 0


@needs_cspdk
def test_generate_views_live_export_then_import_roundtrip(tmp_path):
    # GDS roundtrip is an artifact, not the test: the export recipe
    # publishes the layout file, and the import recipe maps it back
    # to the same cell identity with the match in diagnostics.
    mod = _load_adapter()  # RED: missing module
    adapter = mod.GdsfactoryViewsAdapter()
    job = _job(["mzi_views.yml"], tmp_path, recipe="export_gds",
               cspdk_path=str(VENDORED_CSPDK))
    exported = adapter.parse(adapter.execute(job))
    assert exported["total"] == 0
    layouts = [a for a in exported["artifacts"] if a["kind"] == "layout"]
    assert len(layouts) == 1
    assert Path(layouts[0]["path"]).is_file()
    reimport = adapter.parse(adapter.execute({
        "operation": "generate_views",
        "recipe": "import_gds",
        "sources": [layouts[0]["path"]],
        "workdir": job["workdir"],
        "cspdk_path": str(VENDORED_CSPDK),
    }))
    assert reimport["total"] == 0
    assert reimport["mappings"][0]["component"].startswith("mzi")
    assert sorted(reimport["mappings"][0]["ports"]) == ["o1", "o2", "o3"]
    assert reimport["mappings"][0]["n_polygons"] > 0
    assert exported["diagnostics"]["roundtrip_match"] is True


@needs_cspdk
def test_generate_views_live_agrees_with_qualification_smoke(tmp_path):
    # The MZI smoke is the qualification fixture: the op must agree
    # with run_layout_smoke on ports and polygon count, not replace
    # its proof with a second hardcoded oracle.
    from rocket_engine.adapters.gdsfactory import run_layout_smoke

    mod = _load_adapter()  # RED: missing module
    adapter = mod.GdsfactoryViewsAdapter()
    job = _job(["mzi_views.yml"], tmp_path,
               cspdk_path=str(VENDORED_CSPDK))
    got = adapter.parse(adapter.execute(job))
    smoke = run_layout_smoke(cell="mzi", cspdk_path=str(VENDORED_CSPDK))
    mapping = got["mappings"][0]
    assert sorted(mapping["ports"]) == sorted(smoke["ports"])
    assert mapping["n_polygons"] == smoke["n_polygons"]
    assert mapping["bbox_um"] == smoke["bbox_um"]
