"""POSTLAYOUT RED — PostLayoutAdapter behind run_post_layout (deck.tool ngspice).

Valid RED = `src/adapters/postlayout/adapter.py` does not exist yet, so
the loader below fails on FileNotFoundError. One call replays an analog
block post-layout: extracted netlist + testbench + PDK models through
live ngspice, with a pre/post delta table against the schematic run
referenced by schematic_run_id (run_id accepted as an alias).

Provenance is enforced, never advisory: a missing extraction record or
a netlist whose bytes no longer match the record's sha256 refuses
loudly — a schematic passed as extracted without a fresh record never
sims. Deltas never gate the verdict (bounds do); a zero delta on a
lossy extraction fails the TEST, not the design.

Canned stdout copies real ngspice-42 output lines; the live RC divider
pair (model-free) proves the binary path, while the bandgap and sd_top
lossy pairs prove green-but-nonzero deltas on the vendored fixtures
through a minimal real-model store (skipped, never fake-green, where
ngspice, the PDK source tree, or the upstream fixtures are absent).
"""

import hashlib
import importlib.util
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURES = Path(__file__).parent / "fixtures" / "postlayout"
UPSTREAM = ROOT / "fixtures" / "upstream"
BANDGAP_SNAPSHOT = (
    UPSTREAM
    / "sky130-bandgap"
    / "sim"
    / "output-voltage-tc"
    / "netlist-snapshots"
    / "20260817-015751-13476b7.spice"
)
SDTOP_PEX = UPSTREAM / "ttsky-sigma-delta" / "spice" / "sd_top_pex.spice"
MODEL_REL = "libs.tech/combined/sky130.lib.spice"

# DR-005 ratified accuracy row: 1.20 V +/-2% untrimmed.
VREF_MIN = 1.176
VREF_MAX = 1.224
# sd_top integrator monitor DC window (VALIDATE-M Phase 1.1).
INT_MIN = 0.8
INT_MAX = 1.0

# Real ngspice-42 stdout shape (op + let/print meas_*); values mirror
# the committed RC pair: schematic 1.2 V, lossy extraction ~500 uV low.
CANNED_POST = """Note: Compatibility modes selected: hs a


Circuit: * rocket_engine run_post_layout

Doing analysis at TEMP = 27.000000 and TNOM = 27.000000

Using KLU as Direct Linear Solver
 Reference value :  0.00000e+00
No. of Data Rows : 1
meas_vout = 1.199500e+00
ngspice-42 done
"""

# Real `wrdata postlayout_waveforms.dat v(out)` shape: one scale column
# plus one column per vector, whitespace separated, no header.
CANNED_WRDATA = """0.000000e+00 0.000000e+00
1.000000e-06 1.199500e+00
2.000000e-06 1.199500e+00
"""

ngspice_present = shutil.which("ngspice") is not None
needs_ngspice = pytest.mark.skipif(not ngspice_present, reason="ngspice not on PATH")


def _load_adapter():
    # RED: src/adapters/postlayout/adapter.py does not exist yet.
    path = ROOT / "src" / "adapters" / "postlayout" / "adapter.py"
    spec = importlib.util.spec_from_file_location("postlayout_adapter", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _provenance(extracted, run_id="ext-run-test-1"):
    return {
        "extraction_run_id": run_id,
        "netlist_sha256": _sha256(extracted),
        "cell": "rc_divider",
        "tech": "sky130A",
        "spice_file": str(extracted),
    }


def _job(tmp_path, **over):
    workdir = tmp_path / "work"
    workdir.mkdir(exist_ok=True)
    staged = workdir / "rc_extracted.spice"
    shutil.copy(FIXTURES / "rc_extracted.spice", staged)
    job = {
        "operation": "run_post_layout",
        "extracted_netlist": str(staged),
        "workdir": str(workdir),
        "measurements": [
            {"name": "vout", "expr": "v(out)", "unit": "V",
             "min": 1.199, "max": 1.201},
        ],
        "schematic_run_id": "schem-run-test-1",
        "schematic_measurements": [
            {"name": "vout", "value": 1.2, "unit": "V"},
        ],
        "extraction_provenance": _provenance(staged),
    }
    job.update(over)
    return job


def _native(stdout, measurements=None, **over):
    native = {
        "exit_code": 0,
        "stdout": stdout,
        "stderr": "",
        "log": "",
        "deck": "postlayout_deck.spice",
        "extracted_netlist": "rc_extracted.spice",
        "measurements": (
            list(measurements)
            if measurements is not None
            else [{"name": "vout", "expr": "v(out)", "unit": "V",
                   "min": 1.199, "max": 1.201}]
        ),
        "schematic": {"run_id": "schem-run-test-1",
                      "values": {"vout": {"value": 1.2, "unit": "V"}}},
        "provenance": {"extraction_run_id": "ext-run-test-1",
                       "netlist_sha256": "0" * 64},
        "waveforms_spec": [],
        "waveforms_file": "",
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
        return subprocess.CompletedProcess(command, self._exit_code, self._stdout, "")


def test_postlayout_adapter_exists():
    mod = _load_adapter()  # RED: missing module
    assert mod.OPERATION == "run_post_layout"
    assert callable(mod.PostLayoutAdapter)


def test_postlayout_implements_tool_port():
    from rocket_engine.adapters import ToolAdapter  # live surface

    mod = _load_adapter()  # RED: missing module
    assert issubclass(mod.PostLayoutAdapter, ToolAdapter)


def test_postlayout_capabilities_advertise_tool():
    mod = _load_adapter()  # RED: missing module
    caps = mod.PostLayoutAdapter().capabilities({"cell": "bandgap_core"})
    assert caps["operations"] == ["run_post_layout"]
    assert caps["tool"] == "ngspice"


def test_postlayout_preflight_refuses_bad_operation(tmp_path):
    mod = _load_adapter()  # RED: missing module
    job = _job(tmp_path, operation="run_spice")
    try:
        mod.PostLayoutAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "unsupported_operation"
    else:
        raise AssertionError("expected unsupported_operation for run_spice")


def test_postlayout_preflight_refuses_missing_netlist(tmp_path):
    mod = _load_adapter()  # RED: missing module
    job = _job(tmp_path)
    job["extracted_netlist"] = str(tmp_path / "ghost.spice")
    try:
        mod.PostLayoutAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_reference"
    else:
        raise AssertionError("expected invalid_reference for missing netlist")


def test_postlayout_preflight_refuses_sources_alias(tmp_path):
    mod = _load_adapter()  # RED: missing module
    job = _job(tmp_path)
    job["sources"] = [job["extracted_netlist"]]
    try:
        mod.PostLayoutAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_command"
    else:
        raise AssertionError("expected invalid_command for sources alias")


def test_postlayout_preflight_refuses_missing_provenance(tmp_path):
    mod = _load_adapter()  # RED: missing module
    job = _job(tmp_path)
    del job["extraction_provenance"]
    try:
        mod.PostLayoutAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_command"
    else:
        raise AssertionError("expected invalid_command for missing provenance")


def test_postlayout_preflight_refuses_malformed_provenance(tmp_path):
    mod = _load_adapter()  # RED: missing module
    bad_records = [
        {"netlist_sha256": "0" * 64},
        {"extraction_run_id": "ext-1"},
        {"extraction_run_id": "", "netlist_sha256": "0" * 64},
        {"extraction_run_id": "ext-1", "netlist_sha256": "not-a-hash"},
        "ext-run-test-1",
    ]
    for record in bad_records:
        job = _job(tmp_path, extraction_provenance=record)
        try:
            mod.PostLayoutAdapter().preflight(job)
        except Exception as exc:
            assert getattr(exc, "code", None) == "invalid_command", record
        else:
            raise AssertionError(f"expected invalid_command for {record!r}")


def test_postlayout_stale_provenance_fails_loudly_and_never_sims(tmp_path):
    mod = _load_adapter()  # RED: missing module
    runner = FakeRunner(CANNED_POST)
    adapter = mod.PostLayoutAdapter(runner=runner)
    job = _job(tmp_path)
    Path(job["extracted_netlist"]).write_text("* TAMPERED\n")
    try:
        adapter.execute(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_reference"
    else:
        raise AssertionError("expected invalid_reference for stale provenance")
    assert runner.seen == {}


def test_postlayout_preflight_refuses_foreign_provenance(tmp_path):
    mod = _load_adapter()  # RED: missing module
    job = _job(tmp_path)
    job["extraction_provenance"]["spice_file"] = "other_cell.spice"
    try:
        mod.PostLayoutAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_reference"
    else:
        raise AssertionError("expected invalid_reference for foreign provenance")


def test_postlayout_preflight_refuses_missing_schematic_ref(tmp_path):
    mod = _load_adapter()  # RED: missing module
    job = _job(tmp_path)
    del job["schematic_run_id"]
    del job["schematic_measurements"]
    try:
        mod.PostLayoutAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_command"
    else:
        raise AssertionError("expected invalid_command for missing schematic ref")


def test_postlayout_preflight_accepts_run_id_alias(tmp_path):
    mod = _load_adapter()  # RED: missing module
    job = _job(tmp_path)
    job["run_id"] = job.pop("schematic_run_id")
    checked = mod.PostLayoutAdapter().preflight(job)
    assert checked["schematic"]["run_id"] == "schem-run-test-1"


def test_postlayout_preflight_refuses_conflicting_run_ids(tmp_path):
    mod = _load_adapter()  # RED: missing module
    job = _job(tmp_path, run_id="other-run")
    try:
        mod.PostLayoutAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_command"
    else:
        raise AssertionError("expected invalid_command for conflicting run ids")


def test_postlayout_preflight_refuses_unknown_schematic_run(tmp_path):
    mod = _load_adapter()  # RED: missing module
    job = _job(tmp_path)
    del job["schematic_measurements"]

    def _missing(run_id):
        raise KeyError(run_id)

    adapter = mod.PostLayoutAdapter(runs=_missing)
    try:
        adapter.preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_reference"
    else:
        raise AssertionError("expected invalid_reference for unknown schematic")


def test_postlayout_preflight_resolves_schematic_via_runs(tmp_path):
    mod = _load_adapter()  # RED: missing module
    job = _job(tmp_path)
    del job["schematic_measurements"]
    seen = {}

    def _runs(run_id):
        seen["run_id"] = run_id
        return {"measurements": [{"name": "vout", "value": 1.2, "unit": "V"}]}

    checked = mod.PostLayoutAdapter(runs=_runs).preflight(job)
    assert seen == {"run_id": "schem-run-test-1"}
    assert checked["schematic"]["values"]["vout"]["value"] == 1.2


def test_postlayout_preflight_refuses_schematic_missing_name(tmp_path):
    mod = _load_adapter()  # RED: missing module
    job = _job(
        tmp_path,
        schematic_measurements=[{"name": "other", "value": 1.2, "unit": "V"}],
    )
    try:
        mod.PostLayoutAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_command"
    else:
        raise AssertionError("expected invalid_command for schematic gap")


def test_postlayout_preflight_refuses_bad_measurements(tmp_path):
    mod = _load_adapter()  # RED: missing module
    bad = [
        [],
        [{"name": "vout", "expr": "v(out)"}],
        [{"name": "vout", "expr": "v(out)", "min": 2.0, "max": 1.0}],
        [{"name": "9v", "expr": "v(out)", "min": 0.0, "max": 5.0}],
    ]
    for measurements in bad:
        job = _job(tmp_path, measurements=measurements)
        try:
            mod.PostLayoutAdapter().preflight(job)
        except Exception as exc:
            assert getattr(exc, "code", None) == "invalid_command", measurements
        else:
            raise AssertionError(
                f"expected invalid_command for {measurements!r}"
            )


def test_postlayout_preflight_refuses_missing_testbench(tmp_path):
    mod = _load_adapter()  # RED: missing module
    job = _job(tmp_path, testbench=str(tmp_path / "ghost_tb.spice"))
    try:
        mod.PostLayoutAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_reference"
    else:
        raise AssertionError("expected invalid_reference for missing testbench")


def test_postlayout_preflight_refuses_bad_waveforms(tmp_path):
    mod = _load_adapter()  # RED: missing module
    bad = [
        [{"expr": "v(out)"}],
        [{"name": "out", "expr": "line one\nline two"}],
        [{"name": "9v", "expr": "v(out)"}],
        "v(out)",
    ]
    for waveforms in bad:
        job = _job(tmp_path, waveforms=waveforms)
        try:
            mod.PostLayoutAdapter().preflight(job)
        except Exception as exc:
            assert getattr(exc, "code", None) == "invalid_command", waveforms
        else:
            raise AssertionError(
                f"expected invalid_command for {waveforms!r}"
            )


def test_postlayout_preflight_refuses_bad_scalar_knobs(tmp_path):
    mod = _load_adapter()  # RED: missing module
    cases = [
        {"timeout_s": 0},
        {"corner": "tt; rm -rf /"},
        {"temp_c": "hot"},
        {"title": ""},
        {"analyses": [".op"]},
        {"params": {"vsup": True}},
    ]
    for over in cases:
        job = _job(tmp_path, **over)
        try:
            mod.PostLayoutAdapter().preflight(job)
        except Exception as exc:
            assert getattr(exc, "code", None) == "invalid_command", over
        else:
            raise AssertionError(f"expected invalid_command for {over!r}")


def test_postlayout_preflight_refuses_missing_tools(tmp_path):
    mod = _load_adapter()  # RED: missing module
    job = _job(tmp_path, tool_dir="/nonexistent-dir-for-postlayout-tests")
    try:
        mod.PostLayoutAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "missing_dependency"
    else:
        raise AssertionError("expected missing_dependency for bad tool_dir")


def test_postlayout_wrong_pdk_revision_fails_loudly(tmp_path):
    mod = _load_adapter()  # RED: missing module
    from rocket_engine.interfaces.pdks import register_pdk

    src = tmp_path / "tiny_pdk_src"
    (src / "libs.tech" / "combined").mkdir(parents=True)
    (src / "libs.tech" / "combined" / "sky130.lib.spice").write_text(
        "* tiny model lib\n.lib tt\n.ends\n"
    )
    engine_root = tmp_path / "engine"
    register_pdk(src, "sky130a", "r1", engine_root=engine_root)
    runner = FakeRunner(CANNED_POST)
    job = _job(tmp_path)
    job["pdk"] = {
        "id": "sky130a",
        "revision": "r2-never-registered",
        "engine_root": str(engine_root),
    }
    try:
        mod.PostLayoutAdapter(runner=runner).execute(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "unknown_pdk"
    else:
        raise AssertionError("expected unknown_pdk before any sim")
    assert runner.seen == {}


def test_postlayout_parse_evaluates_post_measurements():
    mod = _load_adapter()  # RED: missing module
    result = mod.PostLayoutAdapter().parse(_native(CANNED_POST))
    assert result["total"] == 0
    assert result["violations"] == []
    assert result["measurements"][0]["value"] == pytest.approx(1.1995, abs=1e-6)
    assert result["measurements"][0]["status"] == "pass"


def test_postlayout_parse_builds_pre_post_comparison():
    mod = _load_adapter()  # RED: missing module
    result = mod.PostLayoutAdapter().parse(_native(CANNED_POST))
    (row,) = result["comparison"]
    assert row["name"] == "vout"
    assert row["pre"] == pytest.approx(1.2)
    assert row["post"] == pytest.approx(1.1995, abs=1e-6)
    assert row["delta"] == pytest.approx(-0.0005, abs=1e-6)
    assert row["rel"] == pytest.approx(-0.0005 / 1.2, abs=1e-6)
    assert row["status"] == "pass"
    assert result["provenance"]["extraction_run_id"] == "ext-run-test-1"
    assert result["provenance"]["schematic_run_id"] == "schem-run-test-1"


def test_postlayout_parse_flags_bound_miss_with_delta():
    mod = _load_adapter()  # RED: missing module
    measurements = [
        {"name": "vout", "expr": "v(out)", "unit": "V", "min": 1.20, "max": 1.21},
    ]
    result = mod.PostLayoutAdapter().parse(_native(CANNED_POST, measurements))
    assert result["total"] == 1
    assert result["violations"][0]["rule"] == "measurement"
    assert result["measurements"][0]["status"] == "fail"
    assert result["comparison"][0]["status"] == "fail"
    assert result["comparison"][0]["delta"] == pytest.approx(-0.0005, abs=1e-6)


def test_postlayout_parse_missing_meas_fails_loudly():
    mod = _load_adapter()  # RED: missing module
    measurements = [
        {"name": "vout", "expr": "v(out)", "unit": "V", "min": 1.19, "max": 1.21},
        {"name": "nope", "expr": "v(nope)", "unit": "V", "min": 0.0, "max": 5.0},
    ]
    result = mod.PostLayoutAdapter().parse(_native(CANNED_POST, measurements))
    assert result["total"] >= 1
    assert any(v["rule"] == "sim_fail" for v in result["violations"])


def test_postlayout_parse_rejects_native_without_output():
    mod = _load_adapter()  # RED: missing module
    try:
        mod.PostLayoutAdapter().parse({"exit_code": 0})
    except Exception as exc:
        assert getattr(exc, "code", None) == "runner_unavailable"
    else:
        raise AssertionError("expected runner_unavailable for outputless native")


def test_postlayout_parse_reads_waveforms_file(tmp_path):
    mod = _load_adapter()  # RED: missing module
    dat = tmp_path / "postlayout_waveforms.dat"
    dat.write_text(CANNED_WRDATA)
    native = _native(
        CANNED_POST,
        waveforms_spec=[{"name": "out", "expr": "v(out)"}],
        waveforms_file=str(dat),
    )
    result = mod.PostLayoutAdapter().parse(native)
    (series,) = result["waveforms"]
    assert series["name"] == "out"
    assert series["count"] == 3
    assert series["samples"] == pytest.approx([0.0, 1.1995, 1.1995], abs=1e-6)


def test_postlayout_parse_tolerates_missing_waveforms():
    mod = _load_adapter()  # RED: missing module
    native = _native(
        CANNED_POST,
        waveforms_spec=[{"name": "out", "expr": "v(out)"}],
        waveforms_file="/nonexistent/postlayout_waveforms.dat",
    )
    result = mod.PostLayoutAdapter().parse(native)
    assert result["waveforms"] == []
    assert result["total"] == 0


def test_postlayout_execute_stages_deck_and_testbench(tmp_path):
    mod = _load_adapter()  # RED: missing module
    bindir = tmp_path / "fakebin"
    bindir.mkdir()
    (bindir / "ngspice").write_text("")
    tb = tmp_path / "tb.spice"
    tb.write_text("C1 out 0 1p\n")
    runner = FakeRunner(CANNED_POST)
    job = _job(
        tmp_path,
        tool_dir=str(bindir),
        testbench=str(tb),
        params={"vsup": 3.3},
        waveforms=[{"name": "out", "expr": "v(out)"}],
    )
    native = mod.PostLayoutAdapter(runner=runner).execute(job)
    workdir = Path(job["workdir"])
    deck = (workdir / "postlayout_deck.spice").read_text()
    assert "Rpar n1 out 5" in deck
    assert "C1 out 0 1p" in deck
    assert ".param vsup=3.3" in deck
    assert "let meas_vout = v(out)" in deck
    assert "wrdata postlayout_waveforms.dat v(out)" in deck
    assert (workdir / ".spiceinit").is_file()
    assert runner.seen["command"][-3:] == [
        "-o", "postlayout.log", "postlayout_deck.spice",
    ]
    assert native["schematic"]["values"]["vout"]["value"] == 1.2


def test_postlayout_execute_omits_wrdata_without_waveforms(tmp_path):
    mod = _load_adapter()  # RED: missing module
    bindir = tmp_path / "fakebin"
    bindir.mkdir()
    (bindir / "ngspice").write_text("")
    runner = FakeRunner(CANNED_POST)
    job = _job(tmp_path, tool_dir=str(bindir))
    mod.PostLayoutAdapter(runner=runner).execute(job)
    deck = (Path(job["workdir"]) / "postlayout_deck.spice").read_text()
    assert "wrdata" not in deck


def test_postlayout_execute_refuses_missing_workdir(tmp_path):
    mod = _load_adapter()  # RED: missing module
    bindir = tmp_path / "fakebin"
    bindir.mkdir()
    (bindir / "ngspice").write_text("")
    job = _job(tmp_path, tool_dir=str(bindir))
    job["workdir"] = str(tmp_path / "no-such-workdir")
    try:
        mod.PostLayoutAdapter(runner=FakeRunner(CANNED_POST)).execute(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_reference"
    else:
        raise AssertionError("expected invalid_reference for missing workdir")


def test_postlayout_runs_executable_end_to_end(tmp_path):
    mod = _load_adapter()  # RED: missing module
    bindir = tmp_path / "fakebin"
    bindir.mkdir()
    fake = bindir / "ngspice"
    fake.write_text("#!/bin/sh\necho 'meas_vout = 1.1995e+00'\n")
    fake.chmod(0o755)
    job = _job(tmp_path, tool_dir=str(bindir))
    adapter = mod.PostLayoutAdapter()
    result = adapter.parse(adapter.execute(job))
    assert result["total"] == 0
    assert result["comparison"][0]["delta"] == pytest.approx(-0.0005, abs=1e-6)


def test_postlayout_dispatches_as_engine_run(tmp_path):
    from rocket_engine.composition import Engine

    mod = _load_adapter()  # RED: missing module
    engine = Engine("postlayout-lane", actor="tester")
    engine.register_solver(
        "run_post_layout",
        mod.PostLayoutAdapter(runner=FakeRunner(CANNED_POST)),
        tool="ngspice",
    )
    job = _job(tmp_path)
    bindir = tmp_path / "fakebin"
    bindir.mkdir()
    (bindir / "ngspice").write_text("")
    out = engine.run(
        {
            "project_id": "postlayout-lane",
            "operation": "run_post_layout",
            "arguments": {
                "extracted_netlist": job["extracted_netlist"],
                "workdir": job["workdir"],
                "tool_dir": str(bindir),
                "measurements": job["measurements"],
                "schematic_run_id": job["schematic_run_id"],
                "schematic_measurements": job["schematic_measurements"],
                "extraction_provenance": job["extraction_provenance"],
                "deck": {"tool": "ngspice"},
            },
        }
    )
    assert out["operation"] == "run_post_layout"
    assert out["run_id"]
    assert out["verdict"]["status"] == "PASS"
    assert out["verdict"]["measurements"][0]["name"] == "vout"
    assert engine.findings(out["run_id"])["findings"] == []


def test_postlayout_build_provenance_hashes_netlist(tmp_path):
    mod = _load_adapter()  # RED: missing module
    staged = tmp_path / "cell.spice"
    staged.write_text("* extracted\n")
    record = mod.build_provenance(
        str(staged), "ext-9", cell="cell", tech="sky130A"
    )
    assert record["extraction_run_id"] == "ext-9"
    assert record["netlist_sha256"] == _sha256(staged)
    assert record["cell"] == "cell"
    assert record["spice_file"] == str(staged)


def test_postlayout_delta_table_renders_rows():
    mod = _load_adapter()  # RED: missing module
    text = mod.delta_table([
        {"name": "vout", "unit": "V", "pre": 1.2, "post": 1.1995,
         "delta": -0.0005, "rel": -0.0005 / 1.2, "status": "pass"},
    ])
    assert "name" in text.splitlines()[0]
    assert "vout" in text
    assert "1.2" in text
    assert "1.1995" in text
    assert "-0.0005" in text
    assert "pass" in text


def _pdk_source():
    """Real PDK model tree, when the machine carries one (else None)."""
    candidates = [
        Path.home() / ".local" / "share" / "pdk" / "sky130A",
        Path("/usr/local/share/pdk/sky130A"),
    ]
    for candidate in candidates:
        if (candidate / MODEL_REL).is_file():
            return candidate
    return None


def _minimal_pdk_pin(tmp_path):
    """Register a minimal real-model store; skip loudly without one."""
    from rocket_engine.interfaces.pdks import register_pdk

    source = _pdk_source()
    if source is None:
        pytest.skip("sky130 PDK source tree absent (no live models)")
    minimal = tmp_path / "minimal_pdk_src"
    target = minimal / "libs.tech" / "combined"
    target.mkdir(parents=True)
    for child in (source / "libs.tech" / "combined").iterdir():
        dest = target / child.name
        if child.is_dir():
            shutil.copytree(child, dest, symlinks=True)
        else:
            shutil.copy2(child, dest)
    engine_root = tmp_path / "engine"
    register_pdk(minimal, "sky130a", "pl-fixture-1", engine_root=engine_root)
    return {"id": "sky130a", "revision": "pl-fixture-1",
            "engine_root": str(engine_root)}


@needs_ngspice
def test_postlayout_rc_divider_live_delta_is_green_and_nonzero(tmp_path):
    from rocket_engine.adapters.ngspice import NgspiceAdapter

    mod = _load_adapter()  # RED: missing module
    workdir = tmp_path / "work"
    workdir.mkdir(exist_ok=True)
    schem = workdir / "rc_schem.spice"
    extracted = workdir / "rc_extracted.spice"
    shutil.copy(FIXTURES / "rc_schem.spice", schem)
    shutil.copy(FIXTURES / "rc_extracted.spice", extracted)
    measurements = [
        {"name": "vout", "expr": "v(out)", "unit": "V",
         "min": 1.199, "max": 1.201},
    ]
    schem_result = NgspiceAdapter().parse(NgspiceAdapter().execute({
        "operation": "run_spice",
        "sources": [str(schem)],
        "workdir": str(workdir),
        "measurements": measurements,
    }))
    assert schem_result["total"] == 0
    pre = schem_result["measurements"][0]["value"]
    assert pre == pytest.approx(1.2, abs=1e-9)
    adapter = mod.PostLayoutAdapter()
    result = adapter.parse(adapter.execute({
        "operation": "run_post_layout",
        "extracted_netlist": str(extracted),
        "workdir": str(workdir),
        "measurements": measurements,
        "schematic_run_id": "schem-live-rc-1",
        "schematic_measurements": [
            {"name": "vout", "value": pre, "unit": "V"},
        ],
        "extraction_provenance": _provenance(extracted, "ext-live-rc-1"),
    }))
    assert result["total"] == 0, result["violations"]
    (row,) = result["comparison"]
    assert row["post"] == pytest.approx(1.1995, abs=1e-4)
    assert row["delta"] != 0.0
    assert abs(row["delta"]) == pytest.approx(0.0005, abs=1e-4)


@needs_ngspice
def test_postlayout_rc_tran_live_waveforms_have_samples(tmp_path):
    mod = _load_adapter()  # RED: missing module
    workdir = tmp_path / "work"
    workdir.mkdir(exist_ok=True)
    extracted = workdir / "rc_extracted.spice"
    shutil.copy(FIXTURES / "rc_extracted.spice", extracted)
    adapter = mod.PostLayoutAdapter()
    result = adapter.parse(adapter.execute({
        "operation": "run_post_layout",
        "extracted_netlist": str(extracted),
        "workdir": str(workdir),
        "analyses": ["tran 1u 20u"],
        "measurements": [
            {"name": "vout", "expr": "mean(v(out))", "unit": "V",
             "min": 1.199, "max": 1.201},
        ],
        "waveforms": [{"name": "out", "expr": "v(out)"}],
        "schematic_run_id": "schem-live-rc-2",
        "schematic_measurements": [
            {"name": "vout", "value": 1.2, "unit": "V"},
        ],
        "extraction_provenance": _provenance(extracted, "ext-live-rc-2"),
    }))
    assert result["total"] == 0, result["violations"]
    (series,) = result["waveforms"]
    assert series["count"] > 0
    assert all(isinstance(v, float) for v in series["samples"])
    assert series["samples"][-1] == pytest.approx(1.1995, abs=1e-3)


@needs_ngspice
def test_postlayout_bandgap_live_delta_is_green_and_nonzero(tmp_path):
    from rocket_engine.adapters.ngspice import NgspiceAdapter

    mod = _load_adapter()  # RED: missing module
    if not BANDGAP_SNAPSHOT.is_file():
        pytest.skip("sky130-bandgap fixture not fetched")
    pdk = _minimal_pdk_pin(tmp_path)
    workdir = tmp_path / "work"
    workdir.mkdir(exist_ok=True)
    schem = workdir / BANDGAP_SNAPSHOT.name
    shutil.copy(BANDGAP_SNAPSHOT, schem)
    extracted = workdir / "bandgap_extracted.spice"
    lines = schem.read_text().splitlines()
    assert lines[-1].strip().lower() == ".end"
    extracted.write_text("\n".join(lines[:-1]) + "\n"
                         "* POSTLAYOUT fixture: drawn-vs-extracted loss.\n"
                         "Rpar_postlayout VREF 0 10Meg\n.end\n")
    measurements = [
        {"name": "vref", "expr": "v(vref)", "unit": "V",
         "min": VREF_MIN, "max": VREF_MAX},
    ]
    base = {
        "params": {"vsup": 3.3},
        "options": ["wnflag=1"],
        "analyses": ["op"],
        "corner": "tt",
        "temp_c": 27,
        "pdk": pdk,
        "timeout_s": 300,
    }
    schem_result = NgspiceAdapter().parse(NgspiceAdapter().execute({
        "operation": "run_spice",
        "sources": [str(schem)],
        "workdir": str(workdir),
        "measurements": measurements,
        **base,
    }))
    assert schem_result["total"] == 0, schem_result.get("violations")
    pre = schem_result["measurements"][0]["value"]
    adapter = mod.PostLayoutAdapter()
    result = adapter.parse(adapter.execute({
        "operation": "run_post_layout",
        "extracted_netlist": str(extracted),
        "workdir": str(workdir),
        "measurements": measurements,
        "schematic_run_id": "schem-live-bandgap-1",
        "schematic_measurements": [
            {"name": "vref", "value": pre, "unit": "V"},
        ],
        "extraction_provenance": _provenance(extracted, "ext-live-bandgap-1"),
        **base,
    }))
    assert result["total"] == 0, result["violations"]
    (row,) = result["comparison"]
    assert row["pre"] == pytest.approx(pre)
    assert row["delta"] != 0.0


@needs_ngspice
def test_postlayout_sdtop_live_delta_is_green_and_nonzero(tmp_path):
    from rocket_engine.adapters.ngspice import NgspiceAdapter
    from rocket_engine.mutate import stage_design_extras

    mod = _load_adapter()  # RED: missing module
    if not SDTOP_PEX.is_file():
        pytest.skip("ttsky-sigma-delta fixture not fetched")
    pdk = _minimal_pdk_pin(tmp_path)
    workdir = tmp_path / "work"
    schem_dir = tmp_path / "schem"
    schem_dir.mkdir(parents=True)
    shutil.copy(SDTOP_PEX, schem_dir / SDTOP_PEX.name)
    schem_args = stage_design_extras("sd_top", schem_dir, ROOT)
    schem_args["workdir"] = str(workdir)
    workdir.mkdir(exist_ok=True)
    for staged in schem_args["sources"]:
        shutil.copy(staged, workdir / Path(staged).name)
    schem_args["sources"] = [str(workdir / Path(s).name)
                              for s in schem_args["sources"]]
    extracted = workdir / "sd_top_extracted.spice"
    pex_text = (workdir / SDTOP_PEX.name).read_text()
    assert pex_text.count("\n.ends") == 1
    extracted.write_text(pex_text.replace(
        "\n.ends",
        "\n* POSTLAYOUT fixture: drawn-vs-extracted leakage loss.\n"
        "Rpar_postlayout UA1 VGND 50Meg\n.ends",
    ))
    measurements = list(schem_args["measurements"])
    base = {
        "analyses": list(schem_args["analyses"]),
        "options": list(schem_args["options"]),
        "params": dict(schem_args["params"]),
        "corner": "tt",
        "temp_c": 27,
        "pdk": pdk,
        "timeout_s": 300,
    }
    schem_result = NgspiceAdapter().parse(NgspiceAdapter().execute({
        "operation": "run_spice",
        "sources": schem_args["sources"],
        "workdir": str(workdir),
        "measurements": measurements,
        **base,
    }))
    assert schem_result["total"] == 0, schem_result.get("violations")
    pre = schem_result["measurements"][0]["value"]
    adapter = mod.PostLayoutAdapter()
    result = adapter.parse(adapter.execute({
        "operation": "run_post_layout",
        "extracted_netlist": str(extracted),
        "testbench": str(workdir / "sd_top_tb.spice"),
        "workdir": str(workdir),
        "measurements": measurements,
        "schematic_run_id": "schem-live-sdtop-1",
        "schematic_measurements": [
            {"name": "int_dc", "value": pre, "unit": "V"},
        ],
        "extraction_provenance": _provenance(extracted, "ext-live-sdtop-1"),
        **base,
    }))
    assert result["total"] == 0, result["violations"]
    (row,) = result["comparison"]
    assert row["pre"] == pytest.approx(pre)
    assert row["delta"] != 0.0
