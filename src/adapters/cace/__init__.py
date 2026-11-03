"""CACE characterization adapter: run_characterize port."""

import re
import shutil
import subprocess
from pathlib import Path

from ...execution.errors import ExecutionError
from ...interfaces import ToolAdapter
from ..errors import AdapterError

OPERATION = "run_characterize"
_TOOL = "cace"
_TIMEOUT_S = 900
_STATUS_RE = re.compile(r"\|\s*(Pass|Fail|Error|Unknown|Skip|Cancel)\s",
                        re.IGNORECASE)


class CaceAdapter(ToolAdapter):
    """run_characterize via cace: CLI run plus summary.md verdicts.

    Serves the run_characterize operation with tool `cace`. Runs
    `cace <datasheet>` as a subprocess and gates on the exit code
    (0 pass, 2 spec miss, 1/3/4 error/unknown/canceled); values
    come from summary.md rows plus simulation_summary.csv, never
    flow.log scraping. In-process reads reuse pure helpers only.

    Job keys:
        datasheet (required): Input datasheet YAML path.
        run_path: Run dir parent (RUNDIR lands beneath it).
        workdir: Run directory (default ".").
        timeout_s: Budget in seconds (default 900).

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
        """Check operation, datasheet, and cace presence.

        Args:
            job: Solver job with operation run_characterize.

        Returns:
            Checked mapping with datasheet, binary, timeout.

        Raises:
            AdapterError: unsupported_operation, invalid_reference
                for a missing datasheet, missing_dependency with
                BLOCKED-needs-host when cace is absent (2.13.0 pin).
        """
        if job.get("operation") != OPERATION:
            raise AdapterError(
                "unsupported_operation",
                f"Cace handles {OPERATION}, got {job.get('operation')}.")
        datasheet = job.get("datasheet")
        if not datasheet or not Path(datasheet).is_file():
            raise AdapterError(
                "invalid_reference", f"Datasheet not found: {datasheet}.")
        binary = shutil.which(_TOOL)
        if binary is None:
            raise AdapterError(
                "missing_dependency",
                "BLOCKED-needs-host: cace absent (need cace==2.13.0).")
        try:
            __import__("cace")
        except ImportError as exc:
            raise AdapterError(
                "missing_dependency",
                "BLOCKED-needs-host: cace python package absent.",
            ) from exc
        timeout = job.get("timeout_s", _TIMEOUT_S)
        if (not isinstance(timeout, (int, float))
                or isinstance(timeout, bool) or not timeout > 0):
            raise AdapterError("invalid_command", f"Bad timeout: {timeout!r}.")
        checked = {"datasheet": str(datasheet), "binary": binary,
                   "timeout_s": timeout,
                   "run_path": job.get("run_path")}
        if self._runner is not None:
            try:
                self._runner.preflight()
            except ExecutionError as exc:
                raise AdapterError(exc.code, str(exc)) from exc
        return checked

    def execute(self, job):
        """Run cace on the datasheet under a timeout.

        Args:
            job: Solver job with operation run_characterize.

        Returns:
            Native output with exit_code, stdout/stderr, summary
                markdown, and run dir.
        """
        checked = self.preflight(job)
        workdir = job.get("workdir", ".")
        if not Path(workdir).is_dir():
            raise AdapterError(
                "invalid_reference", f"Workdir not found: {workdir}.")
        argv = [checked["binary"], checked["datasheet"],
                "--no-progress-bar"]
        if checked["run_path"]:
            argv.extend(["--run-path", str(checked["run_path"])])
        try:
            proc = subprocess.run(argv, capture_output=True, text=True,
                                  timeout=checked["timeout_s"], cwd=workdir)
        except subprocess.TimeoutExpired as exc:
            raise AdapterError(
                "runner_unavailable", "Cace run timed out.") from exc
        summary = ""
        run_dir = checked["run_path"] or workdir
        for cand in sorted(Path(run_dir).glob("RUN_*/summary.md")):
            summary = cand.read_text(errors="replace")
            run_dir = str(cand.parent)
            break
        return {"exit_code": proc.returncode, "stdout": proc.stdout,
                "stderr": proc.stderr, "summary_md": summary,
                "run_dir": run_dir}

    def parse(self, native_output):
        """Parse summary.md status cells to pass/fail verdict.

        Args:
            native_output: Native output with summary markdown.

        Returns:
            {total, violations[], source}.

        Raises:
            AdapterError: runner_unavailable with no summary.
        """
        summary = native_output.get("summary_md")
        if not summary or not _STATUS_RE.search(summary):
            raise AdapterError(
                "runner_unavailable", "Cace run left no summary.md.")
        bad = [m for m in ("Fail", "Error") if m.lower() in summary.lower()]
        if native_output.get("exit_code", 0) not in (0,) or bad:
            fails = [line.strip() for line in summary.splitlines()
                     if "Fail" in line or "Error" in line]
            violations = [{"rule": "characterize_fail", "severity": "error",
                           "message": line[:300] or "Cace spec miss."}
                          for line in fails] or [{
                              "rule": "characterize_fail",
                              "severity": "error",
                              "message": "Cace run failed."}]
            return {"total": len(violations), "violations": violations,
                    "source": "summary_md"}
        return {"total": 0, "violations": [], "source": "summary_md"}
