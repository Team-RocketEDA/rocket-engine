"""View-sync solver adapter: run_view_sync, no subprocess.

Pure-Python ToolAdapter over the VIEW-SYNC workflow: preflight
validates the job, execute diffs intended vs extracted through
shared CONNECT-GRAPH extraction plus CellLink identity, parse
normalizes findings and carries coverage plus the report as
measurements. Every net name flows from the cited view's shared
`Connectivity.net_name` authority.
"""

from ...interfaces import ToolAdapter
from ...workflows.viewsync import ViewSyncError, compare_views
from ..errors import AdapterError

OPERATION = "run_view_sync"
TOOL = "connectgraph"


class ViewSyncAdapter(ToolAdapter):
    """Intended-vs-extracted connectivity diff for photonic P14.

    Serves run_view_sync with deck.tool `connectgraph` (the only
    tool). Both views arrive in the job; extraction, naming, and
    the diff all run in-process — no tool to resolve, no timeout.

    Job keys:
        intended (required): Intended-view schematic record (see
            workflows.connectgraph for the shape).
        extracted (required): Extracted-view schematic record.
        links: CellLink block links correlating symbol pins to
            cell pins (default []).
        variant: Variant selector applied to every link (default
            None, the stored base link).
        deck: Optional mapping; deck.tool must be connectgraph here.

    Caution: FAIL-on-diff, PASS-with-coverage — the verdict judges
        finding severities, never the exit path; read the coverage
        statement before trusting a clean diff.
    """

    def capabilities(self, target):
        """Report the served operation and tool name.

        Args:
            target: Target the capabilities are reported for
                (accepted, unused — both views arrive per job).

        Returns:
            Capability mapping with operations and tool.
        """
        return {"operations": [OPERATION], "tool": TOOL}

    def preflight(self, job):
        """Check operation, tool hint, views, links, and variant.

        Args:
            job: Solver job with operation run_view_sync plus
                intended and extracted views with identity inputs.

        Returns:
            Checked mapping with operation, intended, extracted,
                links, and variant.

        Raises:
            AdapterError: unsupported_operation for another
                operation or deck tool, invalid_command for a
                missing view, a non-list links, or a non-string
                variant.
        """
        if job.get("operation") != OPERATION:
            raise AdapterError(
                "unsupported_operation",
                f"ViewSync handles {OPERATION}, got {job.get('operation')}.",
            )
        hint = (job.get("deck") or {}).get("tool")
        if hint is not None and hint != TOOL:
            raise AdapterError(
                "unsupported_operation",
                f"No {OPERATION} solver for deck tool: {hint}.",
            )
        intended = job.get("intended")
        if not isinstance(intended, dict):
            raise AdapterError(
                "invalid_command", "run_view_sync needs an intended mapping."
            )
        extracted = job.get("extracted")
        if not isinstance(extracted, dict):
            raise AdapterError(
                "invalid_command", "run_view_sync needs an extracted mapping."
            )
        links = job.get("links", [])
        if not isinstance(links, list):
            raise AdapterError(
                "invalid_command",
                f"links must be a list, got {job.get('links')!r}.",
            )
        variant = job.get("variant")
        if variant is not None and not isinstance(variant, str):
            raise AdapterError(
                "invalid_command",
                f"variant must be a string, got {variant!r}.",
            )
        return {
            "operation": OPERATION,
            "intended": intended,
            "extracted": extracted,
            "links": links,
            "variant": variant,
        }

    def execute(self, job):
        """Diff the job's views through shared extraction.

        Args:
            job: Solver job with operation run_view_sync plus
                intended and extracted views with identity inputs.

        Returns:
            Native output with exit_code, findings, coverage,
                report, and a one-line log.

        Raises:
            AdapterError: invalid_command for a malformed view or
                bad identity mapping, plus the preflight codes
                (execute re-checks first).
        """
        checked = self.preflight(job)
        try:
            result = compare_views(
                checked["intended"],
                checked["extracted"],
                links=checked["links"],
                variant=checked["variant"],
            )
        except ViewSyncError as exc:
            raise AdapterError("invalid_command", str(exc)) from exc
        findings = result["findings"]
        errors = sum(1 for f in findings if f["severity"] == "error")
        return {
            "exit_code": 0,
            "operation": OPERATION,
            "findings": findings,
            "coverage": result["coverage"],
            "report": result["report"],
            "log": f"{OPERATION}: {len(findings)} findings, {errors} errors",
        }

    def parse(self, native_output):
        """Normalize findings into violations; coverage rides measurements.

        Args:
            native_output: Native output from execute.

        Returns:
            {total, violations[]} plus measurements with coverage
                and the text report.

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
            violation = {
                "rule": finding["rule"],
                "severity": finding["severity"],
                "message": finding.get("message", finding["rule"]),
            }
            for key, value in finding.items():
                if key not in violation:
                    violation[key] = value
            violations.append(violation)
        return {
            "total": len(violations),
            "violations": violations,
            "measurements": {
                "coverage": native_output.get("coverage", {}),
                "report": native_output.get("report", ""),
            },
        }
