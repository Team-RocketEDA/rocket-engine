"""Equivalence adapter: run_formal with the eqy provider."""

import re
import shutil
import subprocess
from pathlib import Path

from ...execution.errors import ExecutionError
from ...interfaces import ToolAdapter
from ..errors import AdapterError

OPERATION = "run_formal"
_TOOL = "eqy"
_DONE_RE = re.compile(r"DONE \((PASS|FAIL|UNKNOWN|ERROR), rc=(\d+)\)")


class EqyAdapter(ToolAdapter):
    """run_formal via eqy: verdict file plus DONE plus partitions.

    Serves the run_formal operation with tool `eqy`. Gating is the
    V1 verdict filename (PASS/FAIL/UNKNOWN/ERROR), confirmed by the
    DONE line; per-partition S1 status rows plus partition JSON
    carry the table. Never imports eqy.py (exit-unsafe).

    Job keys:
        config (required): Eqy .eqy config path.
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
        return {"operations": [OPERATION], "tool": _TOOL}

    def preflight(self, job):
        """Check operation, config, and eqy presence.

        Args:
            job: Solver job with operation run_formal plus config.

        Returns:
            Checked mapping with config, binary, and timeout.

        Raises:
            AdapterError: unsupported_operation, invalid_reference
                for a missing config, missing_dependency when eqy
                is absent (BLOCKED-needs-host).
        """
        if job.get("operation") != OPERATION:
            raise AdapterError(
                "unsupported_operation",
                f"Eqy handles {OPERATION}, got {job.get('operation')}.")
        config = job.get("config")
        if not config or not Path(config).is_file():
            raise AdapterError(
                "invalid_reference", f"Eqy config not found: {config}.")
        binary = shutil.which(_TOOL)
        if binary is None:
            raise AdapterError(
                "missing_dependency",
                "BLOCKED-needs-host: eqy not on PATH (oss-cad-suite).")
        timeout = job.get("timeout_s", 600)
        if (not isinstance(timeout, (int, float))
                or isinstance(timeout, bool) or not timeout > 0):
            raise AdapterError("invalid_command", f"Bad timeout: {timeout!r}.")
        checked = {"config": str(config), "binary": binary,
                   "timeout_s": timeout}
        if self._runner is not None:
            try:
                self._runner.preflight()
            except ExecutionError as exc:
                raise AdapterError(exc.code, str(exc)) from exc
        return checked

    def execute(self, job):
        """Run eqy on the config under a timeout.

        Args:
            job: Solver job with operation run_formal plus config.

        Returns:
            Native output with exit_code, stdout/stderr, verdict
                file, and partitions.
        """
        checked = self.preflight(job)
        workdir = job.get("workdir", ".")
        if not Path(workdir).is_dir():
            raise AdapterError(
                "invalid_reference", f"Workdir not found: {workdir}.")
        try:
            proc = subprocess.run(
                [checked["binary"], checked["config"]], capture_output=True,
                text=True, timeout=checked["timeout_s"], cwd=workdir)
        except subprocess.TimeoutExpired as exc:
            raise AdapterError(
                "runner_unavailable", "Eqy run timed out.") from exc
        verdict = None
        for name in ("PASS", "FAIL", "UNKNOWN", "ERROR"):
            if (Path(workdir) / name).is_file():
                verdict = name
                break
        return {"exit_code": proc.returncode, "stdout": proc.stdout,
                "stderr": proc.stderr, "verdict_file": verdict,
                "partitions": []}

    def parse(self, native_output):
        """Parse the V1 verdict file plus DONE line.

        Args:
            native_output: Native output with verdict file/stdout.

        Returns:
            {total, violations[], verdict, source}.

        Raises:
            AdapterError: runner_unavailable with no verdict file
                and no DONE line.
        """
        verdict = native_output.get("verdict_file")
        match = _DONE_RE.search(native_output.get("stdout") or "")
        if match is not None:
            verdict = verdict or match.group(1)
        if verdict not in ("PASS", "FAIL", "UNKNOWN", "ERROR"):
            raise AdapterError(
                "runner_unavailable", "Eqy output has no verdict.")
        partitions = native_output.get("partitions") or []
        failed = [p for p in partitions
                  if str(p.get("status", "")).split()[0:1] == ["FAIL"]
                  or p.get("status") == "FAIL"]
        if verdict == "PASS" and not failed:
            return {"total": 0, "violations": [], "verdict": verdict,
                    "partitions": partitions, "source": "verdict_file"}
        violations = [{
            "rule": "equivalence_fail", "severity": "error",
            "message": f"Eqy verdict {verdict}."}]
        for part in failed:
            violations.append({"rule": "equivalence_partition",
                               "severity": "error",
                               "message": f"Partition {part.get('name')}"
                                          " failed."})
        return {"total": len(violations), "violations": violations,
                "verdict": verdict, "partitions": partitions,
                "source": "verdict_file"}
