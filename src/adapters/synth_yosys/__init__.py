"""Yosys synth solver adapter: run_synth behind the ToolAdapter port.

Protocol, verified against Yosys 0.70+219 (oss-cad-suite): write a
synth script (`read_verilog` the sources, `hierarchy -check -top`,
`synth -top`, then `stat` plus `write_verilog`), run it under a
timeout, and parse the log plus the stat report. With a `liberty`
input the flow maps to standard cells instead (`dfflibmap` +
`abc -liberty`, `stat -liberty`): evidence is the mapped netlist
artifact, per-family cell counts, and the chip area. `hierarchy
-check` fails loudly (nonzero exit plus `ERROR:`) on a missing top,
and broken RTL fails the same way; warnings (`Warning:`, including
`Latch inferred` and `has no driver`) parse as findings that never
fail the verdict on their own. ABC's own `ABC: Warning:` chatter is
tool noise, never a design finding.

Tool resolution: an explicit job `tool_dir` wins, else PATH, and the
resolved binary must answer `yosys -V` with a parseable `Yosys
major.minor` banner — ambient installs are kept and
version-asserted, never reinstalled. Where the tools live on disk is
B10 integration scope.
"""

import re
import shutil
import subprocess
from pathlib import Path

from ...execution.errors import ExecutionError
from ...execution.runner import tool_roots
from ...interfaces import ToolAdapter
from ..errors import AdapterError

OPERATION = "run_synth"
_TOOL = "yosys"
_TIMEOUT_S = 120
_VERSION_TIMEOUT_S = 30

_SCRIPT_NAME = "synth.ys"
_LOG_NAME = "synth.log"
_STAT_NAME = "synth_stat.txt"
_NETLIST_NAME = "synth_netlist.v"

_TOP_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
# Verilog `define names, with an optional =value (no whitespace or
# shell metacharacters; argv is never shelled, belt and suspenders).
_DEFINE_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(=[A-Za-z0-9_.+-]+)?")
_VERSION_RE = re.compile(r"Yosys (\d+)\.(\d+)")
_ERROR_RE = re.compile(r"^(?:(.+?):(\d+): )?ERROR: (.*)$", re.M)
_WARNING_RE = re.compile(r"^(?:(.+?):(\d+): )?Warning: (.*)$", re.M)
_CELLS_RE = re.compile(r"^\s*(\d+)(?:\s+[\d.Ee+-]+)?\s+cells\s*$")
_CELL_LINE_RE = re.compile(r"^\s*(\d+)(?:\s+([\d.Ee+-]+))?\s+(\S+)\s*$")
_WIRES_RE = re.compile(r"^\s*(\d+)(?:\s+(?:[\d.Ee+-]+|-))?\s+wires\s*$")
_SUBMODULES_RE = re.compile(r"^\s*\d+\s+submodules\s*$")
_AREA_TOP_RE = re.compile(r"Chip area for top module '[^']*':\s*([\d.Ee+-]+)")
_AREA_MODULE_RE = re.compile(r"Chip area for module '[^']*':\s*([\d.Ee+-]+)")


def _parse_errors(text):
    """Collect synth_error violations from yosys ERROR lines.

    Args:
        text: Combined yosys log/stdout/stderr text.

    Returns:
        Error violations with file/line when the log carries them.
    """
    violations = []
    for match in _ERROR_RE.finditer(text):
        file, line, message = match.groups()
        violation = {
            "rule": "synth_error",
            "severity": "error",
            "message": message,
        }
        if file is not None:
            violation["file"] = file
            violation["line"] = int(line)
        violations.append(violation)
    return violations


def _warning_rule(message):
    """Classify one yosys warning into its finding rule.

    Args:
        message: Warning body after the `Warning:` prefix.

    Returns:
        Latch, undriven, or the generic synth_warning rule name.
    """
    if "Latch inferred" in message:
        return "latch"
    if "has no driver" in message:
        return "undriven"
    return "synth_warning"


def _parse_warnings(text):
    """Collect warning findings from yosys Warning lines.

    ABC's own `ABC: Warning:` lines are optimizer chatter, and the
    trailing `Warnings: N unique` line is a summary — neither is a
    design finding, so both are skipped.

    Args:
        text: Combined yosys log/stdout/stderr text.

    Returns:
        Warning violations with file/line when the log carries them.
    """
    violations = []
    for match in _WARNING_RE.finditer(text):
        start = match.start()
        line_start = text.rfind("\n", 0, start) + 1
        prefix = text[line_start:start]
        if "ABC:" in prefix:
            continue
        file, line, message = match.groups()
        violation = {
            "rule": _warning_rule(message),
            "severity": "warning",
            "message": message,
        }
        if file is not None:
            violation["file"] = file
            violation["line"] = int(line)
        violations.append(violation)
    return violations


def _parse_stat(text):
    """Aggregate cell counts, wires, and area over stat sections.

    Each `=== module ===` section reports local counts excluding
    submodules, so summing across sections is the design total. The
    `Chip area for top module` line wins when present; otherwise the
    per-module areas sum (same total, verified on SERV).

    Args:
        text: Stat report text from `tee -o stat`.

    Returns:
        Mapping with cells (type -> count), cell_count, wire_count,
            area (None without a liberty-mapped stat), and
            saw_cells (whether any cells block parsed).
    """
    cells = {}
    cell_count = 0
    wire_count = 0
    saw_cells = False
    in_cells = False
    for line in text.splitlines():
        if _WIRES_RE.match(line):
            wire_count += int(_WIRES_RE.match(line).group(1))
            in_cells = False
            continue
        if _CELLS_RE.match(line):
            saw_cells = True
            in_cells = True
            continue
        if in_cells:
            if not line.strip() or _SUBMODULES_RE.match(line):
                in_cells = False
                continue
            entry = _CELL_LINE_RE.match(line)
            if entry is not None:
                count, _area, cell_type = entry.groups()
                cells[cell_type] = cells.get(cell_type, 0) + int(count)
                cell_count += int(count)
    top_area = _AREA_TOP_RE.search(text)
    if top_area is not None:
        area = float(top_area.group(1))
    else:
        module_areas = _AREA_MODULE_RE.findall(text)
        area = sum(float(a) for a in module_areas) if module_areas else None
    return {
        "cells": cells,
        "cell_count": cell_count,
        "wire_count": wire_count,
        "area": area,
        "saw_cells": saw_cells,
    }


def _quote(path):
    """Quote one path for the yosys script language.

    Args:
        path: Filesystem path to embed in the script.

    Returns:
        Double-quoted path with backslashes and quotes escaped.
    """
    return '"' + str(path).replace("\\", "\\\\").replace('"', '\\"') + '"'


class YosysSynthAdapter(ToolAdapter):
    """run_synth via Yosys: RTL to mapped netlist plus evidence.

    Serves the run_synth operation with deck.tool `yosys` (the only
    tool). Synthesizes the sources for the named top with `synth
    -top`; with a `liberty` input it maps to standard cells
    (`dfflibmap` + `abc -liberty`) and reports the chip area.
    Evidence is the mapped netlist artifact, per-family cell counts,
    the area estimate when mapped, and warnings as findings.

    Job keys:
        sources (required): Verilog source paths under synth.
        top (required): Top module name (plain identifier).
        defines: Verilog `define list, optional =value each.
        liberty: Liberty (.lib) path for standard-cell mapping;
            generic synth without it.
        timeout_s: Synth budget in seconds (default 120).
        tool_dir: Directory holding yosys; PATH otherwise.
        deck: Optional mapping; deck.tool must be yosys here.
        workdir: Run directory (default ".").

    Args:
        runner: Optional isolated runner; direct subprocess when None.

    Caution: Broken RTL and a missing top fail loudly (nonzero exit
        plus synth_error findings) — a failed run never parses as
        clean, and warnings alone never fail the verdict.
    """

    def __init__(self, runner=None):
        self._runner = runner

    def capabilities(self, target):
        """Report the served operation, tool, and mapping modes.

        Args:
            target: Target the capabilities are reported for
                (accepted, unused — one top per job).

        Returns:
            Capability mapping with operations, tool, defines, and
                liberty support.
        """
        return {
            "operations": [OPERATION],
            "tool": _TOOL,
            "defines": True,
            "liberty": True,
        }

    def preflight(self, job):
        """Check operation, top, sources, defines, liberty, yosys.

        Cheap deterministic checks first, tool resolution last; the
        resolved binary must answer its version probe.

        Args:
            job: Solver job with operation run_synth plus sources,
                top, and optional defines/liberty/timeout inputs.

        Returns:
            Checked mapping with the resolved yosys path and
                version, sources, top, defines, liberty, timeout_s.

        Raises:
            AdapterError: unsupported_operation for another
                operation, invalid_command for a bad top, timeout,
                or defines, invalid_reference for missing sources
                or liberty, missing_dependency for an unresolvable
                or unassertable yosys.
        """
        # Cheap deterministic checks first: operation, top, timeout,
        # sources, defines, liberty. Tool resolution last, since it
        # depends on the machine.
        if job.get("operation") != OPERATION:
            raise AdapterError(
                "unsupported_operation",
                f"Yosys synth handles {OPERATION}, got {job.get('operation')}.",
            )
        top = job.get("top")
        if not isinstance(top, str) or not _TOP_RE.fullmatch(top):
            raise AdapterError("invalid_command", f"Bad top: {top!r}.")
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
        liberty = job.get("liberty")
        if liberty is not None and not Path(liberty).is_file():
            raise AdapterError("invalid_reference", f"Liberty not found: {liberty}.")
        yosys = self._resolve(job, _TOOL)
        checked = {
            "yosys": yosys,
            "yosys_version": self._version(yosys),
            "sources": list(sources),
            "top": top,
            "defines": list(defines),
            "liberty": liberty,
            "timeout_s": timeout,
        }
        if self._runner is not None:
            try:
                self._runner.preflight()
            except ExecutionError as exc:
                raise AdapterError(exc.code, str(exc)) from exc
        return checked

    def execute(self, job):
        """Synthesize the sources for the top with yosys.

        Writes the synth script into the workdir, runs it under the
        timeout, and returns the log, stat report, and netlist path.
        A failed run still returns its log — the verdict comes from
        parse, never the exit code alone.

        Args:
            job: Solver job with operation run_synth plus sources,
                top, and optional defines/liberty/timeout inputs.

        Returns:
            Native output with exit_code, stdout/stderr, log and
                stat text, netlist path, top, mapped flag, and the
                yosys version.

        Raises:
            AdapterError: invalid_reference for a missing workdir,
                runner_unavailable on a synth timeout, plus the
                preflight codes (execute re-checks first).
        """
        checked = self.preflight(job)
        workdir = job.get("workdir", ".")
        if not Path(workdir).is_dir():
            raise AdapterError(
                "invalid_reference", f"Workdir not found: {workdir}."
            )
        script = self._script(checked)
        (Path(workdir) / _SCRIPT_NAME).write_text(script)
        roots = tool_roots([checked["yosys"]])
        proc = self._run(
            [checked["yosys"], "-q", "-s", _SCRIPT_NAME, "-l", _LOG_NAME],
            workdir,
            checked["timeout_s"],
            roots,
        )
        log_path = Path(workdir) / _LOG_NAME
        stat_path = Path(workdir) / _STAT_NAME
        return {
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "log": log_path.read_text() if log_path.is_file() else "",
            "stat": stat_path.read_text() if stat_path.is_file() else "",
            "netlist": str(Path(workdir) / _NETLIST_NAME),
            "top": checked["top"],
            "mapped": checked["liberty"] is not None,
            "yosys_version": checked["yosys_version"],
        }

    def parse(self, native_output):
        """Parse errors, warnings, stat counts, and area evidence.

        Failed runs surface their ERROR lines (synthesizing one when
        the log carries none, so failure never parses as clean);
        warnings become findings that never fail alone; a clean run
        reports cell counts plus the mapped area.

        Args:
            native_output: Native output with exit_code, log and
                stat text, and the netlist path.

        Returns:
            {total, violations[], measurements[]} plus cells,
                cell_count, wire_count, area, mapped, netlist, top,
                and yosys_version evidence.

        Raises:
            AdapterError: runner_unavailable when the output has no
                exit code, or a clean run left no stat verdict or
                netlist — unparseable never parses as clean.
        """
        exit_code = native_output.get("exit_code")
        if exit_code is None:
            raise AdapterError(
                "runner_unavailable", "Native output has no exit code."
            )
        text = "\n".join(
            native_output.get(key, "") or ""
            for key in ("log", "stdout", "stderr")
        )
        errors = _parse_errors(text)
        warnings = _parse_warnings(text)
        stat = _parse_stat(native_output.get("stat") or "")
        netlist = native_output.get("netlist")
        if exit_code != 0:
            if not errors:
                # Defensive: a failed run must never parse as clean.
                errors = [
                    {
                        "rule": "synth_error",
                        "severity": "error",
                        "message": f"yosys exited {exit_code}",
                    }
                ]
            violations = errors + warnings
            return {
                "total": len(violations),
                "violations": violations,
                "measurements": [],
                "cells": stat["cells"],
                "cell_count": stat["cell_count"],
                "wire_count": stat["wire_count"],
                "area": None,
                "mapped": bool(native_output.get("mapped")),
                "netlist": netlist,
                "top": native_output.get("top"),
                "yosys_version": native_output.get("yosys_version"),
            }
        if not stat["saw_cells"]:
            raise AdapterError(
                "runner_unavailable", "yosys output has no stat verdict."
            )
        if netlist is None or not Path(netlist).is_file():
            raise AdapterError(
                "runner_unavailable", "yosys run left no netlist artifact."
            )
        violations = errors + warnings
        measurements = [
            {"name": "cell_count", "value": stat["cell_count"], "unit": "cells"},
            {"name": "wire_count", "value": stat["wire_count"], "unit": "wires"},
        ]
        if stat["area"] is not None:
            measurements.append(
                {"name": "area", "value": stat["area"], "unit": "um^2"}
            )
        return {
            "total": len(violations),
            "violations": violations,
            "measurements": measurements,
            "cells": stat["cells"],
            "cell_count": stat["cell_count"],
            "wire_count": stat["wire_count"],
            "area": stat["area"],
            "mapped": bool(native_output.get("mapped")),
            "netlist": netlist,
            "top": native_output.get("top"),
            "yosys_version": native_output.get("yosys_version"),
        }

    @staticmethod
    def _script(checked):
        """Render the yosys synth script for the checked job.

        Args:
            checked: Preflight mapping with sources, top, defines,
                and the optional liberty path.

        Returns:
            Yosys script text (read, check, synth, map, stat, dump).
        """
        lines = [
            "read_verilog"
            + "".join(f" -D{d}" for d in checked["defines"])
            + "".join(f" {_quote(s)}" for s in checked["sources"]),
            f"hierarchy -check -top {checked['top']}",
            f"synth -top {checked['top']}",
        ]
        if checked["liberty"] is not None:
            quoted = _quote(checked["liberty"])
            lines.extend(
                [
                    f"dfflibmap -liberty {quoted}",
                    f"abc -liberty {quoted}",
                    "clean",
                    f"tee -o {_STAT_NAME} stat -liberty {quoted}",
                ]
            )
        else:
            lines.append(f"tee -o {_STAT_NAME} stat")
        lines.append(f"write_verilog {_NETLIST_NAME}")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _resolve(job, binary):
        tool_dir = job.get("tool_dir")
        if tool_dir:
            candidate = Path(tool_dir) / binary
            if candidate.is_file():
                return str(candidate)
            raise AdapterError(
                "missing_dependency",
                f"{binary} not found in {tool_dir} — install the pinned "
                "oss-cad-suite bundle (see docs/provision-plan.md).",
            )
        found = shutil.which(binary)
        if found is None:
            raise AdapterError(
                "missing_dependency",
                f"{binary} not on PATH — install the pinned oss-cad-suite "
                "bundle (see docs/provision-plan.md) or pass tool_dir.",
            )
        return found

    @staticmethod
    def _version(yosys):
        """Assert the binary answers with a parseable yosys banner.

        Args:
            yosys: Resolved yosys binary path.

        Returns:
            Full `yosys -V` banner line (kept as evidence).

        Raises:
            AdapterError: missing_dependency when the probe fails,
                times out, or answers no yosys banner.
        """
        try:
            proc = subprocess.run(
                [yosys, "-V"],
                capture_output=True,
                text=True,
                timeout=_VERSION_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired as exc:
            raise AdapterError(
                "missing_dependency",
                f"yosys version probe timed out at {yosys}.",
            ) from exc
        banner = (proc.stdout + "\n" + proc.stderr).strip().splitlines()
        versioned = next((line for line in banner if _VERSION_RE.search(line)), None)
        if proc.returncode != 0 or versioned is None:
            raise AdapterError(
                "missing_dependency",
                f"yosys at {yosys} answered no yosys banner — install the "
                "pinned oss-cad-suite bundle (see docs/provision-plan.md).",
            )
        return versioned.strip()

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
                "runner_unavailable", f"synth timed out after {timeout_s}s."
            ) from exc
