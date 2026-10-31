"""SEAM-COSIM fast suite — run_cosim port, estimator, and joint verdict.

Valid RED = `rocket_engine.adapters.cosim` does not exist yet, so
every adapter-importing test fails on ImportError (the two staging
tests pin the control-free wrapper seam and pass without it). No
tools needed: the port and
preflight run against staged text bodies, the SNDR estimator runs
against the recorded acceptance vector, and the joint verdict runs
against canned natives. Live tier-1/PEX proofs are in
test_cosim_live.py.

Oracles (designer's documented numbers, pthomas ttsky-sigma-delta):
pex_bits.txt is the 40.2 dB acceptance run (2048 bits, bin 13, ones
0.4946); the SNDR estimator must reproduce 40.2 dB from those bytes
with the exact sim/snr.py index arithmetic. Joint rules reuse the
halves' native names so seam mutations keep their declared rules:
quantitative misses (SNDR, ones-density, golden model, handoff)
are rule measurement, digital native violations pass through.
"""

import math
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SIGMA = ROOT / "fixtures" / "upstream" / "ttsky-sigma-delta"
VECTORS = SIGMA / "rtl" / "tb" / "vectors" / "pex_bits.txt"

PEX_NBITS = 2048
PEX_SIG_BIN = 13
PEX_ONES = 1013
PEX_SNDR_DB = 40.2
OSR_FAST = 25
OSR_PREC = 250
GATE_DB = 36.0


def _sinc3_model(bits, osr):
    """Golden model with the RTL's exact sampling convention (copied
    verbatim from the vendored cocotb TB test_sdm_rx.py via
    tests/validate/test_mixed.py — the independent oracle)."""
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
            out.append(_sign32(c3))
        else:
            cnt += 1
    return out


def _sign32(v):
    v &= 0xFFFFFFFF
    return v - (1 << 32) if v & 0x80000000 else v


def _pex_bits():
    lines = VECTORS.read_text().splitlines()
    return [int(line) for line in lines[1:]]


def _bodies(tmp_path):
    analog = tmp_path / "half.spice"
    analog.write_text("* control-free body\nR1 a b 1k\n", encoding="utf-8")
    digital = tmp_path / "dut.v"
    digital.write_text("module dut; endmodule\n", encoding="utf-8")
    return str(analog), str(digital)


def _job(tmp_path, **over):
    analog, digital = _bodies(tmp_path)
    job = {
        "operation": "run_cosim",
        "analog_sources": [analog],
        "digital_sources": [digital],
        "workdir": str(tmp_path),
        "analog": {
            "clock_hz": 50e6,
            "nbits": 2048,
            "nsettle": 64,
            "sig_bin": 13,
            "sample_node": "uo0",
            "sample_threshold_v": 0.9,
        },
    }
    job.update(over)
    return job


def _native_bits(nbits=512, ones=256):
    bits = [1] * ones + [0] * (nbits - ones)
    return bits


def _good_native(tmp_path, sndr_db=37.2):
    from rocket_engine.adapters.cosim import VECTOR_NAME  # RED: missing adapter

    assert VECTOR_NAME == "cosim_bits.txt"
    bits = _native_bits()
    stdout = (
        "SDM_RX_ID 53444D31\n"
        "DC_DATA_FAST 15625\n"
        f"COSIM_BITS {len(bits)} {sum(bits)}\n"
        "COSIM_COUNT_FAST 20\n"
        "COSIM_COUNT_PREC 2\n"
        f"COSIM_DATA_FAST {_sinc3_model(bits, OSR_FAST)[-1]}\n"
        f"COSIM_DATA_PREC {_sinc3_model(bits, OSR_PREC)[-1]}\n"
        "COSIM_PASS\n"
    )
    return {
        "exit_code": 0,
        "analog": {"exit_code": 0, "stdout": "", "stderr": "",
                   "log": "", "deck": "* deck", "sources": ["half.spice"],
                   "csv_rows": 1000, "error": None},
        "digital": {
            "exit_code": 0,
            "compile": {"exit_code": 0, "stdout": "", "stderr": ""},
            "run": {"exit_code": 0, "stdout": stdout, "stderr": ""},
        },
        "bits": bits,
        "ones_density": sum(bits) / len(bits),
        "sndr_db": sndr_db,
        "int_mean_v": 0.9,
        "int_min_v": 0.85,
        "int_max_v": 0.95,
        "nbits": len(bits),
        "sig_bin": 5,
        "osr_fast": OSR_FAST,
        "osr_prec": OSR_PREC,
        "gates": {"gate_db": GATE_DB, "ones_min": 0.2, "ones_max": 0.8},
        "vector_name": VECTOR_NAME,
    }


def test_cosim_adapter_implements_tool_port():
    from rocket_engine.adapters import ToolAdapter  # live surface
    from rocket_engine.adapters.cosim import CosimAdapter  # RED: missing adapter

    assert issubclass(CosimAdapter, ToolAdapter)


def test_cosim_operation_names_run_cosim():
    from rocket_engine.adapters.cosim import OPERATION, TOOL  # RED: missing adapter

    assert OPERATION == "run_cosim"
    assert TOOL == "cosim"


def test_cosim_capabilities_advertise_coupled_solver():
    from rocket_engine.adapters.cosim import CosimAdapter  # RED: missing adapter

    caps = CosimAdapter().capabilities({"top": "sd_top"})
    assert caps["operations"] == ["run_cosim"]
    assert caps["tool"] == "cosim"
    assert caps["analog"] == "ngspice"
    assert caps["digital"] == "icarus"


def test_cosim_preflight_accepts_minimal_valid_job(tmp_path):
    from rocket_engine.adapters.cosim import CosimAdapter  # RED: missing adapter

    checked = CosimAdapter().preflight(_job(tmp_path))
    assert checked["nbits"] == 2048
    assert checked["sig_bin"] == 13
    assert checked["tstop_s"] == pytest.approx((2048 + 64) / 50e6)
    assert checked["gate_db"] == GATE_DB
    assert checked["model_lib"] is None


def test_cosim_preflight_refuses_wrong_operation(tmp_path):
    from rocket_engine.adapters.cosim import CosimAdapter  # RED: missing adapter
    from rocket_engine.adapters.errors import AdapterError

    job = _job(tmp_path, operation="run_spice")
    with pytest.raises(AdapterError) as caught:
        CosimAdapter().preflight(job)
    assert caught.value.code == "unsupported_operation"


def test_cosim_preflight_refuses_missing_sources(tmp_path):
    from rocket_engine.adapters.cosim import CosimAdapter  # RED: missing adapter
    from rocket_engine.adapters.errors import AdapterError

    ghost = str(tmp_path / "ghost.spice")
    with pytest.raises(AdapterError) as caught:
        CosimAdapter().preflight(_job(tmp_path, analog_sources=[ghost]))
    assert caught.value.code == "invalid_reference"
    with pytest.raises(AdapterError) as caught:
        CosimAdapter().preflight(_job(tmp_path, digital_sources=[ghost]))
    assert caught.value.code == "invalid_reference"


@pytest.mark.parametrize("nbits", [0, 100, 2047, 2049, 16384, -64])
def test_cosim_preflight_refuses_bad_nbits(tmp_path, nbits):
    from rocket_engine.adapters.cosim import CosimAdapter  # RED: missing adapter
    from rocket_engine.adapters.errors import AdapterError

    job = _job(tmp_path)
    job["analog"]["nbits"] = nbits
    with pytest.raises(AdapterError) as caught:
        CosimAdapter().preflight(job)
    assert caught.value.code == "invalid_command"


def test_cosim_preflight_refuses_window_shorter_than_osr(tmp_path):
    from rocket_engine.adapters.cosim import CosimAdapter  # RED: missing adapter
    from rocket_engine.adapters.errors import AdapterError

    job = _job(tmp_path)
    job["analog"]["nbits"] = 128
    job["analog"]["sig_bin"] = 5
    with pytest.raises(AdapterError) as caught:
        CosimAdapter().preflight(job)
    assert caught.value.code == "invalid_command"


@pytest.mark.parametrize("sig_bin", [0, 1, 3, 37, 38, 40, 100])
def test_cosim_preflight_refuses_sig_bin_outside_guards(tmp_path, sig_bin):
    from rocket_engine.adapters.cosim import CosimAdapter  # RED: missing adapter
    from rocket_engine.adapters.errors import AdapterError

    job = _job(tmp_path)
    job["analog"]["sig_bin"] = sig_bin
    with pytest.raises(AdapterError) as caught:
        CosimAdapter().preflight(job)
    assert caught.value.code == "invalid_command"


@pytest.mark.parametrize("line", [".tran 0.5n 2u", ".CONTROL", "wrdata f v(x)",
                                  "run", "write rawfile", "plot v(q)"])
def test_cosim_preflight_refuses_control_carrying_bodies(tmp_path, line):
    from rocket_engine.adapters.cosim import CosimAdapter  # RED: missing adapter
    from rocket_engine.adapters.errors import AdapterError

    body = tmp_path / "ctrl.spice"
    body.write_text(f"* body\nR1 a b 1k\n{line}\n", encoding="utf-8")
    with pytest.raises(AdapterError) as caught:
        CosimAdapter().preflight(_job(tmp_path, analog_sources=[str(body)]))
    assert caught.value.code == "invalid_command"


def test_cosim_preflight_refuses_bad_gates(tmp_path):
    from rocket_engine.adapters.cosim import CosimAdapter  # RED: missing adapter
    from rocket_engine.adapters.errors import AdapterError

    job = _job(tmp_path)
    job["analog"]["ones_min"] = 0.8
    with pytest.raises(AdapterError) as caught:
        CosimAdapter().preflight(job)
    assert caught.value.code == "invalid_command"
    job = _job(tmp_path)
    job["analog"]["gate_db"] = 0.0
    with pytest.raises(AdapterError) as caught:
        CosimAdapter().preflight(job)
    assert caught.value.code == "invalid_command"


def test_cosim_preflight_refuses_unresolvable_tools(tmp_path):
    from rocket_engine.adapters.cosim import CosimAdapter  # RED: missing adapter
    from rocket_engine.adapters.errors import AdapterError

    job = _job(tmp_path, tool_dir=str(tmp_path / "no-tools-here"))
    with pytest.raises(AdapterError) as caught:
        CosimAdapter().preflight(job)
    assert caught.value.code == "missing_dependency"


def test_rfft_power_matches_naive_dft():
    from rocket_engine.adapters.cosim import rfft_power  # RED: missing adapter

    samples = [math.sin(2 * math.pi * 5 * k / 256) for k in range(256)]
    got = rfft_power(samples)
    assert len(got) == 129
    for m in (0, 1, 5, 64, 128):
        real = sum(v * math.cos(2 * math.pi * m * k / 256)
                   for k, v in enumerate(samples))
        imag = sum(v * math.sin(2 * math.pi * m * k / 256)
                   for k, v in enumerate(samples))
        assert got[m] == pytest.approx(real * real + imag * imag, rel=1e-9)


def test_rfft_power_refuses_non_power_of_two():
    from rocket_engine.adapters.cosim import rfft_power  # RED: missing adapter

    with pytest.raises(ValueError):
        rfft_power([1.0] * 100)


def test_sndr_recorded_vector_matches_acceptance():
    from rocket_engine.adapters.cosim import sndr_bits  # RED: missing adapter

    if not VECTORS.is_file():
        pytest.skip("ttsky-sigma-delta fixture not fetched")
    bits = _pex_bits()
    assert len(bits) == PEX_NBITS
    assert sum(bits) == PEX_ONES
    samples = [1.0 if b else -1.0 for b in bits]
    value = sndr_bits(samples, OSR_FAST, PEX_SIG_BIN)
    assert value == pytest.approx(PEX_SNDR_DB, abs=0.2)


def test_sndr_constant_bits_is_minus_inf():
    from rocket_engine.adapters.cosim import sndr_bits  # RED: missing adapter

    assert sndr_bits([1.0] * 2048, OSR_FAST, PEX_SIG_BIN) == float("-inf")


def test_sample_mid_period_interpolates_linearly():
    from rocket_engine.adapters.cosim import sample_bits  # RED: missing adapter

    period = 20e-9
    times = [k * 0.5e-9 for k in range(9)]
    values = [float(k) for k in range(9)]
    bits01, bits_pm = sample_bits(times, values, 0, 2, period, 25.0)
    # Mid-period instants 10 ns and 30 ns read past the 4 ns grid, so
    # both clamp to the edge value 8.0 (np.interp semantics): zeros.
    assert bits01 == [0, 0]
    assert bits_pm == [-1.0, -1.0]
    bits01, _ = sample_bits(times, values, 0, 1, 4e-9, 1.0)
    # Mid-period instant 2 ns interpolates exactly to 4.0: a one.
    assert bits01 == [1]


def test_settled_stats_cover_settled_window_only():
    from rocket_engine.adapters.cosim import settled_stats  # RED: missing adapter

    period = 20e-9
    times = [k * period for k in range(6)]
    values = [3.3, 3.3, 0.9, 0.9, 0.9, 0.9]
    mean, low, high = settled_stats(times, values, 2, period)
    assert mean == pytest.approx(0.9)
    assert (low, high) == (0.9, 0.9)


def test_build_cosim_deck_carries_tran_and_single_thread():
    from rocket_engine.adapters.cosim import build_cosim_deck  # RED: missing

    deck = build_cosim_deck(
        "rocket_engine run_cosim", "tt", 27, {"vsup": "3.3"},
        ["wnflag=1"], "/store/sky130.lib.spice", ["R1 a b 1k"],
        "tran 0.5n 2.048u", "uo0", "ua1")
    assert deck.count(".control") == 1
    assert deck.count(".endc") == 1
    assert "set num_threads=1" in deck
    assert "tran 0.5n 2.048u" in deck
    assert "wrdata cosim_out.csv v(uo0) v(ua1)" in deck
    assert '.lib "/store/sky130.lib.spice" tt' in deck
    assert ".param vsup=3.3" in deck
    assert "R1 a b 1k" in deck


def test_parse_good_joint_passes_with_measurements(tmp_path):
    from rocket_engine.adapters.cosim import CosimAdapter  # RED: missing adapter

    result = CosimAdapter().parse(_good_native(tmp_path))
    assert result["total"] == 0
    assert result["violations"] == []
    by_name = {m["name"]: m for m in result["measurements"]}
    assert by_name["sndr_fast_db"]["status"] == "pass"
    assert by_name["sndr_fast_db"]["margin"] == pytest.approx(37.2 - GATE_DB)
    assert by_name["ones_density"]["status"] == "pass"
    assert by_name["data_fast"]["status"] == "pass"
    assert by_name["data_prec"]["status"] == "pass"


def test_parse_sndr_miss_fails_only_measurement(tmp_path):
    from rocket_engine.adapters.cosim import CosimAdapter  # RED: missing adapter

    result = CosimAdapter().parse(_good_native(tmp_path, sndr_db=12.3))
    assert result["total"] == 1
    assert [v["rule"] for v in result["violations"]] == ["measurement"]
    assert "sndr_fast_db" in result["violations"][0]["message"]
    by_name = {m["name"]: m for m in result["measurements"]}
    assert by_name["sndr_fast_db"]["status"] == "fail"
    assert by_name["sndr_fast_db"]["margin"] < 0


def test_parse_ones_miss_fails_only_measurement(tmp_path):
    from rocket_engine.adapters.cosim import CosimAdapter  # RED: missing adapter

    native = _good_native(tmp_path)
    native["ones_density"] = 0.95
    result = CosimAdapter().parse(native)
    assert result["total"] == 1
    assert [v["rule"] for v in result["violations"]] == ["measurement"]
    assert "ones_density" in result["violations"][0]["message"]


def test_parse_rtl_fatal_propagates_only_assert_fatal(tmp_path):
    from rocket_engine.adapters.cosim import CosimAdapter  # RED: missing adapter

    native = _good_native(tmp_path)
    native["digital"]["run"]["stdout"] = "FATAL: sdm_rx_cosim_bench.v:42: oops\n"
    native["digital"]["run"]["exit_code"] = 1
    result = CosimAdapter().parse(native)
    assert result["total"] == 1
    assert [v["rule"] for v in result["violations"]] == ["assert_fatal"]


def test_parse_golden_mismatch_fails_only_measurement(tmp_path):
    from rocket_engine.adapters.cosim import CosimAdapter  # RED: missing adapter

    native = _good_native(tmp_path)
    stdout = native["digital"]["run"]["stdout"]
    model = _sinc3_model(native["bits"], OSR_FAST)[-1]
    native["digital"]["run"]["stdout"] = stdout.replace(
        f"COSIM_DATA_FAST {model}", "COSIM_DATA_FAST 0")
    result = CosimAdapter().parse(native)
    assert result["total"] == 1
    assert [v["rule"] for v in result["violations"]] == ["measurement"]
    assert "data_fast" in result["violations"][0]["message"]


def test_parse_count_mismatch_fails_only_measurement(tmp_path):
    from rocket_engine.adapters.cosim import CosimAdapter  # RED: missing adapter

    native = _good_native(tmp_path)
    stdout = native["digital"]["run"]["stdout"]
    native["digital"]["run"]["stdout"] = stdout.replace(
        "COSIM_COUNT_FAST 20", "COSIM_COUNT_FAST 19")
    result = CosimAdapter().parse(native)
    assert result["total"] == 1
    assert [v["rule"] for v in result["violations"]] == ["measurement"]
    assert "count_fast" in result["violations"][0]["message"]


def test_parse_handoff_mismatch_fails_only_measurement(tmp_path):
    from rocket_engine.adapters.cosim import CosimAdapter  # RED: missing adapter

    native = _good_native(tmp_path)
    stdout = native["digital"]["run"]["stdout"]
    native["digital"]["run"]["stdout"] = stdout.replace(
        "COSIM_BITS 512 256", "COSIM_BITS 512 257")
    result = CosimAdapter().parse(native)
    assert result["total"] == 1
    assert [v["rule"] for v in result["violations"]] == ["measurement"]
    assert "rtl_ones" in result["violations"][0]["message"]


def test_parse_missing_bits_synthesizes_sim_fail(tmp_path):
    from rocket_engine.adapters.cosim import CosimAdapter  # RED: missing adapter

    native = _good_native(tmp_path)
    native["bits"] = None
    native["analog"]["error"] = "Error: KLU Matrix is empty"
    native["digital"] = None
    result = CosimAdapter().parse(native)
    assert result["total"] == 1
    assert [v["rule"] for v in result["violations"]] == ["sim_fail"]
    assert "KLU" in result["violations"][0]["message"]


def test_parse_missing_data_lines_synthesizes_sim_fail(tmp_path):
    from rocket_engine.adapters.cosim import CosimAdapter  # RED: missing adapter

    native = _good_native(tmp_path)
    native["digital"]["run"]["stdout"] = "COSIM_BITS 512 256\nCOSIM_PASS\n"
    result = CosimAdapter().parse(native)
    assert [v["rule"] for v in result["violations"]] == ["sim_fail"]


def test_build_run_record_closes_both_halves(tmp_path):
    from rocket_engine.adapters.cosim import (CosimAdapter,  # RED: missing
                                              build_run_record)

    job = _job(tmp_path)
    native = _good_native(tmp_path)
    parsed = CosimAdapter().parse(native)
    record = build_run_record(
        "can", "sd_top+sdm_rx", job, native, parsed,
        versions={"ngspice": "ngspice-42", "iverilog": "14.0",
                  "vvp": "14.0"})
    assert record["case"] == "can"
    assert record["engine"] == {"operation": "run_cosim"}
    analog = record["ingredients"]["analog"]
    digital = record["ingredients"]["digital"]
    assert analog["solver"] == "ngspice"
    assert digital["solver"] == "icarus"
    assert len(analog["sources"]) == 1
    assert len(digital["sources"]) == 1
    assert len(analog["sources"][0]["sha256"]) == 64
    assert record["ingredients"]["vector"]["sha256"] is not None
    assert record["ingredients"]["sampled_bits"]["sha256"] is not None
    assert record["results"]["total"] == 0


def test_stage_pex_wrapper_honors_documented_deck(tmp_path):
    from .cosim_staging import PEX_SIG_BIN, stage_pex_wrapper

    path = stage_pex_wrapper(tmp_path, 2048, PEX_SIG_BIN)
    text = Path(path).read_text()
    assert "XDUT ua0 uo0 uo1 clk vdpwr ua1 vgnd vapwr sd_top" in text
    assert ".subckt sd_top" not in text
    assert ".tran" not in text and ".control" not in text
    assert "SIN(1.65 0.99 317383)" in text
    assert "PULSE(0 1.8 0 0.2n 0.2n 10.0n 20.0n)" in text


def test_strip_control_body_keeps_circuit_drops_control():
    from .cosim_staging import strip_control_body

    text = strip_control_body(
        "* head\n.options method=gear\nR1 a b 1k\n"
        ".tran 0.5n 1u\n.control\nrun\nwrdata f v(x)\n"
        ".endc\nplot v(x)\n")
    assert ".tran" not in text
    assert ".control" not in text
    assert "wrdata" not in text
    assert "run\n" not in text
    assert ".options method=gear" in text
    assert "R1 a b 1k" in text
