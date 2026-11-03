"""GHDL synth frontend: run_synth via ghdl --synth."""

import shutil
import subprocess
from pathlib import Path

from ...interfaces import ToolAdapter
from ..errors import AdapterError

OPERATION = "run_synth"
_TOOL = "ghdl"


class GhdlSynthAdapter(ToolAdapter):
    """run_synth via ghdl: VHDL to Verilog netlist frontend.

    Serves the run_synth operation with tool `ghdl`. Runs
    `ghdl --synth --out=verilog -o` then reports the netlist
    artifact plus --stats text. Feeds the yosys flow downstream.

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
                "frontend": True}

    def preflight(self, job):
        """Check operation, sources, top, and ghdl presence.

        Args:
            job: Solver job with operation run_synth.

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
                f"GHDL synth handles {OPERATION}, got {job.get('operation')}.")
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
        """Synthesize the top to Verilog under a timeout.

        Args:
            job: Solver job with operation run_synth.

        Returns:
            Native output with exit_code, stdout, netlist, top.
        """
        checked = self.preflight(job)
        workdir = job.get("workdir", ".")
        if not Path(workdir).is_dir():
            raise AdapterError(
                "invalid_reference", f"Workdir not found: {workdir}.")
        netlist = str(Path(workdir) / "ghdl_synth.v")
        try:
            proc = subprocess.run(
                [checked["binary"], "--synth", "--out=verilog",
                 f"--top={checked['top']}", f"-o={netlist}",
                 *checked["sources"]],
                capture_output=True, text=True,
                timeout=checked["timeout_s"], cwd=workdir)
        except subprocess.TimeoutExpired as exc:
            raise AdapterError(
                "runner_unavailable", "GHDL synth timed out.") from exc
        return {"exit_code": proc.returncode, "stdout": proc.stdout,
                "stderr": proc.stderr, "netlist": netlist,
                "top": checked["top"]}

    def parse(self, native_output):
        """Parse ghdl synth stats to a verdict plus netlist.

        Args:
            native_output: Native output with stdout and netlist.

        Returns:
            {total, violations[], netlist, top, source}.
        """
        if native_output.get("exit_code", 0) != 0:
            return {"total": 1, "violations": [{
                "rule": "synth_error", "severity": "error",
                "message": (native_output.get("stderr") or
                            "GHDL synth failed.")[:300]}],
                "netlist": native_output.get("netlist"),
                "top": native_output.get("top"), "source": "stderr"}
        return {"total": 0, "violations": [],
                "netlist": native_output.get("netlist"),
                "top": native_output.get("top"), "source": "stdout"}
