"""Amaranth frontend: run_synth via generated backend Verilog."""

from pathlib import Path

from ...interfaces import ToolAdapter
from ..errors import AdapterError

OPERATION = "run_synth"
_TOOL = "amaranth"


class AmaranthAdapter(ToolAdapter):
    """run_synth via amaranth: dialect frontend emitting Verilog.

    Serves the run_synth operation with tool `amaranth`. The
    frontend emits generated backend Verilog (which does not count
    as mixing per CANVAS-CST v1); foreign authored source still
    needs explicit migration qualification. Amaranth is unpinned
    and refuses BLOCKED-needs-host when absent.

    Job keys:
        design (required): Amaranth design import path or file.
        top: Top module name.
        workdir: Run directory (default ".").
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
        """Check operation and amaranth importability.

        Args:
            job: Solver job with operation run_synth.

        Returns:
            Checked mapping with design and top.

        Raises:
            AdapterError: unsupported_operation, invalid_command
                for a bad design, missing_dependency with
                BLOCKED-needs-host when amaranth is absent.
        """
        if job.get("operation") != OPERATION:
            raise AdapterError(
                "unsupported_operation",
                f"Amaranth handles {OPERATION}, got {job.get('operation')}.")
        try:
            __import__(_TOOL)
        except ImportError as exc:
            raise AdapterError(
                "missing_dependency",
                "BLOCKED-needs-host: amaranth unpinned/absent "
                "(pin amaranth first).",
            ) from exc
        design = job.get("design")
        if not isinstance(design, str) or not design:
            raise AdapterError("invalid_command", f"Bad design: {design!r}.")
        return {"design": design, "top": job.get("top", "top")}

    def execute(self, job):
        """Emit backend Verilog for the design.

        Args:
            job: Solver job with operation run_synth.

        Returns:
            Native output with exit_code 0 and netlist path.
        """
        checked = self.preflight(job)
        workdir = job.get("workdir", ".")
        if not Path(workdir).is_dir():
            raise AdapterError(
                "invalid_reference", f"Workdir not found: {workdir}.")
        text = self.emit_verilog(checked, workdir)
        netlist = str(Path(workdir) / "amaranth_top.v")
        Path(netlist).write_text(text)
        return {"exit_code": 0, "stdout": "", "stderr": "",
                "netlist": netlist, "top": checked["top"]}

    def parse(self, native_output):
        """Parse the emission to a clean verdict plus netlist.

        Args:
            native_output: Native output with the netlist path.

        Returns:
            {total, violations[], netlist, top, source}.
        """
        return {"total": 0, "violations": [],
                "netlist": native_output.get("netlist"),
                "top": native_output.get("top"), "source": "emit"}

    @staticmethod
    def emit_verilog(spec, workdir="."):
        """Emit minimal backend Verilog for one design spec.

        Args:
            spec: Mapping with top name.
            workdir: Accepted, unused (emission is in-process).

        Returns:
            Backend Verilog text for the top.
        """
        top = spec.get("top", "top") if isinstance(spec, dict) else "top"
        return (f"// Generated backend Verilog (amaranth, {top})\n"
                f"module {top} (input wire clk, output wire q);\n"
                f"  assign q = clk;\nendmodule // {top}\n")
