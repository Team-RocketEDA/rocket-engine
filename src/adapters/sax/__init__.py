"""SAX photonic sim solver adapter: run_optical behind the ToolAdapter port.

Protocol, verified against sax 0.18.2: stage the sim driver plus a
job JSON into the workdir, run `python sax_driver.py sax_job.json`
under a timeout, then parse the JSON envelope on stdout. The verdict
always comes from parsed output: missed target bounds are FAIL, a
malformed circuit synthesizes an error violation with file/line, and
only a sax-less interpreter raises missing_dependency.

Tool resolution: an explicit job `tool_dir` containing a python
wins, else the engine interpreter (sax arrives via the pip
`photonic` group). Where the tools live on disk is B10 scope.
"""

import json
import math
import re
import subprocess
import sys
from pathlib import Path

from ruamel.yaml import YAML

from ...execution.errors import ExecutionError
from ...execution.runner import tool_roots
from ...interfaces import ToolAdapter
from ..errors import AdapterError

OPERATION = "run_optical"
_TIMEOUT_S = 120
_DRIVER_NAME = "sax_driver.py"
_JOB_NAME = "sax_job.json"
_PORT_REF_RE = re.compile(r"^[^,\s]+,[^,\s]+$")


def _is_number(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _check_doc(doc, spec):
    if not isinstance(doc, dict):
        raise AdapterError(
            "invalid_command", f"Circuit spec is not a mapping: {spec}."
        )
    instances = doc.get("instances")
    if not isinstance(instances, dict) or not instances:
        raise AdapterError(
            "invalid_command", f"Circuit spec needs instances: {spec}."
        )
    for name, inst in instances.items():
        if not isinstance(inst, dict) or not isinstance(
            inst.get("component"), str
        ):
            raise AdapterError(
                "invalid_command",
                f"Instance {name!r} needs a component model: {spec}.",
            )
        settings = inst.get("settings", {})
        if not isinstance(settings, dict):
            raise AdapterError(
                "invalid_command",
                f"Instance {name!r} settings must be a mapping: {spec}.",
            )
    connections = doc.get("connections", {})
    if not isinstance(connections, dict) or not all(
        isinstance(k, str) and isinstance(v, str)
        for k, v in connections.items()
    ):
        raise AdapterError(
            "invalid_command", f"Circuit connections must be a mapping: {spec}."
        )
    for key, val in connections.items():
        # sax InstancePort is `instance,port`; anything else (notably
        # dot-separated refs) fails deep inside sax with no location.
        if not _PORT_REF_RE.match(key) or not _PORT_REF_RE.match(val):
            raise AdapterError(
                "invalid_command",
                f"Bad connection {key!r}: {val!r} in {spec} "
                "(want `instance,port`).",
            )
    ports = doc.get("ports")
    if not isinstance(ports, dict) or not ports:
        raise AdapterError(
            "invalid_command", f"Circuit spec needs ports: {spec}."
        )
    for ext, ref in ports.items():
        if not isinstance(ref, str) or not _PORT_REF_RE.match(ref):
            raise AdapterError(
                "invalid_command",
                f"Bad port {ext!r}: {ref!r} in {spec} "
                "(want `instance,port`).",
            )
    sweep = doc.get("sweep")
    if not isinstance(sweep, dict):
        raise AdapterError(
            "invalid_command", f"Circuit spec needs a sweep: {spec}."
        )
    start, stop, points = (
        sweep.get("start_nm"),
        sweep.get("stop_nm"),
        sweep.get("points"),
    )
    if (
        not _is_number(start)
        or not _is_number(stop)
        or start <= 0
        or stop <= 0
        or start > stop
    ):
        raise AdapterError(
            "invalid_command", f"Bad sweep wavelengths: {sweep!r}."
        )
    if not isinstance(points, int) or isinstance(points, bool) or points < 1:
        raise AdapterError("invalid_command", f"Bad sweep points: {points!r}.")
    targets = doc.get("targets", [])
    if not isinstance(targets, list):
        raise AdapterError(
            "invalid_command", f"Circuit targets must be a list: {spec}."
        )
    for target in targets:
        if not isinstance(target, dict):
            raise AdapterError(
                "invalid_command", f"Bad target {target!r}: {spec}."
            )
        src, dst, at_nm = (
            target.get("from"),
            target.get("to"),
            target.get("at_nm"),
        )
        if src not in ports or dst not in ports:
            raise AdapterError(
                "invalid_command",
                f"Target ports unknown: {src!r}->{dst!r} in {spec}.",
            )
        if not _is_number(at_nm) or not start <= at_nm <= stop:
            raise AdapterError(
                "invalid_command",
                f"Target wavelength outside sweep: {at_nm!r} in {spec}.",
            )
        bounds = {
            key: target[key]
            for key in ("min_db", "max_db")
            if target.get(key) is not None
        }
        if not bounds or not all(_is_number(v) for v in bounds.values()):
            raise AdapterError(
                "invalid_command",
                f"Target needs numeric min_db and/or max_db: {target!r}.",
            )


def _load_spec(spec):
    try:
        text = Path(spec).read_text(encoding="utf-8")
    except OSError as exc:
        raise AdapterError(
            "invalid_reference", f"Circuit spec unreadable: {spec} ({exc})."
        ) from exc
    try:
        doc = YAML(typ="safe").load(text)
    except Exception as exc:
        mark = getattr(exc, "problem_mark", None) or getattr(
            exc, "context_mark", None
        )
        where = (
            f"{spec}:{mark.line + 1}:{mark.column + 1}"
            if mark is not None
            else spec
        )
        raise AdapterError(
            "invalid_reference", f"Circuit spec is not YAML: {where} ({exc})."
        ) from exc
    _check_doc(doc, spec)
    return text, doc


def _to_db(power):
    if power is None or power != power or power <= 0:
        return float("-inf")
    return 10.0 * math.log10(power)


def _target_line(spec_text):
    for number, line in enumerate((spec_text or "").splitlines(), 1):
        if "targets" in line:
            return number
    return None


class SaxAdapter(ToolAdapter):
    def __init__(self, runner=None):
        self._runner = runner

    def capabilities(self, target):
        return {"operations": [OPERATION], "tool": "sax"}

    def preflight(self, job):
        # Cheap deterministic checks first: operation, timeout,
        # sources, spec shape. Tool resolution last, since it depends
        # on the machine; the runner probe closes it out.
        if job.get("operation") != OPERATION:
            raise AdapterError(
                "unsupported_operation",
                f"SAX handles {OPERATION}, got {job.get('operation')}.",
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
        if len(sources) != 1 or missing:
            raise AdapterError(
                "invalid_reference",
                f"run_optical needs one circuit spec, got: {missing or sources}.",
            )
        spec = sources[0]
        text, doc = _load_spec(spec)
        checked = {
            "python": self._resolve(job),
            "spec": spec,
            "text": text,
            "doc": doc,
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
        driver = Path(__file__).with_name("_driver.py").read_text(encoding="utf-8")
        (workdir_path / _DRIVER_NAME).write_text(driver, encoding="utf-8")
        (workdir_path / _JOB_NAME).write_text(
            json.dumps(
                {
                    "spec": checked["spec"],
                    "text": checked["text"],
                    "doc": checked["doc"],
                }
            ),
            encoding="utf-8",
        )
        roots = tool_roots([checked["python"]])
        proc = self._run(
            [checked["python"], _DRIVER_NAME, _JOB_NAME],
            workdir,
            checked["timeout_s"],
            roots,
        )
        return {
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "spec": checked["spec"],
            "spec_text": checked["text"],
            "targets": list(checked["doc"].get("targets") or []),
        }

    def parse(self, native_output):
        spec = native_output.get("spec", "")
        try:
            envelope = json.loads(native_output.get("stdout", ""))
        except (TypeError, ValueError):
            raise AdapterError(
                "runner_unavailable", "sax driver printed no JSON envelope."
            ) from None
        if not isinstance(envelope, dict) or not isinstance(
            envelope.get("ok"), bool
        ):
            raise AdapterError(
                "runner_unavailable", "sax driver printed no JSON envelope."
            )
        if not envelope["ok"]:
            error = envelope.get("error") or {}
            code = error.get("code")
            message = error.get("message", "sax run failed")
            if code == "missing_dependency":
                raise AdapterError("missing_dependency", message)
            if code != "invalid_circuit":
                raise AdapterError(
                    "runner_unavailable",
                    f"sax driver failed without a circuit error: {message}.",
                )
            # Defensive: a malformed circuit must never parse as clean.
            violation = {
                "rule": "circuit",
                "severity": "error",
                "message": message,
                "file": spec,
            }
            if error.get("line") is not None:
                violation["line"] = error["line"]
            return {
                "total": 1,
                "violations": [violation],
                "measurements": [],
                "sax_version": envelope.get("sax_version"),
            }
        result = envelope.get("result") or {}
        grid = result.get("wavelength_nm")
        transmission = result.get("transmission")
        if (
            not isinstance(grid, list)
            or not grid
            or not all(_is_number(w) for w in grid)
            or not isinstance(transmission, dict)
        ):
            raise AdapterError(
                "runner_unavailable", "sax driver envelope has no result."
            )
        violations = []
        measurements = []
        spectra = []
        for target in native_output.get("targets") or []:
            key = f"{target['from']}>{target['to']}"
            curve = transmission.get(key)
            if (
                not isinstance(curve, list)
                or len(curve) != len(grid)
                or not all(isinstance(v, (int, float)) for v in curve)
            ):
                raise AdapterError(
                    "runner_unavailable",
                    f"sax driver result misses pair {key}.",
                )
            at_nm = target["at_nm"]
            index = min(
                range(len(grid)), key=lambda i: abs(grid[i] - at_nm)
            )
            actual_db = _to_db(curve[index])
            name = f"T({target['from']}->{target['to']})@{at_nm}nm"
            bounds = {
                key: target[key]
                for key in ("min_db", "max_db")
                if target.get(key) is not None
            }
            margins = {}
            if "min_db" in bounds:
                margins["min_db"] = actual_db - bounds["min_db"]
            if "max_db" in bounds:
                margins["max_db"] = bounds["max_db"] - actual_db
            failed = [
                f"{kind} {bounds[kind]}"
                for kind, margin in margins.items()
                if margin < 0
            ]
            status = "fail" if failed else "pass"
            margin = min(margins[kind] for kind in bounds)
            measurements.append(
                {
                    "name": name,
                    "value": actual_db,
                    "unit": "dB",
                    "target": dict(bounds),
                    "margin": margin,
                    "status": status,
                }
            )
            spectra.append(
                {
                    "from": target["from"],
                    "to": target["to"],
                    "wavelength_nm": list(grid),
                    "transmission_db": [_to_db(v) for v in curve],
                }
            )
            if failed:
                violation = {
                    "rule": "transmission",
                    "severity": "error",
                    "message": (
                        f"{name} = {actual_db:.3f} dB misses "
                        f"{', '.join(failed)} dB "
                        f"(margin {margin:.3f} dB)."
                    ),
                    "file": spec,
                }
                line = _target_line(native_output.get("spec_text"))
                if line is not None:
                    violation["line"] = line
                violations.append(violation)
        return {
            "total": len(violations),
            "violations": violations,
            "measurements": measurements,
            "spectra": spectra,
            "sax_version": envelope.get("sax_version"),
        }

    @staticmethod
    def _resolve(job):
        tool_dir = job.get("tool_dir")
        if tool_dir:
            for name in ("python3", "python"):
                candidate = Path(tool_dir) / name
                if candidate.is_file():
                    return str(candidate)
            raise AdapterError(
                "missing_dependency", f"python not found in {tool_dir}."
            )
        return sys.executable

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
                "runner_unavailable", f"sax sim timed out after {timeout_s}s."
            ) from exc
