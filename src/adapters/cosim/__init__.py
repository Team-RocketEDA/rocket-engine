"""Coupled mixed-signal solver adapter: run_cosim behind the ToolAdapter port.

Protocol, mirroring the designer's sim/top_tb.py acceptance plus the
run_spice/run_hdl_test adapters: stage a transient deck into the
workdir — preamble (.param/.option/.temp/.lib) + control-free
netlist bodies + generated .control (single-threaded tran plus a
wrdata of the sampled node) — run `ngspice -b -o` under a timeout,
sample the waveform mid-period into bits, stream the bits live into
the digital half's Verilog bench as cosim_bits.txt, run that under
icarus via HdlSimAdapter, and judge the JOINT verdict: the SNDR
gate plus the RTL ones-density/counts/golden-model checks all PASS.

Verdicts always come from parsed output, never the exit code: bound
misses are FAIL with rule measurement (the halves' shared
quantitative rule, so seam mutations keep their declared rules),
digital native violations pass through with their own rules, and a
sim that yields no bits synthesizes a sim_fail violation quoting
ngspice's error text. Only a missing binary raises
missing_dependency and only a hung sim raises runner_unavailable.

PDK models resolve through the PDK store (resolve_deck): a wrong
revision, an unknown model relpath, or a tampered model file fails
loudly in preflight — the adapter never silently sims against
substitute models. Model-free decks (the tier-1 behavioral tier)
omit the pdk pin and record pdk None in the run record.

Tool resolution: an explicit job `tool_dir` containing ngspice,
iverilog, and vvp wins, else PATH. Where the tools live on disk is
B10 scope.
"""

# TODO: This whole thing might not even be needed. a COSIM workflow just happens by running a full digital workflow, generating gds, using magic ext2spice given a PDK and other vodoo magic scripts to get a spice netlist, then run LVS. the end goal of an analog/digital cosim is to check the PEX model vs the schematic model to see if they match, that is the end goal. 
import bisect
import hashlib
import math
import re
import shutil
import subprocess
from pathlib import Path

from ...execution.errors import ExecutionError
from ...execution.runner import tool_roots
from ...interfaces import ToolAdapter
from ...interfaces.pdks import pdk_ingredient, resolve_deck
from ..errors import AdapterError
from ..hdl_sim import HdlSimAdapter

OPERATION = "run_cosim"
TOOL = "cosim"
VECTOR_NAME = "cosim_bits.txt"

_ANALOG_TIMEOUT_S = 300
_DIGITAL_TIMEOUT_S = 120
_DECK_NAME = "cosim_deck.spice"
_LOG_NAME = "cosim_ngspice.log"
_CSV_NAME = "cosim_out.csv"
_SPICEINIT_NAME = ".spiceinit"
_MODEL_REL = "libs.tech/combined/sky130.lib.spice"

_GATE_DB = 36.0
_ONES_MIN = 0.2
_ONES_MAX = 0.8
_OSR_FAST = 25
_OSR_PREC = 250
_TSTEP_S = 0.5e-9
_NBITS_MIN = 64
_NBITS_MAX = 8192
_SIG_BIN_MIN = 4

# First tokens rejected in analog bodies (case-insensitive): the
# adapter generates the one .control section, so bodies carrying
# their own sim control are refused rather than merged.
_CONTROL_FIRST = frozenset(
    {".tran", ".control", ".endc", "run", "write", "wrdata", "set"}
)
_MEAS_RE = re.compile(r"^\s*meas_([A-Za-z0-9_]+)\s*=")
_ERROR_RE = re.compile(r"error", re.IGNORECASE)
_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_CORNER_RE = re.compile(r"^[A-Za-z0-9_]+$")
_PARAM_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_DEFINE_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(=[A-Za-z0-9_.+-]+)?")
_BITS_RE = re.compile(r"^COSIM_BITS\s+(\d+)\s+(\d+)\s*$")
_COUNT_RE = re.compile(r"^COSIM_COUNT_(FAST|PREC)\s+(\d+)\s*$")
_DATA_RE = re.compile(r"^COSIM_DATA_(FAST|PREC)\s+(-?\d+)\s*$")

# Mirrors the ngspice adapter's init (required to read sky130 libs).
_SPICEINIT = """* rocket_engine cosim init (mirrors the ngspice adapter).
set ngbehavior=hsa     ; HSPICE-ish compatibility, required to read PDK libs
set skywaterpdk        ; skip some checks for faster lib loading
set ng_nomodcheck      ; do not check model parameters
option noinit          ; do not dump operating point data into the log
option klu             ; KLU direct linear solver
"""


def _is_number(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _single_line(value):
    return (
        isinstance(value, str)
        and value.strip()
        and "\n" not in value
        and "\r" not in value
    )


def _is_pow2(value):
    return _is_int(value) and value > 0 and (value & (value - 1)) == 0


def _check_params(params):
    clean = {}
    for key, value in (params or {}).items():
        if not isinstance(key, str) or not _PARAM_KEY_RE.match(key):
            raise AdapterError("invalid_command", f"Bad .param name: {key!r}.")
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            raise AdapterError(
                "invalid_command", f"Bad .param value for {key!r}: {value!r}."
            )
        text = str(value)
        if not text or any(char.isspace() for char in text) or '"' in text:
            raise AdapterError(
                "invalid_command", f"Bad .param value for {key!r}: {value!r}."
            )
        clean[key] = text
    return clean


def _check_options(options):
    clean = []
    for value in options or ["wnflag=1"]:
        if not _single_line(value) or value.strip().startswith("."):
            raise AdapterError(
                "invalid_command", f"Bad options line: {value!r}."
            )
        clean.append(value.strip())
    return clean


def _strip_end_lines(text):
    return "\n".join(
        line for line in text.splitlines() if line.strip().lower() != ".end"
    )


def _body_control_line(line):
    bare = line.strip().lower()
    if not bare or bare.startswith("*") or bare.startswith(";"):
        return False
    first = bare.split()[0]
    return first in _CONTROL_FIRST or first.startswith("plot")


def _read_source(path):
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise AdapterError(
            "invalid_reference", f"Netlist unreadable: {path} ({exc})."
        ) from exc


def _fft(values):
    """In-place radix-2 DIT FFT; returns the complex spectrum."""
    data = [complex(v) for v in values]
    size = len(data)
    rank = 0
    for index in range(1, size):
        bit = size >> 1
        while rank & bit:
            rank ^= bit
            bit >>= 1
        rank ^= bit
        if index < rank:
            data[index], data[rank] = data[rank], data[index]
    length = 2
    while length <= size:
        angle = -2 * math.pi / length
        step = complex(math.cos(angle), math.sin(angle))
        for start in range(0, size, length):
            twiddle = 1 + 0j
            half = length // 2
            for pair in range(half):
                up = data[start + pair]
                down = data[start + pair + half] * twiddle
                data[start + pair] = up + down
                data[start + pair + half] = up - down
                twiddle *= step
        length <<= 1
    return data


def rfft_power(samples):
    """Power spectrum bins 0..n/2 of real samples via radix-2 FFT.

    Args:
        samples: Real-valued sample sequence, power-of-two length.

    Returns:
        Power magnitudes for bins 0 through n/2 inclusive.

    Raises:
        ValueError: Empty input, non-power-of-two length, or a
            non-finite sample.
    """
    values = list(samples)
    if not values or not _is_pow2(len(values)):
        raise ValueError(
            f"rfft_power needs power-of-two samples, got {len(values)}."
        )
    try:
        magnitudes = [float(v) for v in values]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"rfft_power needs real samples ({exc}).") from exc
    if not all(math.isfinite(v) for v in magnitudes):
        raise ValueError("rfft_power needs finite samples.")
    spectrum = _fft(magnitudes)
    half = len(spectrum) // 2
    return [c.real * c.real + c.imag * c.imag for c in spectrum[:half + 1]]


def sndr_bits(bits, osr, sig_bin):
    """SNDR in dB with the designer's sim/snr.py estimator arithmetic.

    Replicates the vendor estimator exactly, including its guard
    quirk: the signal sums spec bins sig-1..sig+1 while the inband
    zeroing covers inband indices sig-3..sig+3, i.e. spec bins
    sig-2..sig+4. Deviates in exactly one place: where numpy yields
    nan with a RuntimeWarning (no signal or no noise power), this
    returns -inf deterministically.

    Args:
        bits: Bitstream samples as +-1.0 floats, power-of-two count.
        osr: Oversampling ratio defining the band edge n/(2*osr).
        sig_bin: Input tone FFT bin, 4 <= sig_bin <= band-4.

    Returns:
        SNDR in dB, or -inf when the ratio is non-positive.

    Raises:
        ValueError: Bad sample count, bad OSR, or a sig_bin whose
            guards do not fit the band.
    """
    values = list(bits)
    if not values or not _is_pow2(len(values)):
        raise ValueError(f"sndr_bits needs power-of-two bits, got {len(values)}.")
    if not _is_int(osr) or osr < 1:
        raise ValueError(f"sndr_bits needs a positive int osr, got {osr!r}.")
    band = len(values) // (2 * osr)
    if (
        not _is_int(sig_bin)
        or sig_bin < _SIG_BIN_MIN
        or sig_bin > band - _SIG_BIN_MIN
    ):
        raise ValueError(
            f"sndr_bits needs 4 <= sig_bin <= band-4 (band {band}), "
            f"got {sig_bin!r}."
        )
    try:
        magnitudes = [float(v) for v in values]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"sndr_bits needs real samples ({exc}).") from exc
    spec = rfft_power(magnitudes)
    p_sig = sum(spec[sig_bin - 1:sig_bin + 2])
    inband = list(spec[1:band + 1])
    for index in range(sig_bin - 3, sig_bin + 4):
        inband[index] = 0.0
    noise = sum(inband)
    if p_sig <= 0 or noise <= 0 or not math.isfinite(p_sig + noise):
        return float("-inf")
    return 10 * math.log10(p_sig / noise)


def _interp(grid_t, grid_v, instant):
    """Linear interpolation with np.interp edge clamping."""
    if instant <= grid_t[0]:
        return grid_v[0]
    if instant >= grid_t[-1]:
        return grid_v[-1]
    slot = bisect.bisect_right(grid_t, instant)
    lo_t, hi_t = grid_t[slot - 1], grid_t[slot]
    if hi_t == lo_t:
        return grid_v[slot]
    frac = (instant - lo_t) / (hi_t - lo_t)
    return grid_v[slot - 1] + frac * (grid_v[slot] - grid_v[slot - 1])


def sample_bits(times, values, nsettle, nbits, period_s, threshold_v):
    """Sample a waveform mid-period into bits, top_tb.py convention.

    Sample instants are (nsettle + k + 0.5) * period_s for
    k in 0..nbits-1, linearly interpolated with np.interp edge
    clamping; instants at or above the threshold read one.

    Args:
        times: Ascending grid times in seconds.
        values: Waveform values on the grid.
        nsettle: Discarded startup cycles before the window.
        nbits: Window length in bits.
        period_s: Clock period in seconds.
        threshold_v: Decision threshold in volts.

    Returns:
        (bits01, bits_pm) pair: 0/1 ints for the RTL vector plus
            +-1.0 floats for the SNDR estimator.

    Raises:
        ValueError: Empty or ragged grid, non-ascending times, or a
            bad window or period.
    """
    grid_t = list(times)
    grid_v = list(values)
    if (
        not grid_t
        or len(grid_t) != len(grid_v)
        or any(b < a for a, b in zip(grid_t, grid_t[1:]))
    ):
        raise ValueError("sample_bits needs a non-empty ascending grid.")
    if not _is_int(nsettle) or nsettle < 0:
        raise ValueError(f"sample_bits needs nsettle >= 0, got {nsettle!r}.")
    if not _is_int(nbits) or nbits < 1:
        raise ValueError(f"sample_bits needs nbits >= 1, got {nbits!r}.")
    if not _is_number(period_s) or period_s <= 0:
        raise ValueError(f"sample_bits needs period_s > 0, got {period_s!r}.")
    if not _is_number(threshold_v):
        raise ValueError(
            f"sample_bits needs a numeric threshold, got {threshold_v!r}."
        )
    bits01 = []
    bits_pm = []
    for k in range(nbits):
        instant = (nsettle + k + 0.5) * period_s
        level = _interp(grid_t, grid_v, instant)
        one = level >= threshold_v
        bits01.append(1 if one else 0)
        bits_pm.append(1.0 if one else -1.0)
    return bits01, bits_pm


def settled_stats(times, values, nsettle, period_s):
    """Mean/min/max over the settled window (t > nsettle * period).

    Args:
        times: Grid times in seconds.
        values: Waveform values on the grid.
        nsettle: Discarded startup cycles before the window.
        period_s: Clock period in seconds.

    Returns:
        (mean, min, max) over samples past the settle point.

    Raises:
        ValueError: Empty grid or no settled samples.
    """
    grid_t = list(times)
    grid_v = list(values)
    settled = [v for t, v in zip(grid_t, grid_v) if t > nsettle * period_s]
    if not settled:
        raise ValueError("settled_stats found no settled samples.")
    return sum(settled) / len(settled), min(settled), max(settled)


def _sinc3_model(bits, osr):
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
            out.append(_sign32(c3))
        else:
            cnt += 1
    return out


def _sign32(v):
    v &= 0xFFFFFFFF
    return v - (1 << 32) if v & 0x80000000 else v


def build_cosim_deck(title, corner, temp_c, params, options, model_lib,
                     bodies, tran_line, sample_node, int_node):
    """Render the coupled deck (preamble + bodies + sampling .control).

    Args:
        title: Deck title line (without the `*`).
        corner: Model corner named on the .lib line.
        temp_c: Temperature in C for the .temp line.
        params: Cleaned .param name/value mapping.
        options: Cleaned .option lines.
        model_lib: Store model library path, or None for model-free.
        bodies: Netlist body texts (.end lines already stripped).
        tran_line: .control tran line, e.g. `tran 0.5n 42.24u`.
        sample_node: Bitstream node sampled mid-period into bits.
        int_node: Integrator health node, or None to skip it.

    Returns:
        Rendered deck text with the single .control section.
    """
    head = [
        f"* {title}",
        f"* corner: {corner} temp: {temp_c}C "
        "(generated by rocket_engine cosim adapter)",
    ]
    for key, value in params.items():
        head.append(f".param {key}={value}")
    for opt in options:
        head.append(f".option {opt}")
    head.append(f".temp {temp_c}")
    if model_lib is not None:
        head.append(f'.lib "{model_lib}" {corner}')
    wrdata = f"wrdata {_CSV_NAME} v({sample_node})"
    if int_node is not None:
        wrdata += f" v({int_node})"
    control = [".control", "set num_threads=1", tran_line, wrdata,
               "quit", ".endc", ".end", ""]
    return "\n".join(head + bodies + control)


def _check_node(node):
    return (
        _single_line(node)
        and not any(char.isspace() for char in node)
    )


def _check_loop(analog):
    if not isinstance(analog, dict):
        raise AdapterError(
            "invalid_command", f"run_cosim needs an analog mapping: {analog!r}."
        )
    clock_hz = analog.get("clock_hz")
    if not _is_number(clock_hz) or clock_hz <= 0:
        raise AdapterError(
            "invalid_command", f"Bad analog clock_hz: {clock_hz!r}."
        )
    nbits = analog.get("nbits")
    if not _is_pow2(nbits) or not _NBITS_MIN <= nbits <= _NBITS_MAX:
        raise AdapterError(
            "invalid_command",
            f"Bad analog nbits (power of two "
            f"{_NBITS_MIN}..{_NBITS_MAX}): {nbits!r}.",
        )
    nsettle = analog.get("nsettle")
    if not _is_int(nsettle) or nsettle < 0:
        raise AdapterError(
            "invalid_command", f"Bad analog nsettle: {nsettle!r}."
        )
    osr_fast = analog.get("osr_fast", _OSR_FAST)
    osr_prec = analog.get("osr_prec", _OSR_PREC)
    for name, value in (("osr_fast", osr_fast), ("osr_prec", osr_prec)):
        if not _is_int(value) or value < 1:
            raise AdapterError(
                "invalid_command", f"Bad analog {name}: {value!r}."
            )
    if nbits < osr_fast or nbits < osr_prec:
        raise AdapterError(
            "invalid_command",
            f"Bad analog nbits (must cover a strobe of osr_fast "
            f"{osr_fast} and osr_prec {osr_prec}): {nbits!r}.",
        )
    band = nbits // (2 * osr_fast)
    sig_bin = analog.get("sig_bin")
    if (
        not _is_int(sig_bin)
        or sig_bin < _SIG_BIN_MIN
        or sig_bin > band - _SIG_BIN_MIN
    ):
        raise AdapterError(
            "invalid_command",
            f"Bad analog sig_bin (4 <= bin <= band-4, band {band}): "
            f"{sig_bin!r}.",
        )
    sample_node = analog.get("sample_node")
    if not _check_node(sample_node):
        raise AdapterError(
            "invalid_command", f"Bad analog sample_node: {sample_node!r}."
        )
    threshold = analog.get("sample_threshold_v")
    if not _is_number(threshold):
        raise AdapterError(
            "invalid_command",
            f"Bad analog sample_threshold_v: {threshold!r}.",
        )
    int_node = analog.get("int_node")
    if int_node is not None and not _check_node(int_node):
        raise AdapterError(
            "invalid_command", f"Bad analog int_node: {int_node!r}."
        )
    tstep_s = analog.get("tstep_s", _TSTEP_S)
    if not _is_number(tstep_s) or tstep_s <= 0:
        raise AdapterError(
            "invalid_command", f"Bad analog tstep_s: {tstep_s!r}."
        )
    uic = analog.get("uic", False)
    if not isinstance(uic, bool):
        raise AdapterError(
            "invalid_command", f"Bad analog uic (bool): {uic!r}."
        )
    gate_db = analog.get("gate_db", _GATE_DB)
    if not _is_number(gate_db) or gate_db <= 0:
        raise AdapterError(
            "invalid_command", f"Bad analog gate_db: {gate_db!r}."
        )
    ones_min = analog.get("ones_min", _ONES_MIN)
    ones_max = analog.get("ones_max", _ONES_MAX)
    if not (
        _is_number(ones_min)
        and _is_number(ones_max)
        and 0 < ones_min < ones_max < 1
    ):
        raise AdapterError(
            "invalid_command",
            f"Bad analog ones bounds: [{ones_min!r}, {ones_max!r}].",
        )
    corner = analog.get("corner", "tt")
    if not isinstance(corner, str) or not _CORNER_RE.match(corner):
        raise AdapterError("invalid_command", f"Bad corner: {corner!r}.")
    temp_c = analog.get("temp_c", 27)
    if not _is_number(temp_c):
        raise AdapterError("invalid_command", f"Bad temp_c: {temp_c!r}.")
    title = analog.get("title", "rocket_engine run_cosim")
    if not _single_line(title):
        raise AdapterError("invalid_command", f"Bad title: {title!r}.")
    return {
        "clock_hz": clock_hz,
        "nbits": nbits,
        "nsettle": nsettle,
        "osr_fast": osr_fast,
        "osr_prec": osr_prec,
        "sig_bin": sig_bin,
        "sample_node": sample_node.strip(),
        "sample_threshold_v": threshold,
        "int_node": int_node.strip() if int_node is not None else None,
        "tstep_s": tstep_s,
        "tstop_s": (nbits + nsettle) / clock_hz,
        "uic": uic,
        "gate_db": gate_db,
        "ones_min": ones_min,
        "ones_max": ones_max,
        "corner": corner,
        "temp_c": temp_c,
        "title": title.strip(),
        "params": _check_params(analog.get("params")),
        "options": _check_options(analog.get("options")),
    }


def _parse_wrdata(text, want_int):
    """Grid columns from ngspice wrdata text: (t, sample[, int])."""
    rows = []
    for line in text.splitlines():
        cells = line.split()
        if not cells:
            continue
        try:
            rows.append([float(cell) for cell in cells])
        except ValueError:
            return None, "non-numeric wrdata row"
    if len(rows) < 2 or any(len(row) < 2 for row in rows):
        return None, "short wrdata table"
    if want_int and any(len(row) < 4 for row in rows):
        return None, "wrdata misses the int column"
    if any(b < a for a, b in zip([r[0] for r in rows], [r[0] for r in rows][1:])):
        return None, "non-ascending wrdata times"
    times = [row[0] for row in rows]
    sample = [row[1] for row in rows]
    integ = [row[3] for row in rows] if want_int else None
    return (times, sample, integ), None


class CosimAdapter(ToolAdapter):
    """run_cosim via ngspice plus icarus: coupled mixed-signal verdicts.

    Serves the run_cosim operation with deck.tool `cosim` (the only
    tool). Runs a transient on the analog half, samples the bitstream
    node mid-period, streams the live bits into the digital half's
    bench, and judges the joint verdict (SNDR gate plus RTL
    ones-density/counts/golden-model checks).

    Job keys:
        analog_sources (required): Control-free SPICE body paths.
        digital_sources (required): Verilog source paths, bench
            included; the bench reads cosim_bits.txt from its cwd.
        analog (required): Loop mapping with clock_hz, nbits
            (power of two 64..8192), nsettle, sig_bin (4..band-4),
            sample_node, sample_threshold_v, and optional int_node,
            tstep_s, uic, gate_db, ones_min/ones_max, osr_fast/osr_prec,
            corner, temp_c, title, params, options, pdk.
        defines: Extra Verilog `define list; COSIM_NBITS is added.
        timeout_s: Per-half budget in seconds (default 300).
        analog_timeout_s: Analog budget override.
        digital_timeout_s: Digital budget override (default 120).
        tool_dir: Directory holding ngspice/iverilog/vvp; PATH
            otherwise.
        deck: Optional mapping; deck.tool must be cosim here.
        workdir: Run directory (default "."); analog/ and digital/
            subdirs are created beneath it.

    Args:
        runner: Optional isolated runner; direct subprocess when None.

    Caution: The verdict always comes from parsed output, never the
        exit code — and a tran that ends before the window closes
        fails loudly (sim_fail) instead of judging clamped tail
        bits.
    """

    def __init__(self, runner=None):
        self._runner = runner

    def capabilities(self, target):
        """Report the served operation plus the coupled tools.

        Args:
            target: Target the capabilities are reported for
                (accepted, unused — one loop per job).

        Returns:
            Capability mapping with operations, tool, analog, and
                digital.
        """
        return {
            "operations": [OPERATION],
            "tool": TOOL,
            "analog": "ngspice",
            "digital": "icarus",
        }

    def preflight(self, job):
        """Check operation, halves, loop config, PDK pin, and tools.

        Cheap deterministic checks first, PDK resolution next (a
        wrong rev must fail before any sim), tool resolution last.

        Args:
            job: Solver job with operation run_cosim plus analog
                and digital halves and the loop config.

        Returns:
            Checked mapping with resolved tool paths, sources,
                defines, timeouts, loop config, deck shape, and the
                model library path (None when model-free).

        Raises:
            AdapterError: unsupported_operation for another
                operation, invalid_command for a bad loop config,
                deck shape, timeout, or defines, or for a body
                carrying sim control, invalid_reference for missing
                sources, store codes (unknown_pdk, pdk_drift, ...)
                for a bad PDK pin, missing_dependency for
                unresolvable tools.
        """
        if job.get("operation") != OPERATION:
            raise AdapterError(
                "unsupported_operation",
                f"cosim handles {OPERATION}, got {job.get('operation')}.",
            )
        timeout = job.get("timeout_s", _ANALOG_TIMEOUT_S)
        analog_timeout = job.get("analog_timeout_s", timeout)
        digital_timeout = job.get("digital_timeout_s", _DIGITAL_TIMEOUT_S)
        for name, value in (("timeout_s", timeout),
                            ("analog_timeout_s", analog_timeout),
                            ("digital_timeout_s", digital_timeout)):
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not value > 0
            ):
                raise AdapterError(
                    "invalid_command", f"Bad {name}: {value!r}."
                )
        analog_sources = job.get("analog_sources") or []
        missing = [s for s in analog_sources if not Path(s).is_file()]
        if not analog_sources or missing:
            raise AdapterError(
                "invalid_reference",
                f"Analog sources not found: {missing or analog_sources}.",
            )
        digital_sources = job.get("digital_sources") or []
        missing = [s for s in digital_sources if not Path(s).is_file()]
        if not digital_sources or missing:
            raise AdapterError(
                "invalid_reference",
                f"Digital sources not found: {missing or digital_sources}.",
            )
        for path in analog_sources:
            for line in _read_source(path).splitlines():
                if _body_control_line(line):
                    raise AdapterError(
                        "invalid_command",
                        f"Analog body carries sim control: {path}: "
                        f"{line.strip()[:60]}.",
                    )
        defines = job.get("defines") or []
        if not isinstance(defines, list) or any(
            not isinstance(d, str) or not _DEFINE_RE.fullmatch(d) for d in defines
        ):
            raise AdapterError("invalid_command", f"Bad defines: {defines!r}.")
        loop = _check_loop(job.get("analog"))
        model_lib = self._resolve_model(loop, job)
        checked = {
            "ngspice": self._resolve(job, "ngspice"),
            "iverilog": self._resolve(job, "iverilog"),
            "vvp": self._resolve(job, "vvp"),
            "analog_sources": list(analog_sources),
            "digital_sources": list(digital_sources),
            "defines": list(defines),
            "timeout_s": timeout,
            "analog_timeout_s": analog_timeout,
            "digital_timeout_s": digital_timeout,
            "model_lib": model_lib,
        }
        checked.update(loop)
        if self._runner is not None:
            try:
                self._runner.preflight()
            except ExecutionError as exc:
                raise AdapterError(exc.code, str(exc)) from exc
        return checked

    def execute(self, job):
        """Run the coupled sim: tran, sample, stream, RTL, joint native.

        Stages the sampling deck, runs ngspice, samples mid-period
        into bits, writes the live vector, and runs the digital half
        through HdlSimAdapter. A valueless analog sim returns its
        block with no digital half; the verdict still comes from
        parse, never the exit code alone.

        Args:
            job: Solver job with operation run_cosim plus analog
                and digital halves and the loop config.

        Returns:
            Native output with exit_code, the analog block, the
                digital native (None when the analog half yielded
                no bits), sampled bits, SNDR, ones-density,
                integrator stats, loop echoes, and gates.

        Raises:
            AdapterError: invalid_reference for a missing workdir,
                runner_unavailable on a sim timeout, plus the
                preflight codes (execute re-checks first).
        """
        checked = self.preflight(job)
        workdir = job.get("workdir", ".")
        if not Path(workdir).is_dir():
            raise AdapterError(
                "invalid_reference", f"Workdir not found: {workdir}."
            )
        workdir_path = Path(workdir)
        analog_dir = workdir_path / "analog"
        digital_dir = workdir_path / "digital"
        analog_dir.mkdir(parents=True, exist_ok=True)
        digital_dir.mkdir(parents=True, exist_ok=True)
        # Remove any previous run's output FIRST: an aborted sim must
        # never be judged on stale data from the prior invocation.
        stale = analog_dir / _CSV_NAME
        if stale.exists():
            stale.unlink()
        bodies = [
            _strip_end_lines(_read_source(path))
            for path in checked["analog_sources"]
        ]
        period_s = 1 / checked["clock_hz"]
        tran_line = f"tran {checked['tstep_s']:.6g} {checked['tstop_s']:.6g}"
        if checked["uic"]:
            tran_line += " uic"
        deck = build_cosim_deck(
            checked["title"],
            checked["corner"],
            checked["temp_c"],
            checked["params"],
            checked["options"],
            checked["model_lib"],
            bodies,
            tran_line,
            checked["sample_node"],
            checked["int_node"],
        )
        (analog_dir / _DECK_NAME).write_text(deck, encoding="utf-8")
        (analog_dir / _SPICEINIT_NAME).write_text(_SPICEINIT, encoding="utf-8")
        roots = tool_roots([checked["ngspice"]])
        proc = self._run(
            [checked["ngspice"], "-b", "-o", _LOG_NAME, _DECK_NAME],
            str(analog_dir),
            checked["analog_timeout_s"],
            roots,
        )
        log_path = analog_dir / _LOG_NAME
        log_text = log_path.read_text(encoding="utf-8", errors="replace") if (
            log_path.is_file()
        ) else ""
        analog = {
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "log": log_text,
            "deck": deck,
            "sources": checked["analog_sources"],
            "csv_rows": 0,
            "error": None,
        }
        bits01, detail = self._sample_analog(checked, analog_dir, analog)
        if detail is not None or bits01 is None:
            analog["error"] = detail or "no bits sampled"
            return self._native(checked, analog, None, None, proc.returncode or 1)
        bits_pm = [1.0 if b else -1.0 for b in bits01]
        ones = sum(bits01) / len(bits01)
        sndr_db = sndr_bits(bits_pm, checked["osr_fast"], checked["sig_bin"])
        (digital_dir / VECTOR_NAME).write_text(
            "\n".join(str(b) for b in bits01) + "\n", encoding="utf-8"
        )
        hdl_job = {
            "operation": "run_hdl_test",
            "sources": checked["digital_sources"],
            "workdir": str(digital_dir),
            "timeout_s": checked["digital_timeout_s"],
            "defines": checked["defines"] + [f"COSIM_NBITS={checked['nbits']}"],
        }
        if job.get("tool_dir"):
            hdl_job["tool_dir"] = job["tool_dir"]
        digital = HdlSimAdapter(runner=self._runner).execute(hdl_job)
        native = self._native(checked, analog, digital, bits01,
                              digital["exit_code"])
        native["ones_density"] = ones
        native["sndr_db"] = sndr_db
        return native

    def parse(self, native_output):
        """Judge the joint verdict from the coupled native.

        Analog gates (SNDR, ones-density) always evaluate;
        digital native violations pass through with their own
        rules; the Python-side handoff/count/golden checks
        evaluate only while the bench reports clean, so a $fatal
        stands alone instead of collecting pile-on violations.

        Args:
            native_output: Native output with the analog block,
                the digital native, sampled bits, SNDR, loop
                echoes, and gates.

        Returns:
            {total, violations[], measurements[], source} with
                rule measurement for quantitative misses, digital
                native rules passed through, sim_fail for
                valueless halves, and the COSIM_* channel read
                (`log` or `stdio_fallback`).

        Raises:
            AdapterError: runner_unavailable when sampled bits
                exist but the digital block is missing.
        """
        return _parse_joint(native_output)

    def _sample_analog(self, checked, analog_dir, analog):
        csv_path = analog_dir / _CSV_NAME
        if not csv_path.is_file():
            return None, self._no_value_detail(
                analog, checked["sample_node"], "no waveform file")
        grid, problem = _parse_wrdata(
            csv_path.read_text(encoding="utf-8", errors="replace"),
            checked["int_node"] is not None,
        )
        if grid is None:
            return None, self._no_value_detail(
                analog, checked["sample_node"], problem)
        times, sample, integ = grid
        analog["csv_rows"] = len(times)
        period_s = 1 / checked["clock_hz"]
        last_instant = (checked["nsettle"] + checked["nbits"] - 0.5) * period_s
        if times[-1] < last_instant:
            return None, (
                f"tran ended at {times[-1]:.6g} s before the window "
                f"closed at {last_instant:.6g} s."
            )
        bits01, _ = sample_bits(
            times, sample, checked["nsettle"], checked["nbits"],
            period_s, checked["sample_threshold_v"],
        )
        if integ is not None:
            mean, low, high = settled_stats(
                times, integ, checked["nsettle"], period_s)
            analog["int_mean_v"] = mean
            analog["int_min_v"] = low
            analog["int_max_v"] = high
        return bits01, None

    @staticmethod
    def _no_value_detail(analog, node, problem):
        combined = "\n".join(
            [analog.get("stdout") or "", analog.get("stderr") or "",
             analog.get("log") or ""]
        )
        errors = [line.strip() for line in combined.splitlines()
                  if _ERROR_RE.search(line)]
        said = f" ngspice said: {errors[0]}" if errors else ""
        return f"ngspice produced no waveform for v({node}) ({problem}).{said}"

    @staticmethod
    def _native(checked, analog, digital, bits01, exit_code):
        return {
            "exit_code": exit_code,
            "analog": analog,
            "digital": digital,
            "bits": bits01,
            "ones_density": None,
            "sndr_db": None,
            "int_mean_v": analog.get("int_mean_v"),
            "int_min_v": analog.get("int_min_v"),
            "int_max_v": analog.get("int_max_v"),
            "nbits": checked["nbits"],
            "sig_bin": checked["sig_bin"],
            "osr_fast": checked["osr_fast"],
            "osr_prec": checked["osr_prec"],
            "gates": {
                "gate_db": checked["gate_db"],
                "ones_min": checked["ones_min"],
                "ones_max": checked["ones_max"],
            },
            "vector_name": VECTOR_NAME,
        }

    @staticmethod
    def _resolve_model(loop, job):
        pdk = loop_analog_pdk(job)
        if pdk is None:
            return None
        if not isinstance(pdk, dict):
            raise AdapterError(
                "invalid_command", f"PDK pin must be a mapping: {pdk!r}."
            )
        pdk_id = pdk.get("id")
        revision = pdk.get("revision")
        if not pdk_id or not revision:
            raise AdapterError(
                "invalid_command",
                f"PDK pin needs id and revision: {pdk!r}.",
            )
        rel = pdk.get("model_rel", _MODEL_REL)
        try:
            hit = resolve_deck(
                pdk_id, revision, rel, engine_root=pdk.get("engine_root")
            )
        except Exception as exc:
            # PdkError codes (unknown_pdk, pdk_drift, ...) ride
            # through unchanged so a model mismatch fails loudly
            # with its store meaning, never as a generic error.
            raise AdapterError(
                getattr(exc, "code", "unknown_pdk"), str(exc)
            ) from exc
        return hit["path"]

    @staticmethod
    def _resolve(job, binary):
        tool_dir = job.get("tool_dir")
        if tool_dir:
            candidate = Path(tool_dir) / binary
            if candidate.is_file():
                return str(candidate)
            raise AdapterError(
                "missing_dependency", f"{binary} not found in {tool_dir}."
            )
        found = shutil.which(binary)
        if found is None:
            raise AdapterError(
                "missing_dependency",
                f"{binary} not on PATH (pass tool_dir or integrate via B10).",
            )
        return found

    def _run(self, argv, workdir, timeout_s, extra_binds=()):
        if self._runner is not None:
            try:
                return self._runner.run(argv, workdir, timeout_s, extra_binds)
            except ExecutionError as exc:
                raise AdapterError(exc.code, str(exc)) from exc
        try:
            return subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                cwd=workdir,
            )
        except subprocess.TimeoutExpired as exc:
            raise AdapterError(
                "runner_unavailable",
                f"cosim analog sim timed out after {timeout_s}s.",
            ) from exc


def loop_analog_pdk(job):
    """Read the analog PDK pin from a run_cosim job mapping.

    Args:
        job: Solver job mapping carrying the analog config.

    Returns:
        PDK pin mapping, or None when the deck is model-free.
    """
    analog = job.get("analog") or {}
    return analog.get("pdk")


def _measurement_violation(first_source, name, actual, failed, margin, unit):
    unit_suffix = f" {unit}" if unit else ""
    return {
        "rule": "measurement",
        "severity": "error",
        "message": (
            f"{name} = {actual:.6g}{unit_suffix} "
            f"misses {', '.join(failed)}{unit_suffix} "
            f"(margin {margin:.6g}{unit_suffix})."
        ),
        "file": first_source,
    }


def _parse_cosim_reports(text):
    """COSIM_* bench reports: (bits, counts, data) mappings or None."""
    bits = counts = data = None
    for line in text.splitlines():
        match = _BITS_RE.match(line.strip())
        if match:
            bits = {"total": int(match.group(1)), "ones": int(match.group(2))}
            continue
        match = _COUNT_RE.match(line.strip())
        if match:
            counts = counts or {}
            counts[match.group(1).lower()] = int(match.group(2))
            continue
        match = _DATA_RE.match(line.strip())
        if match:
            data = data or {}
            data[match.group(1).lower()] = int(match.group(2))
    if bits is None or counts is None or data is None:
        return None
    if set(counts) != {"fast", "prec"} or set(data) != {"fast", "prec"}:
        return None
    return bits, counts, data


def _parse_joint(native_output):
    """Joint analog/digital verdict (parse delegates here)."""
    analog = native_output.get("analog") or {}
    sources = analog.get("sources") or []
    first_source = sources[0] if sources else ""
    bits = native_output.get("bits")
    if not bits:
        detail = analog.get("error") or "no bits sampled"
        violations = [
            {
                "rule": "sim_fail",
                "severity": "error",
                "message": f"cosim analog half yielded no bits ({detail}).",
                "file": first_source,
            }
        ]
        return {"total": 1, "violations": violations}
    gates = native_output.get("gates") or {}
    gate_db = gates.get("gate_db", _GATE_DB)
    ones_min = gates.get("ones_min", _ONES_MIN)
    ones_max = gates.get("ones_max", _ONES_MAX)
    violations = []
    measurements = []
    sndr_db = native_output.get("sndr_db")
    margin = sndr_db - gate_db
    status = "fail" if margin < 0 else "pass"
    measurements.append(
        {
            "name": "sndr_fast_db",
            "value": sndr_db,
            "unit": "dB",
            "target": {"min": gate_db},
            "margin": margin,
            "status": status,
        }
    )
    if status == "fail":
        violations.append(
            _measurement_violation(
                first_source, "sndr_fast_db", sndr_db,
                [f"min {gate_db}"], margin, "dB")
        )
    ones = native_output.get("ones_density")
    margins = {"min": ones - ones_min, "max": ones_max - ones}
    failed = [f"{kind} {bound}" for kind, bound, edge in
              (("min", ones_min, margins["min"]),
               ("max", ones_max, margins["max"])) if edge < 0]
    margin = min(margins.values())
    status = "fail" if failed else "pass"
    measurements.append(
        {
            "name": "ones_density",
            "value": ones,
            "unit": "",
            "target": {"min": ones_min, "max": ones_max},
            "margin": margin,
            "status": status,
        }
    )
    if status == "fail":
        violations.append(
            _measurement_violation(
                first_source, "ones_density", ones, failed, margin, "")
        )
    digital = native_output.get("digital")
    if digital is None:
        raise AdapterError(
            "runner_unavailable", "Native output has no digital block."
        )
    fres = HdlSimAdapter().parse(digital)
    violations.extend(fres["violations"])
    if any(v.get("severity") == "error" for v in fres["violations"]):
        # The bench already failed: its reports are untrustworthy, so
        # the Python-side handoff/count/golden checks stay silent and
        # the native rule stands alone (no pile-on after $fatal).
        return {
            "total": len(violations),
            "violations": violations,
            "measurements": measurements,
        }
    run_block = digital.get("run") or {}
    # MIGRATE-STDIO-FILE: the `vvp -l` log (written by the shared
    # HdlSimAdapter.execute digital half) is the reports channel;
    # stdio survives only as a loud fallback for older natives.
    run_log = run_block.get("log") or ""
    if run_log.strip():
        text, report_source = run_log, "log"
    else:
        text = run_block.get("stdout", "") + "\n" + run_block.get("stderr", "")
        report_source = "stdio_fallback"
    reports = _parse_cosim_reports(text)
    if reports is None:
        violations.append(
            {
                "rule": "sim_fail",
                "severity": "error",
                "message": "cosim bench reported no COSIM_* lines.",
                "file": first_source,
            }
        )
        return {
            "total": len(violations),
            "violations": violations,
            "measurements": measurements,
            "source": report_source,
        }
    report_bits, counts, data = reports
    nbits = native_output.get("nbits", len(bits))
    analog_ones = sum(bits)
    if report_bits["total"] != nbits or report_bits["ones"] != analog_ones:
        if report_bits["total"] != nbits:
            violations.append(
                _measurement_violation(
                    first_source, "rtl_total", report_bits["total"],
                    [f"streamed {nbits}"],
                    report_bits["total"] - nbits, "")
            )
        if report_bits["ones"] != analog_ones:
            violations.append(
                _measurement_violation(
                    first_source, "rtl_ones", report_bits["ones"],
                    [f"analog {analog_ones}"],
                    -(abs(report_bits["ones"] - analog_ones)), "")
            )
    osr_fast = native_output.get("osr_fast", _OSR_FAST)
    osr_prec = native_output.get("osr_prec", _OSR_PREC)
    for name, want in (("count_fast", nbits // osr_fast),
                       ("count_prec", nbits // osr_prec)):
        got = counts["fast" if name == "count_fast" else "prec"]
        if got != want:
            violations.append(
                _measurement_violation(
                    first_source, name, got, [f"strobes {want}"],
                    -(abs(got - want)), "")
            )
    for name, osr, key in (("data_fast", osr_fast, "fast"),
                           ("data_prec", osr_prec, "prec")):
        model = _sinc3_model(bits, osr)[-1]
        got = data[key]
        margin = -abs(got - model)
        status = "fail" if got != model else "pass"
        measurements.append(
            {
                "name": name,
                "value": got,
                "unit": "",
                "target": {"min": model, "max": model},
                "margin": margin,
                "status": status,
            }
        )
        if status == "fail":
            violations.append(
                _measurement_violation(
                    first_source, name, got, [f"golden {model}"],
                    margin, "")
            )
    return {
        "total": len(violations),
        "violations": violations,
        "measurements": measurements,
        "source": report_source,
    }


def _sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _probe_versions():
    versions = {}
    for binary in ("ngspice", "iverilog", "vvp"):
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


def build_run_record(case, design, job, native, parsed, mutation=None,
                     versions=None, extra=None, engine_root=None):
    """Build the I28 run record with ingredient closure for both halves.

    Pins every regenerability ingredient: per-half source bytes,
    deck bytes, the streamed vector bytes, sampled bits, loop
    config, solver versions, and the PDK closure (verified fresh —
    drift fails loudly instead of recording a stale hash).

    Args:
        case: Case name for the record.
        design: Design pair name, e.g. sd_top+sdm_rx.
        job: run_cosim job mapping the run executed.
        native: Native output mapping from execute.
        parsed: Parsed result mapping from parse.
        mutation: Mutation evidence mapping, or None for good.
        versions: Solver version mapping; probed live when omitted.
        extra: Extra ingredient mappings merged in (fixture pin).
        engine_root: Explicit PDK store root; resolved when omitted.

    Returns:
        Run record mapping with case, design, engine, ingredients,
            and results sections.

    Raises:
        OSError: A recorded source file is unreadable.
        PdkError: unknown_pdk for a missing entry, pdk_drift when
            the store changed since registration.
    """
    analog_cfg = job.get("analog") or {}
    analog = native.get("analog") or {}
    pdk_pin = analog_cfg.get("pdk")
    if pdk_pin is None:
        pdk = None
    else:
        pdk = pdk_ingredient(
            pdk_pin["id"], pdk_pin["revision"],
            engine_root=pdk_pin.get("engine_root", engine_root),
        )
    analog_sources = [
        {"name": Path(path).name, "sha256": _sha256_file(path)}
        for path in checked_job_sources(job, "analog_sources")
    ]
    digital_sources = [
        {"name": Path(path).name, "sha256": _sha256_file(path)}
        for path in checked_job_sources(job, "digital_sources")
    ]
    bits = native.get("bits") or []
    bits_text = "\n".join(str(b) for b in bits) + "\n" if bits else ""
    versions = dict(versions) if versions is not None else _probe_versions()
    verdict = "FAIL" if any(v.get("severity") == "error"
                            for v in parsed.get("violations", [])) else "PASS"
    ingredients = {
        "analog": {
            "solver": "ngspice",
            "tool_version": versions.get("ngspice"),
            "sources": sorted(analog_sources, key=lambda s: s["name"]),
            "deck_sha256": _sha256_text(analog.get("deck") or ""),
            "pdk": pdk,
        },
        "digital": {
            "solver": "icarus",
            "tool_versions": {
                "iverilog": versions.get("iverilog"),
                "vvp": versions.get("vvp"),
            },
            "sources": sorted(digital_sources, key=lambda s: s["name"]),
            "defines": list(job.get("defines") or []),
        },
        "config": {
            "clock_hz": analog_cfg.get("clock_hz"),
            "nbits": analog_cfg.get("nbits"),
            "nsettle": analog_cfg.get("nsettle"),
            "sig_bin": analog_cfg.get("sig_bin"),
            "osr_fast": analog_cfg.get("osr_fast", _OSR_FAST),
            "osr_prec": analog_cfg.get("osr_prec", _OSR_PREC),
            "sample_node": analog_cfg.get("sample_node"),
            "sample_threshold_v": analog_cfg.get("sample_threshold_v"),
            "int_node": analog_cfg.get("int_node"),
            "tstep_s": analog_cfg.get("tstep_s", _TSTEP_S),
            "uic": analog_cfg.get("uic", False),
            "gate_db": analog_cfg.get("gate_db", _GATE_DB),
            "ones_min": analog_cfg.get("ones_min", _ONES_MIN),
            "ones_max": analog_cfg.get("ones_max", _ONES_MAX),
            "corner": analog_cfg.get("corner", "tt"),
            "temp_c": analog_cfg.get("temp_c", 27),
            "params": dict(analog_cfg.get("params") or {}),
            "options": list(analog_cfg.get("options") or ["wnflag=1"]),
            "timeout_s": job.get("timeout_s", _ANALOG_TIMEOUT_S),
        },
        "vector": {
            "name": native.get("vector_name", VECTOR_NAME),
            "sha256": _sha256_text(bits_text) if bits_text else None,
        },
        "sampled_bits": {
            "nbits": len(bits),
            "ones": sum(bits),
            "sha256": _sha256_text(bits_text) if bits_text else None,
        },
        "mutation": mutation,
    }
    for key, value in (extra or {}).items():
        ingredients[key] = value
    return {
        "case": case,
        "design": design,
        "engine": {"operation": OPERATION},
        "ingredients": ingredients,
        "results": {
            "verdict": verdict,
            "total": parsed.get("total", 0),
            "rules": sorted({v.get("rule") for v in
                             parsed.get("violations", [])}),
            "measurements": parsed.get("measurements", []),
        },
    }


def checked_job_sources(job, key):
    """Source paths echoed from a run_cosim job mapping.

    Args:
        job: Solver job mapping carrying the source lists.
        key: Source list key (analog_sources/digital_sources).

    Returns:
        Source path list (empty when the key is absent).
    """
    return list(job.get(key) or [])
