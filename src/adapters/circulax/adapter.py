"""Circulax time-domain solver adapter: run_optical behind the ToolAdapter port.

Protocol, mirroring the SAX adapter: stage the sim driver plus a job
JSON into the workdir, run `python circulax_driver.py
circulax_job.json` under a timeout, then parse the JSON envelope on
stdout. The verdict always comes from parsed output: missed voltage
bounds are FAIL, a malformed circuit synthesizes an error violation
with file/line/sim_time, and only a circulax-less interpreter raises
missing_dependency.

Generalization law: the project circuit YAML is the input — R/C/V,
topology, time grid, observed port, and targets all ride the spec.
`run_rc_step` (the sibling smoke) qualifies the install; this op
generalizes it and must never hardcode the proof values. Only the
proven transient path runs; DC/AC/harmonic-balance specs are refused
until a proof lands.

Tool resolution: an explicit job `tool_dir` containing a python
wins, else the engine interpreter (circulax arrives via the pip
`photonic` group). Where the tools live on disk is B10 scope.
"""

import json
import math
import re
import subprocess
import sys
from pathlib import Path

from ruamel.yaml import YAML

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
    from ..errors import AdapterError
except ImportError:
    from rocket_engine.adapters.errors import AdapterError

OPERATION = "run_optical"
_TIMEOUT_S = 120
_DRIVER_NAME = "circulax_driver.py"
_JOB_NAME = "circulax_job.json"
_PORT_REF_RE = re.compile(r"^[^,\s]+,[^,\s]+$")
_COMPONENTS = ("vsource", "resistor", "capacitor", "ground")


def _is_number(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _check_instance(name, inst, spec):
    if not isinstance(inst, dict) or inst.get("component") not in _COMPONENTS:
        raise AdapterError(
            "invalid_command",
            f"Instance {name!r} needs a component model "
            f"({', '.join(_COMPONENTS)}): {spec}.",
        )
    settings = inst.get("settings", {})
    if not isinstance(settings, dict):
        raise AdapterError(
            "invalid_command",
            f"Instance {name!r} settings must be a mapping: {spec}.",
        )
    component = inst["component"]
    if component == "vsource" and not _is_number(settings.get("V")):
        raise AdapterError(
            "invalid_command",
            f"Instance {name!r} needs a numeric V setting: {spec}.",
        )
    if component == "resistor" and not (
        _is_number(settings.get("R")) and settings["R"] > 0
    ):
        raise AdapterError(
            "invalid_command",
            f"Instance {name!r} needs a positive R setting: {spec}.",
        )
    if component == "capacitor" and not (
        _is_number(settings.get("C")) and settings["C"] > 0
    ):
        raise AdapterError(
            "invalid_command",
            f"Instance {name!r} needs a positive C setting: {spec}.",
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
        _check_instance(name, inst, spec)
    connections = doc.get("connections", {})
    if not isinstance(connections, dict) or not all(
        isinstance(k, str) and isinstance(v, str)
        for k, v in connections.items()
    ):
        raise AdapterError(
            "invalid_command", f"Circuit connections must be a mapping: {spec}."
        )
    for key, val in connections.items():
        if not _PORT_REF_RE.match(key) or not _PORT_REF_RE.match(val):
            raise AdapterError(
                "invalid_command",
                f"Bad connection {key!r}: {val!r} in {spec} "
                "(want `instance,port`).",
            )
        for ref in (key, val):
            if ref.partition(",")[0] not in instances:
                raise AdapterError(
                    "invalid_command",
                    f"Connection names unknown instance {ref!r}: {spec}.",
                )
    transient = doc.get("transient")
    if not isinstance(transient, dict):
        raise AdapterError(
            "invalid_command", f"Circuit spec needs a transient: {spec}."
        )
    t1, points = transient.get("t1_s"), transient.get("points")
    if not _is_number(t1) or not t1 > 0:
        raise AdapterError(
            "invalid_command", f"Bad transient t1_s: {t1!r} in {spec}."
        )
    if not isinstance(points, int) or isinstance(points, bool) or points < 2:
        raise AdapterError(
            "invalid_command", f"Bad transient points: {points!r} in {spec}."
        )
    dt0 = transient.get("dt0_s", 1e-8)
    if not _is_number(dt0) or not dt0 > 0:
        raise AdapterError(
            "invalid_command", f"Bad transient dt0_s: {dt0!r} in {spec}."
        )
    observe = transient.get("observe")
    if (
        not isinstance(observe, str)
        or not _PORT_REF_RE.match(observe)
        or observe.partition(",")[0] not in instances
    ):
        raise AdapterError(
            "invalid_command",
            f"Bad transient observe port: {observe!r} in {spec} "
            "(want `instance,port` of a known instance).",
        )
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
        at_s = target.get("at_s")
        if not _is_number(at_s) or not 0 <= at_s <= t1:
            raise AdapterError(
                "invalid_command",
                f"Target time outside transient: {at_s!r} in {spec}.",
            )
        bounds = {
            key: target[key]
            for key in ("min_V", "max_V")
            if target.get(key) is not None
        }
        if not bounds or not all(_is_number(v) for v in bounds.values()):
            raise AdapterError(
                "invalid_command",
                f"Target needs numeric min_V and/or max_V: {target!r}.",
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


def _target_line(spec_text):
    for number, line in enumerate((spec_text or "").splitlines(), 1):
        if "targets" in line:
            return number
    return None


class CirculaxAdapter(ToolAdapter):
    """run_optical via circulax: time-domain transient circuit sim.

    Serves the run_optical operation with deck.tool `circulax` (the
    second tool; sax stays the default). Stages the sim driver plus
    a job JSON, runs it under a timeout, and parses the JSON
    envelope: the observed voltage trace plus per-target
    measurements against min_V/max_V bounds.

    Job keys:
        sources (required): Exactly one circuit spec YAML path.
        timeout_s: Sim budget in seconds (default 120).
        tool_dir: Directory holding the sim python; the engine
            interpreter otherwise.
        deck: Optional mapping; deck.tool must be circulax here.
        workdir: Run directory (default ".").

    Args:
        runner: Optional isolated runner; direct subprocess when None.

    Caution: Missed voltage bounds are FAIL and a malformed circuit
        synthesizes an error violation with file/line/sim_time —
        the verdict always comes from parsed output, never the
        exit code.
    """

    def __init__(self, runner=None):
        self._runner = runner

    def capabilities(self, target):
        """Report the served operation and tool name.

        Args:
            target: Target the capabilities are reported for
                (accepted, unused — one circuit per job).

        Returns:
            Capability mapping with operations and tool.
        """
        return {"operations": [OPERATION], "tool": "circulax"}

    def preflight(self, job):
        """Check operation, timeout, spec shape, and sim python.

        Cheap deterministic checks first, tool resolution last, the
        runner probe closing it out.

        Args:
            job: Solver job with operation run_optical plus the
                circuit spec source and timeout inputs.

        Returns:
            Checked mapping with the resolved python, spec, spec
                text, parsed doc, and timeout_s.

        Raises:
            AdapterError: unsupported_operation for another
                operation, invalid_command for a bad timeout or
                circuit spec, invalid_reference unless exactly one
                readable spec source is given, missing_dependency
                for an unresolvable sim python.
        """
        if job.get("operation") != OPERATION:
            raise AdapterError(
                "unsupported_operation",
                f"Circulax handles {OPERATION}, got {job.get('operation')}.",
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
        """Stage the driver plus job JSON, then run the sim.

        Args:
            job: Solver job with operation run_optical plus the
                circuit spec source and timeout inputs.

        Returns:
            Native output with exit_code, stdout/stderr, spec,
                spec_text, observe port, and the parsed targets.

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
        driver = Path(__file__).with_name("_driver.py").read_text(
            encoding="utf-8"
        )
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
            "observe": checked["doc"]["transient"]["observe"],
            "targets": list(checked["doc"].get("targets") or []),
        }

    def parse(self, native_output):
        """Parse the driver envelope into a trace and measurements.

        Malformed circuits synthesize one error violation with
        file/line rather than parsing as clean; voltage bound
        misses carry engine-computed margins.

        Args:
            native_output: Native output with the driver stdout
                envelope, spec, spec_text, observe port, and
                targets.

        Returns:
            {total, violations[], measurements[], transient,
                circulax_version} with volt values and margins.

        Raises:
            AdapterError: missing_dependency when the sim python
                has no circulax, runner_unavailable when the
                driver printed no JSON envelope or no result.
        """
        spec = native_output.get("spec", "")
        try:
            envelope = json.loads(native_output.get("stdout", ""))
        except (TypeError, ValueError):
            raise AdapterError(
                "runner_unavailable",
                "circulax driver printed no JSON envelope.",
            ) from None
        if not isinstance(envelope, dict) or not isinstance(
            envelope.get("ok"), bool
        ):
            raise AdapterError(
                "runner_unavailable",
                "circulax driver printed no JSON envelope.",
            )
        if not envelope["ok"]:
            error = envelope.get("error") or {}
            code = error.get("code")
            message = error.get("message", "circulax run failed")
            if code == "missing_dependency":
                raise AdapterError("missing_dependency", message)
            if code != "invalid_circuit":
                raise AdapterError(
                    "runner_unavailable",
                    f"circulax driver failed without a circuit error: "
                    f"{message}.",
                )
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
                "circulax_version": envelope.get("circulax_version"),
            }
        result = envelope.get("result") or {}
        grid = result.get("t_s")
        curve = result.get("v_V")
        if (
            not isinstance(grid, list)
            or len(grid) < 2
            or not all(_is_number(t) for t in grid)
            or not isinstance(curve, list)
            or len(curve) != len(grid)
            or not all(isinstance(v, (int, float)) for v in curve)
        ):
            raise AdapterError(
                "runner_unavailable",
                "circulax driver envelope has no result.",
            )
        observe = native_output.get("observe", "")
        violations = []
        measurements = []
        for target in native_output.get("targets") or []:
            at_s = target["at_s"]
            index = min(range(len(grid)), key=lambda i: abs(grid[i] - at_s))
            actual = float(curve[index])
            name = f"V({observe})@{at_s}s"
            bounds = {
                key: target[key]
                for key in ("min_V", "max_V")
                if target.get(key) is not None
            }
            margins = {}
            if "min_V" in bounds:
                margins["min_V"] = actual - bounds["min_V"]
            if "max_V" in bounds:
                margins["max_V"] = bounds["max_V"] - actual
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
                    "value": actual,
                    "unit": "V",
                    "target": dict(bounds),
                    "margin": margin,
                    "status": status,
                }
            )
            if failed:
                violation = {
                    "rule": "transient",
                    "severity": "error",
                    "message": (
                        f"{name} = {actual:.6g} V misses "
                        f"{', '.join(failed)} V "
                        f"(margin {margin:.6g} V)."
                    ),
                    "file": spec,
                    "sim_time": at_s,
                }
                line = _target_line(native_output.get("spec_text"))
                if line is not None:
                    violation["line"] = line
                violations.append(violation)
        return {
            "total": len(violations),
            "violations": violations,
            "measurements": measurements,
            "transient": {
                "t_s": list(grid),
                "v_V": [float(v) for v in curve],
                "observe": observe,
            },
            "circulax_version": envelope.get("circulax_version"),
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
                "runner_unavailable",
                f"circulax sim timed out after {timeout_s}s.",
            ) from exc
