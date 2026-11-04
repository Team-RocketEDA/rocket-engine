"""Xschem netlist-to-sim deck: one call from schematic to verdict.

The solver adapter (`src/adapters/xschem/__init__.py`) netlists one
schematic per call. This deck chains the two deck phases behind one
call: netlist the schematic, refuse an empty (device-free) netlist
loudly instead of fake-greening it, and optionally run the
schematic-owned sim (`-S`) whose failures combine under the same
verdict. Engine vocabulary/composition wiring belongs to the owning
surface; this file only orchestrates the solver.
"""

from pathlib import Path

from ...interfaces import ToolAdapter
from ..errors import AdapterError
from . import XschemAdapter

OPERATION = "run_xschem"


def deck_elements(text):
    """Device lines of one netlist, without comments or directives.

    Args:
        text: Raw (or normalized) netlist text.

    Returns:
        Device lines such as `V1 ...` or `X...`, in file order.
            Comment lines (`*...`), dot directives (`.end`,
            `.GLOBAL`), and blanks never count as devices.
    """
    lines = []
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(("*", ".")):
            continue
        lines.append(line)
    return lines


class XschemDeck(ToolAdapter):
    """run_xschem as a deck: netlist, guard empty, optionally sim.

    Serves the run_xschem operation with tool `xschem` in deck
    modes (`netlist`, `sim`, `deck`). Phase one netlists the
    schematic; a netlist with zero device lines fails loudly as
    `empty_netlist` (an empty schematic or all symbols missing
    never parses as clean). Phase two, only when the job sets
    `sim`, reruns with the schematic-owned sim (`-S`) and reports
    its failures under `sim`.

    Job keys:
        sch_file (required): Schematic file under netlist.
        rcfile: Project rcfile path (library paths may derive
            from the adapter-pinned XSCHEM_SHAREDIR).
        output_name: Netlist file name (default `<stem>.spice`).
        flat: Flat netlist (`-f`) when true.
        sim: Run the schematic-owned sim (`-S`) when true.
        workdir: Run directory (default ".").

    Args:
        runner: Optional isolated runner; direct subprocess when None.
        xschem_bin: Explicit xschem binary; PATH when None.

    Caution: The deck reruns the netlister for the sim phase, so
        a schematic whose outputs differ run to run decks
        non-deterministically — byte-compare only the netlist
        phase, never the sim phase.
    """

    def __init__(self, runner=None, xschem_bin=None):
        self._runner = runner
        self._xschem_bin = xschem_bin

    def capabilities(self, target):
        """Report the served operation, tool, and deck modes.

        Args:
            target: Target the capabilities are reported for
                (accepted, unused — one schematic per job).

        Returns:
            Capability mapping with operations, tool, and modes.
        """
        return {
            "operations": [OPERATION],
            "tool": "xschem",
            "modes": ["netlist", "sim", "deck"],
        }

    def _adapter(self):
        """One solver adapter sharing this deck's runner and binary."""
        return XschemAdapter(
            runner=self._runner, xschem_bin=self._xschem_bin)

    def netlist(self, job):
        """Netlist one schematic and parse it to a deck verdict.

        Args:
            job: Solver job with operation run_xschem plus
                sch_file and deck inputs (any `sim` flag is
                ignored: this phase never simulates).

        Returns:
            Mapping with netlist_file, normalized_text, elements
                (device lines), total, and violations.

        Raises:
            AdapterError: invalid_reference for a missing
                schematic/rcfile, missing_dependency without
                xschem V3, runner_unavailable with no netlist
                output, plus the solver preflight codes.
        """
        adapter = self._adapter()
        native = adapter.execute(dict(job, sim=False))
        parsed = adapter.parse(native)
        elements = deck_elements(native.get("normalized_text"))
        return {
            "netlist_file": native.get("netlist_file"),
            "normalized_text": native.get("normalized_text"),
            "elements": elements,
            "total": parsed.get("total"),
            "violations": list(parsed.get("violations") or []),
        }

    def deck(self, job):
        """Deck one schematic from netlist to an optional sim verdict.

        Args:
            job: Solver job with operation run_xschem plus
                sch_file and deck inputs; `sim` true adds the
                schematic-owned sim phase.

        Returns:
            Netlist verdict (netlist_file, normalized_text,
                elements, total, violations) plus `sim`: None
                without the sim flag, else the sim failures as
                {total, violations, log_file}. A device-free
                netlist appends an `empty_netlist` error and
                skips the sim phase.

        Raises:
            AdapterError: invalid_reference for a missing
                schematic, missing_dependency without xschem
                V3, runner_unavailable with no netlist output,
                plus the solver preflight codes (netlist first,
                sim reruns the same checks).
        """
        verdict = self.netlist(job)
        if not verdict["elements"]:
            verdict["violations"] = verdict["violations"] + [{
                "rule": "empty_netlist",
                "severity": "error",
                "message": ("xschem deck netlist has no device lines: "
                            "empty schematic or all symbols missing."),
            }]
            verdict["total"] = len(verdict["violations"])
            verdict["sim"] = None
            return verdict
        if not job.get("sim"):
            verdict["sim"] = None
            return verdict
        adapter = self._adapter()
        sim_native = adapter.execute(dict(job, sim=True))
        sim_parsed = adapter.parse(sim_native)
        sim_fails = [v for v in (sim_parsed.get("violations") or [])
                     if v.get("rule") == "xschem_sim_fail"]
        verdict["sim"] = {
            "total": len(sim_fails),
            "violations": sim_fails,
            "log_file": sim_native.get("log_file"),
        }
        return verdict

    def preflight(self, job):
        """Check the deck job through the solver preflight.

        Args:
            job: Solver job with operation run_xschem plus
                sch_file and deck inputs.

        Returns:
            Checked mapping from the solver preflight.

        Raises:
            AdapterError: unsupported_operation, invalid_reference,
                invalid_command, or missing_dependency, exactly as
                the solver reports them.
        """
        return self._adapter().preflight(job)

    def execute(self, job):
        """Deck one schematic: netlist natively, sim natively on flag.

        Args:
            job: Solver job with operation run_xschem plus
                sch_file and deck inputs.

        Returns:
            Native output with the netlist phase and, on the sim
                flag with devices present, the sim phase.

        Raises:
            AdapterError: invalid_reference, missing_dependency,
                or runner_unavailable, exactly as the solver
                reports them.
        """
        net_native = self._adapter().execute(dict(job, sim=False))
        phases = {"netlist": net_native, "sim": None}
        if job.get("sim") and deck_elements(
                net_native.get("normalized_text")):
            phases["sim"] = self._adapter().execute(dict(job, sim=True))
        return phases

    def parse(self, native_output):
        """Parse deck natives to the combined deck verdict.

        Args:
            native_output: Native output with netlist (and
                optional sim) phases from execute.

        Returns:
            Deck verdict with elements, violations (including
                the empty_netlist guard), and the sim sub-verdict.

        Raises:
            AdapterError: runner_unavailable when the netlist
                phase is missing.
        """
        adapter = self._adapter()
        net_native = (native_output or {}).get("netlist")
        if net_native is None:
            raise AdapterError(
                "runner_unavailable", "xschem deck has no netlist phase.")
        parsed = adapter.parse(net_native)
        elements = deck_elements(net_native.get("normalized_text"))
        violations = list(parsed.get("violations") or [])
        if not elements:
            violations = violations + [{
                "rule": "empty_netlist",
                "severity": "error",
                "message": ("xschem deck netlist has no device lines: "
                            "empty schematic or all symbols missing."),
            }]
        sim_native = (native_output or {}).get("sim")
        sim = None
        if sim_native is not None:
            sim_parsed = adapter.parse(sim_native)
            sim_fails = [v for v in (sim_parsed.get("violations") or [])
                         if v.get("rule") == "xschem_sim_fail"]
            sim = {
                "total": len(sim_fails),
                "violations": sim_fails,
                "log_file": sim_native.get("log_file"),
            }
        return {
            "netlist_file": net_native.get("netlist_file"),
            "normalized_text": net_native.get("normalized_text"),
            "elements": elements,
            "total": (len(violations) if not elements
                      else parsed.get("total")),
            "violations": violations,
            "sim": sim,
        }
