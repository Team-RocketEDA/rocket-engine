"""Netgen LVS solver adapter (EXTRACT-SKY130): layout vs schematic.

Protocol, verified against netgen 1.5.316 + sky130A_setup.tcl: the
one-shot `netgen -batch lvs <layout> <schematic> <setup> <report>`
compares TOP-level circuits, so both sides are first flattened to
top level (leaf-cell normalization: the single `.subckt` wrapper is
dropped; a library file needs `cell` to select its block). Netgen
exits 0 on match and mismatch alike, so the verdict always comes
from parsed output, never the exit code. Batch runs with DISPLAY
scrubbed: netgen's Tk init fails against an unreachable display.
Because netgen matches by topology, a rename of a singly-connected
net escapes it (LVS-ESCAPE): the flattened net-name inventories are
compared too, and name-only-on-one-side nets fail as
`lvs_net_mismatch`.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

from ...execution.errors import ExecutionError
from ...interfaces import ToolAdapter
from ...interfaces.runparams import MAX_TIMEOUT_S, MIN_TIMEOUT_S
from ..errors import AdapterError

OPERATION = "run_lvs"
_TIMEOUT_S = 120
_IDENTIFY_TIMEOUT_S = 10


def _budget_or_raise(job):
    """Job solver budget: validated, or the adapter default.

    Args:
        job: Solver job, maybe with a `timeout_s`.

    Returns:
        Budget seconds for every `_run` call.

    Raises:
        AdapterError: invalid_command for a boolean,
            non-number, or out-of-bounds budget.
    """
    timeout = job.get("timeout_s", _TIMEOUT_S)
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not MIN_TIMEOUT_S <= timeout <= MAX_TIMEOUT_S
    ):
        raise AdapterError(
            "invalid_command", f"Bad timeout_s: {timeout!r}."
        )
    return timeout

# Observed impostor markers (Oct 2026): the `netgen` apt package is
# the Schoeberl mesh generator — same name, different tool. Denylist
# only: NGSPICE-LIVE promotes this to a strict allowlist once the
# real LVS banner is verifiable against an installed binary.
_IMPOSTOR_RE = re.compile(
    r"Schoeberl|Vienna University|RWTH Aachen|Johannes Kepler"
)

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
    """Return the wrapped `.subckt cell ... .ends` block from a library.

    Args:
        text: Netlist library text to slice.
        cell: Subcircuit name to select (case-insensitive).

    Returns:
        The wrapped .subckt block with its closing .ends.

    Raises:
        AdapterError: invalid_command when the cell is absent or
            has no closing .ends.
    """
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

    Args:
        text: Netlist text to normalize.
        cell: Subcircuit to select from a library, or None for a
            bare or single-wrapper netlist.

    Returns:
        Top-level netlist text with .subckt/.ends lines dropped.

    Raises:
        AdapterError: invalid_command for an ambiguous multi-block
            library without cell, or a missing/unclosed block.
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


def inventory_nets(text):
    """Net names of the flattened netlist's X device lines.

    Netgen's one-shot `lvs` matches by topology, so a rename of a
    singly-connected net escapes it (LVS-ESCAPE). This inventory
    keeps the dropped name evidence: comment, subckt/ends, empty,
    and non-X lines never contribute; params (`k=v`) never count
    as nets; the class token is the last bare token before the
    params start.

    Args:
        text: Flattened netlist text to inventory.

    Returns:
        Set of net names on X device lines.
    """
    nets = set()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("*") or stripped.startswith("."):
            continue
        tokens = stripped.split()
        if not tokens or not tokens[0].upper().startswith("X"):
            continue
        body = tokens[1:]
        params_at = next(
            (i for i, token in enumerate(body) if "=" in token), len(body)
        )
        bare = body[:params_at]
        if params_at < len(body):
            bare = bare[:-1] if bare else []
        nets.update(bare)
    return nets


def _inventory_violations(layout_nets, schematic_nets):
    """Name-only-on-one-side nets as `lvs_net_mismatch` violations.

    Args:
        layout_nets: Net names on the layout side.
        schematic_nets: Net names on the schematic side.

    Returns:
        Violations naming each asymmetric net with its side.
    """
    violations = []
    for net in sorted(set(layout_nets) - set(schematic_nets)):
        violations.append(
            {
                "rule": "lvs_net_mismatch",
                "message": f"Net: {net} (only in layout)",
                "net": net,
                "severity": "error",
            }
        )
    for net in sorted(set(schematic_nets) - set(layout_nets)):
        violations.append(
            {
                "rule": "lvs_net_mismatch",
                "message": f"Net: {net} (only in schematic)",
                "net": net,
                "severity": "error",
            }
        )
    return violations


def netgen_env():
    """Process env for netgen: DISPLAY scrubbed, the rest intact.

    Returns:
        Process environment mapping without DISPLAY (netgen's Tk
            init fails against an unreachable display).
    """
    env = dict(os.environ)
    env.pop("DISPLAY", None)
    return env


def _identify_netgen(path):
    """Banner check: None if usable, else the rejection cause."""
    try:
        proc = subprocess.run(
            [path, "-help"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=_IDENTIFY_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired):
        return (
            f"netgen at {path} is unprovable: the identity probe "
            "failed (see docs/tickets/NGSPICE-LIVE.md)."
        )
    banner = (proc.stdout or "") + (proc.stderr or "")
    if _IMPOSTOR_RE.search(banner):
        first = banner.strip().splitlines()[0] if banner.strip() else "empty banner"
        return (
            f"netgen at {path} is the Schoeberl mesh-generator "
            f"impostor, not the LVS netgen ({first}); install "
            "opencircuitdesign netgen (see docs/tickets/NGSPICE-LIVE.md)."
        )
    return None


def resolve_netgen():
    """Path to a usable LVS netgen, or None.

    PATH presence is NOT enough: the `netgen` apt package is the
    Schoeberl mesh generator, a same-named different tool (caught
    live Oct 2026). Denylist: only observed impostor markers
    reject; an unknown banner admits — NGSPICE-LIVE promotes this
    to a strict allowlist once the real binary is verifiable.

    Returns:
        Path to a usable LVS netgen, or None when missing or
            rejected by the banner probe.
    """
    found = shutil.which("netgen")
    if found is None:
        return None
    if _identify_netgen(found) is not None:
        return None
    return found


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
    """run_lvs via Netgen: layout vs schematic, TOP-level compare.

    Serves the run_lvs operation with deck.tool `netgen` (the only
    tool). Both netlists flatten to top level first (a library file
    needs `cell` to select its block), then the one-shot batch LVS
    runs; the result is {match, total, violations[]} with net and
    device mismatches.

    Job keys:
        layout_spice (required): Layout netlist path.
        schematic_spice (required): Schematic netlist path.
        setup_file (required): Netgen setup path — one setup form
            is required (setup_file or deck.path/setup_file/setup/
            file).
        deck: Optional mapping naming the setup file (see above).
        cell: .subckt block to select from library netlists.
        workdir: Run directory (default ".").

    Args:
        runner: Optional isolated runner; direct subprocess when None.

    Caution: Netgen exits 0 on match and mismatch alike — the
        verdict always comes from parsed output, never the exit
        code. PATH presence is not enough: same-named impostor
        binaries are rejected by banner probe.
    """

    def __init__(self, runner=None):
        self._runner = runner

    def capabilities(self, target):
        """Report the served operation and tool name.

        Args:
            target: Target the capabilities are reported for
                (accepted, unused — one netlist pair per job).

        Returns:
            Capability mapping with operations and tool.
        """
        return {"operations": [OPERATION], "tool": "netgen"}

    def preflight(self, job):
        """Check operation, banner-proved binary, setup, and netlists.

        Args:
            job: Solver job with operation run_lvs plus netlist,
                setup, and cell inputs.

        Returns:
            Checked mapping with setup_file, both netlist paths,
                and cell when given.

        Raises:
            AdapterError: unsupported_operation for another
                operation, missing_dependency for a missing netgen
                or a banner-rejected impostor, invalid_reference
                for missing netlist files, invalid_command when no
                setup form is given.
        """
        if job.get("operation") != OPERATION:
            raise AdapterError(
                "unsupported_operation",
                f"Netgen LVS handles {OPERATION}, got {job.get('operation')}.",
            )
        timeout = _budget_or_raise(job)
        found = shutil.which("netgen")
        if found is None:
            raise AdapterError("missing_dependency", "netgen binary not found.")
        cause = _identify_netgen(found)
        if cause is not None:
            raise AdapterError("missing_dependency", cause)
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
        checked["timeout_s"] = timeout
        return checked

    def execute(self, job):
        """Flatten both sides, then run the one-shot batch LVS.

        Batch runs with DISPLAY scrubbed: netgen's Tk init fails
        against an unreachable display.

        Args:
            job: Solver job with operation run_lvs plus netlist,
                setup, and cell inputs.

        Returns:
            Native output with exit_code, stdout/stderr, report
                file/text, and both netlist paths.

        Raises:
            AdapterError: invalid_reference for a missing workdir,
                invalid_command for an ambiguous library without
                cell, runner_unavailable when netgen produces no
                report, plus the preflight codes (execute
                re-checks first).
        """
        checked = self.preflight(job)
        workdir = job.get("workdir", ".")
        if not Path(workdir).is_dir():
            raise AdapterError(
                "invalid_reference", f"Workdir not found: {workdir}."
            )
        cell = checked.get("cell")
        staged = {}
        flats = {}
        for key, name in (
            ("layout_spice", "layout_flat.spice"),
            ("schematic_spice", "schematic_flat.spice"),
        ):
            flat = flatten_spice(
                Path(checked[key]).read_text(encoding="utf-8"), cell
            )
            staged[key] = Path(workdir) / name
            staged[key].write_text(flat, encoding="utf-8")
            flats[key] = flat
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
            timeout=checked["timeout_s"],
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
            "layout_nets": sorted(inventory_nets(flats["layout_spice"])),
            "schematic_nets": sorted(inventory_nets(flats["schematic_spice"])),
        }

    def parse(self, native_output):
        """Parse the match line or the net/device mismatches.

        A match returns zero violations — unless the flattened net
        inventories disagree (a rename of a singly-connected net
        is topologically invisible to netgen, LVS-ESCAPE), in which
        case the name-only-on-one-side nets fail as
        lvs_net_mismatch. Mismatches parse per net and instance
        plus any inventory extras; anything without a verdict
        raises instead of guessing.

        Args:
            native_output: Native output with the report text/file
                or stdout fallback, plus optional layout_nets /
                schematic_nets inventories from execute (absent in
                legacy outputs, which parse exactly as before).

        Returns:
            {match, total, violations[]} with lvs_net_mismatch and
                lvs_device_mismatch rules.

        Raises:
            AdapterError: runner_unavailable when the output has no
                LVS verdict.
        """
        report = native_output.get("report_text")
        if report is None:
            report_file = native_output.get("report_file")
            if report_file and Path(report_file).is_file():
                report = Path(report_file).read_text(encoding="utf-8")
            else:
                report = native_output.get("stdout", "")
        layout_nets = native_output.get("layout_nets")
        schematic_nets = native_output.get("schematic_nets")
        extra = []
        if layout_nets is not None and schematic_nets is not None:
            extra = _inventory_violations(layout_nets, schematic_nets)
        if _MATCH_RE.search(report):
            if extra:
                return {"match": False, "total": len(extra), "violations": extra}
            return {"match": True, "total": 0, "violations": []}
        if any(rx.search(report) for rx in _MISMATCH_RES):
            violations = _parse_mismatches(report)
            seen = {violation["message"] for violation in violations}
            for violation in extra:
                if violation["message"] not in seen:
                    violations.append(violation)
                    seen.add(violation["message"])
            return {
                "match": False,
                "total": len(violations),
                "violations": violations,
            }
        raise AdapterError(
            "runner_unavailable", "netgen output has no LVS verdict."
        )

    def _run(self, argv, workdir, timeout=_TIMEOUT_S):
        if self._runner is not None:
            try:
                return self._runner.run(argv, workdir, timeout)
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
                timeout=timeout,
                cwd=workdir,
                env=netgen_env(),
            )
        except subprocess.TimeoutExpired as exc:
            raise AdapterError(
                "runner_unavailable", f"netgen timed out after {timeout}s."
            ) from exc
