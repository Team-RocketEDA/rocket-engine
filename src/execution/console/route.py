"""Console tier-2 routing (CONSOLE-ROUTE): mutations via admission.

A console cell that edits the project is an ingredient, not exhaust:
tier-2 calls (cell add/place, wire ops, doc writes, and the sibling
project mutations) route through ProjectService admission — the
expected_revision gate, one actor-attributed ledger record per
accepted mutation, and idempotent envelope ids — using the identical
verbs and the shared ENGINE-ECS / WIRE-PLACE addressing the CRUD and
MCP paths use. The console is a client of admission, never a
side-channel writer: nothing here calls a private doc-store writer,
and the suite scans this file to keep it that way.

Two namespaces share the verb list (CONSOLE_TOOL_VERBS):
ConsoleTools records worker-side op calls in the prelude shape
(explicit wrappers naming every tier-2 verb, generic fallback for
the rest), while ConsoleNamespace executes host-side through the
matching ProjectService verbs. ECS and wire verbs fail loudly with
unsupported_operation until their peer patches land — a refused
call writes nothing and advances nothing.

Effects stay report-with-run_ids, never re-execute: collect_run_ids
lifts child run ids off replayed op results, build_effects_report
packs the shared effects shape, and report_completions reads stored
completions back by id without running anything.
"""

from ..routing.calls import (
    CELL_VERBS,
    CONSOLE_TOOL_VERBS,
    DOC_VERBS,
    ECS_VERBS,
    PROJECT_VERBS,
    TIER_2_OPERATIONS,
    WIRE_VERBS,
    admission_envelope,
    build_effects_report,
    collect_run_ids,
    entity_doc_path,
    format_address,
    is_tier2,
    parse_address,
    report_completions,
    stamp_tier2_call,
    tier_for,
    tool_call,
)
from ..routing.namespace import ConsoleNamespace
from ..routing.tools import ConsoleTools


__all__ = [
    "CELL_VERBS",
    "CONSOLE_TOOL_VERBS",
    "DOC_VERBS",
    "ECS_VERBS",
    "PROJECT_VERBS",
    "TIER_2_OPERATIONS",
    "WIRE_VERBS",
    "ConsoleNamespace",
    "ConsoleTools",
    "admission_envelope",
    "build_effects_report",
    "collect_run_ids",
    "entity_doc_path",
    "format_address",
    "is_tier2",
    "parse_address",
    "report_completions",
    "stamp_tier2_call",
    "tier_for",
    "tool_call",
]
