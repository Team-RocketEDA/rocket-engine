"""VALIDATE-M RED — mixed-signal correctness end-to-end (ttsky-sigma-delta).

Valid RED = the sigma-delta designs do not exist yet in
`rocket_engine.mutate` (KeyError on stage_good_design /
stage_design_extras for "sdm_rx" / "sd_top"), the five seam-pair
operators are not in the registry (KeyError), the committed
sdm_rx Verilog bench is absent (FileNotFoundError), the hdl_sdm /
ngspice_sdtop scenario backends are unknown, and the SEAM-COSIM
follow-up ticket is not tracked — so every staging/mutant/live/
seam test below fails while the oracle/canned/structure tests prove
the parse and quoting paths without the binaries.

Correct = the designer's documented numbers (pthomas ttsky-sigma-delta):
digital wrapper sdm_rx.v (AXI4-Lite + dual sinc3, rtl/sdm_rx.v):
ID 0x53444D31 "SDM1", VERSION 0x0100, OSR_FAST default 25,
OSR_PREC default 250, DC full scale OSR^3 (25^3=15625,
250^3=15625000), BITS_TOTAL/BITS_ONES health metric. Analog macro
sd_top PEX (spice/sd_top_pex.spice, 133 devices, 8-port subckt):
top_tb.py acceptance GATE_DB 36.0 dB on a 2048-bit window
(sig_bin 13, NSETTLE 64, ones gate 0.2-0.8), extracted fast-path
SNDR 38.3-40.7 dB (tier-1 band 36.4-38.0), corners ss 33.4 /
ff 35.3, rebuilt 40.2 dB, pex_bits.txt 2048 bits ones 0.4946
(1013/2048, fs 50 MHz), sd_top DRC 0 / LVS match, frame DRC 0.
Params (params.py): FS 50 MHz, VCM 0.9 / VREFP 1.4 / VREFN 0.4 V,
RIN 132k / RDAC 20k / CINT 2 pF, K_FB 0.25 V, FS_IN +-1.65 V.
Each mutation must flip its e2e to FAIL with its declared rule
and only it. There is NO closed-loop co-sim in the engine: the
digital half verifies live, the analog half verifies structurally
+ canned (live quarantined under NGSPICE-LIVE), and the seam
(one-way pex_bits handoff, no coupled sim) is reported honestly
with closure tracked as follow-up, never cut silently.
"""

import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SIGMA = ROOT / "fixtures" / "upstream" / "ttsky-sigma-delta"
SDM_RX = SIGMA / "rtl" / "sdm_rx.v"
PEX = SIGMA / "spice" / "sd_top_pex.spice"
VECTORS = SIGMA / "rtl" / "tb" / "vectors" / "pex_bits.txt"
PARAMS = SIGMA / "params.py"
TOP_TB = SIGMA / "sim" / "top_tb.py"
DESIGN_MD = SIGMA / "DESIGN.md"
STATUS_MD = SIGMA / "STATUS.md"
ARTIFACTS = ROOT / "tmp" / "validate-m"

# sdm_rx documented register map (rtl/sdm_rx.v header).
SDM_ID = 0x53444D31
SDM_VERSION = 0x0100
OSR_FAST = 25
OSR_PREC = 250
DC_FAST = 25 ** 3  # 15625
DC_PREC = 250 ** 3  # 15625000

# pex_bits.txt documented vector (top_tb.py acceptance run).
PEX_NBITS = 2048
PEX_ONES = 1013
PEX_ONES_DENSITY = 0.4946
PEX_SIG_BIN = 13
PEX_FS_HZ = 50e6

# top_tb.py acceptance gates.
GATE_DB = 36.0
NSETTLE = 64
ONES_MIN = 0.2
ONES_MAX = 0.8

# Extracted vs tier-1 SNDR (STATUS.md snapshot 2026-07-26, top_tb.py).
SNDR_EXTRACTED_LO = 38.3
SNDR_EXTRACTED_HI = 40.7
SNDR_TIER1_LO = 36.4
SNDR_TIER1_HI = 38.0
SNDR_SS = 33.4
SNDR_FF = 35.3
SNDR_REBUILT = 40.2

# PEX structure oracle.
PEX_DEVICES = 133
PEX_SUBCKT = "sd_top UA0 UO0 UO1 CLK VDPWR UA1 VGND VAPWR"

# params.py single source of truth.
P_FS = 50e6
P_VCM = 0.9
P_VREFP = 1.4
P_VREFN = 0.4
P_RIN = 132e3
P_RDAC = 20e3
P_CINT = 2e-12

# Analog run_spice job shape: integrator monitor UA1 DC ~0.9 V mean
# (docs/09b Phase 1.1). Live where ngspice + the sky130 store exist;
# otherwise quarantined under NGSPICE-LIVE with canned-parse pinning.
INT_MIN = 0.8
INT_MAX = 1.0
ORACLE_INT_DC = 0.9

SDM_OP_SEEDS = {
    "sdm_reset_break": [0, 1],
    "sdm_truncation": [0, 1, 2],
    "sdm_unconnected_port": [0, 1],
}
SDTOP_OP_SEEDS = {
    "sdtop_sizing_out_of_spec": [0, 1, 2],
    "sdtop_open_net": [0, 1],
}

SDM_RX_NAME = "sdm_rx.v"
SDM_BENCH_NAME = "sdm_rx_bench.v"
PEX_NAME = "sd_top_pex.spice"
PEX_CLEAN_NAME = "pex_bits_clean.txt"

SEAM_TICKET = ROOT / "docs" / "tickets" / "SEAM-COSIM.md"


def sinc3_model(bits, osr):
    """Golden model with the RTL's exact sampling convention (copied
    verbatim from the vendored cocotb TB test_sdm_rx.py)."""
    i1 = i2 = i3 = 0
    z1 = z2 = z3 = 0
    cnt = 0
    out = []
    for b in bits:
        d = 1 if b else -1
        i3_old, c1 = i3, i3 - z1
        c2 = c1 - z2
        c3 = c2 - z3
        i1, i2, i3 = i1 + d, i2 + i1, i3 + i2
        if cnt == osr - 1:
            cnt = 0
            z1, z2, z3 = i3_old, c1, c2
            out.append(sign32(c3))
        else:
            cnt += 1
    return out


def sign32(v):
    v &= 0xFFFFFFFF
    return v - (1 << 32) if v & 0x80000000 else v


tools_present = shutil.which("iverilog") is not None and shutil.which("vvp") is not None
needs_icarus = pytest.mark.skipif(
    not tools_present,
    reason="VALIDATE-M digital live: iverilog/vvp not on PATH (B10-owned tooling)",
)


def _require_sdm():
    if not SDM_RX.is_file() or not VECTORS.is_file():
        pytest.skip(
            "VALIDATE-M live: ttsky-sigma-delta fixture not fetched "
            "(scripts/fetch_fixtures.py; docs/tickets/VALIDATE-M.md)"
        )


def _require_sdtop():
    if not PEX.is_file():
        pytest.skip(
            "VALIDATE-M live: ttsky-sigma-delta fixture not fetched "
            "(scripts/fetch_fixtures.py; docs/tickets/VALIDATE-M.md)"
        )


def _require_ngspice():
    if shutil.which("ngspice") is None:
        pytest.skip(
            "VALIDATE-M analog live: ngspice not on PATH "
            "(see docs/tickets/NGSPICE-LIVE.md)"
        )


def _require_pdk():
    try:
        from rocket_engine.interfaces.paths import slugify
        from rocket_engine.interfaces.pdks import list_pdks, resolve_deck
    except Exception as exc:
        pytest.skip(
            "VALIDATE-M analog live: pdk store unavailable "
            f"({exc}; see docs/tickets/NGSPICE-LIVE.md)"
        )
    try:
        entries = list_pdks()
    except Exception as exc:
        pytest.skip(
            "VALIDATE-M analog live: sky130 PDK not registered "
            f"({exc}; set ROCKETEDA_HOME; see docs/tickets/NGSPICE-LIVE.md)"
        )
    cands = [e for e in entries
             if slugify(e.get("id") or "") == "sky130a"]
    if not cands:
        pytest.skip(
            "VALIDATE-M analog live: sky130 PDK not registered "
            "(set ROCKETEDA_HOME to a store with sky130A; "
            "see docs/tickets/NGSPICE-LIVE.md)"
        )
    entry = sorted(cands, key=lambda e: e["revision"])[0]
    try:
        resolve_deck(
            entry["id"], entry["revision"], "libs.tech/combined/sky130.lib.spice"
        )
    except Exception as exc:
        pytest.skip(
            "VALIDATE-M analog live: sky130 model lib not resolvable "
            f"({exc}; see docs/tickets/NGSPICE-LIVE.md)"
        )
    return entry


def _engine_run(project, operation, arguments):
    from rocket_engine.composition import Engine

    engine = Engine(project, actor="validate-m")
    out = engine.run({"project_id": project, "operation": operation, "arguments": arguments})
    return engine, out


def _stage_good_digital(dest):
    # RED: stage_good_design rejects "sdm_rx" (KeyError).
    from rocket_engine.mutate import stage_good_design

    return stage_good_design("sdm_rx", dest, ROOT)


def _stage_mut_digital(operator, dest, seed):
    # RED: sdm operators are not in the registry yet.
    from rocket_engine.mutate import OPERATORS, apply_operator, stage_design_extras

    entry = OPERATORS[operator]
    apply_operator(operator, dest, seed, ROOT / entry["base"])
    return stage_design_extras(entry["design"], dest, ROOT)


def _stage_good_analog(dest):
    # RED: stage_good_design rejects "sd_top" (KeyError).
    from rocket_engine.mutate import stage_good_design

    return stage_good_design("sd_top", dest, ROOT)


def _stage_mut_analog(operator, dest, seed):
    # RED: sdtop operators are not in the registry yet.
    from rocket_engine.mutate import OPERATORS, apply_operator, stage_design_extras

    entry = OPERATORS[operator]
    apply_operator(operator, dest, seed, ROOT / entry["base"])
    return stage_design_extras(entry["design"], dest, ROOT)


def _hdl_job(staged):
    return {
        "operation": "run_hdl_test",
        "sources": staged["sources"],
        "workdir": staged["workdir"],
        "timeout_s": staged["timeout_s"],
        "defines": staged["defines"],
        "deck": {"tool": "icarus"},
    }


def _spice_job(staged, pdk_entry):
    return {
        "operation": "run_spice",
        "sources": staged["sources"],
        "workdir": staged["workdir"],
        "timeout_s": staged["timeout_s"],
        "measurements": staged["measurements"],
        "analyses": staged["analyses"],
        "options": staged["options"],
        "params": staged["params"],
        "corner": staged["corner"],
        "temp_c": staged["temp_c"],
        "pdk": {"id": pdk_entry["id"], "revision": pdk_entry["revision"]},
        "deck": {"tool": "ngspice"},
    }


def _native_text(native):
    run = native.get("run") or {}
    return run.get("stdout", "") + "\n" + run.get("stderr", "")


def _canon_findings(findings):
    canon = []
    for finding in findings:
        location = dict(finding.get("location") or {})
        if "file" in location:
            location["file"] = Path(location["file"]).name
        canon.append(
            (
                finding.get("rule"),
                finding.get("severity"),
                finding.get("message"),
                sorted(location.items()),
            )
        )
    return sorted(canon)


def _fixture_pin():
    note = ROOT / "fixtures" / "upstream" / "ttsky-sigma-delta.md"
    rev = None
    if note.is_file():
        for line in note.read_text().splitlines():
            if "pinned rev:" in line:
                rev = line.split("`")[1]
    head = None
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        cwd=SIGMA,
    )
    if proc.returncode == 0:
        head = proc.stdout.strip()
    return rev, head


def _tool_versions():
    versions = {}
    for binary in ("iverilog", "vvp", "ngspice"):
        found = shutil.which(binary)
        versions[binary] = found or "absent"
        if found:
            flag = "--version" if binary == "ngspice" else "-V"
            try:
                proc = subprocess.run(
                    [binary, flag], capture_output=True, text=True, timeout=30
                )
                versions[binary] = (proc.stdout + proc.stderr).splitlines()[0][:120]
            except Exception:
                pass
    return versions


def _write_artifacts(case, *, verdict, findings, native, staged, design, mutation, operation):
    case_dir = ARTIFACTS / case
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "verdict.json").write_text(
        json.dumps({"verdict": verdict, "findings": findings}, indent=2, sort_keys=True) + "\n"
    )
    if operation == "run_hdl_test":
        compile_block = native.get("compile") or {}
        run_block = native.get("run") or {}
        (case_dir / "native.log").write_text(
            "=== compile stdout ===\n"
            + compile_block.get("stdout", "")
            + "\n=== compile stderr ===\n"
            + compile_block.get("stderr", "")
            + "\n=== run stdout ===\n"
            + run_block.get("stdout", "")
            + "\n=== run stderr ===\n"
            + run_block.get("stderr", "")
        )
    else:
        (case_dir / "native.log").write_text(
            "=== deck ===\n"
            + (native.get("deck") or "")
            + "\n=== stdout ===\n"
            + (native.get("stdout") or "")
            + "\n=== stderr ===\n"
            + (native.get("stderr") or "")
            + "\n=== log ===\n"
            + (native.get("log") or "")
        )
    pinned, head = _fixture_pin()
    sources = []
    for path in staged["sources"]:
        digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        sources.append({"name": Path(path).name, "sha256": digest})
    record = {
        "case": case,
        "design": design,
        "engine": {"operation": operation, "project_id": "validate-m"},
        "ingredients": {
            "fixture": {"pinned_rev": pinned, "actual_head": head},
            "sources": sorted(sources, key=lambda s: s["name"]),
            "defines": list(staged.get("defines", [])),
            "timeout_s": staged["timeout_s"],
            "solver": {"tool": operation.split("_")[1], **_tool_versions()},
            "mutation": mutation,
        },
        "results": {"verdict": verdict, "findings": findings},
    }
    (case_dir / "run_record.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n"
    )
    return case_dir


def _spice_measurements():
    return [
        {"name": "int_dc", "expr": "v(ua1)", "unit": "V", "min": INT_MIN, "max": INT_MAX}
    ]


def _op_params(table):
    return [(op, seed) for op, seeds in table.items() for seed in seeds]


def _pex_bits():
    lines = VECTORS.read_text().splitlines()
    header = dict(kv.split("=") for kv in lines[0][2:].split())
    bits = [int(line) for line in lines[1:]]
    return header, bits


# Good-matches-documented: sdm_rx wrapper through the engine.
#
# The vendored cocotb TB (rtl/tb/test_sdm_rx.py, 5/5 green per STATUS.md)
# needs cocotb + cocotbext-axi + numpy, which the engine HdlSimAdapter
# does not run. The committed Verilog bench (tests/adapters/fixtures/
# hdl/sdm_rx_bench.v) reproduces its documented checks without cocotb:
# ID/VERSION/OSR defaults, DC full scale OSR^3, and the committed PEX
# bitstream ones-density + bit-exact golden-model compares.


@needs_icarus
def test_sdm_good_matches_documented_registers(tmp_path):
    from rocket_engine.adapters.hdl_sim import HdlSimAdapter

    _require_sdm()
    staged = _stage_good_digital(tmp_path / "good")
    engine, out = _engine_run("validate_m_sdm_good", "run_hdl_test", _hdl_job(staged))
    assert out["verdict"]["status"] == "PASS", out["verdict"]
    assert engine.findings(out["run_id"])["findings"] == []
    native = HdlSimAdapter().execute(_hdl_job(staged))
    result = HdlSimAdapter().parse(native)
    assert result["total"] == 0, result["violations"]
    text = _native_text(native)
    # Documented: ID "SDM1", VERSION 0x0100, OSR 25/250.
    # (iverilog %X prints lowercase hex.)
    assert "SDM_RX_ID" in text and f"{SDM_ID:08x}" in text.lower()
    assert f"SDM_RX_VERSION {SDM_VERSION:04X}" in text
    assert f"SDM_RX_OSR {OSR_FAST} {OSR_PREC}" in text


@needs_icarus
def test_sdm_good_dc_full_scale_is_osr_cubed(tmp_path):
    from rocket_engine.adapters.hdl_sim import HdlSimAdapter

    _require_sdm()
    staged = _stage_good_digital(tmp_path / "good")
    _, out = _engine_run("validate_m_sdm_dc", "run_hdl_test", _hdl_job(staged))
    assert out["verdict"]["status"] == "PASS", out["verdict"]
    native = HdlSimAdapter().execute(_hdl_job(staged))
    text = _native_text(native)
    # Documented: all-ones DC steady state = OSR^3 (cocotb
    # test_cic_known_patterns asserts model[-1] == 25**3).
    assert f"DC_DATA_FAST {DC_FAST}" in text
    assert text.count("DC_DATA_FAST") >= 1


@needs_icarus
def test_sdm_good_pex_vector_matches_acceptance(tmp_path):
    from rocket_engine.adapters.hdl_sim import HdlSimAdapter

    _require_sdm()
    staged = _stage_good_digital(tmp_path / "good")
    _, out = _engine_run("validate_m_sdm_pex", "run_hdl_test", _hdl_job(staged))
    assert out["verdict"]["status"] == "PASS", out["verdict"]
    native = HdlSimAdapter().execute(_hdl_job(staged))
    text = _native_text(native)
    # Documented: pex_bits.txt header ones=0.4946 over 2048 bits
    # (1013 ones), streamed through the RTL in cocotb
    # test_pex_bitstream with |density - 0.4946| < 1e-3.
    assert f"PEX_BITS {PEX_NBITS} {PEX_ONES}" in text
    match = re.search(r"PEX_DATA_FAST (-?\d+)", text)
    assert match, text[-2000:]
    header, bits = _pex_bits()
    model = sinc3_model(bits, OSR_FAST)
    assert int(match.group(1)) == model[-1]
    match_p = re.search(r"PEX_DATA_PREC (-?\d+)", text)
    assert match_p, text[-2000:]
    model_p = sinc3_model(bits, OSR_PREC)
    assert int(match_p.group(1)) == model_p[-1]


@needs_icarus
def test_sdm_staging_pairs_dut_bench_and_vector(tmp_path):
    _require_sdm()
    # RED: stage_good_design rejects "sdm_rx" (KeyError).
    staged = _stage_good_digital(tmp_path / "good")
    names = sorted(Path(p).name for p in staged["sources"])
    assert names == [SDM_RX_NAME, SDM_BENCH_NAME], names
    assert staged["defines"] == []
    vector = Path(staged["workdir"]) / PEX_CLEAN_NAME
    assert vector.is_file()
    clean = vector.read_text().splitlines()
    assert len(clean) == PEX_NBITS
    assert sum(int(line) for line in clean) == PEX_ONES
    # Staged DUT equals vendored bytes modulo the iverilog-14
    # elaboration shim (one declaration moved earlier, no value
    # change — see stage_design_extras; vendored tree stays pristine).
    dut = Path(staged["workdir"]) / SDM_RX_NAME
    staged_text = dut.read_text()
    vendored_text = SDM_RX.read_text()
    assert staged_text != vendored_text
    strobe_decl = "    reg fast_strobe, prec_strobe;\n"
    assert staged_text.count(strobe_decl) == 1
    assert vendored_text.count(strobe_decl) == 1
    # Removing the moved line from both yields identical bytes.
    assert staged_text.replace(strobe_decl, "") == vendored_text.replace(strobe_decl, "")


# Analog oracles: documented measurements quoted from fixture bytes.
# All run without ngspice (no-silent-skip: live below skips LOUDLY).


def test_sdtop_pex_structure_oracle():
    _require_sdtop()
    text = PEX.read_text()
    assert text.count("\nX") + (1 if text.startswith("X") else 0) >= PEX_DEVICES
    devices = [line for line in text.splitlines() if line.startswith("X")]
    assert len(devices) == PEX_DEVICES, len(devices)
    assert f".subckt {PEX_SUBCKT}" in text
    assert text.strip().endswith(".ends")


def test_pex_vector_oracle():
    _require_sdm()
    header, bits = _pex_bits()
    assert header["nfft"] == str(PEX_NBITS)
    assert header["sig_bin"] == str(PEX_SIG_BIN)
    assert float(header["fs_hz"]) == pytest.approx(PEX_FS_HZ)
    assert float(header["ones"]) == pytest.approx(PEX_ONES_DENSITY, abs=1e-4)
    assert len(bits) == PEX_NBITS
    assert sum(bits) == PEX_ONES
    density = sum(bits) / len(bits)
    assert abs(density - PEX_ONES_DENSITY) < 1e-3


def test_top_tb_gate_oracle():
    _require_sdtop()
    text = TOP_TB.read_text()
    assert f"GATE_DB = {GATE_DB}" in text
    assert f"NSETTLE = {NSETTLE}" in text
    assert "38.3-40.7" in text or "38.3" in text
    assert "36.4-38.0" in text or "36.4" in text


def test_params_oracle():
    _require_sdm()
    text = PARAMS.read_text()
    assert "FS   = 50e6" in text
    assert "VCM   = 0.9" in text
    assert "VREFP = 1.4" in text
    assert "VREFN = 0.4" in text
    assert "RIN  = 132e3" in text
    assert "RDAC = 20e3" in text
    assert "CINT = 2e-12" in text
    assert "OSR_FAST = 25" in text
    assert "OSR_PREC = 250" in text
    assert P_FS == 50e6 and P_VCM == 0.9 and P_RIN == 132e3


def test_status_sndr_quotes():
    _require_sdm()
    text = STATUS_MD.read_text()
    assert "38.3" in text and "40.7" in text
    assert "33.4" in text and "35.3" in text
    assert "40.2 dB" in text
    assert "DRC 0" in text
    assert "5/5" in text or "suite green" in text


def test_design_dac_decision_quote():
    _require_sdm()
    text = DESIGN_MD.read_text()
    # RZ-vs-NRZ paired comparison that locked the DAC choice.
    assert "57.9" in text and "48.4 dB" in text
    assert "61.4" in text and "58.0 dB" in text


# Good-matches-documented: sd_top integrator through the engine.
#
# Live where ngspice + the sky130 store exist; otherwise the oracle
# + canned tests pin the parse path and this skips LOUDLY with the
# NGSPICE-LIVE ref (never fake-green).


def test_sdtop_good_matches_documented_outcome(tmp_path):
    from rocket_engine.adapters.ngspice import NgspiceAdapter

    _require_sdtop()
    # RED: staging rejects "sd_top" before any tool check runs.
    staged = _stage_good_analog(tmp_path / "good")
    _require_ngspice()
    pdk_entry = _require_pdk()
    assert staged["measurements"][0]["min"] == INT_MIN
    assert staged["measurements"][0]["max"] == INT_MAX
    engine, out = _engine_run("validate_m_sdtop_good", "run_spice", _spice_job(staged, pdk_entry))
    assert out["verdict"]["status"] == "PASS", out["verdict"]
    assert engine.findings(out["run_id"])["findings"] == []
    native = NgspiceAdapter().execute(_spice_job(staged, pdk_entry))
    result = NgspiceAdapter().parse(native)
    assert result["total"] == 0, result["violations"]
    value = result["measurements"][0]["value"]
    assert INT_MIN <= value <= INT_MAX, value


# Mutation-flips-only-target: file level (no tool needed).


@pytest.mark.parametrize("operator,seed", _op_params(SDM_OP_SEEDS))
def test_sdm_mutation_targets_vendored_site(operator, seed, tmp_path):
    from rocket_engine.mutate import OPERATORS, apply_operator

    _require_sdm()
    assert OPERATORS[operator]["operation"] == "run_hdl_test"
    assert OPERATORS[operator]["expected_verdict"] == "FAIL"
    assert OPERATORS[operator]["expected_rules"] == ["assert_fatal"]
    dest = tmp_path / "mut"
    evidence = apply_operator(operator, dest, seed, SIGMA / "rtl")
    assert evidence["operator"] == operator
    assert evidence["seed"] == seed
    assert evidence["target_file"] == SDM_RX_NAME
    staged = dest / evidence["target_file"]
    assert staged.is_file()
    base = SDM_RX
    assert staged.read_bytes() != base.read_bytes()


@pytest.mark.parametrize("operator,seed", _op_params(SDTOP_OP_SEEDS))
def test_sdtop_mutation_targets_vendored_site(operator, seed, tmp_path):
    from rocket_engine.mutate import OPERATORS, apply_operator

    _require_sdtop()
    assert OPERATORS[operator]["operation"] == "run_spice"
    assert OPERATORS[operator]["expected_verdict"] == "FAIL"
    assert OPERATORS[operator]["expected_rules"] == ["measurement"]
    dest = tmp_path / "mut"
    evidence = apply_operator(operator, dest, seed, SIGMA / "spice")
    assert evidence["operator"] == operator
    assert evidence["seed"] == seed
    assert evidence["target_file"] == PEX_NAME
    staged = dest / evidence["target_file"]
    assert staged.is_file()
    base = PEX
    assert staged.read_bytes() != base.read_bytes()
    text = staged.read_text()
    if operator == "sdtop_sizing_out_of_spec":
        assert "l=102.57" not in text
        assert f"l={evidence['rin_l']}" in text
    else:
        assert "UA0_OPEN" in text or text.count("\nX64 ") == 0


def test_sdm_operator_files_match_manifest():
    from rocket_engine.mutate import OPERATORS

    for operator in SDM_OP_SEEDS:
        assert OPERATORS[operator]["files"] == [SDM_RX_NAME], operator
        assert OPERATORS[operator]["design"] == "sdm_rx", operator


def test_sdtop_operator_files_match_snapshot():
    from rocket_engine.mutate import OPERATORS

    for operator in SDTOP_OP_SEEDS:
        assert OPERATORS[operator]["files"] == [PEX_NAME], operator
        assert OPERATORS[operator]["design"] == "sd_top", operator


def test_sdtop_staging_emits_top_level_wrapper(tmp_path):
    # The PEX is a bare .subckt (133 devices, .ends, no top-level
    # instantiation): fed to ngspice as-is the top circuit is empty
    # ("KLU Matrix is empty"). The mixed-flow testbench must stage a
    # top-level wrapper instantiating sd_top with supplies, clock,
    # stimulus, and probes. No ngspice needed: this pins the staged
    # bytes, so the failure below is the bench contract, not the sim.
    _require_sdtop()
    staged = _stage_good_analog(tmp_path / "good")
    names = sorted(Path(p).name for p in staged["sources"])
    assert names == [PEX_NAME, "sd_top_tb.spice"], names
    wrapper = Path(staged["workdir"]) / "sd_top_tb.spice"
    text = wrapper.read_text()
    # Top-level instantiation honoring the PEX port order
    # (UA0 UO0 UO1 CLK VDPWR UA1 VGND VAPWR) plus supplies, clock,
    # stimulus, and probe loads. The wrapper instantiates; it must
    # not redefine the macro.
    assert "XDUT ua0 uo0 uo1 clk vdpwr ua1 vgnd vapwr sd_top" in text
    assert ".subckt sd_top" not in text
    # Settled-window transient mean of the integrator monitor: the
    # static loop has no in-band OP (CLK low rails low, CLK high
    # rails high), so an ["op"] probe cannot grade the [0.8, 1.0] V
    # window; the 50 MHz clocked run settles UA1 at ~0.9 V.
    assert staged["measurements"][0]["expr"] == "mean(v(ua1))"
    assert staged["analyses"] == ["tran 0.5n 2u 1u"]


def test_sdtop_staging_clamps_unbinned_startup_fet(tmp_path):
    # X99 (bias-startup PFET, w=5 l=50) sits outside every hv-FET
    # model bin (lmax 20.2 um) in the registered store, so ngspice
    # aborts ("could not find a valid modelname") once a wrapper
    # instantiates the macro. Staging clamps the STAGED copy to the
    # top bin edge (l=20, settled-mean shift vs l=15 is 38 uV);
    # vendored bytes stay pristine.
    _require_sdtop()
    staged = _stage_good_analog(tmp_path / "good")
    staged_pex = Path(staged["workdir"]) / PEX_NAME
    assert "w=5 l=50" not in staged_pex.read_text()
    assert staged_pex.read_text().count("w=5 l=20") == 1
    assert "w=5 l=50" in PEX.read_text()


# Canned-parse proofs (no tool needed): the analog verdict mapping is
# pinned even where ngspice is absent (NGSPICE-LIVE quarantine).


def test_sdtop_parse_good_passes_canned():
    from rocket_engine.adapters.ngspice import NgspiceAdapter

    native = {
        "exit_code": 0,
        "stdout": f"meas_int_dc = {ORACLE_INT_DC}e+00\n",
        "stderr": "",
        "log": "",
        "deck": "ngspice_deck.spice",
        "sources": [PEX_NAME],
        "measurements": _spice_measurements(),
    }
    result = NgspiceAdapter().parse(native)
    assert result["total"] == 0
    assert result["measurements"][0]["status"] == "pass"


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_sdtop_parse_mutated_sizing_fails_canned(tmp_path, seed):
    from rocket_engine.adapters.ngspice import NgspiceAdapter
    from rocket_engine.mutate import apply_operator

    _require_sdtop()
    src = SIGMA / "spice"
    evidence = apply_operator("sdtop_sizing_out_of_spec", tmp_path / "mut", seed, src)
    assert evidence["expected_int_dc"] < INT_MIN or evidence["expected_int_dc"] > INT_MAX
    native = {
        "exit_code": 0,
        "stdout": f"meas_int_dc = {evidence['expected_int_dc']}e+00\n",
        "stderr": "",
        "log": "",
        "deck": "ngspice_deck.spice",
        "sources": [PEX_NAME],
        "measurements": _spice_measurements(),
    }
    result = NgspiceAdapter().parse(native)
    assert result["total"] == 1
    assert result["violations"][0]["rule"] == "measurement"
    assert result["measurements"][0]["status"] == "fail"
    assert result["measurements"][0]["margin"] < 0


@pytest.mark.parametrize("value", [0.0, 3.3])
def test_sdtop_parse_open_net_fails_canned(value):
    # An open is a topology break, not a value change: the RIN input
    # leg is lifted (UA0_OPEN) or the device is commented, so the
    # integrator collapses toward ground or rails toward VAPWR. Either
    # way the [0.8, 1.0] V window misses with rule measurement.
    from rocket_engine.adapters.ngspice import NgspiceAdapter

    native = {
        "exit_code": 0,
        "stdout": f"meas_int_dc = {value}e+00\n",
        "stderr": "",
        "log": "",
        "deck": "ngspice_deck.spice",
        "sources": [PEX_NAME],
        "measurements": _spice_measurements(),
    }
    result = NgspiceAdapter().parse(native)
    assert result["total"] == 1
    assert result["violations"][0]["rule"] == "measurement"


# Mutation-flips-only-target: live rechecks.


@needs_icarus
@pytest.mark.parametrize("operator,seed", _op_params(SDM_OP_SEEDS))
def test_sdm_mutated_fails_only_target(operator, seed, tmp_path):
    _require_sdm()
    staged = _stage_mut_digital(operator, tmp_path / "mut", seed)
    engine, out = _engine_run(f"validate_m_sdm_{seed}", "run_hdl_test", _hdl_job(staged))
    assert out["verdict"]["status"] == "FAIL", (operator, seed, out["verdict"])
    found = engine.findings(out["run_id"])["findings"]
    errors = [f for f in found if f["severity"] == "error"]
    assert errors, (operator, seed)
    assert {f["rule"] for f in errors} == {"assert_fatal"}, (operator, seed, found)


@pytest.mark.parametrize("operator,seed", _op_params(SDTOP_OP_SEEDS))
def test_sdtop_mutated_fails_only_target(operator, seed, tmp_path):
    _require_sdtop()
    # RED: staging rejects "sd_top" before any tool check runs.
    staged = _stage_mut_analog(operator, tmp_path / "mut", seed)
    _require_ngspice()
    pdk_entry = _require_pdk()
    engine, out = _engine_run(f"validate_m_sdtop_{seed}", "run_spice", _spice_job(staged, pdk_entry))
    assert out["verdict"]["status"] == "FAIL", (operator, seed, out["verdict"])
    found = engine.findings(out["run_id"])["findings"]
    errors = [f for f in found if f["severity"] == "error"]
    assert errors, (operator, seed)
    assert {f["rule"] for f in errors} == {"measurement"}, (operator, seed, found)


# Determinism-3x: identical verdicts across repeat runs.


@needs_icarus
def test_sdm_determinism_3x(tmp_path):
    _require_sdm()
    cases = [("good", None, None)]
    cases += [(op, op, seed) for op, seed in _op_params(SDM_OP_SEEDS)]
    for name, operator, seed in cases:
        seen = []
        for rep in range(3):
            dest = tmp_path / f"{name}-{seed}-{rep}"
            if operator is None:
                staged = _stage_good_digital(dest)
            else:
                staged = _stage_mut_digital(operator, dest, seed)
            engine, out = _engine_run(f"validate_m_sdm_det_{rep}", "run_hdl_test", _hdl_job(staged))
            found = engine.findings(out["run_id"])["findings"]
            seen.append((out["verdict"]["status"], _canon_findings(found)))
        assert seen[0] == seen[1] == seen[2], (name, seed, seen)
        want = "PASS" if operator is None else "FAIL"
        assert seen[0][0] == want, (name, seed, seen)


def test_sdtop_determinism_3x(tmp_path):
    _require_sdtop()
    # RED: staging rejects "sd_top" before any tool check runs.
    probe = _stage_good_analog(tmp_path / "probe")
    assert probe["measurements"][0]["min"] == INT_MIN
    _require_ngspice()
    pdk_entry = _require_pdk()
    from rocket_engine.adapters.ngspice import NgspiceAdapter

    cases = [("good", None, None)]
    cases += [(op, op, seed) for op, seed in _op_params(SDTOP_OP_SEEDS)]
    for name, operator, seed in cases:
        seen = []
        for rep in range(3):
            dest = tmp_path / f"{name}-{seed}-{rep}"
            if operator is None:
                staged = _stage_good_analog(dest)
            else:
                staged = _stage_mut_analog(operator, dest, seed)
            job = _spice_job(staged, pdk_entry)
            engine, out = _engine_run(f"validate_m_sdtop_det_{rep}", "run_spice", job)
            found = engine.findings(out["run_id"])["findings"]
            native = NgspiceAdapter().execute(job)
            parsed = NgspiceAdapter().parse(native)
            values = tuple((m["name"], m["value"], m["status"]) for m in parsed.get("measurements", []))
            seen.append((out["verdict"]["status"], _canon_findings(found), values))
        assert seen[0] == seen[1] == seen[2], (name, seed, seen)
        want = "PASS" if operator is None else "FAIL"
        assert seen[0][0] == want, (name, seed, seen)


# Artifacts-kept: verdict JSON + native logs + run record.


@needs_icarus
def test_sdm_failure_artifacts_kept(tmp_path):
    from rocket_engine.adapters.hdl_sim import HdlSimAdapter
    from rocket_engine.mutate import OPERATORS, apply_operator, stage_design_extras

    _require_sdm()
    operator, seed = "sdm_truncation", 0
    dest = tmp_path / "mut"
    evidence = apply_operator(operator, dest, seed, SIGMA / "rtl")
    staged = stage_design_extras(OPERATORS[operator]["design"], dest, ROOT)
    job = _hdl_job(staged)
    engine, out = _engine_run("validate_m_sdm_art", "run_hdl_test", job)
    assert out["verdict"]["status"] == "FAIL"
    native = HdlSimAdapter().execute(job)
    assert HdlSimAdapter().parse(native)["total"] >= 1
    found = engine.findings(out["run_id"])["findings"]
    case_dir = _write_artifacts(
        "sdm_truncation-0",
        verdict=out["verdict"],
        findings=found,
        native=native,
        staged=staged,
        design="sdm_rx",
        mutation=evidence,
        operation="run_hdl_test",
    )
    for name in ("verdict.json", "native.log", "run_record.json"):
        path = case_dir / name
        assert path.is_file(), name
        assert path.stat().st_size > 0, name
    record = json.loads((case_dir / "run_record.json").read_text())
    assert record["ingredients"]["mutation"]["operator"] == operator
    assert len(record["ingredients"]["sources"]) == len(staged["sources"])


def test_sdtop_failure_artifacts_kept(tmp_path):
    from rocket_engine.adapters.ngspice import NgspiceAdapter
    from rocket_engine.mutate import OPERATORS, apply_operator, stage_design_extras

    _require_sdtop()
    operator, seed = "sdtop_sizing_out_of_spec", 0
    # RED: operator missing from the registry (KeyError).
    entry = OPERATORS[operator]
    dest = tmp_path / "mut"
    evidence = apply_operator(operator, dest, seed, ROOT / entry["base"])
    staged = stage_design_extras(entry["design"], dest, ROOT)
    _require_ngspice()
    pdk_entry = _require_pdk()
    job = _spice_job(staged, pdk_entry)
    engine, out = _engine_run("validate_m_sdtop_art", "run_spice", job)
    assert out["verdict"]["status"] == "FAIL"
    native = NgspiceAdapter().execute(job)
    assert NgspiceAdapter().parse(native)["total"] >= 1
    found = engine.findings(out["run_id"])["findings"]
    case_dir = _write_artifacts(
        "sdtop_sizing_out_of_spec-0",
        verdict=out["verdict"],
        findings=found,
        native=native,
        staged=staged,
        design="sd_top",
        mutation=evidence,
        operation="run_spice",
    )
    for name in ("verdict.json", "native.log", "run_record.json"):
        path = case_dir / name
        assert path.is_file(), name
        assert path.stat().st_size > 0, name


# Co-sim seam: honest status, closure tracked as follow-up.
#
# There is NO closed-loop co-sim in the engine. The digital half
# consumes the analog half's RECORDED bitstream (pex_bits.txt, the
# 40.2 dB acceptance run) one-way through the Verilog bench — the
# engine never couples a live analog tran to the RTL in one run.
# This section pins that seam: the handoff works, the gap is named,
# and closure is tracked, never cut silently.


@needs_icarus
def test_seam_handoff_pex_bits_drive_digital(tmp_path):
    # The seam pair: analog's recorded 2048-bit / 0.4946 vector is the
    # digital bench's stimulus; the RTL ones-density registers must
    # reproduce the acceptance metric within the cocotb 1e-3 gate.
    _require_sdm()
    staged = _stage_good_digital(tmp_path / "good")
    _, out = _engine_run("validate_m_seam", "run_hdl_test", _hdl_job(staged))
    assert out["verdict"]["status"] == "PASS", out["verdict"]
    header, bits = _pex_bits()
    assert len(bits) == PEX_NBITS
    assert abs(sum(bits) / len(bits) - float(header["ones"])) < 1e-3


def test_seam_closure_tracked_as_followup():
    # Seam closure is follow-up work, never silent scope-cut: the
    # ticket names the gap (no closed-loop co-sim) and the live
    # analog gate it will close (GATE_DB 36.0 dB).
    assert SEAM_TICKET.is_file(), f"seam follow-up not tracked: {SEAM_TICKET}"
    text = SEAM_TICKET.read_text()
    assert "co-sim" in text.lower() or "cosim" in text.lower()
    assert "VALIDATE-M" in text
    assert "36" in text


def test_seam_closed_loop_wired():
    # SEAM-COSIM closed the loop: run_cosim couples a live analog
    # tran to the RTL in one engine run with joint verdicts. The
    # one-way pex_bits handoff test above stays as the
    # recorded-vector regression; this probe pins the wiring shape
    # (single cosim tool; the halves keep their single tools).
    from rocket_engine.composition import Engine
    from rocket_engine.interfaces.vocabulary import OPERATIONS

    engine = Engine("validate_m_seam_probe", actor="validate-m")
    solvers = engine._solvers
    assert set(solvers.get("run_cosim", {})) == {"cosim"}
    assert "run_mixed_signal" not in solvers
    assert set(solvers.get("run_hdl_test", {})) == {"icarus"}
    assert set(solvers.get("run_spice", {})) == {"ngspice"}
    assert "run_cosim" in OPERATIONS


# Staging guards: unknown designs and missing pieces fail loudly.


def test_stage_sdm_missing_base_raises(tmp_path):
    from rocket_engine.mutate import stage_design_extras

    dest = tmp_path / "mut"
    dest.mkdir()
    try:
        stage_design_extras("sdm_rx", dest, ROOT)
    except KeyError:
        # RED: "sdm_rx" is not a known design yet.
        raise AssertionError("expected FileNotFoundError for missing base")
    except FileNotFoundError as exc:
        assert "base file missing" in str(exc) or "missing" in str(exc).lower()
    else:
        raise AssertionError("expected FileNotFoundError for missing base")


def test_stage_sdtop_missing_base_raises(tmp_path):
    from rocket_engine.mutate import stage_design_extras

    dest = tmp_path / "mut"
    dest.mkdir()
    try:
        stage_design_extras("sd_top", dest, ROOT)
    except KeyError:
        # RED: "sd_top" is not a known design yet.
        raise AssertionError("expected FileNotFoundError for missing base")
    except FileNotFoundError as exc:
        assert "base file missing" in str(exc)
    else:
        raise AssertionError("expected FileNotFoundError for missing base")


def test_stage_unknown_design_raises_key_error(tmp_path):
    from rocket_engine.mutate import stage_good_design

    with pytest.raises(KeyError):
        stage_good_design("not_a_design", tmp_path / "x", ROOT)


# CLI rechecks prove the scripts/mutate.py path on the seam pairs.


@needs_icarus
@pytest.mark.parametrize("operator", ["sdm_reset_break", "sdm_truncation", "sdm_unconnected_port"])
def test_cli_recheck_proves_sdm_flip(operator, tmp_path):
    from rocket_engine.mutate import OPERATORS

    _require_sdm()
    # RED: operator missing from the registry (KeyError).
    assert operator in OPERATORS
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "mutate.py"), "recheck",
         "--operator", operator, "--seed", "0",
         "--dest", str(tmp_path / "recheck")],
        capture_output=True,
        text=True,
        timeout=280,
        cwd=ROOT,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    report = json.loads(proc.stdout)
    assert report["proven"] is True, report
    assert report["good"] == "PASS", report
    assert report["mutated"] == "FAIL", report


@pytest.mark.parametrize("operator", ["sdtop_sizing_out_of_spec", "sdtop_open_net"])
def test_cli_recheck_proves_sdtop_flip_or_quarantines(operator, tmp_path):
    from rocket_engine.mutate import OPERATORS

    _require_sdtop()
    # RED: operator missing from the registry (KeyError).
    assert operator in OPERATORS
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "mutate.py"), "recheck",
         "--operator", operator, "--seed", "0",
         "--dest", str(tmp_path / "recheck")],
        capture_output=True,
        text=True,
        timeout=280,
        cwd=ROOT,
    )
    # Live where ngspice + the sky130 store exist (proven flip);
    # otherwise QUARANTINED with the NGSPICE-LIVE ref, never fake-green.
    if proc.returncode == 2:
        combined = proc.stdout + proc.stderr
        assert "QUARANTINED" in combined
        assert "NGSPICE-LIVE" in combined
        return
    assert proc.returncode == 0, proc.stdout + proc.stderr
    report = json.loads(proc.stdout)
    assert report["proven"] is True, report


