"""SEAM-COSIM staging helpers: sigma-delta halves for run_cosim jobs.

The CosimAdapter itself stays project-agnostic (sources plus loop
config arrive through the job, never from fixtures). These helpers
carry the sigma-delta fixture knowledge instead: the PEX stimuli
wrapper quoted from the designer's sim/top_tb.py deck, the tier-1
behavioral body generated from the vendored xschem schematic, and
the digital half staged through the shipped MUTATE-HARNESS extras
so the DUT bytes and the iverilog-14 shim never drift from
VALIDATE-M.

Tier presets mirror the designer's documented acceptance windows:
tier-1 runs the fixture's own 4096-bit / settle-256 / bin-5 window
(params.py; tier-1 band 36.4-38.0 dB), PEX runs the top_tb.py
2048-bit / settle-64 / bin-13 window (extracted band 38.3-40.7 dB,
gate 36.0 dB both tiers).
"""

import shutil
import subprocess
from pathlib import Path

TIER1_NBITS = 4096
TIER1_NSETTLE = 256
TIER1_SIG_BIN = 5
PEX_NBITS = 2048
PEX_NSETTLE = 64
PEX_SIG_BIN = 13
GATE_DB = 36.0
ONES_MIN = 0.2
ONES_MAX = 0.8
FS_HZ = 50e6
TS_S = 1 / FS_HZ

PEX_PORT_ORDER = "ua0 uo0 uo1 clk vdpwr ua1 vgnd vapwr"

# Tier-1 loop nodes (xschem/tier1_sdm.sch): the retimed bitstream q is
# the sampled node (3.3 V logic, 1.65 V threshold mirrors sim/snr.py
# load_bits), int is the integrator health evidence.
TIER1_SAMPLE_NODE = "q"
TIER1_SAMPLE_THRESHOLD_V = 1.65
TIER1_INT_NODE = "int"

# PEX loop nodes (sim/top_tb.py): UO0 sampled at 0.9 V mid-period,
# UA1 integrator swing as health evidence.
PEX_SAMPLE_NODE = "uo0"
PEX_SAMPLE_THRESHOLD_V = 0.9
PEX_INT_NODE = "ua1"

_COSIM_BENCH = "tests/adapters/fixtures/hdl/sdm_rx_cosim_bench.v"


def stage_pex_wrapper(dest_dir, nbits=PEX_NBITS, sig_bin=PEX_SIG_BIN,
                      fs_hz=FS_HZ, vin_mid=1.65, amp=0.99, vapwr=3.3):
    """Stage the PEX cosim stimuli wrapper; return its path.

    Quotes the sim/top_tb.py deck stimuli (supplies, 50 MHz clock,
    sine input through 50 ohms, pad-ish loads, port-ordered XDUT)
    without the .lib/.tran/.control lines, which the run_cosim job
    carries instead so the body stays control-free.

    Args:
        dest_dir: Directory receiving sd_top_cosim_tb.spice.
        nbits: Analysis window in bits (sets the FIN tone only).
        sig_bin: Input tone FFT bin (sets FIN, coherent with nbits).
        fs_hz: Modulator clock in Hz.
        vin_mid: Input mid-scale in V.
        amp: Input tone amplitude in V.
        vapwr: Analog rail in V (references are ratiometric to it).

    Returns:
        Staged wrapper path as a string.
    """
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    period = 1 / fs_hz
    half_ns = period / 2 * 1e9
    fin = sig_bin * fs_hz / nbits
    text = (
        "* sd_top cosim stimuli (staged; mirrors sim/top_tb.py deck)\n"
        f"VAP vapwr 0 {vapwr:g}\n"
        "VDP vdpwr 0 1.8\n"
        "VGN vgnd 0 0\n"
        f"VCLK clk 0 PULSE(0 1.8 0 0.2n 0.2n {half_ns:.1f}n "
        f"{period * 1e9:.1f}n)\n"
        f"VIN vsrc 0 SIN({vin_mid * vapwr / 3.3:g} "
        f"{amp * vapwr / 3.3:g} {fin:g})\n"
        "RS vsrc ua0 50\n"
        "CU0 uo0 0 1p\n"
        "CU1 uo1 0 1p\n"
        "CA1 ua1 0 50f\n"
        f"XDUT {PEX_PORT_ORDER} sd_top\n"
    )
    path = dest / "sd_top_cosim_tb.spice"
    path.write_text(text, encoding="utf-8")
    return str(path)


def strip_control_body(text):
    """Remove sim-control lines from a netlist body; keep the circuit.

    Drops .tran/.control/.endc lines, bare control words (run, write,
    wrdata), plot lines, and set lines. Preserves everything else,
    including .options (tier-1's gear selector), .param, .subckt,
    .include, .ic, and * comments.

    Args:
        text: Netlist body text to strip.

    Returns:
        Control-free body text.
    """
    kept = []
    for line in text.splitlines():
        bare = line.strip().lower()
        if not bare:
            kept.append(line)
            continue
        if bare.startswith("*") or bare.startswith(";"):
            kept.append(line)
            continue
        first = bare.split()[0]
        if first in (".tran", ".control", ".endc", "run", "write",
                     "wrdata", "set") or first.startswith("plot"):
            continue
        kept.append(line)
    return "\n".join(kept) + "\n"


def stage_tier1_body(dest_dir, fixture_root, workdir, param_overrides=None,
                     lift_rin=False):
    """Generate the tier-1 behavioral body from the vendored schematic.

    Runs the fixture Makefile's own flow headlessly (params.spice via
    params.py, netlist via xschem --netlist --spice) into a scratch
    dir, strips the sim-control lines, applies braced-{TOKEN}
    overrides to the staged copy, and pre-stages params.spice where
    the adapter's analog cwd resolves the body's .include.

    Args:
        dest_dir: Directory receiving tier1_cosim.spice.
        fixture_root: Vendored ttsky-sigma-delta fixture root.
        workdir: run_cosim workdir (params.spice pre-staged under
            its analog/ subdir before the run).
        param_overrides: Optional {TOKEN: value} braced-param
            rewrites, e.g. {"AMP": 0} for the mute mutant.
        lift_rin: When True, comment the R_IN input leg (open-net
            fault-class equivalent of sdtop_open_net).

    Returns:
        Staged body path as a string.

    Raises:
        RuntimeError: xschem netlisting failed.
        KeyError: An override token is absent from the netlist.
    """
    fixture = Path(fixture_root)
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    scratch = dest / "_tier1gen"
    scratch.mkdir(parents=True, exist_ok=True)
    (scratch / "spice").mkdir(exist_ok=True)
    params_proc = subprocess.run(
        ["python3", str(fixture / "params.py")],
        capture_output=True, text=True, timeout=60, cwd=scratch,
    )
    if params_proc.returncode != 0:
        raise RuntimeError(
            "tier-1 staging: params.py failed: "
            + (params_proc.stdout + params_proc.stderr)[-500:]
        )
    # xschem-3.4.8 compat normalization on a SCRATCH copy (the
    # vendored .sch is never touched): gOF1 is the only ground
    # symbol without an explicit lab=GND (g1..g6 all carry it), and
    # this xschem leaves its net floating (R_OFF dangles on net1,
    # SNDR 23 dB). One attribute mirroring the six siblings grounds
    # the offset leg and reproduces the documented tier-1 band.
    sch_src = fixture / "xschem" / "tier1_sdm.sch"
    sch_text = sch_src.read_text(encoding="utf-8")
    if "{name=gOF1 lab=GND}" in sch_text:
        pass
    elif sch_text.count("{name=gOF1}") == 1:
        sch_text = sch_text.replace(
            "{name=gOF1}", "{name=gOF1 lab=GND}")
    else:
        raise RuntimeError("tier-1 staging: gOF1 compat site drifted.")
    sch_dir = scratch / "xschem"
    sch_dir.mkdir(exist_ok=True)
    sch = sch_dir / "tier1_sdm.sch"
    sch.write_text(sch_text, encoding="utf-8")
    tcl = (
        "set XSCHEM_LIBRARY_PATH "
        f"{scratch / 'xschem'}:{fixture / 'xschem'}:"
        "/usr/local/share/xschem/xschem_library"
    )
    net_proc = subprocess.run(
        ["xschem", "--tcl", tcl, "-n", "-s", "-q", "-x",
         "-o", str(scratch / "spice"), "-N", "tier1_sdm.spice",
         str(sch)],
        capture_output=True, text=True, timeout=120, cwd=scratch,
    )
    generated = scratch / "spice" / "tier1_sdm.spice"
    if net_proc.returncode != 0 or not generated.is_file():
        raise RuntimeError(
            "tier-1 staging: xschem netlist failed: "
            + (net_proc.stdout + net_proc.stderr)[-800:]
        )
    raw = generated.read_text(encoding="utf-8")
    if "R_OFF sum GND" not in raw:
        raise RuntimeError(
            "tier-1 staging: R_OFF offset leg is not grounded "
            "(xschem compat normalization did not hold).")
    text = strip_control_body(raw)
    if ".control" in text.lower() or "wrdata" in text.lower():
        raise RuntimeError("tier-1 staging: control lines survived stripping.")
    for token, value in (param_overrides or {}).items():
        braced = "{" + token + "}"
        if braced not in text:
            raise KeyError(f"tier-1 staging: token {braced} absent.")
        text = text.replace(braced, str(value))
    if lift_rin:
        old = "R_IN sum vin {RIN}"
        if old not in text:
            raise RuntimeError("tier-1 staging: R_IN site drifted.")
        text = text.replace(
            old, "* R_IN lifted (cosim analog open-net fault)")
    body = dest / "tier1_cosim.spice"
    body.write_text(text, encoding="utf-8")
    analog_dir = Path(workdir) / "analog"
    analog_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(scratch / "spice" / "params.spice",
                analog_dir / "params.spice")
    return str(body)


def stage_cosim_digital(dest_dir, root, operator=None, seed=0):
    """Stage the sdm_rx digital half for the cosim bench; return job args.

    Reuses the shipped MUTATE-HARNESS staging (DUT bytes, iverilog-14
    shim, PEX vector) so the digital half never drifts from
    VALIDATE-M, then swaps the recorded-vector bench for the
    live-vector cosim bench. The staged PEX vector file stays on disk
    unused: the bench reads the adapter-streamed cosim_bits.txt.

    Args:
        dest_dir: Staged sim dir receiving DUT plus benches.
        root: Repo root the extras copy from.
        operator: Optional sdm_* operator name for a mutant half.
        seed: Mutant seed selecting the variant.

    Returns:
        Mapping with sources, defines, timeout_s, workdir, and the
            mutation evidence (None for the good half).

    Raises:
        FileNotFoundError: Missing cosim bench or base piece.
        KeyError: Unknown operator.
    """
    from rocket_engine.mutate import (OPERATORS, apply_operator,
                                      copy_base_files, stage_design_extras)

    root = Path(root)
    dest = Path(dest_dir)
    mutation = None
    if operator is None:
        entry = next(item for item in OPERATORS.values()
                     if item.get("design") == "sdm_rx")
        copy_base_files(entry, root / entry["base"], dest)
    else:
        entry = OPERATORS[operator]
        mutation = apply_operator(operator, dest, seed, root / entry["base"])
    staged = stage_design_extras("sdm_rx", dest, root)
    bench_src = root / _COSIM_BENCH
    if not bench_src.is_file():
        raise FileNotFoundError(f"cosim bench missing: {bench_src}")
    bench_dest = dest / Path(_COSIM_BENCH).name
    shutil.copy(bench_src, bench_dest)
    dut = [path for path in staged["sources"]
           if Path(path).name == "sdm_rx.v"]
    return {
        "sources": dut + [str(bench_dest)],
        "defines": [],
        "timeout_s": staged["timeout_s"],
        "workdir": str(dest),
        "mutation": mutation,
    }


def tier1_job(workdir, analog_body, digital):
    """Build the tier-1 run_cosim job (model-free, fixture window).

    Args:
        workdir: run_cosim workdir (params.spice pre-staged under
            its analog/ subdir by stage_tier1_body).
        analog_body: Staged tier-1 body path.
        digital: stage_cosim_digital mapping for the digital half.

    Returns:
        run_cosim job mapping with the analog loop config.
    """
    return {
        "operation": "run_cosim",
        "analog_sources": [analog_body],
        "digital_sources": digital["sources"],
        "workdir": str(workdir),
        "defines": digital["defines"],
        "timeout_s": 300,
        "analog": {
            "clock_hz": FS_HZ,
            "nbits": TIER1_NBITS,
            "nsettle": TIER1_NSETTLE,
            "sig_bin": TIER1_SIG_BIN,
            "sample_node": TIER1_SAMPLE_NODE,
            "sample_threshold_v": TIER1_SAMPLE_THRESHOLD_V,
            "int_node": TIER1_INT_NODE,
            "tstep_s": 0.5e-9,
            # Tier-1 seeds its integrator from .ic v(int) (the
            # fixture's own `uic` tran); PEX starts from the DC OP.
            "uic": True,
            "gate_db": GATE_DB,
            "ones_min": ONES_MIN,
            "ones_max": ONES_MAX,
        },
    }


def pex_job(workdir, analog_sources, digital, pdk_entry):
    """Build the PEX run_cosim job (top_tb.py window, store models).

    Args:
        workdir: run_cosim workdir.
        analog_sources: Staged PEX macro copy plus wrapper paths.
        digital: stage_cosim_digital mapping for the digital half.
        pdk_entry: Store entry mapping with id and revision.

    Returns:
        run_cosim job mapping with the analog loop config.
    """
    return {
        "operation": "run_cosim",
        "analog_sources": list(analog_sources),
        "digital_sources": digital["sources"],
        "workdir": str(workdir),
        "defines": digital["defines"],
        "timeout_s": 900,
        "analog": {
            "clock_hz": FS_HZ,
            "nbits": PEX_NBITS,
            "nsettle": PEX_NSETTLE,
            "sig_bin": PEX_SIG_BIN,
            "sample_node": PEX_SAMPLE_NODE,
            "sample_threshold_v": PEX_SAMPLE_THRESHOLD_V,
            "int_node": PEX_INT_NODE,
            "tstep_s": 0.5e-9,
            "gate_db": GATE_DB,
            "ones_min": ONES_MIN,
            "ones_max": ONES_MAX,
            "options": ["wnflag=1", "method=gear", "reltol=1e-4",
                        "vntol=1e-6", "abstol=1e-10", "itl4=200"],
            "pdk": {"id": pdk_entry["id"],
                    "revision": pdk_entry["revision"]},
        },
    }
