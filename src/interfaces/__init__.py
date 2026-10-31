"""Single source of truth for engine contracts: wire schemas, typed
commands, events, and outbound ports. No I/O, no logic."""

from .documents import validate_document
from .errors import ContractError
from .ports import ToolAdapter
from .references import check_connection, resolve_reference
from .runparams import (
    NETLIST_TYPES,
    RUN_REQUEST_DEFAULTS,
    RUN_REQUEST_FIELDS,
    RUN_REQUEST_SCHEMA,
    RunParamsError,
    freeze_run_request,
    parse_run_request,
    validate_run_request,
)

__all__ = [
    "NETLIST_TYPES",
    "RUN_REQUEST_DEFAULTS",
    "RUN_REQUEST_FIELDS",
    "RUN_REQUEST_SCHEMA",
    "ContractError",
    "RunParamsError",
    "ToolAdapter",
    "check_connection",
    "freeze_run_request",
    "parse_run_request",
    "resolve_reference",
    "validate_document",
    "validate_run_request",
]
