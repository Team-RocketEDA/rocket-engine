"""Outbound ports: contracts the engine depends on, adapters implement."""

from abc import ABC, abstractmethod


class ToolAdapter(ABC):
    """One solver family behind four calls. No transport knowledge."""

    @abstractmethod
    def capabilities(self, target):
        """What this tool can do for the target (operations, limits).

        Args:
            target: Target the capabilities are reported for.

        Returns:
            Capability mapping naming the served operations.
        """

    @abstractmethod
    def preflight(self, job):
        """Refuse early when inputs, deck, or environment disqualify.

        Args:
            job: Solver job mapping (operation plus tool inputs).

        Returns:
            Checked job inputs the execute call runs with.

        Raises:
            AdapterError: Implementations raise stable codes
                (unsupported_operation, missing_dependency,
                invalid_reference, invalid_command) — never a
                silent pass.
        """

    @abstractmethod
    def execute(self, job):
        """Run the tool; return native artifacts and exit state.

        Args:
            job: Solver job mapping (operation plus tool inputs).

        Returns:
            Native output mapping with exit state and artifacts.

        Raises:
            AdapterError: Implementations raise stable codes
                (runner_unavailable, missing_dependency,
                invalid_reference) — never a faked result.
        """

    @abstractmethod
    def parse(self, native_output):
        """Normalize native output into findings and measurements.

        Violation convention: rule/severity/message plus FLAT location
        keys (file/line/col/sim_time/bbox/bbox_um/area). run() nests
        them into finding.location; nested location dicts are ignored.

        Args:
            native_output: Native output mapping from execute.

        Returns:
            Normalized result with total, violations, and any
            measurements.

        Raises:
            AdapterError: Implementations raise runner_unavailable
                when the output carries no parseable verdict —
                unparseable never parses as clean.
        """
