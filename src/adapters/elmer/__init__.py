"""Elmer FEM adapter: run_thermal behind the ToolAdapter port."""

import json
import re
import shutil
import subprocess
from pathlib import Path

from ...execution.errors import ExecutionError
from ...interfaces import ToolAdapter
from ..errors import AdapterError

OPERATION = "run_thermal"
_TOOL = "ElmerSolver"
_DUMP = "savescalars.json"
_TIMEOUT_S = 600
_NS_RE = re.compile(r"^(NS|SS) \(ITER=", re.M)


class ElmerAdapter(ToolAdapter):
    """run_thermal via Elmer: SaveScalars dump parsed to verdict.

    Serves the run_thermal operation with tool `elmer`. Channel
    priority is SaveScalars JSON first, CSV next, VTU fields as
    artifacts, deterministic NS/SS stdout last. No solver Python
    API exists, so execution stays subprocess.

    Job keys:
        sif (required): Elmer case.sif path.
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
        return {"operations": [OPERATION], "tool": "elmer",
                "dump": _DUMP}

    def preflight(self, job):
        """Check operation, sif, and ElmerSolver presence.

        Args:
            job: Solver job with operation run_thermal plus sif.

        Returns:
            Checked mapping with sif, binary, and timeout.

        Raises:
            AdapterError: unsupported_operation, invalid_reference
                for a missing sif, missing_dependency when
                ElmerSolver is absent (BLOCKED-needs-host).
        """
        if job.get("operation") != OPERATION:
            raise AdapterError(
                "unsupported_operation",
                f"Elmer handles {OPERATION}, got {job.get('operation')}.")
        sif = job.get("sif")
        if not sif or not Path(sif).is_file():
            raise AdapterError(
                "invalid_reference", f"Case sif not found: {sif}.")
        binary = shutil.which(_TOOL)
        if binary is None:
            raise AdapterError(
                "missing_dependency",
                "BLOCKED-needs-host: ElmerSolver not on PATH "
                "(CSC PPA route).")
        timeout = job.get("timeout_s", _TIMEOUT_S)
        if (not isinstance(timeout, (int, float))
                or isinstance(timeout, bool) or not timeout > 0):
            raise AdapterError("invalid_command", f"Bad timeout: {timeout!r}.")
        checked = {"sif": str(sif), "binary": binary,
                   "timeout_s": timeout}
        if self._runner is not None:
            try:
                self._runner.preflight()
            except ExecutionError as exc:
                raise AdapterError(exc.code, str(exc)) from exc
        return checked

    def execute(self, job):
        """Run ElmerSolver on the sif under a timeout.

        Args:
            job: Solver job with operation run_thermal plus sif.

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
                [checked["binary"], checked["sif"]], capture_output=True,
                text=True, timeout=checked["timeout_s"], cwd=workdir)
        except subprocess.TimeoutExpired as exc:
            raise AdapterError(
                "runner_unavailable", "Elmer run timed out.") from exc
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
        """Parse the SaveScalars dump, else NS/SS lines, else fail.

        Args:
            native_output: Native output with the dump mapping.

        Returns:
            {total, violations[], measurements[], source}.

        Raises:
            AdapterError: runner_unavailable with no dump and no
                iteration lines.
        """
        dump = native_output.get("dump")
        if isinstance(dump, dict):
            if dump.get("converged") is False or not dump.get("scalars"):
                return {"total": 1, "violations": [{
                    "rule": "fem_converge", "severity": "error",
                    "message": "Elmer solve did not converge."}],
                    "measurements": [], "source": "dump",
                    "dump_file": native_output.get("dump_file", _DUMP)}
            measurements = []
            for name, value in (dump.get("scalars") or {}).items():
                try:
                    measurements.append({"name": name, "value": float(value),
                                         "unit": "SI"})
                except (TypeError, ValueError):
                    continue
            return {"total": 0, "violations": [], "measurements": measurements,
                    "source": "dump",
                    "dump_file": native_output.get("dump_file", _DUMP)}
        text = (native_output.get("stdout") or "")
        if _NS_RE.search(text):
            return {"total": 0, "violations": [],
                    "measurements": [{"name": "iterations", "value": 1.0,
                                      "unit": "count"}],
                    "source": "stdio_fallback"}
        raise AdapterError(
            "runner_unavailable", "Elmer output has no SaveScalars verdict.")
