"""Ngspice SPICE solver adapter: run_spice behind the ToolAdapter port.

Protocol, mirroring the vendored sky130-bandgap harness
(sim/bin/corner-run.py): stage a corner deck into the workdir —
preamble (.param/.option/.temp/.lib) + netlist bodies (bare
`.end` lines stripped, else ngspice stops before .control) +
generated .control (save all, analyses, let/print meas_*) — plus
a .spiceinit (ngbehavior=hsa, required to read sky130 libs),
then run `ngspice -b -o ngspice.log ngspice_deck.spice` under a
timeout and parse `meas_* = value` lines. Verdicts always come
from parsed output, never the exit code: bound misses are FAIL,
a sim that yields no values synthesizes sim_fail violations, and
only a missing binary raises missing_dependency.

PDK models resolve through the PDK store (resolve_deck): a wrong
revision, an unknown model relpath, or a tampered model file
fails loudly in preflight — the adapter never silently sims
against substitute models.

Tool resolution: an explicit job `tool_dir` containing ngspice
wins, else PATH. Where the tools live on disk is B10 scope.
"""

import math
import re
import shutil
import subprocess
from pathlib import Path

from ...execution.errors import ExecutionError
from ...execution.runner import tool_roots
from ...interfaces import ToolAdapter
from ...interfaces.pdks import resolve_deck
from ..errors import AdapterError

OPERATION = "run_spice"
_TIMEOUT_S = 120
_DECK_NAME = "ngspice_deck.spice"
_LOG_NAME = "ngspice.log"
_WAVEFORM_PREFIX = "waveforms-"
_SWEEPS = ("ac", "dc", "tran", "noise")
_SPICEINIT_NAME = ".spiceinit"
_MODEL_REL = "libs.tech/combined/sky130.lib.spice"

# Mirrors corner-run.py MEAS_RE (leading whitespace tolerated).
_MEAS_RE = re.compile(
    r"^\s*meas_([A-Za-z0-9_]+)\s*=\s*"
    r"(-?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)",
    re.M,
)
_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_CORNER_RE = re.compile(r"^[A-Za-z0-9_]+$")
_PARAM_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
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
            "invalid_command", "run_spice needs at least one measurement."
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


def build_deck(title, corner, temp_c, params, options, model_lib, bodies,
               analyses, measurements):
    """Render the corner deck (preamble + bodies + .control)."""
    head = [
        f"* {title}",
        f"* corner: {corner} temp: {temp_c}C "
        "(generated by rocket_engine ngspice adapter)",
    ]
    for key, value in params.items():
        head.append(f".param {key}={value}")
    for opt in options:
        head.append(f".option {opt}")
    head.append(f".temp {temp_c}")
    if model_lib is not None:
        head.append(f'.lib "{model_lib}" {corner}')
    control = [".control", "save all", "set filetype=ascii"]
    # Each sweep's vectors go to an ASCII rawfile right after it runs: the dataset
    # behind the verdict, for clients to plot (rendering stays out of the engine).
    sweeps = 0
    for line in analyses or ["op"]:
        control.append(line)
        kind = line.split()[0].lower() if line.split() else ""
        if kind in _SWEEPS:
            sweeps += 1
            control.append(f"write {_WAVEFORM_PREFIX}{sweeps}-{kind}.raw")
    for item in measurements:
        control.append(f"let meas_{item['name']} = {item['expr']}")
    for item in measurements:
        control.append(f"print meas_{item['name']}")
    control.extend(["quit", ".endc", ".end", ""])
    return "\n".join(head + bodies + control)


class NgspiceAdapter(ToolAdapter):
    def __init__(self, runner=None):
        self._runner = runner

    def capabilities(self, target):
        return {"operations": [OPERATION], "tool": "ngspice"}

    def preflight(self, job):
        # Cheap deterministic checks first: operation, timeout,
        # sources, measurements, deck shape. PDK resolution next
        # (wrong rev must fail before any sim). Tool resolution
        # last, since it depends on the machine.
        if job.get("operation") != OPERATION:
            raise AdapterError(
                "unsupported_operation",
                f"ngspice handles {OPERATION}, got {job.get('operation')}.",
            )
        timeout = job.get("timeout_s", _TIMEOUT_S)
        if (
            not isinstance(timeout, (int, float))
            or isinstance(timeout, bool)
            or not timeout > 0
        ):
            raise AdapterError("invalid_command", f"Bad timeout_s: {timeout!r}.")
        sources = job.get("sources") or []
        missing = [s for s in sources if not Path(s).is_file()]
        if not sources or missing:
            raise AdapterError(
                "invalid_reference", f"Sources not found: {missing or sources}."
            )
        measurements = _check_measurements(job.get("measurements"))
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
        title = job.get("title", "rocket_engine run_spice")
        if not _single_line(title):
            raise AdapterError("invalid_command", f"Bad title: {title!r}.")
        model_lib = self._resolve_model(job.get("pdk"))
        checked = {
            "ngspice": self._resolve(job),
            "sources": list(sources),
            "measurements": measurements,
            "analyses": analyses,
            "options": options,
            "params": params,
            "corner": corner,
            "temp_c": temp_c,
            "title": title.strip(),
            "model_lib": model_lib,
            "timeout_s": timeout,
        }
        if self._runner is not None:
            try:
                self._runner.preflight()
            except ExecutionError as exc:
                raise AdapterError(exc.code, str(exc)) from exc
        return checked

    def execute(self, job):
        checked = self.preflight(job)
        workdir = job.get("workdir", ".")
        if not Path(workdir).is_dir():
            raise AdapterError(
                "invalid_reference", f"Workdir not found: {workdir}."
            )
        workdir_path = Path(workdir)
        bodies = [
            _strip_end_lines(_read_source(path)) for path in checked["sources"]
        ]
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
        )
        # Rawfiles from an earlier run in this workdir must not pass as this run's data.
        for stale in workdir_path.glob(f"{_WAVEFORM_PREFIX}*.raw"):
            stale.unlink()
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
            "waveforms": [
                {"analysis": path.stem.rsplit("-", 1)[-1], "path": str(path)}
                for path in sorted(workdir_path.glob(f"{_WAVEFORM_PREFIX}*.raw"))
            ],
            "sources": checked["sources"],
            "measurements": checked["measurements"],
        }

    def parse(self, native_output):
        sources = native_output.get("sources") or []
        first_source = sources[0] if sources else ""
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
            violations = [
                {
                    "rule": "sim_fail",
                    "severity": "error",
                    "message": (
                        f"ngspice produced no value for {name}.{detail}"
                    ),
                    "file": first_source,
                }
                for name in missing
            ]
            return {"total": len(violations), "violations": violations}
        violations = []
        measurements = []
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
                        "file": first_source,
                    }
                )
        return {
            "total": len(violations),
            "violations": violations,
            "measurements": measurements,
        }

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
                "runner_unavailable", f"spice sim timed out after {timeout_s}s."
            ) from exc
