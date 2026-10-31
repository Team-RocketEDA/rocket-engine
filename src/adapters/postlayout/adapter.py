"""Post-layout SPICE adapter: run_post_layout behind the ToolAdapter port.

Protocol, mirroring the run_spice adapter: stage a corner deck into the
workdir — preamble (.param/.option/.temp/.lib) + extracted netlist plus
testbench bodies (bare `.end` lines stripped, else ngspice stops before
.control) + generated .control (save all, analyses, let/print meas_*,
optional wrdata) — plus a .spiceinit (ngbehavior=hsa, required to read
sky130 libs), then run `ngspice -b -o postlayout.log postlayout_deck.spice`
under a timeout and parse `meas_* = value` lines. Verdicts always come
from parsed output, never the exit code: bound misses are FAIL, a sim
that yields no values synthesizes sim_fail violations, and only a
missing binary raises missing_dependency.

Two post-layout additions ride on top. Provenance is enforced: the job
carries the extraction record (extraction_run_id plus the netlist
sha256), and a missing record or bytes that no longer match the record
refuse loudly — a schematic passed as extracted without a fresh record
never sims. And every parsed measurement joins a pre/post comparison
row against the schematic run referenced by schematic_run_id (run_id
accepted as an alias), whose values arrive either explicitly in the job
or through the runs resolver; deltas are evidence only and never gate
the verdict.

PDK models resolve through the PDK store (resolve_deck): a wrong
revision, an unknown model relpath, or a tampered model file fails
loudly in preflight — the adapter never silently sims against
substitute models.

Tool resolution: an explicit job `tool_dir` containing ngspice wins,
else PATH. Where the tools live on disk is B10 scope.
"""

import hashlib
import math
import re
import shutil
import subprocess
from pathlib import Path

try:
    from ...execution.errors import ExecutionError
except ImportError:
    from rocket_engine.execution.errors import ExecutionError
try:
    from ...execution.runner import tool_roots
except ImportError:
    from rocket_engine.execution.runner import tool_roots
try:
    from ...interfaces import ToolAdapter
except ImportError:
    from rocket_engine.interfaces import ToolAdapter
try:
    from ...interfaces.pdks import resolve_deck
except ImportError:
    from rocket_engine.interfaces.pdks import resolve_deck
try:
    from ..errors import AdapterError
except ImportError:
    from rocket_engine.adapters.errors import AdapterError

OPERATION = "run_post_layout"
_TIMEOUT_S = 120
_DECK_NAME = "postlayout_deck.spice"
_LOG_NAME = "postlayout.log"
_SPICEINIT_NAME = ".spiceinit"
_WAVEFORMS_NAME = "postlayout_waveforms.dat"
_MODEL_REL = "libs.tech/combined/sky130.lib.spice"
_WAVEFORM_MAX_ROWS = 100000

# Mirrors the run_spice adapter MEAS_RE (leading whitespace tolerated).
_MEAS_RE = re.compile(
    r"^\s*meas_([A-Za-z0-9_]+)\s*=\s*"
    r"(-?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)",
    re.M,
)
_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_CORNER_RE = re.compile(r"^[A-Za-z0-9_]+$")
_PARAM_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SHA_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_ERROR_RE = re.compile(r"error", re.IGNORECASE)

_SPICEINIT = """* rocket_engine ngspice init (mirrors sky130-bandgap sim/spiceinit).
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


def _single_line(value):
    return (
        isinstance(value, str)
        and value.strip()
        and "\n" not in value
        and "\r" not in value
    )


def _check_measurements(measurements):
    if not isinstance(measurements, list) or not measurements:
        raise AdapterError(
            "invalid_command", "run_post_layout needs at least one measurement."
        )
    clean = []
    for item in measurements:
        if not isinstance(item, dict):
            raise AdapterError(
                "invalid_command", f"Bad measurement {item!r} (not a mapping)."
            )
        name = item.get("name")
        expr = item.get("expr")
        if not isinstance(name, str) or not _NAME_RE.match(name):
            raise AdapterError(
                "invalid_command", f"Bad measurement name: {name!r}."
            )
        if not _single_line(expr):
            raise AdapterError(
                "invalid_command",
                f"Measurement {name!r} needs a one-line expr.",
            )
        bounds = {
            key: item[key]
            for key in ("min", "max")
            if item.get(key) is not None
        }
        if not bounds or not all(_is_number(v) for v in bounds.values()):
            raise AdapterError(
                "invalid_command",
                f"Measurement {name!r} needs numeric min and/or max.",
            )
        if (
            "min" in bounds
            and "max" in bounds
            and bounds["min"] > bounds["max"]
        ):
            raise AdapterError(
                "invalid_command",
                f"Measurement {name!r} has min above max.",
            )
        clean.append(
            {
                "name": name,
                "expr": expr.strip(),
                "unit": item.get("unit", ""),
                "min": bounds.get("min"),
                "max": bounds.get("max"),
            }
        )
    return clean


def _check_waveforms(waveforms):
    if waveforms is None:
        return []
    if not isinstance(waveforms, list):
        raise AdapterError(
            "invalid_command", f"Waveforms must be a list: {waveforms!r}."
        )
    clean = []
    for item in waveforms:
        if not isinstance(item, dict):
            raise AdapterError(
                "invalid_command", f"Bad waveform {item!r} (not a mapping)."
            )
        name = item.get("name")
        expr = item.get("expr")
        if not isinstance(name, str) or not _NAME_RE.match(name):
            raise AdapterError(
                "invalid_command", f"Bad waveform name: {name!r}."
            )
        if not _single_line(expr) or expr.strip().startswith("."):
            raise AdapterError(
                "invalid_command",
                f"Waveform {name!r} needs a one-line vector expr.",
            )
        clean.append({"name": name, "expr": expr.strip()})
    return clean


def _check_control_lines(values, kind):
    clean = []
    for value in values or []:
        if not _single_line(value) or value.strip().startswith("."):
            raise AdapterError(
                "invalid_command", f"Bad {kind} line: {value!r}."
            )
        clean.append(value.strip())
    return clean


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


def _strip_end_lines(text):
    return "\n".join(
        line for line in text.splitlines() if line.strip().lower() != ".end"
    )


def _read_source(path):
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise AdapterError(
            "invalid_reference", f"Netlist unreadable: {path} ({exc})."
        ) from exc


def _sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _check_provenance(record, extracted):
    if not isinstance(record, dict):
        raise AdapterError(
            "invalid_command",
            "run_post_layout needs extraction_provenance "
            "{extraction_run_id, netlist_sha256, ...}; refusing to sim "
            "a schematic as extracted.",
        )
    run_id = record.get("extraction_run_id")
    if not _single_line(run_id):
        raise AdapterError(
            "invalid_command",
            "extraction_provenance needs a one-line extraction_run_id.",
        )
    digest = record.get("netlist_sha256")
    if not isinstance(digest, str) or _SHA_RE.match(digest) is None:
        raise AdapterError(
            "invalid_command",
            "extraction_provenance needs netlist_sha256 as 64 hex chars.",
        )
    if _sha256_file(extracted).lower() != digest.lower():
        raise AdapterError(
            "invalid_reference",
            f"Stale extraction record for {extracted}: netlist bytes differ "
            f"from extraction {run_id} (re-extract, then rerun).",
        )
    spice_file = record.get("spice_file")
    if spice_file is not None:
        if Path(spice_file).name != Path(extracted).name:
            raise AdapterError(
                "invalid_reference",
                f"extraction_provenance names {spice_file}, got {extracted}.",
            )
    clean = {
        "extraction_run_id": run_id.strip(),
        "netlist_sha256": digest.lower(),
    }
    for key in ("cell", "tech"):
        if record.get(key) is not None:
            if not _single_line(record[key]):
                raise AdapterError(
                    "invalid_command",
                    f"extraction_provenance needs a one-line {key}.",
                )
            clean[key] = record[key].strip()
    if spice_file is not None:
        clean["spice_file"] = str(spice_file)
    if record.get("device_count") is not None:
        count = record["device_count"]
        if (
            not isinstance(count, int)
            or isinstance(count, bool)
            or count < 0
        ):
            raise AdapterError(
                "invalid_command",
                f"Bad device_count: {count!r} (want an int >= 0).",
            )
        clean["device_count"] = count
    return clean


def _clean_value_list(items, what, code):
    if not isinstance(items, list) or not items:
        raise AdapterError(code, f"{what} has no measurements.")
    values = {}
    for item in items:
        if not isinstance(item, dict):
            raise AdapterError(code, f"{what} entry is not a mapping: {item!r}.")
        name = item.get("name")
        value = item.get("value")
        if not isinstance(name, str) or not name:
            raise AdapterError(code, f"{what} entry needs a name: {item!r}.")
        if not _is_number(value):
            raise AdapterError(
                code, f"{what} entry {name!r} needs a numeric value."
            )
        values[name] = {"value": float(value), "unit": item.get("unit", "")}
    return values


def _normalize_runs_result(raw, run_id):
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict) and isinstance(raw.get("measurements"), list):
        items = raw["measurements"]
    elif isinstance(raw, dict):
        items = [
            {
                "name": name,
                "value": value.get("value") if isinstance(value, dict) else value,
                "unit": value.get("unit", "") if isinstance(value, dict) else "",
            }
            for name, value in raw.items()
        ]
    else:
        raise AdapterError(
            "invalid_reference",
            f"Unknown schematic run: {run_id} (no measurements).",
        )
    return _clean_value_list(items, f"Schematic run {run_id}", "invalid_reference")


def _parse_waveforms_file(path, spec):
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return []
    columns = [[] for _ in range(len(spec) + 1)]
    for line in text.splitlines():
        parts = line.split()
        if not parts:
            continue
        try:
            numbers = [float(part) for part in parts]
        except ValueError:
            continue
        if len(numbers) != len(spec) + 1:
            continue
        for index, number in enumerate(numbers):
            columns[index].append(number)
    if not columns[0]:
        return []
    downsampled = False
    if len(columns[0]) > _WAVEFORM_MAX_ROWS:
        step = -(-len(columns[0]) // _WAVEFORM_MAX_ROWS)
        columns = [column[::step] for column in columns]
        downsampled = True
    scale, rest = columns[0], columns[1:]
    return [
        {
            "name": item["name"],
            "expr": item["expr"],
            "samples": samples,
            "scale": list(scale),
            "count": len(scale),
            "downsampled": downsampled,
        }
        for item, samples in zip(spec, rest)
    ]


def _format_cell(value):
    if value is None:
        return "-"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return f"{value:.6g}"
    return str(value)


def build_provenance(spice_file, extraction_run_id, cell=None, tech=None,
                     device_count=None):
    """Build an extraction record hashing the netlist on disk.

    The extraction side calls this when the .spice artifact lands, so
    the post-layout side can verify freshness instead of trusting a
    hand-written hash.

    Args:
        spice_file: Extracted netlist path the record pins.
        extraction_run_id: run_extraction run id that produced it.
        cell: Extracted cell name, when known.
        tech: Extraction tech name, when known.
        device_count: Extracted device count, when known.

    Returns:
        Provenance record with extraction_run_id, netlist_sha256,
            spice_file, and the known extras.

    Raises:
        AdapterError: invalid_reference for a missing netlist,
            invalid_command for a bad run id, cell, tech, or count.
    """
    if not _single_line(extraction_run_id):
        raise AdapterError(
            "invalid_command",
            "build_provenance needs a one-line extraction_run_id.",
        )
    if not Path(spice_file).is_file():
        raise AdapterError(
            "invalid_reference", f"Extracted netlist not found: {spice_file}."
        )
    record = {
        "extraction_run_id": extraction_run_id.strip(),
        "netlist_sha256": _sha256_file(spice_file),
        "spice_file": str(spice_file),
    }
    for key, value in (("cell", cell), ("tech", tech)):
        if value is not None:
            if not _single_line(value):
                raise AdapterError(
                    "invalid_command",
                    f"build_provenance needs a one-line {key}.",
                )
            record[key] = value.strip()
    if device_count is not None:
        if (
            not isinstance(device_count, int)
            or isinstance(device_count, bool)
            or device_count < 0
        ):
            raise AdapterError(
                "invalid_command",
                f"Bad device_count: {device_count!r} (want an int >= 0).",
            )
        record["device_count"] = device_count
    return record


def build_deck(title, corner, temp_c, params, options, model_lib, bodies,
               analyses, measurements, waveforms):
    """Render the post-layout deck (preamble + bodies + .control).

    Args:
        title: Deck title line (without the `*`).
        corner: Model corner named on the .lib line.
        temp_c: Temperature in C for the .temp line.
        params: Cleaned .param name/value mapping.
        options: Cleaned .option lines.
        model_lib: Store model library path, or None for model-free.
        bodies: Netlist body texts (.end lines already stripped).
        analyses: .control analysis lines (op when empty).
        measurements: Cleaned measurement items (let/print pairs).
        waveforms: Cleaned waveform items (one wrdata line).

    Returns:
        Rendered post-layout deck text.
    """
    head = [
        f"* {title}",
        f"* corner: {corner} temp: {temp_c}C "
        "(generated by rocket_engine postlayout adapter)",
    ]
    for key, value in params.items():
        head.append(f".param {key}={value}")
    for opt in options:
        head.append(f".option {opt}")
    head.append(f".temp {temp_c}")
    if model_lib is not None:
        head.append(f'.lib "{model_lib}" {corner}')
    control = [".control", "save all"]
    control.extend(analyses or ["op"])
    for item in measurements:
        control.append(f"let meas_{item['name']} = {item['expr']}")
    for item in measurements:
        control.append(f"print meas_{item['name']}")
    if waveforms:
        exprs = " ".join(item["expr"] for item in waveforms)
        control.append(f"wrdata {_WAVEFORMS_NAME} {exprs}")
    control.extend(["quit", ".endc", ".end", ""])
    return "\n".join(head + bodies + control)


def delta_table(comparison):
    """Render pre/post comparison rows as an ASCII delta table.

    Args:
        comparison: Comparison rows with name, pre, post, delta,
            rel, and status keys.

    Returns:
        Table text with one header line plus one line per row.
    """
    header = (
        f"{'name':<14} {'pre':>12} {'post':>12} "
        f"{'delta':>12} {'rel':>12}  status"
    )
    if not comparison:
        return header + "\n(no comparison rows)"
    lines = [header]
    for row in comparison:
        lines.append(
            f"{row.get('name', '?'):<14} "
            f"{_format_cell(row.get('pre')):>12} "
            f"{_format_cell(row.get('post')):>12} "
            f"{_format_cell(row.get('delta')):>12} "
            f"{_format_cell(row.get('rel')):>12}  "
            f"{row.get('status', '?')}"
        )
    return "\n".join(lines)


class PostLayoutAdapter(ToolAdapter):
    """run_post_layout via ngspice: extracted sims with pre/post deltas.

    Serves the run_post_layout operation with deck.tool `ngspice`
    (the only tool). Sims the extracted netlist plus testbench
    through ngspice in batch, evaluates post-layout measurements
    against min/max bounds, dumps requested waveforms via wrdata,
    and joins every measurement with its schematic value into a
    pre/post comparison table; deltas are evidence only and never
    gate the verdict.

    Job keys:
        extracted_netlist (required): Extracted netlist path simmed
            as the first body (never a schematic without a record).
        extraction_provenance (required): {extraction_run_id,
            netlist_sha256, cell?, tech?, spice_file?, device_count?}
            pinning the extraction; stale records refuse loudly.
        measurements (required): [{name, expr, unit?, min?, max?}]
            with numeric min and/or max each (bounds judge POST).
        schematic_run_id (required): Schematic run_spice run id the
            comparison reads pre values for (run_id is an alias).
        schematic_measurements: Explicit pre values [{name, value,
            unit?}] winning over the runs resolver.
        testbench: Testbench wrapper path staged after the netlist.
        waveforms: [{name, expr}] vector exprs dumped via wrdata.
        analyses: .control analysis lines (default op).
        options: .option lines (default [wnflag=1]).
        params: .param name/value mapping.
        corner: Model corner (default tt).
        temp_c: Temperature in C (default 27).
        title: Deck title line.
        pdk: {id, revision, model_rel?, engine_root?} pin for PDK
            models via the store; omitted sims model-free.
        timeout_s: Sim budget in seconds (default 120).
        tool_dir: Directory holding ngspice; PATH otherwise.
        deck: Optional mapping; deck.tool must be ngspice here.
        workdir: Run directory (default ".").

    Args:
        runner: Optional isolated runner; direct subprocess when None.
        runs: Optional schematic resolver run_id -> measurements
            (list, {measurements: [...]}, or {name: value}); used
            only when the job carries no schematic_measurements.

    Caution: Verdicts always come from parsed output, never the exit
        code — a missing or stale extraction record refuses instead
        of simming a schematic as extracted, and PDK models resolve
        through the store, so a wrong revision or tampered model
        fails loudly instead of simming against substitutes.
    """

    def __init__(self, runner=None, runs=None):
        self._runner = runner
        self._runs = runs

    def capabilities(self, target):
        """Report the served operation and tool name.

        Args:
            target: Target the capabilities are reported for
                (accepted, unused — one netlist per job).

        Returns:
            Capability mapping with operations and tool.
        """
        return {"operations": [OPERATION], "tool": "ngspice"}

    def preflight(self, job):
        """Check operation, inputs, provenance, schematic ref, and binary.

        Cheap deterministic checks first, provenance and schematic
        resolution next (a stale record or unknown schematic run
        must fail before any sim), PDK resolution after that, tool
        resolution last.

        Args:
            job: Solver job with operation run_post_layout plus the
                extracted netlist, provenance, measurements, and
                schematic reference inputs.

        Returns:
            Checked mapping with the resolved ngspice path,
                extracted netlist, testbench, measurements,
                waveforms, analyses, options, params, corner,
                temp_c, title, model_lib, schematic values,
                provenance, and timeout_s.

        Raises:
            AdapterError: unsupported_operation for another
                operation, invalid_command for bad inputs (sources
                alias, timeout, measurements, waveforms, analyses,
                options, params, corner, temp_c, title, missing or
                malformed provenance, missing or conflicting
                schematic ref, schematic gap), invalid_reference
                for a missing netlist or testbench, a stale or
                foreign provenance record, or an unresolvable
                schematic run, store codes (unknown_pdk, pdk_drift,
                ...) for a bad PDK pin, missing_dependency for an
                unresolvable ngspice.
        """
        # Cheap deterministic checks first: operation, shape,
        # timeout, inputs. Provenance and schematic resolution next
        # (both must fail before any sim). PDK resolution after that
        # (wrong rev must fail before any sim). Tool resolution last,
        # since it depends on the machine.
        if job.get("operation") != OPERATION:
            raise AdapterError(
                "unsupported_operation",
                f"postlayout handles {OPERATION}, got {job.get('operation')}.",
            )
        if job.get("sources") is not None:
            raise AdapterError(
                "invalid_command",
                "run_post_layout takes extracted_netlist, not sources.",
            )
        timeout = job.get("timeout_s", _TIMEOUT_S)
        if (
            not isinstance(timeout, (int, float))
            or isinstance(timeout, bool)
            or not timeout > 0
        ):
            raise AdapterError("invalid_command", f"Bad timeout_s: {timeout!r}.")
        extracted = job.get("extracted_netlist")
        if not extracted or not Path(extracted).is_file():
            raise AdapterError(
                "invalid_reference", f"Extracted netlist not found: {extracted}."
            )
        testbench = job.get("testbench")
        if testbench is not None and not Path(testbench).is_file():
            raise AdapterError(
                "invalid_reference", f"Testbench not found: {testbench}."
            )
        measurements = _check_measurements(job.get("measurements"))
        waveforms = _check_waveforms(job.get("waveforms"))
        analyses = _check_control_lines(job.get("analyses"), "analyses")
        options = _check_control_lines(
            job.get("options", ["wnflag=1"]), "options"
        )
        params = _check_params(job.get("params"))
        corner = job.get("corner", "tt")
        if not isinstance(corner, str) or not _CORNER_RE.match(corner):
            raise AdapterError("invalid_command", f"Bad corner: {corner!r}.")
        temp_c = job.get("temp_c", 27)
        if not _is_number(temp_c):
            raise AdapterError("invalid_command", f"Bad temp_c: {temp_c!r}.")
        title = job.get("title", "rocket_engine run_post_layout")
        if not _single_line(title):
            raise AdapterError("invalid_command", f"Bad title: {title!r}.")
        provenance = _check_provenance(
            job.get("extraction_provenance"), extracted
        )
        schematic = self._schematic_values(job, measurements)
        model_lib = self._resolve_model(job.get("pdk"))
        checked = {
            "ngspice": self._resolve(job),
            "extracted_netlist": str(extracted),
            "testbench": str(testbench) if testbench is not None else None,
            "measurements": measurements,
            "waveforms": waveforms,
            "analyses": analyses,
            "options": options,
            "params": params,
            "corner": corner,
            "temp_c": temp_c,
            "title": title.strip(),
            "model_lib": model_lib,
            "schematic": schematic,
            "provenance": provenance,
            "timeout_s": timeout,
        }
        if self._runner is not None:
            try:
                self._runner.preflight()
            except ExecutionError as exc:
                raise AdapterError(exc.code, str(exc)) from exc
        return checked

    def execute(self, job):
        """Stage the post-layout deck plus .spiceinit, then run ngspice.

        Args:
            job: Solver job with operation run_post_layout plus the
                extracted netlist, provenance, measurements, and
                schematic reference inputs.

        Returns:
            Native output with exit_code, stdout/stderr, log, deck,
                extracted netlist, testbench, measurements, the
                schematic sidecar, provenance, and the waveforms
                spec plus file.

        Raises:
            AdapterError: invalid_reference for a missing workdir
                or unreadable netlist, runner_unavailable on a sim
                timeout, plus the preflight codes (execute
                re-checks first).
        """
        checked = self.preflight(job)
        workdir = job.get("workdir", ".")
        if not Path(workdir).is_dir():
            raise AdapterError(
                "invalid_reference", f"Workdir not found: {workdir}."
            )
        workdir_path = Path(workdir)
        bodies = [_strip_end_lines(_read_source(checked["extracted_netlist"]))]
        if checked["testbench"] is not None:
            bodies.append(_strip_end_lines(_read_source(checked["testbench"])))
        deck = build_deck(
            checked["title"],
            checked["corner"],
            checked["temp_c"],
            checked["params"],
            checked["options"],
            checked["model_lib"],
            bodies,
            checked["analyses"],
            checked["measurements"],
            checked["waveforms"],
        )
        (workdir_path / _DECK_NAME).write_text(deck, encoding="utf-8")
        (workdir_path / _SPICEINIT_NAME).write_text(_SPICEINIT, encoding="utf-8")
        roots = tool_roots([checked["ngspice"]])
        proc = self._run(
            [checked["ngspice"], "-b", "-o", _LOG_NAME, _DECK_NAME],
            workdir,
            checked["timeout_s"],
            roots,
        )
        log_path = workdir_path / _LOG_NAME
        log_text = log_path.read_text(encoding="utf-8", errors="replace") if (
            log_path.is_file()
        ) else ""
        return {
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "log": log_text,
            "deck": deck,
            "extracted_netlist": checked["extracted_netlist"],
            "testbench": checked["testbench"],
            "measurements": checked["measurements"],
            "schematic": checked["schematic"],
            "provenance": checked["provenance"],
            "waveforms_spec": checked["waveforms"],
            "waveforms_file": str(workdir_path / _WAVEFORMS_NAME),
        }

    def parse(self, native_output):
        """Parse meas_* values, join the pre/post table, read waveforms.

        Bound misses are FAIL (margin always engine-computed, never
        left to the caller); expected measurements with no value
        synthesize sim_fail violations quoting ngspice's error text.
        The comparison joins each post value with its schematic pre
        value (delta = post - pre); deltas never gate the verdict.
        Waveforms parse from the wrdata file when present and read
        as empty otherwise — auxiliary evidence, never a failure.

        Args:
            native_output: Native output with stdout/stderr/log, the
                extracted netlist, the expected measurements, the
                schematic sidecar, provenance, and the waveforms
                spec plus file.

        Returns:
            {total, violations[], measurements[], comparison[],
                waveforms[], provenance} with value, unit, target,
                margin, and status per measurement plus pre, post,
                delta, and rel per comparison row.

        Raises:
            AdapterError: runner_unavailable when ngspice produced
                no output at all or the native carries no
                schematic sidecar.
        """
        chunks = [
            native_output.get("stdout") or "",
            native_output.get("stderr") or "",
            native_output.get("log") or "",
        ]
        if not any(chunks):
            raise AdapterError(
                "runner_unavailable", "ngspice produced no output at all."
            )
        combined = "\n".join(chunks)
        values = {}
        for match in _MEAS_RE.finditer(combined):
            try:
                values[match.group(1)] = float(match.group(2))
            except ValueError:
                continue
        expected = native_output.get("measurements") or []
        waveforms = _parse_waveforms_file(
            native_output.get("waveforms_file") or "",
            native_output.get("waveforms_spec") or [],
        )
        provenance = self._provenance_echo(native_output)
        missing = [item["name"] for item in expected if item["name"] not in values]
        if missing:
            errors = [
                line.strip()
                for line in combined.splitlines()
                if _ERROR_RE.search(line)
            ]
            detail = (
                f" ngspice said: {errors[0]}"
                if errors
                else " (no meas lines and no ngspice error text)"
            )
            first = native_output.get("extracted_netlist") or ""
            violations = [
                {
                    "rule": "sim_fail",
                    "severity": "error",
                    "message": (
                        f"ngspice produced no value for {name}.{detail}"
                    ),
                    "file": first,
                }
                for name in missing
            ]
            return {
                "total": len(violations),
                "violations": violations,
                "comparison": [],
                "waveforms": waveforms,
                "provenance": provenance,
            }
        schematic = native_output.get("schematic") or {}
        pre_values = schematic.get("values") or {}
        if not schematic.get("run_id") or not pre_values:
            raise AdapterError(
                "runner_unavailable",
                "post-layout native has no schematic sidecar.",
            )
        first = native_output.get("extracted_netlist") or ""
        violations = []
        measurements = []
        comparison = []
        for item in expected:
            actual = values[item["name"]]
            bounds = {
                key: item[key]
                for key in ("min", "max")
                if item.get(key) is not None
            }
            margins = {}
            if "min" in bounds:
                margins["min"] = actual - bounds["min"]
            if "max" in bounds:
                margins["max"] = bounds["max"] - actual
            failed = [
                f"{kind} {bounds[kind]}"
                for kind, margin in margins.items()
                if margin < 0
            ]
            status = "fail" if failed else "pass"
            margin = min(margins.values())
            unit = item.get("unit") or ""
            measurements.append(
                {
                    "name": item["name"],
                    "value": actual,
                    "unit": unit,
                    "target": dict(bounds),
                    "margin": margin,
                    "status": status,
                }
            )
            if failed:
                unit_suffix = f" {unit}" if unit else ""
                violations.append(
                    {
                        "rule": "measurement",
                        "severity": "error",
                        "message": (
                            f"{item['name']} = {actual:.6g}{unit_suffix} "
                            f"misses {', '.join(failed)}{unit_suffix} "
                            f"(margin {margin:.6g}{unit_suffix})."
                        ),
                        "file": first,
                    }
                )
            pre = pre_values[item["name"]]["value"]
            delta = actual - pre
            comparison.append(
                {
                    "name": item["name"],
                    "unit": unit,
                    "pre": pre,
                    "post": actual,
                    "delta": delta,
                    "rel": delta / pre if pre != 0 else None,
                    "status": status,
                }
            )
        return {
            "total": len(violations),
            "violations": violations,
            "measurements": measurements,
            "comparison": comparison,
            "waveforms": waveforms,
            "provenance": provenance,
        }

    def _schematic_values(self, job, measurements):
        schem_id = job.get("schematic_run_id")
        alias = job.get("run_id")
        if schem_id is not None and alias is not None and schem_id != alias:
            raise AdapterError(
                "invalid_command",
                "schematic_run_id and run_id disagree "
                f"({schem_id!r} vs {alias!r}).",
            )
        run_id = schem_id if schem_id is not None else alias
        if not isinstance(run_id, str) or not run_id:
            raise AdapterError(
                "invalid_command",
                "run_post_layout needs schematic_run_id (the schematic "
                "run_spice run id the comparison reads pre values for).",
            )
        explicit = job.get("schematic_measurements")
        if explicit is not None:
            values = _clean_value_list(
                explicit, "schematic_measurements", "invalid_command"
            )
        elif self._runs is not None:
            try:
                raw = self._runs(run_id)
            except AdapterError:
                raise
            except (KeyError, LookupError):
                raise AdapterError(
                    "invalid_reference",
                    f"Unknown schematic run: {run_id} (no measurements).",
                ) from None
            values = _normalize_runs_result(raw, run_id)
        else:
            raise AdapterError(
                "invalid_reference",
                f"Unknown schematic run: {run_id} (pass "
                "schematic_measurements or a runs resolver).",
            )
        for item in measurements:
            if item["name"] not in values:
                raise AdapterError(
                    "invalid_command",
                    f"Schematic run {run_id} has no value for "
                    f"measurement {item['name']!r}.",
                )
        return {"run_id": run_id, "values": values}

    @staticmethod
    def _provenance_echo(native_output):
        record = native_output.get("provenance") or {}
        schematic = native_output.get("schematic") or {}
        echo = {
            "extraction_run_id": record.get("extraction_run_id"),
            "netlist_sha256": record.get("netlist_sha256"),
            "schematic_run_id": schematic.get("run_id"),
        }
        for key in ("cell", "tech", "spice_file", "device_count"):
            if record.get(key) is not None:
                echo[key] = record[key]
        return echo

    @staticmethod
    def _resolve_model(pdk):
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
    def _resolve(job):
        tool_dir = job.get("tool_dir")
        if tool_dir:
            candidate = Path(tool_dir) / "ngspice"
            if candidate.is_file():
                return str(candidate)
            raise AdapterError(
                "missing_dependency", f"ngspice not found in {tool_dir}."
            )
        found = shutil.which("ngspice")
        if found is None:
            raise AdapterError(
                "missing_dependency",
                "ngspice not on PATH (pass tool_dir or integrate via B10).",
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
                f"post-layout sim timed out after {timeout_s}s.",
            ) from exc
