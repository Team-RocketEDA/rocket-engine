"""Devsim TCAD adapter: run_tcad behind the ToolAdapter port."""

import json
import shutil
import subprocess
from pathlib import Path

from ...execution.errors import ExecutionError
from ...interfaces import ToolAdapter
from ..errors import AdapterError

OPERATION = "run_tcad"
_TOOL = "devsim"
_DUMP = "devsim_dump.json"
_TIMEOUT_S = 300


class DevsimAdapter(ToolAdapter):
    """run_tcad via devsim: driver dump parsed to measurements.

    Serves the run_tcad operation with tool `devsim`. The driver
    script calls get_contact_current/get_*_model_values plus
    solve(info=True) and dumps JSON; the adapter parses the dump
    file, never stdout scraping.

    Job keys:
        script (required): Driver python script path.
        workdir: Run directory (default ".").
        timeout_s: Budget in seconds (default 300).
        python: Driver python binary (default sys python).

    Args:
        runner: Optional isolated runner; direct subprocess when None.
    """

    def __init__(self, runner=None):
        self._runner = runner

    def capabilities(self, target):
        """Report the served operation and tool.

        Args:
            target: Target the capabilities are reported for.

        Returns:
            Capability mapping with operations and tool.
        """
        return {"operations": [OPERATION], "tool": _TOOL,
                "dump": _DUMP}

    def preflight(self, job):
        """Check operation, script, and devsim importability.

        Args:
            job: Solver job with operation run_tcad plus script.

        Returns:
            Checked mapping with script, timeout, and python.

        Raises:
            AdapterError: unsupported_operation, invalid_reference
                for a missing script, missing_dependency with
                BLOCKED-needs-host when devsim is not importable.
        """
        if job.get("operation") != OPERATION:
            raise AdapterError(
                "unsupported_operation",
                f"Devsim handles {OPERATION}, got {job.get('operation')}.",
            )
        script = job.get("script")
        if not script or not Path(script).is_file():
            raise AdapterError(
                "invalid_reference", f"Driver script not found: {script}.")
        try:
            __import__(_TOOL)
        except ImportError as exc:
            raise AdapterError(
                "missing_dependency",
                "BLOCKED-needs-host: devsim not importable "
                "(need devsim==2.11.2 in the engine venv).",
            ) from exc
        timeout = job.get("timeout_s", _TIMEOUT_S)
        if (not isinstance(timeout, (int, float))
                or isinstance(timeout, bool) or not timeout > 0):
            raise AdapterError("invalid_command", f"Bad timeout: {timeout!r}.")
        checked = {"script": str(script), "timeout_s": timeout,
                   "python": job.get("python") or "python3"}
        if self._runner is not None:
            try:
                self._runner.preflight()
            except ExecutionError as exc:
                raise AdapterError(exc.code, str(exc)) from exc
        return checked

    def execute(self, job):
        """Run the driver script under a timeout.

        Args:
            job: Solver job with operation run_tcad plus script.

        Returns:
            Native output with exit_code, stdout/stderr, dump, file.
        """
        checked = self.preflight(job)
        workdir = job.get("workdir", ".")
        if not Path(workdir).is_dir():
            raise AdapterError(
                "invalid_reference", f"Workdir not found: {workdir}.")
        proc = self._run([checked["python"], checked["script"]],
                         workdir, checked["timeout_s"])
        dump_path = Path(workdir) / _DUMP
        dump = None
        if dump_path.is_file():
            try:
                dump = json.loads(dump_path.read_text())
            except ValueError:
                dump = None
        return {"exit_code": proc.returncode, "stdout": proc.stdout,
                "stderr": proc.stderr, "dump": dump,
                "dump_file": _DUMP}

    def parse(self, native_output):
        """Parse the driver JSON dump to verdict plus measurements.

        Args:
            native_output: Native output with the dump mapping.

        Returns:
            {total, violations[], measurements[], source} with the
                dump file as source.

        Raises:
            AdapterError: runner_unavailable when no dump is present.
        """
        dump = native_output.get("dump")
        if not isinstance(dump, dict):
            raise AdapterError(
                "runner_unavailable", "Devsim run left no dump JSON.")
        solve = dump.get("solve") or {}
        violations = []
        if solve.get("converged") is False or not dump.get("currents"):
            violations.append({"rule": "tcad_converge",
                               "severity": "error",
                               "message": "Devsim solve did not converge."})
        measurements = []
        for name, value in (dump.get("currents") or {}).items():
            try:
                measurements.append({"name": f"current.{name}",
                                     "value": float(value), "unit": "A"})
            except (TypeError, ValueError):
                continue
        pots = dump.get("potentials") or []
        if pots:
            measurements.append({"name": "potential.count",
                                 "value": float(len(pots)), "unit": "count"})
        return {"total": len(violations), "violations": violations,
                "measurements": measurements, "source": "dump",
                "dump_file": native_output.get("dump_file", _DUMP)}

    def _run(self, argv, workdir, timeout_s):
        if self._runner is not None:
            try:
                return self._runner.run(argv, workdir, timeout_s)
            except ExecutionError as exc:
                raise AdapterError(exc.code, str(exc)) from exc
        try:
            return subprocess.run(argv, capture_output=True, text=True,
                                  timeout=timeout_s, cwd=workdir)
        except subprocess.TimeoutExpired as exc:
            raise AdapterError(
                "runner_unavailable", "Devsim run timed out.") from exc
