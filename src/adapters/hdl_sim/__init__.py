"""Icarus HDL sim solver adapter: run_hdl_test behind the ToolAdapter port.

Protocol, verified against iverilog 14.0 + vvp: compile the sources
(exit 2 + `file:line: msg` diagnostics on failure), run the sim under
a timeout, and parse `FATAL:`/`ERROR:` lines for the verdict. `$error`
exits 0, so the verdict always comes from parsed output, never from
the exit code alone. Hangs raise instead of hanging the engine.

Tool resolution: an explicit job `tool_dir` wins, else PATH. Where
the tools live on disk is B10 integration scope — this adapter only
requires them resolvable, and refuses loudly when they are not.
"""

import re
import shutil
import subprocess
from pathlib import Path

from ...execution.errors import ExecutionError
from ...execution.runner import tool_roots
from ...interfaces import ToolAdapter
from ..errors import AdapterError

OPERATION = "run_hdl_test"
_TIMEOUT_S = 120

_COMPILE_RE = re.compile(r"^([^:\s][^:]*):(\d+):\s*(.+)$", re.M)
_SIM_RE = re.compile(r"^(FATAL|ERROR):\s*(\S+):(\d+):\s*(.*)$")
_TIME_RE = re.compile(r"Time:\s*(\d+)")
# Verilog `define names, with an optional =value (no whitespace or
# shell metacharacters; argv is never shelled, belt and suspenders).
_DEFINE_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(=[A-Za-z0-9_.+-]+)?")


def _parse_compile(text):
    violations = []
    for match in _COMPILE_RE.finditer(text):
        file, line, message = match.group(1), match.group(2), match.group(3)
        warning = message.lower().startswith("warning")
        violations.append(
            {
                "rule": "compile",
                "severity": "warning" if warning else "error",
                "message": message,
                "file": file,
                "line": int(line),
            }
        )
    return violations


def _parse_sim(text):
    violations = []
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = _SIM_RE.match(line)
        if match is None:
            continue
        kind, file, lineno, message = match.groups()
        violation = {
            "rule": "assert_fatal" if kind == "FATAL" else "assert_error",
            "severity": "error",
            "message": message,
            "file": file,
            "line": int(lineno),
        }
        if index + 1 < len(lines):
            timed = _TIME_RE.search(lines[index + 1])
            if timed:
                violation["sim_time"] = int(timed.group(1))
        violations.append(violation)
    return violations


class HdlSimAdapter(ToolAdapter):
    """run_hdl_test via Icarus: compile plus timed Verilog sim.

    Serves the run_hdl_test operation with deck.tool `icarus` (the
    only tool). Compiles the sources with iverilog, runs the sim
    under vvp with a timeout, and parses compile diagnostics plus
    FATAL/ERROR assertion lines.

    Job keys:
        sources (required): Verilog source paths, bench included.
        defines: Verilog `define list, optional =value each.
        timeout_s: Sim budget in seconds (default 120).
        tool_dir: Directory holding iverilog/vvp; PATH otherwise.
        deck: Optional mapping; deck.tool must be icarus here.
        workdir: Run directory (default ".").

    Args:
        runner: Optional isolated runner; direct subprocess when None.

    Caution: $error exits 0 and hangs raise instead of hanging the
        engine — the verdict always comes from parsed output, never
        the exit code alone.
    """

    def __init__(self, runner=None):
        self._runner = runner

    def capabilities(self, target):
        """Report the served operation, tool, sim, and defines.

        Args:
            target: Target the capabilities are reported for
                (accepted, unused — one bench per job).

        Returns:
            Capability mapping with operations, tool, sim, and
                defines.
        """
        return {"operations": [OPERATION], "tool": "icarus", "sim": "vvp", "defines": True}

    def preflight(self, job):
        """Check operation, timeout, sources, defines, and tools.

        Cheap deterministic checks first, tool resolution last.

        Args:
            job: Solver job with operation run_hdl_test plus
                sources, defines, and timeout inputs.

        Returns:
            Checked mapping with resolved iverilog/vvp paths,
                sources, timeout_s, and defines.

        Raises:
            AdapterError: unsupported_operation for another
                operation, invalid_command for a bad timeout or
                defines, invalid_reference for missing sources,
                missing_dependency for unresolvable tools.
        """
        # Cheap deterministic checks first: operation, timeout, sources.
        # Tool resolution last, since it depends on the machine.
        if job.get("operation") != OPERATION:
            raise AdapterError(
                "unsupported_operation",
                f"HDL sim handles {OPERATION}, got {job.get('operation')}.",
            )
        timeout = job.get("timeout_s", _TIMEOUT_S)
        if (
            not isinstance(timeout, (int, float))
            or isinstance(timeout, bool)
            or not timeout > 0
        ):
            raise AdapterError("invalid_command", f"Bad timeout_s: {timeout!r}.")
        sources = job.get("sources") or []
        missing = [s for s in sources if not Path(s).is_file()]
        if not sources or missing:
            raise AdapterError(
                "invalid_reference", f"Sources not found: {missing or sources}."
            )
        defines = job.get("defines") or []
        if not isinstance(defines, list) or any(
            not isinstance(d, str) or not _DEFINE_RE.fullmatch(d) for d in defines
        ):
            raise AdapterError("invalid_command", f"Bad defines: {defines!r}.")
        checked = {
            "iverilog": self._resolve(job, "iverilog"),
            "vvp": self._resolve(job, "vvp"),
            "sources": list(sources),
            "timeout_s": timeout,
            "defines": list(defines),
        }
        if self._runner is not None:
            try:
                self._runner.preflight()
            except ExecutionError as exc:
                raise AdapterError(exc.code, str(exc)) from exc
        return checked

    def execute(self, job):
        """Compile with iverilog, then run the sim under vvp.

        A failed compile returns its block with no run; the verdict
        still comes from parse, never the exit code alone.

        Args:
            job: Solver job with operation run_hdl_test plus
                sources, defines, and timeout inputs.

        Returns:
            Native output with exit_code plus compile and run
                blocks (run is None when the build failed).

        Raises:
            AdapterError: invalid_reference for a missing workdir,
                runner_unavailable on a sim timeout, plus the
                preflight codes (execute re-checks first).
        """
        checked = self.preflight(job)
        workdir = job.get("workdir", ".")
        if not Path(workdir).is_dir():
            raise AdapterError(
                "invalid_reference", f"Workdir not found: {workdir}."
            )
        roots = tool_roots([checked["iverilog"], checked["vvp"]])
        build = self._run(
            [
                checked["iverilog"],
                "-o",
                "sim.vvp",
                *[f"-D{d}" for d in checked["defines"]],
                *checked["sources"],
            ],
            workdir,
            checked["timeout_s"],
            roots,
        )
        if build.returncode != 0:
            return {
                "exit_code": build.returncode,
                "compile": _block(build),
                "run": None,
            }
        run = self._run(
            [checked["vvp"], "sim.vvp"], workdir, checked["timeout_s"], roots
        )
        return {
            "exit_code": run.returncode,
            "compile": _block(build),
            "run": _block(run),
        }

    def parse(self, native_output):
        """Parse compile diagnostics plus sim assertion lines.

        Failed compiles and crashed sims with nothing parseable
        synthesize error violations rather than going clean.

        Args:
            native_output: Native output with compile and run blocks.

        Returns:
            {total, violations[]} with file/line locations and
                sim_time where the sim reports it.

        Raises:
            AdapterError: runner_unavailable when a compiled run
                has no run block.
        """
        compile_block = native_output.get("compile") or {}
        diags = _parse_compile(
            compile_block.get("stdout", "") + "\n" + compile_block.get("stderr", "")
        )
        if compile_block.get("exit_code", 0) != 0:
            if not diags:
                # Defensive: a failed compile must never parse as clean.
                diags = [
                    {
                        "rule": "compile",
                        "severity": "error",
                        "message": f"iverilog exited {compile_block.get('exit_code')}",
                    }
                ]
            return {"total": len(diags), "violations": diags}
        run_block = native_output.get("run")
        if run_block is None:
            raise AdapterError(
                "runner_unavailable", "Native output has no run block."
            )
        sim = _parse_sim(run_block.get("stdout", "") + "\n" + run_block.get("stderr", ""))
        if run_block.get("exit_code", 0) != 0 and not sim:
            # Defensive: crashes print nothing parseable; the nonzero
            # exit is the only signal, and it must fail loudly.
            sim = [
                {
                    "rule": "sim_fail",
                    "severity": "error",
                    "message": f"vvp exited {run_block.get('exit_code')}",
                }
            ]
        violations = diags + sim
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

    def _run(self, argv, workdir, timeout_s, extra_binds=()):
        if self._runner is not None:
            try:
                return self._runner.run(argv, workdir, timeout_s, extra_binds)
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
                "runner_unavailable", f"sim timed out after {timeout_s}s."
            ) from exc


def _block(proc):
    return {
        "exit_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }
