"""OpenSTA timing adapter: run_timing behind the ToolAdapter port.

Protocol, best-knowledge OpenSTA (live proof deferred: `sta` is not
provisioned in this sandbox, so the report flags every unverified
command-line assumption for the gate host): write a timing script
(`read_liberty` the libs, `read_verilog` the mapped netlist files,
`link_design` the top, `read_spef` when a top-level SPEF is given,
`read_sdc` the constraints), then marker-delimited report sections
(`report_checks -path_delay min_max` for setup+hold critical paths,
`report_wns`/`report_tns` per corner for WNS/TNS, bare
`report_constraint` for slew/load violators, bare `check_setup` for
unconstrained endpoints) closed by a trailing `exit` so `sta` can
never linger at its interactive prompt. Parse splits the log on the
markers: per-path slack records with MET/VIOLATED status, the four
WNS/TNS margins, constraint violators, and check_setup evidence.
Unconstrained endpoints are findings (rule
`unconstrained_endpoint`) plus raw `check_setup` text that is always
attached — listed, never silent, never assumed.

Tool resolution: an explicit job `tool_dir` wins, then
`$OPENSTA_PREFIX/bin` (the PROV consumer contract), else PATH, and
the resolved binary must answer its version probe with an `OpenSTA`
banner — ambient installs are kept and version-asserted, never
reinstalled. Where the tools live on disk is B10 integration scope.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

from ...execution.errors import ExecutionError
from ...execution.runner import tool_roots
from ...interfaces import ToolAdapter
from ..errors import AdapterError

OPERATION = "run_timing"
_TOOL = "sta"
_TIMEOUT_S = 300
_VERSION_TIMEOUT_S = 30

_SCRIPT_NAME = "timing.tcl"
_LOG_NAME = "timing.log"

_TOP_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_VERSION_RE = re.compile(r"OpenSTA", re.IGNORECASE)
_ERROR_RE = re.compile(r"^(?:Error|ERROR):\s*(.*)$", re.M)
_WARNING_RE = re.compile(r"^Warning:\s*(.*)$", re.M)
_MARKER_RE = re.compile(r"^===== TIMING_STA ([A-Z_]+) =====\s*$", re.M)
_MARGIN_RE = re.compile(
    r"^\s*(?:wns|tns)\s+([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)",
    re.M,
)
_STARTPOINT_RE = re.compile(r"^Startpoint:\s*(\S+)", re.M)
_ENDPOINT_RE = re.compile(r"^Endpoint:\s*(\S+)", re.M)
_GROUP_RE = re.compile(r"^Path Group:\s*(.+?)\s*$", re.M)
_TYPE_RE = re.compile(r"^Path Type:\s*(max|min)\s*$", re.M)
_SLACK_RE = re.compile(
    r"^\s*([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)"
    r"\s+slack\s+\((MET|VIOLATED)\)",
    re.M,
)


def _parse_errors(text):
    """Collect sta_error violations from sta Error lines.

    Args:
        text: Combined sta log/stdout/stderr text.

    Returns:
        Error violations in log order.
    """
    return [
        {"rule": "sta_error", "severity": "error", "message": message}
        for message in _ERROR_RE.findall(text)
    ]


def _parse_warnings(text):
    """Collect warning findings, flagging unconstrained endpoints.

    Warnings whose message names something unconstrained become
    `unconstrained_endpoint` findings; every other warning is a
    generic `sta_warning`. Neither fails the verdict on its own.

    Args:
        text: Combined sta log/stdout/stderr text.

    Returns:
        Warning violations in log order.
    """
    violations = []
    for message in _WARNING_RE.findall(text):
        rule = (
            "unconstrained_endpoint"
            if "unconstrained" in message.lower()
            else "sta_warning"
        )
        violations.append(
            {"rule": rule, "severity": "warning", "message": message}
        )
    return violations


def _parse_sections(text):
    """Split the log on TIMING_STA markers into {name: body}.

    Args:
        text: Combined sta log/stdout/stderr text.

    Returns:
        Mapping of section name to section body (possibly empty).
    """
    sections = {}
    marks = list(_MARKER_RE.finditer(text))
    for index, mark in enumerate(marks):
        start = mark.end()
        end = marks[index + 1].start() if index + 1 < len(marks) else len(text)
        sections[mark.group(1)] = text[start:end]
    return sections


def _parse_paths(text):
    """Parse critical paths from the report_checks section.

    Each `Startpoint:` chunk yields startpoint, endpoint, path group,
    path type (max = setup, min = hold), slack in ns, and the
    violated flag. Chunks without a slack line are skipped: an empty
    or pathless section parses as no paths, never as an error.

    Args:
        text: REPORT_CHECKS section body.

    Returns:
        Path records in report order.
    """
    paths = []
    starts = list(_STARTPOINT_RE.finditer(text))
    for index, start in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(text)
        chunk = text[start.start() : end]
        slack = _SLACK_RE.search(chunk)
        if slack is None:
            continue
        endpoint = _ENDPOINT_RE.search(chunk)
        group = _GROUP_RE.search(chunk)
        path_type = _TYPE_RE.search(chunk)
        value = float(slack.group(1))
        paths.append(
            {
                "startpoint": start.group(1),
                "endpoint": endpoint.group(1) if endpoint else "",
                "group": group.group(1) if group else "",
                "type": path_type.group(1) if path_type else "",
                "slack": value,
                "violated": slack.group(2) == "VIOLATED" or value < 0,
            }
        )
    return paths


def _parse_margin(text):
    """Read the first wns/tns value from one margin section.

    Args:
        text: One WNS_*/TNS_* section body.

    Returns:
        Margin in ns, or None when the section carries no value.
    """
    match = _MARGIN_RE.search(text)
    return float(match.group(1)) if match is not None else None


def _parse_constraint_violations(text):
    """Collect constraint_violation errors from VIOLATED lines.

    Args:
        text: CONSTRAINTS section body.

    Returns:
        Error violations, one per VIOLATED line.
    """
    return [
        {
            "rule": "constraint_violation",
            "severity": "error",
            "message": line.strip(),
        }
        for line in text.splitlines()
        if "VIOLATED" in line
    ]


def _quote(path):
    """Brace-quote one path for the sta TCL script.

    Args:
        path: Filesystem path to embed in the script.

    Returns:
        Brace-quoted path (no TCL substitution inside braces).
    """
    return "{" + str(path) + "}"


class OpenStaTimingAdapter(ToolAdapter):
    """run_timing via OpenSTA: top-level STA recheck plus evidence.

    Serves the run_timing operation with deck.tool `opensta` (the
    only tool). Reads the timing libs, the mapped netlist files, the
    optional top-level SPEF, and the SDC constraints, then reports
    setup/hold WNS/TNS margins, critical paths, slew/load
    violators, and unconstrained endpoints. Evidence is the four
    margins, the critical-path records, the unconstrained-endpoint
    findings with the raw check_setup text, and the sta version.

    Job keys:
        netlist (required): Mapped Verilog netlist paths, non-empty
            list, every file must exist.
        libs (required): Timing liberty (.lib) paths, non-empty
            list, every file must exist.
        sdc (required): SDC constraints path, must exist. Passed to
            sta opaquely — generated clocks and boundary
            constraints flow through untouched.
        spef: Top-level SPEF path for extracted-RC annotation;
            no parasitics without it.
        top (required): Top module name (plain identifier).
        timeout_s: STA budget in seconds (default 300).
        tool_dir: Directory holding sta; $OPENSTA_PREFIX/bin then
            PATH otherwise.
        deck: Optional mapping; deck.tool must be opensta here.
        workdir: Run directory (default ".").

    Args:
        runner: Optional isolated runner; direct subprocess when None.

    Caution: Exit zero is not PASS — sta keeps going past command
        errors, so any `Error:` line fails the run however it
        exited, and a clean run without all four WNS/TNS margins
        is runner_unavailable, never a clean verdict.
    """

    def __init__(self, runner=None):
        self._runner = runner

    def capabilities(self, target):
        """Report the served operation, tool, and SPEF support.

        Args:
            target: Target the capabilities are reported for
                (accepted, unused — one top per job).

        Returns:
            Capability mapping with operations, tool, and spef
                support.
        """
        return {
            "operations": [OPERATION],
            "tool": "opensta",
            "spef": True,
        }

    def preflight(self, job):
        """Check operation, top, inputs, timeout, and sta.

        Cheap deterministic checks first, tool resolution last; the
        resolved binary must answer its version probe with an
        OpenSTA banner.

        Args:
            job: Solver job with operation run_timing plus netlist,
                libs, sdc, and optional spef/top/timeout inputs.

        Returns:
            Checked mapping with the resolved sta path and
                version, netlist, libs, sdc, spef, top, timeout_s.

        Raises:
            AdapterError: unsupported_operation for another
                operation, invalid_command for a bad top or
                timeout, invalid_reference for missing or
                non-list netlist/libs, a missing sdc/spef, or a
                path unsafe for the TCL script, missing_dependency
                for an unresolvable or unassertable sta.
        """
        # Cheap deterministic checks first: operation, top, timeout,
        # netlist, libs, sdc, spef. Tool resolution last, since it
        # depends on the machine.
        if job.get("operation") != OPERATION:
            raise AdapterError(
                "unsupported_operation",
                f"OpenSTA timing handles {OPERATION}, got {job.get('operation')}.",
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
        netlist = self._checked_paths(job.get("netlist"), "netlist")
        libs = self._checked_paths(job.get("libs"), "libs")
        sdc = job.get("sdc")
        if not isinstance(sdc, (str, Path)) or not Path(sdc).is_file():
            raise AdapterError("invalid_reference", f"SDC not found: {sdc}.")
        spef = job.get("spef")
        if spef is not None and (
            not isinstance(spef, (str, Path)) or not Path(spef).is_file()
        ):
            raise AdapterError("invalid_reference", f"SPEF not found: {spef}.")
        for path in [sdc] + ([spef] if spef is not None else []):
            self._checked_scriptable(str(path))
        sta = self._resolve(job, _TOOL)
        checked = {
            "sta": sta,
            "sta_version": self._version(sta),
            "netlist": netlist,
            "libs": libs,
            "sdc": str(sdc),
            "spef": str(spef) if spef is not None else None,
            "top": top,
            "timeout_s": timeout,
        }
        if self._runner is not None:
            try:
                self._runner.preflight()
            except ExecutionError as exc:
                raise AdapterError(exc.code, str(exc)) from exc
        return checked

    def execute(self, job):
        """Run the timing script under sta with the job timeout.

        Writes timing.tcl into the workdir, runs it (stdin closed
        so sta can never linger at its prompt), and returns the
        captured log plus the run inputs. A failed run still
        returns its log — the verdict comes from parse, never the
        exit code alone.

        Args:
            job: Solver job with operation run_timing plus netlist,
                libs, sdc, and optional spef/top/timeout inputs.

        Returns:
            Native output with exit_code, stdout/stderr, log,
                top, netlist, libs, sdc, spef, and the sta version.

        Raises:
            AdapterError: invalid_reference for a missing workdir,
                runner_unavailable on an STA timeout, plus the
                preflight codes (execute re-checks first).
        """
        checked = self.preflight(job)
        workdir = job.get("workdir", ".")
        if not Path(workdir).is_dir():
            raise AdapterError(
                "invalid_reference", f"Workdir not found: {workdir}."
            )
        (Path(workdir) / _SCRIPT_NAME).write_text(self._script(checked))
        roots = tool_roots([checked["sta"]])
        proc = self._run(
            [checked["sta"], _SCRIPT_NAME],
            workdir,
            checked["timeout_s"],
            roots,
        )
        log = proc.stdout or ""
        (Path(workdir) / _LOG_NAME).write_text(log)
        return {
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "log": log,
            "top": checked["top"],
            "netlist": list(checked["netlist"]),
            "libs": list(checked["libs"]),
            "sdc": checked["sdc"],
            "spef": checked["spef"],
            "sta_version": checked["sta_version"],
        }

    def parse(self, native_output):
        """Parse margins, paths, violations, and endpoint evidence.

        Failed runs (nonzero exit or any `Error:` line) surface
        their errors plus warnings with no measurements — a failed
        run never parses as clean. Clean runs require all four
        WNS/TNS margins; violated paths become setup/hold error
        findings, constraint VIOLATED lines become errors, and
        warnings (including unconstrained endpoints) never fail
        alone. Raw check_setup text always rides along so missing
        constraints stay visible however the parse lands.

        Args:
            native_output: Native output with exit_code and log
                text.

        Returns:
            {total, violations[], measurements[]} plus
                critical_paths, unconstrained_endpoints, the four
                margins, check_setup/constraints raw text, top,
                netlist, libs, sdc, spef, and sta_version evidence.

        Raises:
            AdapterError: runner_unavailable when the output has no
                exit code, or a clean run left no parseable
                WNS/TNS verdict — unparseable never parses as
                clean.
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
        sections = _parse_sections(text)
        paths = _parse_paths(sections.get("REPORT_CHECKS", ""))
        unconstrained = [
            v["message"] for v in warnings if v["rule"] == "unconstrained_endpoint"
        ]
        evidence = {
            "critical_paths": paths,
            "unconstrained_endpoints": unconstrained,
            "check_setup": sections.get("CHECK_SETUP", ""),
            "constraints": sections.get("CONSTRAINTS", ""),
            "top": native_output.get("top"),
            "netlist": native_output.get("netlist"),
            "libs": native_output.get("libs"),
            "sdc": native_output.get("sdc"),
            "spef": native_output.get("spef"),
            "sta_version": native_output.get("sta_version"),
        }
        if exit_code != 0 or errors:
            if exit_code != 0 and not errors:
                # Defensive: a failed run must never parse as clean.
                errors = [
                    {
                        "rule": "sta_error",
                        "severity": "error",
                        "message": f"sta exited {exit_code}",
                    }
                ]
            violations = errors + warnings
            return {
                "total": len(violations),
                "violations": violations,
                "measurements": [],
                **evidence,
            }
        margins = {
            "wns_setup": _parse_margin(sections.get("WNS_MAX", "")),
            "tns_setup": _parse_margin(sections.get("TNS_MAX", "")),
            "wns_hold": _parse_margin(sections.get("WNS_MIN", "")),
            "tns_hold": _parse_margin(sections.get("TNS_MIN", "")),
        }
        missing = sorted(name for name, value in margins.items() if value is None)
        if missing:
            raise AdapterError(
                "runner_unavailable",
                f"sta output has no parseable verdict: {', '.join(missing)}.",
            )
        violations = warnings + _parse_constraint_violations(
            sections.get("CONSTRAINTS", "")
        )
        for path in paths:
            if not path["violated"]:
                continue
            rule = "setup_violation" if path["type"] == "max" else "hold_violation"
            violations.append(
                {
                    "rule": rule,
                    "severity": "error",
                    "message": (
                        f"{path['type']} path {path['startpoint']} -> "
                        f"{path['endpoint']} slack {path['slack']} ns"
                        + (f" ({path['group']})" if path["group"] else "")
                    ),
                }
            )
        violated = sum(1 for path in paths if path["violated"])
        measurements = [
            {"name": name, "value": value, "unit": "ns"}
            for name, value in margins.items()
        ]
        measurements.extend(
            [
                {
                    "name": "critical_path_count",
                    "value": len(paths),
                    "unit": "count",
                },
                {
                    "name": "violated_path_count",
                    "value": violated,
                    "unit": "count",
                },
                {
                    "name": "unconstrained_count",
                    "value": len(unconstrained),
                    "unit": "count",
                },
            ]
        )
        return {
            "total": len(violations),
            "violations": violations,
            "measurements": measurements,
            **margins,
            **evidence,
        }

    @staticmethod
    def _checked_paths(value, key):
        """Require a non-empty list of existing, scriptable paths.

        Args:
            value: Job value for the key, expected to be a list of
                paths.
            key: Job key name for error messages.

        Returns:
            The paths as plain strings.

        Raises:
            AdapterError: invalid_reference when the value is not a
                non-empty list, a path is missing, or a path is
                unsafe for the TCL script.
        """
        if not isinstance(value, list) or not value:
            raise AdapterError(
                "invalid_reference", f"{key} must be a non-empty list: {value!r}."
            )
        missing = [
            item
            for item in value
            if not isinstance(item, (str, Path)) or not Path(item).is_file()
        ]
        if missing:
            raise AdapterError("invalid_reference", f"{key} not found: {missing}.")
        for item in value:
            OpenStaTimingAdapter._checked_scriptable(str(item))
        return [str(item) for item in value]

    @staticmethod
    def _checked_scriptable(path):
        """Refuse paths that brace-quoting cannot carry safely.

        Args:
            path: Filesystem path destined for the TCL script.

        Raises:
            AdapterError: invalid_reference when the path holds
                braces or newlines (TCL injection surface).
        """
        if any(char in path for char in ("{", "}", "\n", "\r")):
            raise AdapterError(
                "invalid_reference", f"Path unsafe for the TCL script: {path}."
            )

    @staticmethod
    def _script(checked):
        """Render the sta timing script for the checked job.

        Args:
            checked: Preflight mapping with netlist, libs, sdc,
                spef, and top.

        Returns:
            TCL script text (read, link, constrain, report, exit).
        """
        lines = [f"read_liberty {_quote(lib)}" for lib in checked["libs"]]
        lines += [f"read_verilog {_quote(net)}" for net in checked["netlist"]]
        lines.append(f"link_design {checked['top']}")
        if checked["spef"] is not None:
            lines.append(f"read_spef {_quote(checked['spef'])}")
        lines.append(f"read_sdc {_quote(checked['sdc'])}")
        reports = [
            (
                "REPORT_CHECKS",
                "report_checks -path_delay min_max -format full_clock_expanded "
                "-fields {slew cap} -group_count 50",
            ),
            ("WNS_MAX", "report_wns -max"),
            ("TNS_MAX", "report_tns -max"),
            ("WNS_MIN", "report_wns -min"),
            ("TNS_MIN", "report_tns -min"),
            ("CONSTRAINTS", "report_constraint"),
            ("CHECK_SETUP", "check_setup"),
        ]
        for name, command in reports:
            lines.append(f"puts {{===== TIMING_STA {name} =====}}")
            lines.append(command)
        lines.append("exit")
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
                "OpenSTA build via scripts/provision_toolchain.sh --install "
                "(PROV phase 1; see docs/work/PROV/report.md).",
            )
        prefix = os.environ.get("OPENSTA_PREFIX")
        if prefix:
            candidate = Path(prefix) / "bin" / binary
            if candidate.is_file():
                return str(candidate)
            raise AdapterError(
                "missing_dependency",
                f"{binary} not found under $OPENSTA_PREFIX={prefix} — rebuild "
                "the pinned OpenSTA build via "
                "scripts/provision_toolchain.sh --install (PROV phase 1; "
                "see docs/work/PROV/report.md).",
            )
        found = shutil.which(binary)
        if found is None:
            raise AdapterError(
                "missing_dependency",
                f"{binary} not on PATH and $OPENSTA_PREFIX unset — install "
                "the pinned OpenSTA build via "
                "scripts/provision_toolchain.sh --install (PROV phase 1; "
                "see docs/work/PROV/report.md) or pass tool_dir.",
            )
        return found

    @staticmethod
    def _version(sta):
        """Assert the binary answers with a parseable OpenSTA banner.

        Probes `-version` first, then `--version` (same fallback the
        PROV provisioner uses).

        Args:
            sta: Resolved sta binary path.

        Returns:
            OpenSTA banner line (kept as evidence).

        Raises:
            AdapterError: missing_dependency when the probes fail,
                time out, or answer no OpenSTA banner.
        """
        for flag in ("-version", "--version"):
            try:
                proc = subprocess.run(
                    [sta, flag],
                    capture_output=True,
                    text=True,
                    timeout=_VERSION_TIMEOUT_S,
                )
            except subprocess.TimeoutExpired as exc:
                raise AdapterError(
                    "missing_dependency",
                    f"sta version probe timed out at {sta}.",
                ) from exc
            banner = (proc.stdout + "\n" + proc.stderr).strip().splitlines()
            versioned = next(
                (line for line in banner if _VERSION_RE.search(line)), None
            )
            if proc.returncode == 0 and versioned is not None:
                return versioned.strip()
        raise AdapterError(
            "missing_dependency",
            f"sta at {sta} answered no OpenSTA banner — install the "
            "pinned OpenSTA build via scripts/provision_toolchain.sh "
            "--install (PROV phase 1; see docs/work/PROV/report.md).",
        )

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
                stdin=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired as exc:
            raise AdapterError(
                "runner_unavailable", f"timing timed out after {timeout_s}s."
            ) from exc
