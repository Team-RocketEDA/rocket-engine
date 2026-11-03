"""Mutation adapter: run_mutation with the mcy provider."""

import re
import shutil
import sqlite3
import subprocess
from pathlib import Path

from ...execution.errors import ExecutionError
from ...interfaces import ToolAdapter
from ..errors import AdapterError

OPERATION = "run_mutation"
_TOOL = "mcy"
_DB = "database/db.sqlite3"
_OUTPUT_RE = re.compile(r"^(\d+)\s+(\S+)\s*$")


def _parse_output_txt(text):
    """Parse one output.txt streaming verdict file.

    Args:
        text: output.txt text with `<idx> <RESULT>` per line.

    Returns:
        List of {mutation_id, result} rows.
    """
    rows = []
    for line in (text or "").splitlines():
        match = _OUTPUT_RE.match(line.strip())
        if match is None:
            continue
        rows.append({"mutation_id": int(match.group(1)),
                     "result": match.group(2)})
    return rows


class McyAdapter(ToolAdapter):
    """run_mutation via mcy: sqlite DB plus output.txt streaming.

    Serves the run_mutation operation with tool `mcy`. Primary
    results come from database/db.sqlite3 via stdlib sqlite3;
    output.txt `<idx> <RESULT>` rows stream per-task verdicts
    before DB commit. Never scrapes list/source/status stdout.

    Job keys:
        project (required): Mcy project dir with database/.
        test: Test name for run scoping.
        workdir: Run directory (default ".").
        timeout_s: Budget in seconds (default 600).

    Args:
        runner: Optional isolated runner; direct subprocess when None.
    """

    def __init__(self, runner=None):
        self._runner = runner

    parse_output_txt = staticmethod(_parse_output_txt)

    def capabilities(self, target):
        """Report the served operation and tool.

        Args:
            target: Target the capabilities are reported for.

        Returns:
            Capability mapping with operations and tool.
        """
        return {"operations": [OPERATION], "tool": _TOOL, "db": _DB}

    def preflight(self, job):
        """Check operation, project dir, and mcy presence.

        Args:
            job: Solver job with operation run_mutation plus project.

        Returns:
            Checked mapping with project, binary, and timeout.

        Raises:
            AdapterError: unsupported_operation, invalid_reference
                for a missing project, missing_dependency when mcy
                is absent (BLOCKED-needs-host).
        """
        if job.get("operation") != OPERATION:
            raise AdapterError(
                "unsupported_operation",
                f"Mcy handles {OPERATION}, got {job.get('operation')}.")
        project = job.get("project")
        if not project or not Path(project).is_dir():
            raise AdapterError(
                "invalid_reference", f"Mcy project not found: {project}.")
        binary = shutil.which(_TOOL)
        if binary is None:
            raise AdapterError(
                "missing_dependency",
                "BLOCKED-needs-host: mcy not on PATH (oss-cad-suite).")
        timeout = job.get("timeout_s", 600)
        if (not isinstance(timeout, (int, float))
                or isinstance(timeout, bool) or not timeout > 0):
            raise AdapterError("invalid_command", f"Bad timeout: {timeout!r}.")
        checked = {"project": str(project), "binary": binary,
                   "timeout_s": timeout, "test": job.get("test")}
        if self._runner is not None:
            try:
                self._runner.preflight()
            except ExecutionError as exc:
                raise AdapterError(exc.code, str(exc)) from exc
        return checked

    def execute(self, job):
        """Run mcy on the project under a timeout.

        Args:
            job: Solver job with operation run_mutation plus project.

        Returns:
            Native output with exit_code, stdout/stderr, results,
                and db file.
        """
        checked = self.preflight(job)
        workdir = job.get("workdir", checked["project"])
        if not Path(workdir).is_dir():
            raise AdapterError(
                "invalid_reference", f"Workdir not found: {workdir}.")
        argv = [checked["binary"], "run"]
        if checked["test"]:
            argv.extend(["--test", str(checked["test"])])
        try:
            proc = subprocess.run(argv, capture_output=True, text=True,
                                  timeout=checked["timeout_s"], cwd=workdir)
        except subprocess.TimeoutExpired as exc:
            raise AdapterError(
                "runner_unavailable", "Mcy run timed out.") from exc
        results = self.read_db(Path(workdir) / _DB)
        return {"exit_code": proc.returncode, "stdout": proc.stdout,
                "stderr": proc.stderr, "results": results,
                "db_file": _DB}

    def parse(self, native_output):
        """Parse DB results to coverage plus uncovered violations.

        Args:
            native_output: Native output with the results rows.

        Returns:
            {total, violations[], coverage, source}.

        Raises:
            AdapterError: runner_unavailable with no results.
        """
        results = native_output.get("results")
        if not isinstance(results, list) or not results:
            raise AdapterError(
                "runner_unavailable", "Mcy output has no results.")
        uncovered = [r for r in results
                     if str(r.get("result", "")).upper() != "COVERED"
                     and str(r.get("result", "")).upper() != "PASS"]
        coverage = ((len(results) - len(uncovered)) / len(results)
                    if results else 0.0)
        violations = [{"rule": "mutation_uncovered", "severity": "error",
                       "message": f"Mutation {r.get('mutation_id')}"
                                  f" {r.get('result')}."}
                      for r in uncovered]
        return {"total": len(violations), "violations": violations,
                "coverage": coverage, "source": "db",
                "db_file": native_output.get("db_file", _DB)}

    @staticmethod
    def read_db(path):
        """Read cached results from one mcy sqlite DB.

        Args:
            path: database/db.sqlite3 path (missing reads as empty).

        Returns:
            Results rows (empty when the DB is absent).
        """
        if not Path(path).is_file():
            return []
        try:
            conn = sqlite3.connect(str(path))
            try:
                rows = conn.execute(
                    "SELECT mutation_id, test, result FROM results").fetchall()
            finally:
                conn.close()
        except Exception:
            return []
        return [{"mutation_id": r[0], "test": r[1], "result": r[2]}
                for r in rows]
