"""Single source of truth for engine contracts: wire schemas, typed
commands, events, and outbound ports. No I/O, no logic."""

from .documents import validate_document
from .errors import ContractError
from .references import check_connection, resolve_reference

__all__ = ["ContractError", "check_connection", "resolve_reference", "validate_document"]
