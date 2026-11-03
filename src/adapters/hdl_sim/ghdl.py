"""GHDL provider: run_hdl_test with assert-line verdicts."""

import re
import shutil
import subprocess
from pathlib import Path

from ...execution.errors import ExecutionError
from ...interfaces import ToolAdapter
from ..errors import AdapterError

OPERATION = "run_hdl_test"
_TOOL = "ghdl"
_ASSERT_RE = re.compile(
    r"^(.+):(\d+):(\d+):@(\S+):\((\w[\w ]*) (\w+)\): (.*)$")


class GhdlAdapter(ToolAdapter):
    """run_hdl_test via ghdl: analyze, elaborate, run, parse asserts.

    Serves the run_hdl_test operation with tool `ghdl`. Compile
    diagnostics arrive on stderr; sim assert/report lines arrive
    on stdout (never merge blindly). PSL verdicts prefer
    --psl-report JSON; waveforms prefer --vcd/--fst via pywellen.

    Job keys:
        sources (required): VHDL source paths.
        top (required): Top entity name.
        workdir: Run directory (default ".").
        timeout_s: Budget in seconds (default 120).
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
                "modes": ["analyze", "sim"]}

    def preflight(self, job):
        """Check operation, sources, top, and ghdl presence.

        Args:
            job: Solver job with operation run_hdl_test.

        Returns:
            Checked mapping with binary, sources, top, timeout.

        Raises:
            AdapterError: unsupported_operation, invalid_command
                for a bad top, invalid_reference for missing
                sources, missing_dependency when ghdl is absent.
        """
        if job.get("operation") != OPERATION:
            raise AdapterError(
                "unsupported_operation",
                f"GHDL handles {OPERATION}, got {job.get('operation')}.")
        top = job.get("top")
        if not isinstance(top, str) or not top:
            raise AdapterError("invalid_command", f"Bad top: {top!r}.")
        sources = job.get("sources") or []
        missing = [s for s in sources if not Path(s).is_file()]
        if not sources or missing:
            raise AdapterError(
                "invalid_reference", f"Sources not found: {missing or sources}.")
        binary = shutil.which(_TOOL)
        if binary is None:
            raise AdapterError(
                "missing_dependency",
                "BLOCKED-needs-host: ghdl not on PATH.")
        timeout = job.get("timeout_s", 120)
        if (not isinstance(timeout, (int, float))
                or isinstance(timeout, bool) or not timeout > 0):
            raise AdapterError("invalid_command", f"Bad timeout: {timeout!r}.")
        return {"binary": binary, "sources": list(sources), "top": top,
                "timeout_s": timeout}

    def execute(self, job):
        """Analyze, elaborate, and run the top under a timeout.

        Args:
            job: Solver job with operation run_hdl_test.

        Returns:
            Native output with exit_code, stdout, stderr, top.
        """
        checked = self.preflight(job)
        workdir = job.get("workdir", ".")
        if not Path(workdir).is_dir():
            raise AdapterError(
                "invalid_reference", f"Workdir not found: {workdir}.")
        try:
            for src in checked["sources"]:
                proc = subprocess.run(
                    [checked["binary"], "-a", src], capture_output=True,
                    text=True, timeout=checked["timeout_s"], cwd=workdir)
                if proc.returncode != 0:
                    return {"exit_code": proc.returncode,
                            "stdout": proc.stdout, "stderr": proc.stderr,
                            "top": checked["top"]}
            proc = subprocess.run(
                [checked["binary"], "-e", checked["top"]],
                capture_output=True, text=True,
                timeout=checked["timeout_s"], cwd=workdir)
            if proc.returncode != 0:
                return {"exit_code": proc.returncode,
                        "stdout": proc.stdout, "stderr": proc.stderr,
                        "top": checked["top"]}
            proc = subprocess.run(
                [checked["binary"], "-r", checked["top"]],
                capture_output=True, text=True,
                timeout=checked["timeout_s"], cwd=workdir)
        except subprocess.TimeoutExpired as exc:
            raise AdapterError(
                "runner_unavailable", "GHDL run timed out.") from exc
        return {"exit_code": proc.returncode, "stdout": proc.stdout,
                "stderr": proc.stderr, "top": checked["top"]}

    def parse(self, native_output):
        """Parse ghdl assert lines; errors fail, notes do not.

        Args:
            native_output: Native output with sim stdout.

        Returns:
            {total, violations[], source}.
        """
        violations = []
        for line in (native_output.get("stdout") or "").splitlines():
            match = _ASSERT_RE.match(line.strip())
            if match is None:
                continue
            path, line_no, _col, _time, _kind, sev, msg = match.groups()
            if sev.lower() in ("note",):
                continue
            violations.append({"rule": "assert_" + sev.lower(),
                               "severity": ("error" if sev.lower() in
                                            ("error", "failure")
                                            else "warning"),
                               "message": msg[:300], "file": path,
                               "line": int(line_no)})
        if "simulation failed" in (native_output.get("stdout") or ""):
            if not violations:
                violations.append({"rule": "sim_fail", "severity": "error",
                                   "message": "GHDL simulation failed."})
        return {"total": len(violations), "violations": violations,
                "source": "stdout"}
