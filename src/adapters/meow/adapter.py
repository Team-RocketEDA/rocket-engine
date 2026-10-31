"""Meow EME solver adapter: run_em behind the ToolAdapter port.

Protocol, mirroring the SAX adapter: stage the sim driver plus a job
JSON into the workdir, run `python meow_driver.py meow_job.json`
under a timeout, then parse the JSON envelope on stdout. The verdict
always comes from parsed output: missed S-parameter or convergence
bounds are FAIL, a malformed device synthesizes an error violation
with file/line, and only a meow-less interpreter raises
missing_dependency.

Generalization law: the project device YAML is the input — widths,
wavelength, cell length, mode counts, and targets all ride the
spec. `run_eme_smoke` (the sibling smoke) qualifies the install;
this op generalizes it and must never hardcode the proof widths.
Every run solves twice (base then refined modes) so convergence
evidence ships with the verdict, not as prose. FDTD/FEM stay out:
proposed, not proven.

Tool resolution: an explicit job `tool_dir` containing a python
wins, else the engine interpreter (meow arrives via the pip
`photonic` group). Where the tools live on disk is B10 scope.
"""

import json
import math
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

OPERATION = "run_em"
_TIMEOUT_S = 120
_DRIVER_NAME = "meow_driver.py"
_JOB_NAME = "meow_job.json"
_METRICS = (
    "transmission",
    "reflection",
    "convergence_dT",
    "convergence_dneff",
)


def _is_number(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _check_doc(doc, spec):
    if not isinstance(doc, dict):
        raise AdapterError(
            "invalid_command", f"Device spec is not a mapping: {spec}."
        )
    for key in ("wl_um", "cell_length_um"):
        if not _is_number(doc.get(key)) or not doc[key] > 0:
            raise AdapterError(
                "invalid_command",
                f"Device spec needs a positive {key}: {spec}.",
            )
    widths = doc.get("widths_um")
    if (
        not isinstance(widths, list)
        or not widths
        or not all(_is_number(w) and w > 0 for w in widths)
    ):
        raise AdapterError(
            "invalid_command",
            f"Device spec needs positive widths_um: {spec}.",
        )
    modes = doc.get("modes")
    if not isinstance(modes, dict):
        raise AdapterError(
            "invalid_command", f"Device spec needs modes: {spec}."
        )
    base, refined = modes.get("base"), modes.get("refined")
    if not _is_int(base) or base < 1 or not _is_int(refined):
        raise AdapterError(
            "invalid_command",
            f"Device modes need integer base/refined counts: {spec}.",
        )
    if not refined > base:
        raise AdapterError(
            "invalid_command",
            f"Refined modes must exceed base modes: {modes!r} in {spec}.",
        )
    targets = doc.get("targets", [])
    if not isinstance(targets, list):
        raise AdapterError(
            "invalid_command", f"Device targets must be a list: {spec}."
        )
    for target in targets:
        if not isinstance(target, dict) or target.get("metric") not in _METRICS:
            raise AdapterError(
                "invalid_command",
                f"Bad target {target!r}: {spec} "
                f"(metric one of {', '.join(_METRICS)}).",
            )
        bounds = {
            key: target[key]
            for key in ("min", "max")
            if target.get(key) is not None
        }
        if not bounds or not all(_is_number(v) for v in bounds.values()):
            raise AdapterError(
                "invalid_command",
                f"Target needs numeric min and/or max: {target!r}.",
            )


def _load_spec(spec):
    try:
        text = Path(spec).read_text(encoding="utf-8")
    except OSError as exc:
        raise AdapterError(
            "invalid_reference", f"Device spec unreadable: {spec} ({exc})."
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
            "invalid_reference", f"Device spec is not YAML: {where} ({exc})."
        ) from exc
    _check_doc(doc, spec)
    return text, doc


def _target_line(spec_text):
    for number, line in enumerate((spec_text or "").splitlines(), 1):
        if "targets" in line:
            return number
    return None


class MeowAdapter(ToolAdapter):
    """run_em via meow: EME mode/field solving with convergence evidence.

    Serves the run_em operation with deck.tool `meow` (the only
    tool). Stages the sim driver plus a job JSON, runs it under a
    timeout, and parses the JSON envelope: the fundamental
    S-parameters at the base mode count plus the refined-basis
    deltas (convergence evidence) against min/max bounds.

    Job keys:
        sources (required): Exactly one device spec YAML path.
        timeout_s: Sim budget in seconds (default 120).
        tool_dir: Directory holding the sim python; the engine
            interpreter otherwise.
        deck: Optional mapping; deck.tool must be meow here.
        workdir: Run directory (default ".").

    Args:
        runner: Optional isolated runner; direct subprocess when None.

    Caution: Missed S-parameter or convergence bounds are FAIL and
        a malformed device synthesizes an error violation with
        file/line — the verdict always comes from parsed output,
        never the exit code.
    """

    def __init__(self, runner=None):
        self._runner = runner

    def capabilities(self, target):
        """Report the served operation and tool name.

        Args:
            target: Target the capabilities are reported for
                (accepted, unused — one device per job).

        Returns:
            Capability mapping with operations and tool.
        """
        return {"operations": [OPERATION], "tool": "meow"}

    def preflight(self, job):
        """Check operation, timeout, spec shape, and sim python.

        Cheap deterministic checks first, tool resolution last, the
        runner probe closing it out.

        Args:
            job: Solver job with operation run_em plus the device
                spec source and timeout inputs.

        Returns:
            Checked mapping with the resolved python, spec, spec
                text, parsed doc, and timeout_s.

        Raises:
            AdapterError: unsupported_operation for another
                operation, invalid_command for a bad timeout or
                device spec, invalid_reference unless exactly one
                readable spec source is given, missing_dependency
                for an unresolvable sim python.
        """
        if job.get("operation") != OPERATION:
            raise AdapterError(
                "unsupported_operation",
                f"Meow handles {OPERATION}, got {job.get('operation')}.",
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
                f"run_em needs one device spec, got: {missing or sources}.",
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
            job: Solver job with operation run_em plus the device
                spec source and timeout inputs.

        Returns:
            Native output with exit_code, stdout/stderr, spec,
                spec_text, and the parsed targets.

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
            "targets": list(checked["doc"].get("targets") or []),
        }

    def parse(self, native_output):
        """Parse the driver envelope into S-params and convergence.

        Malformed devices synthesize one error violation with
        file/line rather than parsing as clean; S-parameter and
        convergence bound misses carry engine-computed margins.

        Args:
            native_output: Native output with the driver stdout
                envelope, spec, spec_text, and targets.

        Returns:
            {total, violations[], measurements[], modes,
                convergence, meow_version, tidy3d_version} with
                ratio values and margins.

        Raises:
            AdapterError: missing_dependency when the sim python
                has no meow, runner_unavailable when the driver
                printed no JSON envelope or no result.
        """
        spec = native_output.get("spec", "")
        try:
            envelope = json.loads(native_output.get("stdout", ""))
        except (TypeError, ValueError):
            raise AdapterError(
                "runner_unavailable",
                "meow driver printed no JSON envelope.",
            ) from None
        if not isinstance(envelope, dict) or not isinstance(
            envelope.get("ok"), bool
        ):
            raise AdapterError(
                "runner_unavailable",
                "meow driver printed no JSON envelope.",
            )
        if not envelope["ok"]:
            error = envelope.get("error") or {}
            code = error.get("code")
            message = error.get("message", "meow run failed")
            if code == "missing_dependency":
                raise AdapterError("missing_dependency", message)
            if code != "invalid_device":
                raise AdapterError(
                    "runner_unavailable",
                    f"meow driver failed without a device error: {message}.",
                )
            violation = {
                "rule": "device",
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
                "meow_version": envelope.get("meow_version"),
                "tidy3d_version": envelope.get("tidy3d_version"),
            }
        result = envelope.get("result") or {}
        base = result.get("base") or {}
        convergence = result.get("convergence") or {}
        values = {
            "transmission": base.get("transmission"),
            "reflection": base.get("reflection"),
            "convergence_dT": convergence.get("dT"),
            "convergence_dneff": convergence.get("dneff"),
        }
        if not all(_is_number(v) for v in values.values()):
            raise AdapterError(
                "runner_unavailable",
                "meow driver envelope has no result.",
            )
        violations = []
        measurements = []
        for target in native_output.get("targets") or []:
            metric = target["metric"]
            actual = float(values[metric])
            bounds = {
                key: target[key]
                for key in ("min", "max")
                if target.get(key) is not None
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
            measurements.append(
                {
                    "name": metric,
                    "value": actual,
                    "unit": "",
                    "target": dict(bounds),
                    "margin": margin,
                    "status": status,
                }
            )
            if failed:
                rule = (
                    "convergence"
                    if metric.startswith("convergence")
                    else "s_param"
                )
                violation = {
                    "rule": rule,
                    "severity": "error",
                    "message": (
                        f"{metric} = {actual:.6g} misses "
                        f"{', '.join(failed)} "
                        f"(margin {margin:.6g})."
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
            "modes": {
                "base": base,
                "refined": result.get("refined") or {},
            },
            "convergence": dict(convergence),
            "meow_version": envelope.get("meow_version"),
            "tidy3d_version": envelope.get("tidy3d_version"),
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
                f"meow sim timed out after {timeout_s}s.",
            ) from exc
