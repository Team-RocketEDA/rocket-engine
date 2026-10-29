"""EXTRACT-SKY130 RED — Magic extraction + Netgen LVS proof.

Valid RED = `rocket_engine.adapters.extract_magic` and
`rocket_engine.adapters.lvs_netgen` do not exist yet, so every test
fails on ImportError. Known-good cell: sky130_fd_sc_hd__inv_2 from the
registered PDK (mag + spice lib sliced to its subckt, both resolved
via resolve_deck so hashes are checked). Mismatch probe: a single-net
edit (VPB -> VPB_BAD on X3) must FAIL with the edited net named.
Samples are verbatim excerpts of real magic 8.3.685 + netgen 1.5.316
output. Live tests skip (never fake-green) where magic, netgen, or
the PDK decks are absent; parse/flatten units always run.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

CELL = "sky130_fd_sc_hd__inv_2"
TECH_REL = "libs.tech/magic/sky130A.tech"
SETUP_REL = "libs.tech/netgen/sky130A_setup.tcl"
MAG_REL = "libs.ref/sky130_fd_sc_hd/mag/sky130_fd_sc_hd__inv_2.mag"
SPICE_LIB_REL = "libs.ref/sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice"

MISMATCH_OLD = "X3 Y A VPWR VPB sky130_fd_pr__pfet_01v8_hvt"
MISMATCH_NEW = "X3 Y A VPWR VPB_BAD sky130_fd_pr__pfet_01v8_hvt"

MAGIC_SAMPLE_STDOUT = """Magic 8.3 revision 685 - Compiled on Sun Oct 25 03:16:37 PM +04 2026.
Starting magic under Tcl interpreter
Using the terminal as the console.
Using NULL graphics device.
Using technology "sky130A", version 1.0.588-116-g5f09001
Cell sky130_fd_sc_hd__inv_2 read from current working directory
Extracting sky130_fd_sc_hd__inv_2 into sky130_fd_sc_hd__inv_2.ext:
Processing sky130_fd_sc_hd__inv_2
exttospice finished.
"""

LAYOUT_SAMPLE_SPICE = """* NGSPICE file created from sky130_fd_sc_hd__inv_2.ext - technology: sky130A

.subckt sky130_fd_sc_hd__inv_2 A VGND VNB VPB VPWR Y
X0 Y A VPWR VPB sky130_fd_pr__pfet_01v8_hvt ad=0.135 pd=1.27 as=0.26 ps=2.52 w=1 l=0.15
X1 VGND A Y VNB sky130_fd_pr__nfet_01v8 ad=0.169 pd=1.82 as=0.08775 ps=0.92 w=0.65 l=0.15
X2 Y A VGND VNB sky130_fd_pr__nfet_01v8 ad=0.08775 pd=0.92 as=0.169 ps=1.82 w=0.65 l=0.15
X3 VPWR A Y VPB sky130_fd_pr__pfet_01v8_hvt ad=0.26 pd=2.52 as=0.135 ps=1.27 w=1 l=0.15
.ends
"""

MATCH_SAMPLE_REPORT = """Subcircuit summary:
Circuit 1: layout_flat.spice               |Circuit 2: ref_flat.spice
sky130_fd_pr__pfet_01v8_hvt (2->1)         |sky130_fd_pr__pfet_01v8_hvt (2->1)
sky130_fd_pr__nfet_01v8 (2->1)             |sky130_fd_pr__nfet_01v8 (2->1)
Number of devices: 2                       |Number of devices: 2
Number of nets: 6                          |Number of nets: 6
Netlists match uniquely.
Cells have no pins;  pin matching not needed.

Final result: Circuits match uniquely.
.
"""

MISMATCH_SAMPLE_REPORT = """Number of devices: 2 **Mismatch**          |Number of devices: 3 **Mismatch**
Number of nets: 6 **Mismatch**             |Number of nets: 7 **Mismatch**
NET mismatches: Class fragments follow (with fanout counts):
Net: Y                                     |Net: Y
Net: A                                     |Net: A
(no matching net)                          |Net: VPWR
Net: VPWR                                  |Net: VPB_BAD
Net: VPB                                   |Net: VPB
DEVICE mismatches: Class fragments follow (with node fanout counts):
Instance: sky130_fd_pr__pfet_01v8_hvt:0    |Instance: sky130_fd_pr__pfet_01v8_hvt:1
(no matching instance)                     |Instance: sky130_fd_pr__pfet_01v8_hvt:3
Netlists do not match.
Port matching may fail to disambiguate symmetries.

Final result: Netlists do not match.
"""

magic_present = shutil.which("magic") is not None
netgen_present = shutil.which("netgen") is not None
needs_magic = pytest.mark.skipif(not magic_present, reason="magic not installed")
needs_netgen = pytest.mark.skipif(not netgen_present, reason="netgen not installed")
needs_tools = pytest.mark.skipif(
    not (magic_present and netgen_present), reason="magic/netgen not installed"
)


def _resolve_decks():
    try:
        from rocket_engine.interfaces.pdks import list_pdks, resolve_deck
    except Exception:
        pytest.skip("pdk store unavailable")
    try:
        entries = list_pdks()
    except Exception:
        pytest.skip("sky130 PDK deck not registered (ROCKETEDA_HOME)")
    want_rev = os.environ.get("SKY130_PDK_REVISION")
    candidates = [e for e in entries if e.get("id") == "sky130a"]
    if want_rev:
        candidates = [e for e in candidates if e.get("revision") == want_rev]
    if not candidates:
        pytest.skip("sky130 PDK deck not registered (ROCKETEDA_HOME)")
    entry = sorted(candidates, key=lambda e: e["revision"])[0]
    decks = {}
    for key, rel in (
        ("tech", TECH_REL),
        ("setup", SETUP_REL),
        ("mag", MAG_REL),
        ("spice_lib", SPICE_LIB_REL),
    ):
        try:
            hit = resolve_deck(entry["id"], entry["revision"], rel)
        except Exception:
            pytest.skip(f"sky130 deck not resolved: {rel}")
        path = hit.get("path")
        if not path or not Path(path).is_file():
            pytest.skip(f"sky130 deck missing on disk: {rel}")
        decks[key] = path
    return decks


def _mutated(text):
    assert text.count(MISMATCH_OLD) == 1, "mismatch probe site changed"
    return text.replace(MISMATCH_OLD, MISMATCH_NEW)


def _extract_job(decks, tmp_path):
    workdir = tmp_path / "work"
    workdir.mkdir(exist_ok=True)
    cell_file = workdir / f"{CELL}.mag"
    shutil.copy(decks["mag"], cell_file)
    return {
        "operation": "run_extraction",
        "cell": CELL,
        "cell_file": str(cell_file),
        "tech_file": decks["tech"],
        "workdir": str(workdir),
    }


def _lvs_job(layout_spice, schematic_spice, decks, tmp_path, **over):
    workdir = Path(layout_spice).parent
    job = {
        "operation": "run_lvs",
        "layout_spice": str(layout_spice),
        "schematic_spice": str(schematic_spice),
        "setup_file": decks["setup"],
        "workdir": str(workdir),
    }
    job.update(over)
    return job


def test_extract_adapter_implements_tool_port():
    from rocket_engine.adapters import ToolAdapter  # live surface
    from rocket_engine.adapters.extract_magic import (  # RED: missing adapter
        MagicExtractAdapter,
    )
    from rocket_engine.adapters.lvs_netgen import NetgenLvsAdapter  # RED: missing

    assert issubclass(MagicExtractAdapter, ToolAdapter)
    assert issubclass(NetgenLvsAdapter, ToolAdapter)


def test_extract_capabilities_advertise_run_extraction():
    from rocket_engine.adapters.extract_magic import (  # RED: missing adapter
        MagicExtractAdapter,
    )

    caps = MagicExtractAdapter().capabilities({"cell": CELL})
    assert "run_extraction" in caps["operations"]
    assert caps["tool"] == "magic"


def test_lvs_capabilities_advertise_run_lvs():
    from rocket_engine.adapters.lvs_netgen import NetgenLvsAdapter  # RED: missing

    caps = NetgenLvsAdapter().capabilities({"cell": CELL})
    assert "run_lvs" in caps["operations"]
    assert caps["tool"] == "netgen"


def test_flatten_strips_single_subckt_wrappers():
    from rocket_engine.adapters.lvs_netgen import flatten_spice  # RED: missing

    flat = flatten_spice(LAYOUT_SAMPLE_SPICE)
    assert ".subckt" not in flat.lower()
    assert ".ends" not in flat.lower()
    assert sum(1 for line in flat.splitlines() if line.startswith("X")) == 4


def test_flatten_slices_named_cell_from_library():
    from rocket_engine.adapters.lvs_netgen import flatten_spice  # RED: missing

    lib = (
        ".subckt other A Y\nX0 A Y other_dev w=1 l=1\n.ends\n"
        + LAYOUT_SAMPLE_SPICE
    )
    flat = flatten_spice(lib, CELL)
    assert "other_dev" not in flat
    assert sum(1 for line in flat.splitlines() if line.startswith("X")) == 4


def test_flatten_missing_cell_raises():
    from rocket_engine.adapters.lvs_netgen import flatten_spice  # RED: missing

    try:
        flatten_spice(LAYOUT_SAMPLE_SPICE, "no_such_cell")
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_command"
    else:
        raise AssertionError("expected invalid_command for a missing subckt")


def test_flatten_ambiguous_library_raises():
    from rocket_engine.adapters.lvs_netgen import flatten_spice  # RED: missing

    lib = LAYOUT_SAMPLE_SPICE + LAYOUT_SAMPLE_SPICE.replace(CELL, CELL + "_2")
    try:
        flatten_spice(lib)
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_command"
    else:
        raise AssertionError("expected invalid_command for ambiguous library")


def test_extract_parse_devices_from_sample():
    from rocket_engine.adapters.extract_magic import (  # RED: missing adapter
        MagicExtractAdapter,
    )

    result = MagicExtractAdapter().parse(
        {"stdout": MAGIC_SAMPLE_STDOUT, "spice_text": LAYOUT_SAMPLE_SPICE}
    )
    assert result["device_count"] == 4
    assert result["violations"] == []
    by_class = {}
    for device in result["devices"]:
        by_class.setdefault(device["class"], []).append(device)
    assert sorted(by_class) == [
        "sky130_fd_pr__nfet_01v8",
        "sky130_fd_pr__pfet_01v8_hvt",
    ]
    assert {d["w"] for d in by_class["sky130_fd_pr__nfet_01v8"]} == {0.65}
    assert {d["w"] for d in by_class["sky130_fd_pr__pfet_01v8_hvt"]} == {1.0}
    assert {d["l"] for d in result["devices"]} == {0.15}


def test_extract_parse_without_marker_raises():
    from rocket_engine.adapters.extract_magic import (  # RED: missing adapter
        MagicExtractAdapter,
    )

    try:
        MagicExtractAdapter().parse({"stdout": "nothing here\n"})
    except Exception as exc:
        assert getattr(exc, "code", None) == "runner_unavailable"
    else:
        raise AssertionError("expected runner_unavailable without ext2spice marker")


def test_lvs_parse_match_report():
    from rocket_engine.adapters.lvs_netgen import NetgenLvsAdapter  # RED: missing

    result = NetgenLvsAdapter().parse({"report_text": MATCH_SAMPLE_REPORT})
    assert result["match"] is True
    assert result["total"] == 0
    assert result["violations"] == []


def test_lvs_parse_mismatch_report_names_diffs():
    from rocket_engine.adapters.lvs_netgen import NetgenLvsAdapter  # RED: missing

    result = NetgenLvsAdapter().parse({"report_text": MISMATCH_SAMPLE_REPORT})
    assert result["match"] is False
    assert result["total"] >= 1
    messages = [v["message"] for v in result["violations"]]
    assert any("VPB_BAD" in m for m in messages)
    assert any("sky130_fd_pr__pfet_01v8_hvt:3" in m for m in messages)
    assert any(v["rule"] == "lvs_net_mismatch" for v in result["violations"])
    assert any(v["rule"] == "lvs_device_mismatch" for v in result["violations"])


def test_lvs_parse_without_verdict_raises():
    from rocket_engine.adapters.lvs_netgen import NetgenLvsAdapter  # RED: missing

    try:
        NetgenLvsAdapter().parse({"report_text": "nothing conclusive\n"})
    except Exception as exc:
        assert getattr(exc, "code", None) == "runner_unavailable"
    else:
        raise AssertionError("expected runner_unavailable without LVS verdict")


def test_netgen_env_scrubs_display(monkeypatch):
    from rocket_engine.adapters.lvs_netgen import netgen_env  # RED: missing

    monkeypatch.setenv("DISPLAY", ":1")
    monkeypatch.setenv("KEEP_ME", "yes")
    env = netgen_env()
    assert "DISPLAY" not in env
    assert env["KEEP_ME"] == "yes"


def test_extract_uses_injected_runner(tmp_path):
    import subprocess

    from rocket_engine.adapters.extract_magic import (  # RED: missing adapter
        MagicExtractAdapter,
    )

    seen = {}

    class FakeRunner:
        def run(self, command, workdir, timeout_s=120, extra_binds=(), input_text=None):
            seen["command"] = command
            seen["workdir"] = workdir
            seen["input_text"] = input_text
            return subprocess.CompletedProcess(command, 0, "", "")

    adapter = MagicExtractAdapter(runner=FakeRunner())  # RED: no runner slot
    proc = adapter._run("sky130A", "quit\n", str(tmp_path))
    assert seen["command"][:2] == ["magic", "-dnull"]
    assert seen["workdir"] == str(tmp_path)
    assert seen["input_text"] == "quit\n"
    assert proc.returncode == 0


def test_extract_converts_runner_errors(tmp_path):
    from rocket_engine.adapters.extract_magic import (  # RED: missing adapter
        MagicExtractAdapter,
    )
    from rocket_engine.execution.errors import ExecutionError

    class BoomRunner:
        def run(self, *args, **kwargs):
            raise ExecutionError("runner_unavailable", "boom")

    adapter = MagicExtractAdapter(runner=BoomRunner())
    try:
        adapter._run("sky130A", "quit\n", str(tmp_path))
    except Exception as exc:
        assert getattr(exc, "code", None) == "runner_unavailable"
    else:
        raise AssertionError("expected runner error conversion")


def test_lvs_uses_injected_runner(tmp_path):
    import subprocess

    from rocket_engine.adapters.lvs_netgen import NetgenLvsAdapter  # RED: missing

    seen = {}

    class FakeRunner:
        def run(self, command, workdir, timeout_s=120, extra_binds=()):
            seen["command"] = command
            seen["workdir"] = workdir
            return subprocess.CompletedProcess(command, 0, "", "")

    adapter = NetgenLvsAdapter(runner=FakeRunner())  # RED: no runner slot
    proc = adapter._run(["netgen", "-batch"], str(tmp_path))
    assert seen["command"][:2] == ["netgen", "-batch"]
    assert seen["workdir"] == str(tmp_path)
    assert proc.returncode == 0


def test_lvs_converts_runner_errors(tmp_path):
    from rocket_engine.adapters.lvs_netgen import NetgenLvsAdapter  # RED: missing
    from rocket_engine.execution.errors import ExecutionError

    class BoomRunner:
        def run(self, *args, **kwargs):
            raise ExecutionError("runner_unavailable", "boom")

    adapter = NetgenLvsAdapter(runner=BoomRunner())
    try:
        adapter._run(["netgen", "-batch"], str(tmp_path))
    except Exception as exc:
        assert getattr(exc, "code", None) == "runner_unavailable"
    else:
        raise AssertionError("expected runner error conversion")


@needs_magic
def test_extract_preflight_accepts_tech_file(tmp_path):
    from rocket_engine.adapters.extract_magic import (  # RED: missing adapter
        MagicExtractAdapter,
    )

    decks = _resolve_decks()
    checked = MagicExtractAdapter().preflight(_extract_job(decks, tmp_path))
    assert checked["cell"] == CELL


@needs_magic
def test_extract_preflight_refuses_missing_tech(tmp_path):
    from rocket_engine.adapters.extract_magic import (  # RED: missing adapter
        MagicExtractAdapter,
    )

    decks = _resolve_decks()
    job = _extract_job(decks, tmp_path)
    job["tech_file"] = str(tmp_path / "no-such-tech.tech")
    try:
        MagicExtractAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_reference"
    else:
        raise AssertionError("expected invalid_reference for a missing tech")


@needs_magic
def test_extract_inv2_produces_spice_with_four_fets(tmp_path):
    from rocket_engine.adapters.extract_magic import (  # RED: missing adapter
        MagicExtractAdapter,
    )

    decks = _resolve_decks()
    adapter = MagicExtractAdapter()
    native = adapter.execute(_extract_job(decks, tmp_path))
    assert Path(native["ext_file"]).is_file()
    assert Path(native["spice_file"]).is_file()
    result = adapter.parse(native)
    assert result["device_count"] == 4
    assert result["violations"] == []
    classes = sorted(d["class"] for d in result["devices"])
    assert classes == [
        "sky130_fd_pr__nfet_01v8",
        "sky130_fd_pr__nfet_01v8",
        "sky130_fd_pr__pfet_01v8_hvt",
        "sky130_fd_pr__pfet_01v8_hvt",
    ]


@needs_tools
def test_lvs_good_cell_matches(tmp_path):
    from rocket_engine.adapters.extract_magic import (  # RED: missing adapter
        MagicExtractAdapter,
    )
    from rocket_engine.adapters.lvs_netgen import (  # RED: missing
        NetgenLvsAdapter,
        flatten_spice,
    )

    decks = _resolve_decks()
    workdir = tmp_path / "work"
    workdir.mkdir(exist_ok=True)
    native = MagicExtractAdapter().execute(_extract_job(decks, tmp_path))
    ref_text = flatten_spice(Path(decks["spice_lib"]).read_text(), CELL)
    ref_file = workdir / "ref.spice"
    ref_file.write_text(ref_text)
    result = NetgenLvsAdapter().parse(
        NetgenLvsAdapter().execute(
            _lvs_job(native["spice_file"], ref_file, decks, tmp_path)
        )
    )
    assert result["match"] is True
    assert result["violations"] == []


@needs_tools
def test_lvs_mutated_netlist_mismatches_with_named_diffs(tmp_path):
    from rocket_engine.adapters.extract_magic import (  # RED: missing adapter
        MagicExtractAdapter,
    )
    from rocket_engine.adapters.lvs_netgen import (  # RED: missing
        NetgenLvsAdapter,
        flatten_spice,
    )

    decks = _resolve_decks()
    workdir = tmp_path / "work"
    workdir.mkdir(exist_ok=True)
    native = MagicExtractAdapter().execute(_extract_job(decks, tmp_path))
    bad_file = workdir / "bad.spice"
    bad_file.write_text(
        _mutated(flatten_spice(Path(decks["spice_lib"]).read_text(), CELL))
    )
    result = NetgenLvsAdapter().parse(
        NetgenLvsAdapter().execute(
            _lvs_job(native["spice_file"], bad_file, decks, tmp_path)
        )
    )
    assert result["match"] is False
    messages = [v["message"] for v in result["violations"]]
    assert any("VPB_BAD" in m for m in messages)


@needs_tools
def test_lvs_accepts_library_plus_cell(tmp_path):
    from rocket_engine.adapters.extract_magic import (  # RED: missing adapter
        MagicExtractAdapter,
    )
    from rocket_engine.adapters.lvs_netgen import NetgenLvsAdapter  # RED: missing

    decks = _resolve_decks()
    native = MagicExtractAdapter().execute(_extract_job(decks, tmp_path))
    result = NetgenLvsAdapter().parse(
        NetgenLvsAdapter().execute(
            _lvs_job(native["spice_file"], decks["spice_lib"], decks, tmp_path, cell=CELL)
        )
    )
    assert result["match"] is True


@needs_netgen
def test_lvs_unknown_setup_raises_no_substitute(tmp_path):
    from rocket_engine.adapters.lvs_netgen import NetgenLvsAdapter  # RED: missing

    workdir = tmp_path / "work"
    workdir.mkdir(exist_ok=True)
    layout = workdir / "layout.spice"
    layout.write_text("X0 A Y dev w=1 l=1\n")
    schematic = workdir / "schematic.spice"
    schematic.write_text("X0 A Y dev w=1 l=1\n")
    job = {
        "operation": "run_lvs",
        "layout_spice": str(layout),
        "schematic_spice": str(schematic),
        "setup_file": str(tmp_path / "no-such-setup.tcl"),
        "workdir": str(workdir),
    }
    try:
        NetgenLvsAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_reference"
    else:
        raise AssertionError("expected invalid_reference for a missing setup")


@needs_magic
def test_run_extraction_good_cell_passes(tmp_path):
    from rocket_engine.composition import Engine

    decks = _resolve_decks()
    workdir = tmp_path / "work"
    workdir.mkdir(exist_ok=True)
    cell_file = workdir / f"{CELL}.mag"
    shutil.copy(decks["mag"], cell_file)
    engine = Engine("analog_demo", actor="tester")
    out = engine.run(
        {
            "project_id": "analog_demo",
            "operation": "run_extraction",
            "arguments": {
                "cell": CELL,
                "cell_file": str(cell_file),
                "tech_file": decks["tech"],
                "workdir": str(workdir),
            },
        }
    )
    assert out["verdict"]["status"] == "PASS"


def test_run_lvs_unknown_tool_raises():
    from rocket_engine.composition import Engine

    engine = Engine("analog_demo", actor={"kind": "user"}, catalog_root=".")
    ack = engine.submit(
        {
            "project_id": "analog_demo",
            "operation": "run_lvs",
            "arguments": {
                "expected_revision": "p12",
                "target": {"scope": "project", "id": CELL, "revision": "r1"},
            },
            "request_id": "lvs-unknown-tool",
        }
    )
    try:
        engine.run(
            {
                "project_id": "analog_demo",
                "operation": "run_lvs",
                "arguments": {"deck": {"tool": "no_such_tool"}},
                "snapshot_id": ack["snapshot_id"],
            }
        )
    except Exception as exc:
        assert getattr(exc, "code", None) == "unsupported_operation"
    else:
        raise AssertionError("expected unsupported_operation for unknown deck tool")


@needs_tools
def test_extract_lvs_proves_labels_against_real_tools(tmp_path):
    # Oracle check: labels verified against magic + netgen directly,
    # not against the adapters under test.
    from rocket_engine.adapters.extract_magic import (  # noqa: F401  # RED marker
        MagicExtractAdapter,
    )
    from rocket_engine.adapters.lvs_netgen import (  # noqa: F401  # RED marker
        NetgenLvsAdapter,
    )

    decks = _resolve_decks()
    workdir = tmp_path / "work"
    workdir.mkdir(exist_ok=True)
    shutil.copy(decks["mag"], workdir / f"{CELL}.mag")
    script = (
        f"load {CELL}\nselect top cell\nextract all\n"
        "ext2spice lvs\next2spice\nquit\n"
    )
    proc = subprocess.run(
        ["magic", "-dnull", "-noconsole", "-T", decks["tech"]],
        input=script,
        capture_output=True,
        text=True,
        timeout=120,
        cwd=workdir,
    )
    assert "exttospice finished" in proc.stdout
    layout_text = (workdir / f"{CELL}.spice").read_text()
    assert "sky130_fd_pr__nfet_01v8" in layout_text

    def _flat(text, cell):
        lines = text.splitlines()
        start = next(
            i
            for i, line in enumerate(lines)
            if line.strip().lower().startswith(".subckt")
            and cell.lower() in line.lower()
        )
        end = next(
            i
            for i, line in enumerate(lines)
            if i > start and line.strip().lower().startswith(".ends")
        )
        return "\n".join(
            line
            for line in lines[start + 1 : end]
            if not line.strip().lower().startswith((".subckt", ".ends"))
        )

    lib_text = Path(decks["spice_lib"]).read_text()
    layout_flat = workdir / "oracle_layout.spice"
    layout_flat.write_text(_flat(layout_text, CELL))
    env = dict(os.environ)
    env.pop("DISPLAY", None)
    for tag, schematic_text, want in (
        ("good", _flat(lib_text, CELL), "Circuits match uniquely."),
        ("bad", _mutated(_flat(lib_text, CELL)), "Netlists do not match."),
    ):
        schematic = workdir / f"oracle_{tag}.spice"
        schematic.write_text(schematic_text)
        report = workdir / f"oracle_{tag}.out"
        oracle = subprocess.run(
            [
                "netgen",
                "-batch",
                "lvs",
                str(layout_flat),
                str(schematic),
                decks["setup"],
                str(report),
            ],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=workdir,
            env=env,
        )
        assert oracle.returncode == 0
        assert report.is_file()
        assert want in report.read_text()
    assert "VPB_BAD" in (workdir / "oracle_bad.spice").read_text()
