"""Slang syntax solver adapter: run_syntax behind the ToolAdapter port.

Protocol, verified against slang 12.0.0: `slang --lint-only -Wextra`
over the sources, then parse `file:line:col: (error|warning):`
diagnostics plus the `Build ...: N errors, M warnings` summary line.
Exit code is trustworthy here (0 clean, 1 errors) but the verdict
still comes from parsed output: any parsed error is FAIL, warnings
never fail, and a failed build with no parsed diagnostics reports a
synthesized error rather than going clean.

Tool resolution: an explicit job `tool_dir` wins, else PATH. Where
the tools live on disk is B10 integration scope.
"""

import re
import shutil
import subprocess
from pathlib import Path

from ...execution.errors import ExecutionError
from ...interfaces import ToolAdapter
from ..errors import AdapterError

OPERATION = "run_syntax"
_TIMEOUT_S = 120
_DEFAULT_FLAGS = ["-Wextra"]

_DIAG_RE = re.compile(r"^(.+?):(\d+):(\d+):\s*(error|warning):\s*(.*)$", re.M)
_RULE_RE = re.compile(r"\[(-W[\w-]+)\]\s*$")
_SUMMARY_RE = re.compile(r"^Build (succeeded|failed): (\d+) errors?, (\d+) warnings?\s*$", re.M)


class SyntaxAdapter(ToolAdapter):
    """run_syntax via Slang: SystemVerilog lint with diagnostics.

    Serves the run_syntax operation with deck.tool `slang` (the only
    tool). Lints the sources and parses file:line:col diagnostics
    plus the Build summary; errors are FAIL, warnings never fail.

    Job keys:
        sources (required): HDL source paths under lint.
        slang_flags: Extra slang flags (default [-Wextra]).
        timeout_s: Lint budget in seconds (default 120).
        tool_dir: Directory holding slang; PATH otherwise.
        deck: Optional mapping; deck.tool must be slang here.
        workdir: Run directory (default ".").

    Args:
        runner: Optional isolated runner; direct subprocess when None.

    Caution: A failed build with no parsed diagnostics reports a
        synthesized error rather than going clean.
    """

    def __init__(self, runner=None):
        self._runner = runner

    def capabilities(self, target):
        """Report the served operation and tool name.

        Args:
            target: Target the capabilities are reported for
                (accepted, unused — one source set per job).

        Returns:
            Capability mapping with operations and tool.
        """
        return {"operations": [OPERATION], "tool": "slang"}

    def preflight(self, job):
        """Check operation, timeout, flags, sources, and slang.

        Cheap deterministic checks first, tool resolution last.

        Args:
            job: Solver job with operation run_syntax plus
                sources, flags, and timeout inputs.

        Returns:
            Checked mapping with the resolved slang path,
                sources, flags, and timeout_s.

        Raises:
            AdapterError: unsupported_operation for another
                operation, invalid_command for a bad timeout or
                slang_flags, invalid_reference for missing sources,
                missing_dependency for an unresolvable slang.
        """
        # Cheap deterministic checks first: operation, timeout, flags,
        # sources. Tool resolution last, since it depends on the machine.
        if job.get("operation") != OPERATION:
            raise AdapterError(
                "unsupported_operation",
                f"Syntax handles {OPERATION}, got {job.get('operation')}.",
            )
        timeout = job.get("timeout_s", _TIMEOUT_S)
        if (
            not isinstance(timeout, (int, float))
            or isinstance(timeout, bool)
            or not timeout > 0
        ):
            raise AdapterError("invalid_command", f"Bad timeout_s: {timeout!r}.")
        flags = job.get("slang_flags", list(_DEFAULT_FLAGS))
        if not isinstance(flags, list) or not all(
            isinstance(f, str) for f in flags
        ):
            raise AdapterError("invalid_command", f"Bad slang_flags: {flags!r}.")
        sources = job.get("sources") or []
        missing = [s for s in sources if not Path(s).is_file()]
        if not sources or missing:
            raise AdapterError(
                "invalid_reference", f"Sources not found: {missing or sources}."
            )
        return {
            "slang": self._resolve(job, "slang"),
            "sources": list(sources),
            "flags": list(flags),
            "timeout_s": timeout,
        }

    def execute(self, job):
        """Lint the sources with slang --lint-only.

        Args:
            job: Solver job with operation run_syntax plus
                sources, flags, and timeout inputs.

        Returns:
            Native output with exit_code, stdout/stderr, and the
                linted sources.

        Raises:
            AdapterError: invalid_reference for a missing workdir,
                runner_unavailable on a slang timeout, plus the
                preflight codes (execute re-checks first).
        """
        checked = self.preflight(job)
        workdir = job.get("workdir", ".")
        if not Path(workdir).is_dir():
            raise AdapterError(
                "invalid_reference", f"Workdir not found: {workdir}."
            )
        proc = self._run(
            [checked["slang"], "--lint-only", *checked["flags"], *checked["sources"]],
            workdir,
            checked["timeout_s"],
        )
        return {
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "sources": checked["sources"],
        }

    def parse(self, native_output):
        """Parse slang diagnostics plus the Build summary line.

        A failed build with no parsed error diagnostics synthesizes
        one rather than going clean; warnings never fail.

        Args:
            native_output: Native output with slang stdout/stderr.

        Returns:
            {total, violations[]} with rule, severity, message, and
                file/line/col locations.

        Raises:
            AdapterError: runner_unavailable when the output has no
                Build summary line.
        """
        text = native_output.get("stdout", "") + "\n" + native_output.get("stderr", "")
        violations = []
        for match in _DIAG_RE.finditer(text):
            file, line, col, severity, message = match.groups()
            flagged = _RULE_RE.search(message)
            violations.append(
                {
                    "rule": flagged.group(1) if flagged else "syntax",
                    "severity": severity,
                    "message": message,
                    "file": file,
                    "line": int(line),
                    "col": int(col),
                }
            )
        summary = _SUMMARY_RE.search(text)
        if summary is None:
            raise AdapterError(
                "runner_unavailable", "slang output has no Build summary line."
            )
        errors = int(summary.group(2))
        if errors > 0 and not any(v["severity"] == "error" for v in violations):
            # Defensive: a failed build must never parse as clean.
            violations.append(
                {
                    "rule": "syntax",
                    "severity": "error",
                    "message": summary.group(0),
                }
            )
        return {"total": len(violations), "violations": violations}

    @staticmethod
    def _resolve(job, binary):
        tool_dir = job.get("tool_dir")
        if tool_dir:
            candidate = Path(tool_dir) / binary
            if candidate.is_file():
                return str(candidate)
            raise AdapterError(
                "missing_dependency", f"{binary} not found in {tool_dir}."
            )
        found = shutil.which(binary)
        if found is None:
            raise AdapterError(
                "missing_dependency",
                f"{binary} not on PATH (pass tool_dir or integrate via B10).",
            )
        return found

    def _run(self, argv, workdir, timeout_s):
        if self._runner is not None:
            try:
                return self._runner.run(argv, workdir, timeout_s)
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
                "runner_unavailable", f"slang timed out after {timeout_s}s."
            ) from exc
