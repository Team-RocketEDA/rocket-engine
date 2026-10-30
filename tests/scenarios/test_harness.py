"""The harness tests itself: a good scenario passes, a bad expectation fails loudly."""

import importlib.util
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent

needs_magic = pytest.mark.skipif(
    shutil.which("magic") is None, reason="magic not installed"
)


def _load_runner():
    spec = importlib.util.spec_from_file_location(
        "scenarios", ROOT / "scripts" / "scenarios.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_happy_scenario_passes():
    runner = _load_runner()
    result = runner.run_scenario(ROOT / "scenarios" / "drc_fake_fail.yaml")
    assert result["passed"] is True
    assert result["failures"] == []


@needs_magic
def test_live_magic_scenarios_pass_against_real_magic():
    runner = _load_runner()
    for name in ("drc_live_pass.yaml", "drc_live_fail.yaml"):
        result = runner.run_scenario(ROOT / "scenarios" / name)
        assert result["passed"] is True, result["failures"]


needs_klayout = pytest.mark.skipif(
    shutil.which("klayout") is None, reason="klayout not installed"
)


@needs_klayout
def test_live_klayout_scenarios_pass_against_real_klayout():
    runner = _load_runner()
    for name in ("drc_live_kl_pass.yaml", "drc_live_kl_fail.yaml"):
        result = runner.run_scenario(ROOT / "scenarios" / name)
        assert result["passed"] is True, result["failures"]


@needs_klayout
def test_live_sky130_scenarios_pass_against_real_deck():
    for name in ("good.gds", "bad.gds"):
        if not (ROOT / "tests" / "adapters" / "fixtures" / "drc_sky130" / name).is_file():
            pytest.skip(f"sky130 fixtures not generated: {name}")
    try:
        from rocket_engine.interfaces.paths import slugify
        from rocket_engine.interfaces.pdks import list_pdks
    except Exception:
        pytest.skip("pdk store unavailable")
    try:
        entries = list_pdks()
    except Exception:
        pytest.skip("sky130 PDK deck not registered (ROCKETEDA_HOME)")
    if not [e for e in entries
            if slugify(e.get("id") or "") == "sky130a"]:
        pytest.skip("sky130 PDK deck not registered (ROCKETEDA_HOME)")
    runner = _load_runner()
    for name in ("drc_sky130_pass.yaml", "drc_sky130_fail.yaml"):
        result = runner.run_scenario(ROOT / "scenarios" / name)
        assert result["passed"] is True, result["failures"]


needs_lvs_tools = pytest.mark.skipif(
    shutil.which("magic") is None or shutil.which("netgen") is None,
    reason="magic/netgen not on PATH",
)


@needs_lvs_tools
def test_live_lvs_scenarios_pass_against_real_tools():
    try:
        from rocket_engine.interfaces.paths import slugify
        from rocket_engine.interfaces.pdks import list_pdks
    except Exception:
        pytest.skip("pdk store unavailable")
    try:
        entries = list_pdks()
    except Exception:
        pytest.skip("sky130 PDK deck not registered (ROCKETEDA_HOME)")
    if not [e for e in entries
            if slugify(e.get("id") or "") == "sky130a"]:
        pytest.skip("sky130 PDK deck not registered (ROCKETEDA_HOME)")
    runner = _load_runner()
    for name in ("lvs_sky130_pass.yaml", "lvs_sky130_fail.yaml"):
        result = runner.run_scenario(ROOT / "scenarios" / name)
        assert result["passed"] is True, result["failures"]


needs_icarus = pytest.mark.skipif(
    shutil.which("iverilog") is None or shutil.which("vvp") is None,
    reason="iverilog/vvp not on PATH",
)


@needs_icarus
def test_live_hdl_scenarios_pass_against_real_tools():
    runner = _load_runner()
    for name in ("hdl_live_pass.yaml", "hdl_live_fail.yaml"):
        result = runner.run_scenario(ROOT / "scenarios" / name)
        assert result["passed"] is True, result["failures"]


@needs_icarus
def test_live_serv_scenarios_pass_against_real_tools():
    if not (ROOT / "fixtures" / "upstream" / "serv" / "rtl" / "serv_top.v").is_file():
        pytest.skip("serv fixture not fetched (fixtures/upstream/serv)")
    runner = _load_runner()
    for name in ("serv_live_pass.yaml", "serv_live_fail.yaml"):
        result = runner.run_scenario(ROOT / "scenarios" / name)
        assert result["passed"] is True, result["failures"]


@needs_icarus
def test_live_picorv32_scenarios_pass_against_real_tools():
    if not (ROOT / "fixtures" / "upstream" / "picorv32" / "picorv32.v").is_file():
        pytest.skip("picorv32 fixture not fetched (fixtures/upstream/picorv32)")
    runner = _load_runner()
    for name in ("picorv32_live_pass.yaml", "picorv32_live_fail.yaml"):
        result = runner.run_scenario(ROOT / "scenarios" / name)
        assert result["passed"] is True, result["failures"]


@needs_icarus
def test_live_sdm_scenarios_pass_against_real_tools():
    # RED: unknown backend hdl_sdm.
    if not (
        ROOT / "fixtures" / "upstream" / "ttsky-sigma-delta" / "rtl" / "sdm_rx.v"
    ).is_file():
        pytest.skip("ttsky-sigma-delta fixture not fetched (fixtures/upstream/ttsky-sigma-delta)")
    runner = _load_runner()
    for name in ("hdl_sdm_pass.yaml", "hdl_sdm_fail.yaml"):
        result = runner.run_scenario(ROOT / "scenarios" / name)
        assert result["passed"] is True, result["failures"]


needs_ngspice = pytest.mark.skipif(
    shutil.which("ngspice") is None, reason="ngspice not on PATH"
)


@needs_ngspice
def test_live_ngspice_bandgap_scenarios_pass_against_real_tools():
    snapshot = (
        ROOT
        / "fixtures"
        / "upstream"
        / "sky130-bandgap"
        / "sim"
        / "output-voltage-tc"
        / "netlist-snapshots"
        / "20260817-015751-13476b7.spice"
    )
    if not snapshot.is_file():
        pytest.skip("sky130-bandgap fixture not fetched")
    try:
        from rocket_engine.interfaces.paths import slugify
        from rocket_engine.interfaces.pdks import list_pdks
    except Exception:
        pytest.skip("pdk store unavailable")
    try:
        entries = list_pdks()
    except Exception:
        pytest.skip("sky130 PDK deck not registered (ROCKETEDA_HOME)")
    if not [e for e in entries
            if slugify(e.get("id") or "") == "sky130a"]:
        pytest.skip("sky130 PDK deck not registered (ROCKETEDA_HOME)")
    runner = _load_runner()
    for name in ("ngspice_bandgap_pass.yaml", "ngspice_bandgap_fail.yaml"):
        result = runner.run_scenario(ROOT / "scenarios" / name)
        assert result["passed"] is True, result["failures"]


def test_sdtop_scenarios_pass_or_quarantine_loudly():
    # No bare skip: with ngspice + the sky130 store the pair runs
    # live; without them both fail environmentally naming the tool /
    # store + the NGSPICE-LIVE ref. RED: unknown backend ngspice_sdtop.
    snapshot = (
        ROOT
        / "fixtures"
        / "upstream"
        / "ttsky-sigma-delta"
        / "spice"
        / "sd_top_pex.spice"
    )
    if not snapshot.is_file():
        pytest.skip("ttsky-sigma-delta fixture not fetched")
    try:
        from rocket_engine.interfaces.paths import slugify
        from rocket_engine.interfaces.pdks import list_pdks
    except Exception:
        list_pdks = None
    store_ok = False
    if list_pdks is not None:
        try:
            entries = list_pdks()
            store_ok = any(slugify(e.get("id") or "") == "sky130a"
                           for e in entries)
        except Exception:
            store_ok = False
    live = shutil.which("ngspice") is not None and store_ok
    runner = _load_runner()
    for name in ("ngspice_sdtop_pass.yaml", "ngspice_sdtop_fail.yaml"):
        result = runner.run_scenario(ROOT / "scenarios" / name)
        if live:
            assert result["passed"] is True, result["failures"]
        else:
            assert result["passed"] is False, name
            msg = result["failures"][0]
            assert ("ngspice not on PATH" in msg) or ("not registered" in msg) or (
                "not resolvable" in msg
            ), result["failures"]
            assert ("NGSPICE-LIVE" in msg) or ("ROCKETEDA_HOME" in msg) or (
                "not on PATH" in msg
            ), result["failures"]


def test_sax_mzi_scenarios_pass_or_quarantine_loudly():
    # No bare skip: with sax the pair runs live; without it both
    # fail environmentally naming sax + the B10 ref. RED: unknown
    # backend sax_mzi.
    if not (
        ROOT / "fixtures" / "upstream" / "cspdk" / "tests" / "gds_ref_si340"
        / "mzi.gds"
    ).is_file():
        pytest.skip("cspdk fixture not fetched (fixtures/upstream/cspdk)")
    runner = _load_runner()
    sax_present = importlib.util.find_spec("sax") is not None
    for name in ("sax_mzi_pass.yaml", "sax_mzi_fail.yaml"):
        result = runner.run_scenario(ROOT / "scenarios" / name)
        if sax_present:
            assert result["passed"] is True, result["failures"]
        else:
            assert result["passed"] is False, name
            assert "sax not installed" in result["failures"][0], result["failures"]
            assert "B10-owned" in result["failures"][0], result["failures"]


@needs_klayout
def test_live_klayout_mzi_scenarios_pass_against_real_klayout():
    # RED: unknown backend klayout_mzi.
    if not (
        ROOT / "fixtures" / "upstream" / "cspdk" / "tests" / "gds_ref_si340"
        / "mzi.gds"
    ).is_file():
        pytest.skip("cspdk fixture not fetched (fixtures/upstream/cspdk)")
    runner = _load_runner()
    for name in ("klayout_mzi_pass.yaml", "klayout_mzi_fail.yaml"):
        result = runner.run_scenario(ROOT / "scenarios" / name)
        assert result["passed"] is True, result["failures"]


@needs_icarus
def test_hdl_run_live_without_sources_fails_loudly(tmp_path):
    # Needs the hdl toolchain: on a bare PATH the SCENARIO-PATH
    # startup preflight (correctly) fails before the sources check.
    runner = _load_runner()
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        (ROOT / "scenarios" / "hdl_live_pass.yaml")
        .read_text()
        .replace(
            "run_live: {backend: hdl, sources: [counter.v, tb_pass.v]}",
            "run_live: {backend: hdl}",
        )
    )
    result = runner.run_scenario(bad)
    assert result["passed"] is False
    assert "sources" in result["failures"][0]


# --- SCENARIO-PATH slice 1: startup PATH preflight (RED) ---

def test_required_path_tools_declared_per_backend():
    runner = _load_runner()
    assert runner.required_path_tools(
        {"steps": [{"run_live": {"backend": "hdl", "sources": ["x"]}}]}
    ) == ["iverilog", "vvp"]
    assert runner.required_path_tools(
        {"steps": [{"run_live": {"cell": "good"}}]}
    ) == ["magic"]
    assert runner.required_path_tools(
        {"steps": [{"run_live": {"backend": "extract_lvs_sky130", "cell": "x"}}]}
    ) == ["magic", "netgen"]
    assert runner.required_path_tools({"steps": [{"submit": {}}]}) == []


def test_bare_path_hdl_scenario_fails_at_startup_naming_tool(tmp_path, monkeypatch):
    runner = _load_runner()
    monkeypatch.setenv("PATH", str(tmp_path))  # bare PATH: no tools at all
    result = runner.run_scenario(ROOT / "scenarios" / "hdl_live_pass.yaml")
    assert result["passed"] is False
    assert "startup" in result["failures"][0]
    assert "missing_dependency" in result["failures"][0]
    assert "iverilog" in result["failures"][0]


def test_bare_path_drc_scenario_fails_at_startup_naming_magic(tmp_path, monkeypatch):
    runner = _load_runner()
    monkeypatch.setenv("PATH", str(tmp_path))
    result = runner.run_scenario(ROOT / "scenarios" / "drc_live_pass.yaml")
    assert result["passed"] is False
    assert "startup" in result["failures"][0]
    assert "missing_dependency" in result["failures"][0]
    assert "magic" in result["failures"][0]


# --- SCENARIO-PATH slice 2: reason inline + PATH contract doc (RED) ---

@needs_magic
def test_assert_verdict_mismatch_inlines_not_run_reason(tmp_path):
    runner = _load_runner()
    bad = tmp_path / "bad-tech.yaml"
    bad.write_text(
        (ROOT / "scenarios" / "drc_live_pass.yaml")
        .read_text()
        .replace(
            "run_live: {cell: good, tech: scmos}",
            "run_live: {cell: good, tech: bogus-tech}",
        )
    )
    result = runner.run_scenario(bad)
    assert result["passed"] is False
    assert "NOT_RUN" in result["failures"][0]
    assert "Cannot load magic tech" in result["failures"][0]


def test_path_contract_documented():
    text = (ROOT / "scenarios" / "README.md").read_text()
    assert "oss-cad-suite" in text
    assert "iverilog" in text
    assert "missing_dependency" in text


def test_bare_path_ngspice_preflight_keeps_ticket_ref(tmp_path, monkeypatch):
    runner = _load_runner()
    monkeypatch.setenv("PATH", str(tmp_path))
    result = runner.run_scenario(ROOT / "scenarios" / "ngspice_bandgap_pass.yaml")
    assert result["passed"] is False
    assert "ngspice" in result["failures"][0]
    assert "NGSPICE-LIVE" in result["failures"][0]


def test_broken_expectation_names_the_step(tmp_path):
    runner = _load_runner()
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        (ROOT / "scenarios" / "drc_fake_fail.yaml")
        .read_text()
        .replace("assert_verdict: FAIL", "assert_verdict: PASS")
    )
    result = runner.run_scenario(bad)
    assert result["passed"] is False
    assert "step 3 (assert_verdict)" in result["failures"][0]


def test_lvs_startup_rejects_mesher_impostor(tmp_path, monkeypatch):
    # RED: an impostor netgen on PATH must fail at startup with
    # a naming cause — never slip to a mid-run error.
    runner = _load_runner()
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "magic").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (bindir / "magic").chmod(0o755)
    (bindir / "netgen").write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "-help" ]; then echo "NETGEN-x Schoeberl"; exit 0; fi\n'
        "exit 1\n",
        encoding="utf-8",
    )
    (bindir / "netgen").chmod(0o755)
    monkeypatch.setenv("PATH", str(bindir))
    result = runner.run_scenario(ROOT / "scenarios" / "lvs_sky130_pass.yaml")
    assert result["passed"] is False
    assert result["failures"][0].startswith("startup"), result["failures"]
    assert "netgen" in result["failures"][0]
    assert "not the LVS netgen" in result["failures"][0]
    assert "NGSPICE-LIVE" in result["failures"][0]
