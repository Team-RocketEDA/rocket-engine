"""MUTATE-HARNESS RED — systematic incorrect-design generator.

Valid RED = `rocket_engine.mutate` does not exist yet, so every
operator test fails on ImportError. Each operator mutates a scratch
COPY of a committed base fixture (never the fixture tree), is
reproducible from its seed, declares its expected verdict, and is
rechecked end-to-end through Engine.run: unmutated PASS, mutated
expected-FAIL, and only the target verdict flips.

Live rechecks run where the tool exists and skip LOUDLY (reason +
ticket ref, never bare) where it does not: ngspice/netgen via
docs/tickets/NGSPICE-LIVE.md, tool-PATH binaries and sax via
B10-owned tooling. Verdict-mapping parse tests use recorded or
declared-canned envelopes so the adapter contract is pinned even
where the binary is absent.
"""

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
HDL_FIXTURES = ROOT / "tests" / "adapters" / "fixtures" / "hdl"
NGSPICE_FIXTURES = ROOT / "tests" / "adapters" / "fixtures" / "ngspice"
DRC_FIXTURES = ROOT / "tests" / "adapters" / "fixtures" / "drc"
SAX_FIXTURES = ROOT / "tests" / "adapters" / "fixtures" / "sax"
LVS_FIXTURES = Path(__file__).parent / "fixtures" / "lvs_inv"

ALL_OPERATORS = [
    "digital_reset_break",
    "digital_truncation",
    "digital_unconnected_port",
    "analog_sizing_out_of_spec",
    "analog_open_net",
    "layout_drc_violation",
    "netlist_lvs_mismatch",
    "photonic_geometry_mistune",
    "photonic_circuit_mistune",
    # VALIDATE-D: the digital shapes reused on the vendored trees.
    "serv_reset_break",
    "serv_truncation",
    "serv_unconnected_port",
    "picorv32_reset_break",
    "picorv32_truncation",
    "picorv32_unconnected_port",
    # VALIDATE-A: the analog shapes reused on the bandgap snapshot.
    "bandgap_sizing_out_of_spec",
    "bandgap_open_net",
]

SERV_UPSTREAM = ROOT / "fixtures" / "upstream" / "serv"
PICO_UPSTREAM = ROOT / "fixtures" / "upstream" / "picorv32"
BANDGAP_SNAPSHOTS = (
    ROOT
    / "fixtures"
    / "upstream"
    / "sky130-bandgap"
    / "sim"
    / "output-voltage-tc"
    / "netlist-snapshots"
)

OPERATOR_SRC = {
    "digital_reset_break": HDL_FIXTURES,
    "digital_truncation": HDL_FIXTURES,
    "digital_unconnected_port": HDL_FIXTURES,
    "analog_sizing_out_of_spec": NGSPICE_FIXTURES,
    "analog_open_net": NGSPICE_FIXTURES,
    "layout_drc_violation": DRC_FIXTURES,
    "netlist_lvs_mismatch": LVS_FIXTURES,
    "photonic_geometry_mistune": SAX_FIXTURES,
    "photonic_circuit_mistune": SAX_FIXTURES,
    "serv_reset_break": SERV_UPSTREAM,
    "serv_truncation": SERV_UPSTREAM,
    "serv_unconnected_port": SERV_UPSTREAM,
    "picorv32_reset_break": PICO_UPSTREAM,
    "picorv32_truncation": PICO_UPSTREAM,
    "picorv32_unconnected_port": PICO_UPSTREAM,
    "bandgap_sizing_out_of_spec": BANDGAP_SNAPSHOTS,
    "bandgap_open_net": BANDGAP_SNAPSHOTS,
}


def _require_src(operator):
    # Vendored-tree operators skip LOUDLY where the fixture was
    # never fetched; committed-fixture operators always run.
    src = OPERATOR_SRC[operator]
    if src == SERV_UPSTREAM:
        marker, design, ticket = src / "rtl" / "serv_top.v", "serv", "VALIDATE-D"
    elif src == PICO_UPSTREAM:
        marker, design, ticket = src / "picorv32.v", "picorv32", "VALIDATE-D"
    elif src == BANDGAP_SNAPSHOTS:
        marker = src / "20260817-015751-13476b7.spice"
        design, ticket = "sky130-bandgap", "VALIDATE-A"
    else:
        return
    if not marker.is_file():
        pytest.skip(
            f"MUTATE-HARNESS {operator} file: {design} fixture not fetched "
            f"(scripts/fetch_fixtures.py; docs/tickets/{ticket}.md)"
        )

needs_icarus = pytest.mark.skipif(
    shutil.which("iverilog") is None or shutil.which("vvp") is None,
    reason="MUTATE-HARNESS digital live: iverilog/vvp not on PATH (B10-owned tooling)",
)
needs_magic = pytest.mark.skipif(
    shutil.which("magic") is None,
    reason="MUTATE-HARNESS layout live: magic not installed (B10-owned tooling)",
)
needs_ngspice = pytest.mark.skipif(
    shutil.which("ngspice") is None,
    reason="MUTATE-HARNESS analog live: ngspice not on PATH "
    "(see docs/tickets/NGSPICE-LIVE.md)",
)
needs_netgen = pytest.mark.skipif(
    shutil.which("netgen") is None,
    reason="MUTATE-HARNESS LVS live: netgen not on PATH "
    "(see docs/tickets/NGSPICE-LIVE.md)",
)
needs_sax = pytest.mark.skipif(
    importlib.util.find_spec("sax") is None,
    reason="MUTATE-HARNESS photonic live: sax not installed, "
    "uv sync --group photonic (B10-owned tooling)",
)


def _apply(operator, tmp_path, seed=0):
    from rocket_engine.mutate import apply_operator  # RED: missing module

    _require_src(operator)
    dest = tmp_path / "mut"
    return apply_operator(operator, dest, seed, OPERATOR_SRC[operator]), dest


def _snapshot(directory):
    return {
        path.name: path.read_bytes()
        for path in sorted(Path(directory).iterdir())
        if path.is_file()
    }


def _run(engine_project, operation, arguments):
    from rocket_engine.composition import Engine

    engine = Engine(engine_project, actor="tester")
    out = engine.run(
        {"project_id": engine_project, "operation": operation, "arguments": arguments}
    )
    return engine, out


# Registry: every operator declared with its expected verdict.
def test_registry_lists_all_seventeen_operators():
    from rocket_engine.mutate import OPERATORS  # RED: missing module

    assert sorted(OPERATORS) == sorted(ALL_OPERATORS)


def test_registry_declares_expected_verdict_per_operator():
    from rocket_engine.mutate import OPERATORS  # RED: missing module

    want_operation = {
        "digital_reset_break": "run_hdl_test",
        "digital_truncation": "run_hdl_test",
        "digital_unconnected_port": "run_hdl_test",
        "analog_sizing_out_of_spec": "run_spice",
        "analog_open_net": "run_spice",
        "layout_drc_violation": "run_drc",
        "netlist_lvs_mismatch": "run_lvs",
        "photonic_geometry_mistune": "run_optical",
        "photonic_circuit_mistune": "run_optical",
        "serv_reset_break": "run_hdl_test",
        "serv_truncation": "run_hdl_test",
        "serv_unconnected_port": "run_hdl_test",
        "picorv32_reset_break": "run_hdl_test",
        "picorv32_truncation": "run_hdl_test",
        "picorv32_unconnected_port": "run_hdl_test",
        "bandgap_sizing_out_of_spec": "run_spice",
        "bandgap_open_net": "run_spice",
    }
    for name in ALL_OPERATORS:
        entry = OPERATORS[name]
        assert entry["operation"] == want_operation[name], name
        assert entry["expected_verdict"] == "FAIL", name
        assert entry["expected_rules"], name
        assert entry["target_file"], name
        assert entry["doc"], name


def test_unknown_operator_raises(tmp_path):
    from rocket_engine.mutate import apply_operator  # RED: missing module

    try:
        apply_operator("no_such_operator", tmp_path / "mut", 0, HDL_FIXTURES)
    except Exception as exc:
        assert type(exc).__name__ in ("KeyError", "ValueError")
    else:
        raise AssertionError("expected KeyError/ValueError for unknown operator")


def test_mutations_doc_maps_every_operator():
    doc = ROOT / "docs" / "mutations.md"
    assert doc.is_file(), "docs/mutations.md missing: operator→verdict map"
    text = doc.read_text()
    for name in ALL_OPERATORS:
        assert name in text, f"{name} missing from docs/mutations.md"
    assert "PASS" in text and "FAIL" in text


def test_cli_lists_operator_map():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "mutate.py"), "list"],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=ROOT,
    )
    assert proc.returncode == 0, proc.stderr
    for name in ALL_OPERATORS:
        assert name in proc.stdout, f"{name} missing from mutate.py list"


def test_cli_apply_stages_copies_not_fixtures(tmp_path):
    before = _snapshot(HDL_FIXTURES)
    dest = tmp_path / "scratch" / "digital_reset_break-0"
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "mutate.py"),
            "apply",
            "--operator",
            "digital_reset_break",
            "--seed",
            "0",
            "--dest",
            str(dest),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=ROOT,
    )
    assert proc.returncode == 0, proc.stderr
    evidence = json.loads(proc.stdout)
    assert evidence["operator"] == "digital_reset_break"
    assert evidence["seed"] == 0
    assert evidence["expected_verdict"] == "FAIL"
    assert (dest / "counter.v").is_file()
    assert (dest / "counter.v").read_bytes() != before["counter.v"]
    assert _snapshot(HDL_FIXTURES) == before


def test_cli_help_names_scratch_default():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "mutate.py"), "apply", "--help"],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=ROOT,
    )
    assert proc.returncode == 0, proc.stderr
    assert "tmp/scratch" in proc.stdout


# File level: copies mutated, fixtures pristine, seeds reproducible.
@pytest.mark.parametrize("operator", ALL_OPERATORS)
def test_mutation_leaves_fixtures_pristine(operator, tmp_path):
    before = _snapshot(OPERATOR_SRC[operator])
    evidence, dest = _apply(operator, tmp_path)
    assert evidence["operator"] == operator
    assert evidence["expected_verdict"] == "FAIL"
    assert evidence["expected_rule"] in evidence["expected_rules"]
    staged = dest / evidence["target_file"]
    assert staged.is_file()
    base = OPERATOR_SRC[operator] / evidence["target_file"]
    assert staged.read_bytes() != base.read_bytes()
    assert _snapshot(OPERATOR_SRC[operator]) == before


@pytest.mark.parametrize("operator", ALL_OPERATORS)
@pytest.mark.parametrize("seed", [0, 7])
def test_mutations_reproducible_from_seed(operator, tmp_path, seed):
    first, dest_a = _apply(operator, tmp_path / "a", seed)
    second, dest_b = _apply(operator, tmp_path / "b", seed)
    assert first == second
    for name in ("target_file",):
        assert (dest_a / first[name]).read_bytes() == (
            dest_b / second[name]
        ).read_bytes()


def _hdl_run(dest, project="digital_mut"):
    staged = [str(dest / "counter.v"), str(dest / "tb_pass.v")]
    return _run(
        project,
        "run_hdl_test",
        {"sources": staged, "workdir": str(dest), "deck": {"tool": "icarus"}},
    )


@needs_icarus
def test_digital_unmutated_passes(tmp_path):
    dest = tmp_path / "good"
    dest.mkdir()
    shutil.copy(HDL_FIXTURES / "counter.v", dest / "counter.v")
    shutil.copy(HDL_FIXTURES / "tb_pass.v", dest / "tb_pass.v")
    engine, out = _hdl_run(dest)
    assert out["verdict"]["status"] == "PASS"
    assert engine.findings(out["run_id"])["findings"] == []


@needs_icarus
@pytest.mark.parametrize(
    "operator,seeds",
    [
        ("digital_reset_break", [0, 1]),
        ("digital_truncation", [0, 1, 2]),
        ("digital_unconnected_port", [0, 1]),
    ],
)
def test_digital_mutated_fails_only_target(operator, tmp_path, seeds):
    for seed in seeds:
        evidence, dest = _apply(operator, tmp_path / f"s{seed}", seed)
        engine, out = _hdl_run(dest, project=f"digital_mut_{seed}")
        assert out["verdict"]["status"] == "FAIL", (operator, seed)
        found = engine.findings(out["run_id"])["findings"]
        assert found, (operator, seed)
        # ONLY the target flips: every error is the expected sim
        # assertion — the mutation broke behavior, not syntax.
        errors = [f for f in found if f["severity"] == "error"]
        assert errors, (operator, seed)
        assert {f["rule"] for f in errors} == set(
            evidence["expected_rules"]
        ), (operator, seed, found)


def test_digital_reset_break_targets_reset_condition(tmp_path):
    evidence, dest = _apply("digital_reset_break", tmp_path, 0)
    assert evidence["target_file"] == "counter.v"
    text = (dest / "counter.v").read_text()
    assert "if (!rst_n)" not in text
    assert text.count("count <=") >= 2


def test_digital_truncation_narrows_count(tmp_path):
    evidence, dest = _apply("digital_truncation", tmp_path, 0)
    mutated = (dest / "counter.v").read_text()
    assert mutated != (HDL_FIXTURES / "counter.v").read_text()
    assert "count <= count + 4'd1;" not in mutated


def test_digital_unconnected_port_opens_harness_wire(tmp_path):
    evidence, dest = _apply("digital_unconnected_port", tmp_path, 0)
    assert evidence["target_file"] == "tb_pass.v"
    mutated = (dest / "tb_pass.v").read_text()
    assert ".rst_n()" in mutated or ".clk()" in mutated


# Analog (run_spice): file + canned-parse proofs always run; live
# rechecks need ngspice (NGSPICE-LIVE) and the PDK-free RC divider.
def _spice_measurements():
    return [
        {"name": "vout", "expr": "v(out)", "unit": "V",
         "min": 1.199, "max": 1.201},
    ]


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_analog_sizing_moves_value_out_of_spec(tmp_path, seed):
    evidence, dest = _apply("analog_sizing_out_of_spec", tmp_path, seed)
    assert evidence["target_file"] == "rc_divider.spice"
    assert evidence["expected_rule"] == "measurement"
    assert evidence["expected_vout"] < 1.199 or evidence["expected_vout"] > 1.201
    text = (dest / "rc_divider.spice").read_text()
    assert "R2 out 0 8k" not in text
    assert f"R2 out 0 {evidence['resistor']}" in text


@pytest.mark.parametrize("seed", [0, 1])
def test_analog_open_net_breaks_divider(tmp_path, seed):
    evidence, dest = _apply("analog_open_net", tmp_path, seed)
    # An open is a topology break, not a value change: the divider
    # loses its load, out rises to the 1.8 V rail, and the vout
    # measurement misses — rule "measurement", mechanism "open".
    assert evidence["expected_rule"] == "measurement"
    text = (dest / "rc_divider.spice").read_text()
    assert "out_open" in text or text.count("\nR2 ") == 0
    assert "4k" in text and "8k" in text


def test_analog_parse_unmutated_passes_canned():
    from rocket_engine.adapters.ngspice import NgspiceAdapter  # live surface

    native = {
        "exit_code": 0,
        "stdout": "meas_vout = 1.2e+00\n",
        "stderr": "",
        "log": "",
        "deck": "ngspice_deck.spice",
        "sources": ["rc_divider.spice"],
        "measurements": _spice_measurements(),
    }
    result = NgspiceAdapter().parse(native)
    assert result["total"] == 0
    assert result["measurements"][0]["status"] == "pass"


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_analog_parse_mutated_sizing_fails_canned(tmp_path, seed):
    from rocket_engine.adapters.ngspice import NgspiceAdapter  # live surface

    evidence, _ = _apply("analog_sizing_out_of_spec", tmp_path, seed)
    native = {
        "exit_code": 0,
        "stdout": f"meas_vout = {evidence['expected_vout']}e+00\n",
        "stderr": "",
        "log": "",
        "deck": "ngspice_deck.spice",
        "sources": ["rc_divider.spice"],
        "measurements": _spice_measurements(),
    }
    result = NgspiceAdapter().parse(native)
    assert result["total"] == 1
    assert result["violations"][0]["rule"] == "measurement"
    assert result["measurements"][0]["status"] == "fail"
    assert result["measurements"][0]["margin"] < 0


def test_analog_parse_open_net_fails_canned():
    from rocket_engine.adapters.ngspice import NgspiceAdapter  # live surface

    # Open divider: no load, out sits at the 1.8 V rail.
    native = {
        "exit_code": 0,
        "stdout": "meas_vout = 1.8e+00\n",
        "stderr": "",
        "log": "",
        "deck": "ngspice_deck.spice",
        "sources": ["rc_divider.spice"],
        "measurements": _spice_measurements(),
    }
    result = NgspiceAdapter().parse(native)
    assert result["total"] == 1
    assert result["violations"][0]["rule"] == "measurement"
    assert result["measurements"][0]["status"] == "fail"


def _spice_run(dest, project="analog_mut"):
    return _run(
        project,
        "run_spice",
        {
            "sources": [str(dest / "rc_divider.spice")],
            "workdir": str(dest),
            "analyses": ["op"],
            "measurements": _spice_measurements(),
            "deck": {"tool": "ngspice"},
        },
    )


@needs_ngspice
def test_analog_unmutated_passes_live(tmp_path):
    dest = tmp_path / "good"
    dest.mkdir()
    shutil.copy(NGSPICE_FIXTURES / "rc_divider.spice", dest / "rc_divider.spice")
    engine, out = _spice_run(dest)
    assert out["verdict"]["status"] == "PASS", out["verdict"]
    assert engine.findings(out["run_id"])["findings"] == []


@needs_ngspice
@pytest.mark.parametrize("operator", ["analog_sizing_out_of_spec", "analog_open_net"])
def test_analog_mutated_fails_live(operator, tmp_path):
    evidence, dest = _apply(operator, tmp_path, 0)
    engine, out = _spice_run(dest)
    assert out["verdict"]["status"] == "FAIL", (operator, out["verdict"])
    found = engine.findings(out["run_id"])["findings"]
    assert found, operator
    assert {f["rule"] for f in found if f["severity"] == "error"} == set(
        evidence["expected_rules"]
    ), (operator, found)


# Layout (run_drc via magic scmos): live on every PATH with magic.
def _drc_run(dest, cell, project="layout_mut"):
    return _run(
        project,
        "run_drc",
        {
            "tech": "scmos",
            "cell": cell,
            "cell_file": str(dest / f"{cell}.mag"),
            "workdir": str(dest),
        },
    )


@needs_magic
def test_drc_unmutated_passes_live(tmp_path):
    dest = tmp_path / "good"
    dest.mkdir()
    shutil.copy(DRC_FIXTURES / "good.mag", dest / "good.mag")
    engine, out = _drc_run(dest, "good")
    assert out["verdict"]["status"] == "PASS", out["verdict"]
    assert engine.findings(out["run_id"])["findings"] == []


@pytest.mark.parametrize("seed", [0, 1])
def test_drc_violation_moves_rect(tmp_path, seed):
    evidence, dest = _apply("layout_drc_violation", tmp_path, seed)
    assert evidence["target_file"] == "good.mag"
    mutated = (dest / "good.mag").read_text()
    assert mutated != (DRC_FIXTURES / "good.mag").read_text()
    assert "rect" in mutated


@needs_magic
@pytest.mark.parametrize("seed", [0, 1])
def test_drc_violation_mutated_fails_live(tmp_path, seed):
    evidence, dest = _apply("layout_drc_violation", tmp_path, seed)
    engine, out = _drc_run(dest, "good", project=f"layout_mut_{seed}")
    assert out["verdict"]["status"] == "FAIL", (seed, out["verdict"])
    found = engine.findings(out["run_id"])["findings"]
    assert found, seed
    assert any(
        evidence["expected_rule"] in f["rule"] for f in found
    ), (seed, evidence, found)
    assert all(len(f["location"]["bbox_lambda"]) == 4 for f in found)


# Netlist (run_lvs via netgen): file + recorded-report proofs always
# run; the live recheck stages PDK lib slices (netgen + store needed).
def test_lvs_pair_sides_match_unmutated():
    layout = (LVS_FIXTURES / "layout.spice").read_bytes()
    schematic = (LVS_FIXTURES / "schematic.spice").read_bytes()
    assert layout == schematic


@pytest.mark.parametrize("seed", [0, 1])
def test_lvs_mismatch_mutates_schematic_only(tmp_path, seed):
    from rocket_engine.adapters.lvs_netgen import flatten_spice  # live surface

    evidence, dest = _apply("netlist_lvs_mismatch", tmp_path, seed)
    assert evidence["target_file"] == "schematic.spice"
    assert evidence["expected_rule"] == "lvs_net_mismatch"
    assert (dest / "layout.spice").read_bytes() == (
        LVS_FIXTURES / "layout.spice"
    ).read_bytes()
    mutated = (dest / "schematic.spice").read_text()
    assert "_BAD" in mutated
    assert evidence["bad_net"] in mutated
    # Both sides still flatten: the mutation renames a net, it does
    # not break the netlist shape.
    flat_layout = flatten_spice((dest / "layout.spice").read_text())
    flat_schematic = flatten_spice(mutated)
    assert flat_layout != flat_schematic
    assert evidence["bad_net"] in flat_schematic


def test_lvs_parse_recorded_match_passes():
    from rocket_engine.adapters.lvs_netgen import NetgenLvsAdapter  # live surface
    from tests.adapters.test_extract_sky130 import (  # verbatim record
        MATCH_SAMPLE_REPORT,
    )

    result = NetgenLvsAdapter().parse({"report_text": MATCH_SAMPLE_REPORT})
    assert result["match"] is True
    assert result["total"] == 0
    assert result["violations"] == []


def test_lvs_parse_recorded_mismatch_fails():
    from rocket_engine.adapters.lvs_netgen import NetgenLvsAdapter  # live surface
    from tests.adapters.test_extract_sky130 import (  # verbatim record
        MISMATCH_SAMPLE_REPORT,
    )

    result = NetgenLvsAdapter().parse({"report_text": MISMATCH_SAMPLE_REPORT})
    assert result["match"] is False
    assert result["total"] >= 1
    assert any(v["rule"] == "lvs_net_mismatch" for v in result["violations"])
    assert any("VPB_BAD" in v["message"] for v in result["violations"])


def _resolve_lvs_store():
    import os

    from rocket_engine.interfaces.pdks import list_pdks, resolve_deck

    try:
        entries = list_pdks()
    except Exception:
        pytest.skip(
            "MUTATE-HARNESS LVS live: sky130 PDK not registered, "
            "set ROCKETEDA_HOME (see docs/tickets/NGSPICE-LIVE.md)"
        )
    want_rev = os.environ.get("SKY130_PDK_REVISION")
    candidates = [e for e in entries if e.get("id") == "sky130a"]
    if want_rev:
        candidates = [e for e in candidates if e.get("revision") == want_rev]
    if not candidates:
        pytest.skip(
            "MUTATE-HARNESS LVS live: sky130 PDK not registered, "
            "set ROCKETEDA_HOME (see docs/tickets/NGSPICE-LIVE.md)"
        )
    entry = sorted(candidates, key=lambda e: e["revision"])[0]
    decks = {}
    for key, rel in (
        ("setup", "libs.tech/netgen/sky130A_setup.tcl"),
        ("spice_lib", "libs.ref/sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice"),
    ):
        try:
            hit = resolve_deck(entry["id"], entry["revision"], rel)
        except Exception:
            pytest.skip(
                "MUTATE-HARNESS LVS live: sky130 deck not resolved: "
                f"{rel} (see docs/tickets/NGSPICE-LIVE.md)"
            )
        decks[key] = hit["path"]
    return decks


@needs_netgen
def test_lvs_mutated_fails_live(tmp_path):
    from rocket_engine.adapters.lvs_netgen import flatten_spice  # live surface
    from rocket_engine.mutate import apply_operator  # RED: missing module

    decks = _resolve_lvs_store()
    lib_text = Path(decks["spice_lib"]).read_text()
    cell = "sky130_fd_sc_hd__inv_2"
    ref_text = flatten_spice(lib_text, cell)
    assert "VPB sky130_fd_pr__pfet_01v8_hvt" in ref_text
    src = tmp_path / "src"
    src.mkdir()
    (src / "layout.spice").write_text(ref_text)
    (src / "schematic.spice").write_text(ref_text)
    evidence = apply_operator("netlist_lvs_mismatch", tmp_path / "mut", 0, src)
    assert evidence["bad_net"] == "VPB_BAD"

    def _lvs_run(schematic, project):
        return _run(
            project,
            "run_lvs",
            {
                "layout_spice": str(src / "layout.spice"),
                "schematic_spice": str(schematic),
                "setup_file": decks["setup"],
                "workdir": str(tmp_path / "work"),
                "deck": {"tool": "netgen"},
            },
        )

    (tmp_path / "work").mkdir(exist_ok=True)
    engine, good = _lvs_run(src / "schematic.spice", "lvs_mut_good")
    assert good["verdict"]["status"] == "PASS", good["verdict"]
    engine, bad = _lvs_run(tmp_path / "mut" / "schematic.spice", "lvs_mut_bad")
    assert bad["verdict"]["status"] == "FAIL", bad["verdict"]
    found = engine.findings(bad["run_id"])["findings"]
    assert any("VPB_BAD" in f["message"] for f in found), found


# Photonic (run_optical via sax): file + canned-envelope proofs always
# run; live rechecks need sax (photonic group, B10-owned tooling).
def _optical_run(dest, spec_name="mzi.yml", project="photonic_mut"):
    return _run(
        project,
        "run_optical",
        {
            "sources": [str(dest / spec_name)],
            "workdir": str(dest),
            "deck": {"tool": "sax"},
        },
    )


def _canned_optical(pairs, targets, spec="mzi.yml"):
    return {
        "exit_code": 0,
        "stdout": json.dumps(
            {
                "ok": True,
                "sax_version": "0.18.2-canned",
                "result": {
                    "wavelength_nm": [1540.0, 1550.0, 1560.0],
                    "transmission": dict(pairs),
                    "ports": ["in0", "out0", "out1"],
                },
            }
        ),
        "stderr": "",
        "spec": spec,
        "targets": list(targets),
    }


def _mzi_targets():
    return [
        {"from": "in0", "to": "out1", "at_nm": 1550.0, "min_db": -0.5},
        {"from": "in0", "to": "out0", "at_nm": 1550.0, "max_db": -40.0},
    ]


@pytest.mark.parametrize("seed", [0, 1])
def test_photonic_geometry_changes_arm_length(tmp_path, seed):
    from rocket_engine.adapters.sax import SaxAdapter  # live surface

    evidence, dest = _apply("photonic_geometry_mistune", tmp_path, seed)
    assert evidence["target_file"] == "mzi.yml"
    assert evidence["expected_rule"] == "transmission"
    assert evidence["arm_delta_um"] != 0
    text = (dest / "mzi.yml").read_text()
    assert "length: 10.0" in text  # top arm untouched
    assert text.count("length: 10.0") == 1  # bottom arm moved
    # The mutated spec is still a valid circuit: preflight needs no sax.
    job = {
        "operation": "run_optical",
        "sources": [str(dest / "mzi.yml")],
        "workdir": str(dest),
    }
    assert SaxAdapter().preflight(job)["spec"].endswith("mzi.yml")


def test_photonic_circuit_changes_coupling(tmp_path):
    from rocket_engine.adapters.sax import SaxAdapter  # live surface

    evidence, dest = _apply("photonic_circuit_mistune", tmp_path, 0)
    assert evidence["target_file"] == "mzi.yml"
    assert evidence["expected_rule"] == "transmission"
    assert evidence["coupling"] != 0.5
    text = (dest / "mzi.yml").read_text()
    assert "coupling: 0.5" in text  # c1 untouched
    assert text.count("coupling: 0.5") == 1  # c2 mistuned
    job = {
        "operation": "run_optical",
        "sources": [str(dest / "mzi.yml")],
        "workdir": str(dest),
    }
    assert SaxAdapter().preflight(job)["spec"].endswith("mzi.yml")


def test_photonic_parse_unmutated_passes_canned():
    from rocket_engine.adapters.sax import SaxAdapter  # live surface

    native = _canned_optical(
        {"in0>out1": [1.0, 1.0, 1.0], "in0>out0": [0.0, 0.0, 0.0]},
        _mzi_targets(),
    )
    result = SaxAdapter().parse(native)
    assert result["total"] == 0
    assert [m["status"] for m in result["measurements"]] == ["pass", "pass"]


def test_photonic_parse_mutated_geometry_fails_canned(tmp_path):
    from rocket_engine.adapters.sax import SaxAdapter  # live surface

    evidence, _ = _apply("photonic_geometry_mistune", tmp_path, 0)
    assert evidence["expected_db"] < -0.5
    native = _canned_optical(
        {
            "in0>out1": [evidence["expected_linear"]] * 3,
            "in0>out0": [1.0 - evidence["expected_linear"]] * 3,
        },
        _mzi_targets(),
    )
    result = SaxAdapter().parse(native)
    assert result["total"] >= 1
    assert all(v["rule"] == "transmission" for v in result["violations"])
    assert result["measurements"][0]["status"] == "fail"
    assert result["measurements"][0]["margin"] < 0


def test_photonic_parse_mutated_circuit_fails_canned(tmp_path):
    from rocket_engine.adapters.sax import SaxAdapter  # live surface

    evidence, _ = _apply("photonic_circuit_mistune", tmp_path, 0)
    assert evidence["expected_db"] < -0.5
    native = _canned_optical(
        {
            "in0>out1": [evidence["expected_linear"]] * 3,
            "in0>out0": [1.0 - evidence["expected_linear"]] * 3,
        },
        _mzi_targets(),
    )
    result = SaxAdapter().parse(native)
    assert result["total"] >= 1
    assert all(v["rule"] == "transmission" for v in result["violations"])


@needs_sax
def test_photonic_unmutated_passes_live(tmp_path):
    dest = tmp_path / "good"
    dest.mkdir()
    shutil.copy(SAX_FIXTURES / "mzi.yml", dest / "mzi.yml")
    engine, out = _optical_run(dest)
    assert out["verdict"]["status"] == "PASS", out["verdict"]
    assert engine.findings(out["run_id"])["findings"] == []


@needs_sax
@pytest.mark.parametrize(
    "operator", ["photonic_geometry_mistune", "photonic_circuit_mistune"]
)
def test_photonic_mutated_fails_live(operator, tmp_path):
    evidence, dest = _apply(operator, tmp_path, 0)
    engine, out = _optical_run(dest)
    assert out["verdict"]["status"] == "FAIL", (operator, out["verdict"])
    found = engine.findings(out["run_id"])["findings"]
    assert found, operator
    assert {f["rule"] for f in found if f["severity"] == "error"} == set(
        evidence["expected_rules"]
    ), (operator, found)


# Guards: drifted sites and bad seeds fail loudly, never silently.
def test_drifted_probe_site_raises_mutation_error(tmp_path):
    from rocket_engine.mutate import MutationError, apply_operator

    src = tmp_path / "src"
    src.mkdir()
    (src / "counter.v").write_text("module counter; // drifted\nendmodule\n")
    (src / "tb_pass.v").write_text("module tb_pass; endmodule\n")
    try:
        apply_operator("digital_reset_break", tmp_path / "mut", 0, src)
    except MutationError as exc:
        assert "digital_reset_break" in str(exc)
    else:
        raise AssertionError("expected MutationError for a drifted site")


def test_non_integer_seed_raises_mutation_error(tmp_path):
    from rocket_engine.mutate import MutationError, apply_operator

    for bad_seed in ("0", 1.5, True, None):
        try:
            apply_operator(
                "digital_reset_break", tmp_path / "mut", bad_seed, HDL_FIXTURES
            )
        except MutationError:
            continue
        raise AssertionError(f"expected MutationError for seed {bad_seed!r}")
