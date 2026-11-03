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

import json
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
_DIAG_NAME = "diag.json"

_DIAG_RE = re.compile(r"^(.+?):(\d+):(\d+):\s*(error|warning):\s*(.*)$", re.M)
_RULE_RE = re.compile(r"\[(-W[\w-]+)\]\s*$")
_SUMMARY_RE = re.compile(r"^Build (succeeded|failed): (\d+) errors?, (\d+) warnings?\s*$", re.M)
_LOCATION_RE = re.compile(r"^(.*?):(\d+):(\d+)$")

#: Pinned slang --diag-json entry shape (verified slang 12.0.0):
#: [{severity, message, code, location: "f:l:c", ranges:
#: [{start: {file, line, column}, ...}], symbolPath}]. Counts
#: derive from array entries, never from the Build summary line.
_DIAG_SEVERITY = {"error": "error", "warning": "warning"}


def _diag_entry_location(entry):
    """(file, line, col) for one pinned --diag-json entry.

    Ranges carry the structured position; the flat `location`
    string is the fallback. Returns (None, None, None) when
    neither parses.

    Args:
        entry: One slang JSON diagnostic mapping.

    Returns:
        (file, line, col) triple with ints for line/col.
    """
    ranges = entry.get("ranges") or []
    if ranges:
        start = ranges[0].get("start") or {}
        try:
            return (
                start.get("file"),
                int(start.get("line")),
                int(start.get("column")),
            )
        except (TypeError, ValueError):
            pass
    match = _LOCATION_RE.match(entry.get("location") or "")
    if match is not None:
        return match.group(1), int(match.group(2)), int(match.group(3))
    return None, None, None


def _diag_entry_violation(entry):
    """Map one pinned --diag-json entry to a v0 violation.

    Notes surface as warnings (never fail); the slang `code`
    (e.g. UndeclaredIdentifier) is the rule since JSON messages
    carry no [-W...] suffix.

    Args:
        entry: One slang JSON diagnostic mapping.

    Returns:
        Violation with rule, severity, message, and located
            file/line/col when the entry carries them.
    """
    severity = _DIAG_SEVERITY.get(entry.get("severity"), "warning")
    violation = {
        "rule": entry.get("code") or "syntax",
        "severity": severity,
        "message": entry.get("message") or "",
    }
    file, line, col = _diag_entry_location(entry)
    if file is not None:
        violation["file"] = file
    if line is not None:
        violation["line"] = line
    if col is not None:
        violation["col"] = col
    return violation


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

        Runs with `--diag-json diag.json` so diagnostics land in
        a pinned JSON file first (MIGRATE-STDIO-FILE; schema
        pinned at slang 12.0.0, see _diag_entry_violation).

        Args:
            job: Solver job with operation run_syntax plus
                sources, flags, and timeout inputs.

        Returns:
            Native output with exit_code, stdout/stderr, the
                linted sources, and the parsed diag entries
                under `diag_json` (None when slang wrote none).

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
        diag_path = Path(workdir) / _DIAG_NAME
        proc = self._run(
            [checked["slang"], "--lint-only", *checked["flags"],
             "--diag-json", str(diag_path), *checked["sources"]],
            workdir,
            checked["timeout_s"],
        )
        try:
            diag_json = json.loads(diag_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            diag_json = None
        return {
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "sources": checked["sources"],
            "diag_json": diag_json,
        }

    def parse(self, native_output):
        """Parse slang diagnostics from JSON first, stdio second.

        MIGRATE-STDIO-FILE: `--diag-json` entries are the parse
        channel (counts derive from the array, never from the
        Build summary line); the stdio regexes survive only as a
        loud fallback for natives recorded before slang wrote
        the file. A failed build with no parsed error
        diagnostics synthesizes one rather than going clean;
        warnings never fail.

        Args:
            native_output: Native output with slang stdout/stderr
                plus the optional parsed `diag_json` entries.

        Returns:
            {total, violations[], source} with rule, severity,
                message, and file/line/col locations; source is
                `diag_json` or `stdio_fallback`.

        Raises:
            AdapterError: runner_unavailable when the output has
                no diag entries and no Build summary line.
        """
        diag_json = native_output.get("diag_json")
        if isinstance(diag_json, list):
            # Counts derive from the array; [-W...] rule labels are
            # recovered from stdio when it carries the same
            # diagnostic (keeps the pinned rule grammar stable),
            # else the slang code stands as the rule.
            stdio_text = native_output.get("stdout", "") + "\n" + (
                native_output.get("stderr", ""))
            flag_by_loc = {}
            for match in _DIAG_RE.finditer(stdio_text):
                file, line, col, severity, message = match.groups()
                flagged = _RULE_RE.search(message)
                if flagged:
                    flag_by_loc[(file, int(line), int(col),
                                 severity)] = flagged.group(1)
            violations = []
            for entry in diag_json:
                if not isinstance(entry, dict):
                    continue
                violation = _diag_entry_violation(entry)
                key = (violation.get("file"), violation.get("line"),
                       violation.get("col"), violation.get("severity"))
                if key in flag_by_loc:
                    violation["rule"] = flag_by_loc[key]
                violations.append(violation)
            errors = sum(1 for v in violations if v["severity"] == "error")
            source = "diag_json"
            fallback_summary = ""
        else:
            text = native_output.get("stdout", "") + "\n" + native_output.get(
                "stderr", "")
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
                    "runner_unavailable",
                    "slang output has no Build summary line.",
                )
            errors = int(summary.group(2))
            source = "stdio_fallback"
            fallback_summary = summary.group(0)
        if errors > 0 and not any(v["severity"] == "error" for v in violations):
            # Defensive: a failed build must never parse as clean.
            violations.append(
                {
                    "rule": "syntax",
                    "severity": "error",
                    "message": fallback_summary or (
                        f"slang reported {errors} errors, none parsed."
                    ),
                }
            )
        return {
            "total": len(violations),
            "violations": violations,
            "source": source,
        }

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
