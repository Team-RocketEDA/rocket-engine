"""Outbound ports: contracts the engine depends on, adapters implement."""

from abc import ABC, abstractmethod


class ToolAdapter(ABC):
    """One solver family behind four calls. No transport knowledge."""

    @abstractmethod
    def capabilities(self, target):
        """What this tool can do for the target (operations, limits)."""

    @abstractmethod
    def preflight(self, job):
        """Refuse early when inputs, deck, or environment disqualify."""

    @abstractmethod
    def execute(self, job):
        """Run the tool; return native artifacts and exit state."""

    @abstractmethod
    def parse(self, native_output):
        """Normalize native output into findings and measurements."""
