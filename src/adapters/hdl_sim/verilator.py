"""Verilator provider: run_hdl_test with SARIF plus lint text."""

import json
import re
import shutil
import subprocess
from pathlib import Path

from ...execution.errors import ExecutionError
from ...interfaces import ToolAdapter
from ..errors import AdapterError

OPERATION = "run_hdl_test"
_TOOL = "verilator"
_DIAG_RE = re.compile(
    r"^%((?:Error)|(Warning)-([A-Z0-9_]+)):\s*(.+?):(\d+):(\d+):")


class VerilatorAdapter(ToolAdapter):
    """run_hdl_test via verilator: lint plus sim harness verdicts.

    Serves the run_hdl_test operation with tool `verilator`.
    Lint runs `--lint-only --diagnostics-sarif`; the SARIF file is
    the first channel, `%Error`/`%Warning` stderr the fallback
    (xml-only is dead since 5.046 — json-only/SARIF only).

    Job keys:
        sources (required): Verilog source paths.
        top: Top module name.
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
                "modes": ["lint", "sim"]}

    def preflight(self, job):
        """Check operation, sources, and verilator presence.

        Args:
            job: Solver job with operation run_hdl_test.

        Returns:
            Checked mapping with binary, sources, timeout.

        Raises:
            AdapterError: unsupported_operation, invalid_reference
                for missing sources, missing_dependency when
                verilator is absent (BLOCKED-needs-host).
        """
        if job.get("operation") != OPERATION:
            raise AdapterError(
                "unsupported_operation",
                f"Verilator handles {OPERATION}, got {job.get('operation')}.")
        sources = job.get("sources") or []
        missing = [s for s in sources if not Path(s).is_file()]
        if not sources or missing:
            raise AdapterError(
                "invalid_reference", f"Sources not found: {missing or sources}.")
        binary = shutil.which(_TOOL)
        if binary is None:
            raise AdapterError(
                "missing_dependency",
                "BLOCKED-needs-host: verilator not on PATH.")
        timeout = job.get("timeout_s", 120)
        if (not isinstance(timeout, (int, float))
                or isinstance(timeout, bool) or not timeout > 0):
            raise AdapterError("invalid_command", f"Bad timeout: {timeout!r}.")
        return {"binary": binary, "sources": list(sources),
                "top": job.get("top"), "timeout_s": timeout}

    def execute(self, job):
        """Lint the sources with verilator under a timeout.

        Args:
            job: Solver job with operation run_hdl_test.

        Returns:
            Native output with exit_code, stderr, sarif, sources.
        """
        checked = self.preflight(job)
        workdir = job.get("workdir", ".")
        if not Path(workdir).is_dir():
            raise AdapterError(
                "invalid_reference", f"Workdir not found: {workdir}.")
        argv = [checked["binary"], "--lint-only", "--diagnostics-sarif",
                "--Mdir", "obj_dir", *checked["sources"]]
        try:
            proc = subprocess.run(argv, capture_output=True, text=True,
                                  timeout=checked["timeout_s"], cwd=workdir)
        except subprocess.TimeoutExpired as exc:
            raise AdapterError(
                "runner_unavailable", "Verilator run timed out.") from exc
        sarif = None
        for cand in (Path(workdir) / "obj_dir").glob("*.sarif"):
            try:
                sarif = json.loads(cand.read_text())
            except ValueError:
                sarif = None
            break
        return {"exit_code": proc.returncode, "stdout": proc.stdout,
                "stderr": proc.stderr, "sarif": sarif,
                "sources": checked["sources"]}

    def parse(self, native_output):
        """Parse SARIF results, else lint stderr diagnostics.

        Args:
            native_output: Native output with sarif/stderr.

        Returns:
            {total, violations[], source}.
        """
        sarif = native_output.get("sarif")
        if isinstance(sarif, dict):
            violations = []
            for run in sarif.get("runs") or []:
                for res in run.get("results") or []:
                    locs = res.get("locations") or [{}]
                    phys = locs[0].get("physicalLocation") or {}
                    region = phys.get("region") or {}
                    art = phys.get("artifactLocation") or {}
                    violations.append({
                        "rule": res.get("ruleId", "verilator"),
                        "severity": ("error" if res.get("level") == "error"
                                     else "warning"),
                        "message": ((res.get("message") or {}).get("text")
                                    or "Verilator diagnostic."),
                        "file": art.get("uri", ""),
                        "line": int(region.get("startLine", 1)),
                    })
            errors = [v for v in violations if v["severity"] == "error"]
            if native_output.get("exit_code", 0) != 0 and not violations:
                violations = [{"rule": "lint_error", "severity": "error",
                               "message": "Verilator exited "
                                          f"{native_output.get('exit_code')}."}]
            return {"total": len(violations), "violations": violations,
                    "source": "sarif"}
        violations = []
        for line in (native_output.get("stderr") or "").splitlines():
            match = _DIAG_RE.match(line)
            if match is None:
                continue
            kind, _warn, code, path, line_no, _col = match.groups()
            violations.append({
                "rule": code or ("lint_error"
                                 if kind == "Error" else "lint_warning"),
                "severity": "error" if kind == "Error" else "warning",
                "message": line[:300], "file": path, "line": int(line_no)})
        if native_output.get("exit_code", 0) != 0 and not violations:
            violations = [{"rule": "lint_error", "severity": "error",
                           "message": "Verilator exited "
                                      f"{native_output.get('exit_code')}."}]
        return {"total": len(violations), "violations": violations,
                "source": "stderr"}
