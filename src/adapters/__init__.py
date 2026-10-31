"""One duplex adapter per channel: transports and solver wrappers.
Maps at the edge; holds no rules, state, or verdicts."""

from ..interfaces import ToolAdapter
from .errors import AdapterError

__all__ = ["AdapterError", "ToolAdapter"]
