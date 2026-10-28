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

from ...interfaces import ToolAdapter
from ..errors import AdapterError

OPERATION = "run_syntax"
_TIMEOUT_S = 120
_DEFAULT_FLAGS = ["-Wextra"]

_DIAG_RE = re.compile(r"^(.+?):(\d+):(\d+):\s*(error|warning):\s*(.*)$", re.M)
_RULE_RE = re.compile(r"\[(-W[\w-]+)\]\s*$")
_SUMMARY_RE = re.compile(r"^Build (succeeded|failed): (\d+) errors?, (\d+) warnings?\s*$", re.M)


class SyntaxAdapter(ToolAdapter):
    def capabilities(self, target):
        return {"operations": [OPERATION], "tool": "slang"}

    def preflight(self, job):
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

    @staticmethod
    def _run(argv, workdir, timeout_s):
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
