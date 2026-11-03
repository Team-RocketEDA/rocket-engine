"""Meep FDTD adapter: run_optical behind the ToolAdapter port."""

import json
import re
import subprocess
from pathlib import Path

from ...execution.errors import ExecutionError
from ...interfaces import ToolAdapter
from ..errors import AdapterError

OPERATION = "run_optical"
_TOOL = "meep"
_DUMP = "meep_dump.json"
_TIMEOUT_S = 600
_FLUX_RE = re.compile(r"^(flux|force|(?:electric|magnetic|total)-energy"
                       r"|ldos|harminv)\d*:,", re.M)


class MeepAdapter(ToolAdapter):
    """run_optical via meep: in-API dump plus HDF5 telemetry.

    Serves the run_optical operation with tool `meep`. The driver
    runs under subprocess python (pymeep env) and reports via
    get_fluxes/get_dft_array/get_array/Harminv.modes dumped to
    JSON; HDF5 field files stay as artifacts. Deterministic S1
    telemetry lines are the fallback, never the first channel.

    Job keys:
        script (required): Driver python script path.
        workdir: Run directory (default ".").
        timeout_s: Budget in seconds (default 600).

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
        return {"operations": [OPERATION], "tool": _TOOL, "dump": _DUMP}

    def preflight(self, job):
        """Check operation, script, and meep importability.

        Args:
            job: Solver job with operation run_optical plus script.

        Returns:
            Checked mapping with script and timeout.

        Raises:
            AdapterError: unsupported_operation, invalid_reference
                for a missing script, missing_dependency with
                BLOCKED-needs-host when meep is not importable.
        """
        if job.get("operation") != OPERATION:
            raise AdapterError(
                "unsupported_operation",
                f"Meep handles {OPERATION}, got {job.get('operation')}.")
        script = job.get("script")
        if not script or not Path(script).is_file():
            raise AdapterError(
                "invalid_reference", f"Driver script not found: {script}.")
        try:
            __import__(_TOOL)
        except ImportError as exc:
            raise AdapterError(
                "missing_dependency",
                "BLOCKED-needs-host: meep not importable "
                "(need pymeep==1.35.0 via the conda env).",
            ) from exc
        timeout = job.get("timeout_s", _TIMEOUT_S)
        if (not isinstance(timeout, (int, float))
                or isinstance(timeout, bool) or not timeout > 0):
            raise AdapterError("invalid_command", f"Bad timeout: {timeout!r}.")
        checked = {"script": str(script), "timeout_s": timeout}
        if self._runner is not None:
            try:
                self._runner.preflight()
            except ExecutionError as exc:
                raise AdapterError(exc.code, str(exc)) from exc
        return checked

    def execute(self, job):
        """Run the driver script under a timeout.

        Args:
            job: Solver job with operation run_optical plus script.

        Returns:
            Native output with exit_code, stdout/stderr, dump, file.
        """
        checked = self.preflight(job)
        workdir = job.get("workdir", ".")
        if not Path(workdir).is_dir():
            raise AdapterError(
                "invalid_reference", f"Workdir not found: {workdir}.")
        try:
            proc = subprocess.run(
                ["python3", checked["script"]], capture_output=True,
                text=True, timeout=checked["timeout_s"], cwd=workdir)
        except subprocess.TimeoutExpired as exc:
            raise AdapterError(
                "runner_unavailable", "Meep run timed out.") from exc
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
        """Parse the in-API dump, else S1 telemetry, else violation.

        Args:
            native_output: Native output with the dump mapping.

        Returns:
            {total, violations[], measurements[], source}.

        Raises:
            AdapterError: runner_unavailable with no dump and no
                telemetry (a failed run must never parse as clean).
        """
        dump = native_output.get("dump")
        if isinstance(dump, dict):
            measurements = []
            for flux in dump.get("fluxes") or []:
                try:
                    measurements.append({"name": "flux", "value": float(flux),
                                         "unit": "a.u."})
                except (TypeError, ValueError):
                    continue
            trans = dump.get("transmission")
            if isinstance(trans, (int, float)) and not isinstance(trans, bool):
                measurements.append({"name": "transmission",
                                     "value": float(trans), "unit": "ratio"})
            return {"total": 0, "violations": [], "measurements": measurements,
                    "source": "dump",
                    "dump_file": native_output.get("dump_file", _DUMP)}
        text = (native_output.get("stdout") or "")
        if _FLUX_RE.search(text):
            return {"total": 0, "violations": [],
                    "measurements": [{"name": "telemetry", "value": 1.0,
                                      "unit": "count"}],
                    "source": "stdio_fallback"}
        if native_output.get("exit_code", 0) != 0:
            return {"total": 1, "violations": [
                {"rule": "optical_fail", "severity": "error",
                 "message": "Meep run left no dump or telemetry."}],
                "measurements": [], "source": "stdio_fallback"}
        raise AdapterError(
            "runner_unavailable", "Meep output has no dump verdict.")
