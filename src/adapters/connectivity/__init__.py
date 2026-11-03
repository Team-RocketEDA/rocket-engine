"""Connectgraph solver adapter: run_connectivity/run_erc, no subprocess.

Pure-Python ToolAdapter over the shared extraction plus raw-IR
emitters. run_connectivity extracts the graph, emits the requested
netlists, and reports connectivity findings (shorts fail, the rest
warn); run_erc judges the same findings with unconnected pins
escalated to errors. Every net name in findings and netlists flows
from the shared `Connectivity.net_name` authority.
"""

from ...interfaces import ToolAdapter
from ...workflows.connectgraph import (
    RULE_UNCONNECTED_PIN,
    ConnectGraphError,
    erc_findings,
    prepare_netlist_structs,
)
from ...workflows.connectgraph_emit import LANGUAGES, emit_netlists, to_raw_ir
from ..errors import AdapterError

OPERATIONS = ("run_connectivity", "run_erc")
TOOL = "connectgraph"

CONNECTIVITY_POLICY = {RULE_UNCONNECTED_PIN: "warning"}
ERC_POLICY = {RULE_UNCONNECTED_PIN: "error"}


class ConnectivityAdapter(ToolAdapter):
    """Shared-graph connectivity checks plus netlist emission.

    Serves run_connectivity and run_erc with deck.tool
    `connectgraph` (the only tool). Extraction, naming, and emission
    all run in-process; there is no tool to resolve and no timeout.

    Job keys:
        schematic (required): Schematic record (see
            workflows.connectgraph for the shape).
        languages: Netlist languages for run_connectivity
            (default all of spice, verilog, vhdl).
        run_key: Explicit extraction-cache key; uncached when omitted.
        deck: Optional mapping; deck.tool must be connectgraph here.

    Caution: run_erc fails on unconnected pins while
        run_connectivity only warns — same findings, different
        policy; read the verdict, never the exit path.
    """

    def capabilities(self, target):
        """Report the served operations and tool name.

        Args:
            target: Target the capabilities are reported for
                (accepted, unused — one schematic per job).

        Returns:
            Capability mapping with operations and tool.
        """
        return {"operations": list(OPERATIONS), "tool": TOOL}

    def preflight(self, job):
        """Check operation, tool hint, schematic, and languages.

        Args:
            job: Solver job with operation run_connectivity or
                run_erc plus schematic and language inputs.

        Returns:
            Checked mapping with operation, schematic, languages,
                and run_key.

        Raises:
            AdapterError: unsupported_operation for another
                operation or deck tool, invalid_command for a
                missing schematic or an unknown language.
        """
        if job.get("operation") not in OPERATIONS:
            raise AdapterError(
                "unsupported_operation",
                f"Connectivity handles {', '.join(OPERATIONS)}, "
                f"got {job.get('operation')}.",
            )
        hint = (job.get("deck") or {}).get("tool")
        if hint is not None and hint != TOOL:
            raise AdapterError(
                "unsupported_operation",
                f"No {job.get('operation')} solver for deck tool: {hint}.",
            )
        schematic = job.get("schematic")
        if not isinstance(schematic, dict):
            raise AdapterError(
                "invalid_command", "run_connectivity needs a schematic mapping."
            )
        languages = job.get("languages", list(LANGUAGES))
        if not isinstance(languages, list) or any(
            language not in LANGUAGES for language in languages
        ):
            raise AdapterError(
                "invalid_command",
                f"languages must be a list from {list(LANGUAGES)}, "
                f"got {job.get('languages')!r}.",
            )
        return {
            "operation": job.get("operation"),
            "schematic": schematic,
            "languages": list(languages),
            "run_key": job.get("run_key"),
        }

    def execute(self, job):
        """Extract the graph, emit netlists, collect ERC findings.

        Args:
            job: Solver job with operation run_connectivity or
                run_erc plus schematic and language inputs.

        Returns:
            Native output with exit_code, findings, netlists, net
                table, counts, and a one-line log.

        Raises:
            AdapterError: invalid_command for a malformed
                schematic, plus the preflight codes (execute
                re-checks first).
        """
        checked = self.preflight(job)
        try:
            structs = prepare_netlist_structs(
                checked["schematic"], run_key=checked["run_key"]
            )
        except ConnectGraphError as exc:
            raise AdapterError("invalid_command", str(exc)) from exc
        policy = ERC_POLICY if checked["operation"] == "run_erc" else CONNECTIVITY_POLICY
        findings = erc_findings(structs.connectivity, policy=policy)
        try:
            raw = to_raw_ir(structs)
            netlists = emit_netlists(raw, languages=checked["languages"])
        except ConnectGraphError as exc:
            raise AdapterError("invalid_command", str(exc)) from exc
        nets = [net["name"] for net in raw["nets"]]
        errors = sum(1 for f in findings if f["severity"] == "error")
        return {
            "exit_code": 0,
            "operation": checked["operation"],
            "findings": findings,
            "netlists": netlists,
            "nets": nets,
            "net_count": len(nets),
            "instance_count": len(raw["instances"]),
            "skipped": raw["skipped"],
            "log": (
                f"{checked['operation']}: {len(nets)} nets, "
                f"{len(raw['instances'])} instances, {errors} errors"
            ),
        }

    def parse(self, native_output):
        """Normalize findings into violations; netlists ride measurements.

        Args:
            native_output: Native output from execute.

        Returns:
            {total, violations[]} plus measurements with netlists,
                the net table, counts, and skipped instances.

        Raises:
            AdapterError: runner_unavailable when the output has
                no findings list.
        """
        findings = native_output.get("findings")
        if not isinstance(findings, list):
            raise AdapterError(
                "runner_unavailable", "connectgraph output has no findings list."
            )
        violations = []
        for finding in findings:
            violations.append(
                {
                    "rule": finding["rule"],
                    "severity": finding["severity"],
                    "message": finding.get("message", finding["rule"]),
                    "net": finding.get("net"),
                    "net_id": finding.get("net_id"),
                }
            )
        return {
            "total": len(violations),
            "violations": violations,
            "measurements": {
                "netlists": native_output.get("netlists", {}),
                "nets": native_output.get("nets", []),
                "net_count": native_output.get("net_count", 0),
                "instance_count": native_output.get("instance_count", 0),
                "skipped": native_output.get("skipped", []),
            },
        }
