"""Netgen LVS solver adapter (EXTRACT-SKY130): layout vs schematic.

Protocol, verified against netgen 1.5.316 + sky130A_setup.tcl: the
one-shot `netgen -batch lvs <layout> <schematic> <setup> <report>`
compares TOP-level circuits, so both sides are first flattened to
top level (leaf-cell normalization: the single `.subckt` wrapper is
dropped; a library file needs `cell` to select its block). Netgen
exits 0 on match and mismatch alike, so the verdict always comes
from parsed output, never the exit code. Batch runs with DISPLAY
scrubbed: netgen's Tk init fails against an unreachable display.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

from ...execution.errors import ExecutionError
from ...interfaces import ToolAdapter
from ..errors import AdapterError

OPERATION = "run_lvs"
_TIMEOUT_S = 120

_SUBCKT_RE = re.compile(r"^\s*\.subckt\s+(\S+)", re.IGNORECASE)
_ENDS_RE = re.compile(r"^\s*\.ends\b", re.IGNORECASE)
_MATCH_RE = re.compile(r"(Circuits match uniquely|Netlists match uniquely)\.")
_MISMATCH_RES = (
    re.compile(r"Netlists do not match\."),
    re.compile(r"\*\*\* MISMATCH \*\*\*"),
)
_NET_RE = re.compile(r"Net:\s+(\S+)")
_INSTANCE_RE = re.compile(r"Instance:\s+(\S+)")


def slice_subckt(text, cell):
    """Return the wrapped `.subckt cell ... .ends` block from a library."""
    lines = text.splitlines()
    start = next(
        (
            i
            for i, line in enumerate(lines)
            if (m := _SUBCKT_RE.match(line)) and m.group(1).lower() == cell.lower()
        ),
        None,
    )
    if start is None:
        raise AdapterError(
            "invalid_command", f"No .subckt {cell} in the netlist."
        )
    end = next(
        (i for i in range(start + 1, len(lines)) if _ENDS_RE.match(lines[i])),
        None,
    )
    if end is None:
        raise AdapterError(
            "invalid_command", f".subckt {cell} has no closing .ends."
        )
    return "\n".join(lines[start : end + 1]) + "\n"


def flatten_spice(text, cell=None):
    """Normalize a netlist to top level for netgen's one-shot lvs.

    A bare netlist passes through; a single `.subckt` wrapper is
    dropped; a library needs `cell` to select its block, else the
    call refuses instead of guessing.
    """
    if cell is not None:
        text = slice_subckt(text, cell)
    elif sum(1 for line in text.splitlines() if _SUBCKT_RE.match(line)) > 1:
        raise AdapterError(
            "invalid_command", "Ambiguous netlist: pass cell to select a block."
        )
    return "\n".join(
        line
        for line in text.splitlines()
        if not _SUBCKT_RE.match(line) and not _ENDS_RE.match(line)
    ) + "\n"


def netgen_env():
    """Process env for netgen: DISPLAY scrubbed, the rest intact."""
    env = dict(os.environ)
    env.pop("DISPLAY", None)
    return env


def _setup_file_or_raise(job):
    deck = job.get("deck") if isinstance(job.get("deck"), dict) else {}
    for candidate in (
        job.get("setup_file"),
        deck.get("path"),
        deck.get("setup_file"),
        deck.get("setup"),
        deck.get("file"),
    ):
        if candidate is not None:
            if not candidate or not Path(candidate).is_file():
                raise AdapterError(
                    "invalid_reference", f"Netgen setup not found: {candidate}."
                )
            return str(candidate)
    raise AdapterError("invalid_command", "LVS needs a netgen setup file.")


def _parse_mismatches(report):
    violations = []
    net_section, _, device_section = report.partition("DEVICE mismatches:")
    seen = set()
    for name in _NET_RE.findall(net_section):
        if name not in seen:
            seen.add(name)
            violations.append(
                {
                    "rule": "lvs_net_mismatch",
                    "message": f"Net: {name}",
                    "net": name,
                    "severity": "error",
                }
            )
    for _ in re.finditer(r"\(no matching net\)", net_section):
        violations.append(
            {
                "rule": "lvs_net_mismatch",
                "message": "(no matching net)",
                "severity": "error",
            }
        )
    seen = set()
    for name in _INSTANCE_RE.findall(device_section):
        if name not in seen:
            seen.add(name)
            violations.append(
                {
                    "rule": "lvs_device_mismatch",
                    "message": f"Instance: {name}",
                    "instance": name,
                    "severity": "error",
                }
            )
    for _ in re.finditer(r"\(no matching instance\)", device_section):
        violations.append(
            {
                "rule": "lvs_device_mismatch",
                "message": "(no matching instance)",
                "severity": "error",
            }
        )
    return violations


class NetgenLvsAdapter(ToolAdapter):
    def __init__(self, runner=None):
        self._runner = runner

    def capabilities(self, target):
        return {"operations": [OPERATION], "tool": "netgen"}

    def preflight(self, job):
        if job.get("operation") != OPERATION:
            raise AdapterError(
                "unsupported_operation",
                f"Netgen LVS handles {OPERATION}, got {job.get('operation')}.",
            )
        if shutil.which("netgen") is None:
            raise AdapterError("missing_dependency", "netgen binary not found.")
        checked = {"setup_file": _setup_file_or_raise(job)}
        for key in ("layout_spice", "schematic_spice"):
            path = job.get(key)
            if not path or not Path(path).is_file():
                raise AdapterError(
                    "invalid_reference", f"Netlist file not found: {path}."
                )
            checked[key] = path
        if job.get("cell") is not None:
            checked["cell"] = str(job["cell"])
        return checked

    def execute(self, job):
        checked = self.preflight(job)
        workdir = job.get("workdir", ".")
        if not Path(workdir).is_dir():
            raise AdapterError(
                "invalid_reference", f"Workdir not found: {workdir}."
            )
        cell = checked.get("cell")
        staged = {}
        for key, name in (
            ("layout_spice", "layout_flat.spice"),
            ("schematic_spice", "schematic_flat.spice"),
        ):
            flat = flatten_spice(
                Path(checked[key]).read_text(encoding="utf-8"), cell
            )
            staged[key] = Path(workdir) / name
            staged[key].write_text(flat, encoding="utf-8")
        report_file = Path(workdir) / "lvs_report.out"
        proc = self._run(
            [
                "netgen",
                "-batch",
                "lvs",
                str(staged["layout_spice"]),
                str(staged["schematic_spice"]),
                checked["setup_file"],
                str(report_file),
            ],
            workdir,
        )
        if not report_file.is_file():
            raise AdapterError(
                "runner_unavailable",
                f"netgen produced no report: {proc.stderr[:500]}.",
            )
        return {
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "report_file": str(report_file),
            "report_text": report_file.read_text(encoding="utf-8"),
            "layout_spice": checked["layout_spice"],
            "schematic_spice": checked["schematic_spice"],
        }

    def parse(self, native_output):
        report = native_output.get("report_text")
        if report is None:
            report_file = native_output.get("report_file")
            if report_file and Path(report_file).is_file():
                report = Path(report_file).read_text(encoding="utf-8")
            else:
                report = native_output.get("stdout", "")
        if _MATCH_RE.search(report):
            return {"match": True, "total": 0, "violations": []}
        if any(rx.search(report) for rx in _MISMATCH_RES):
            violations = _parse_mismatches(report)
            return {
                "match": False,
                "total": len(violations),
                "violations": violations,
            }
        raise AdapterError(
            "runner_unavailable", "netgen output has no LVS verdict."
        )

    def _run(self, argv, workdir):
        if self._runner is not None:
            try:
                return self._runner.run(argv, workdir, _TIMEOUT_S)
            except ExecutionError as exc:
                raise AdapterError(exc.code, str(exc)) from exc
        if not Path(workdir).is_dir():
            raise AdapterError(
                "invalid_reference", f"Workdir not found: {workdir}."
            )
        try:
            return subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=_TIMEOUT_S,
                cwd=workdir,
                env=netgen_env(),
            )
        except subprocess.TimeoutExpired as exc:
            raise AdapterError(
                "runner_unavailable", f"netgen timed out after {_TIMEOUT_S}s."
            ) from exc
