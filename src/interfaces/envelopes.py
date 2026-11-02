"""v0 envelope contracts: the typed shapes of the v0 wire.

SubmitCommand, SubmitAck, EngineEvent, FindingPage, Finding, and
ErrorPayload are the data contracts every gateway speaks today.
They live here (contracts, no I/O) so gateways, generators, and
tests share one definition instead of re-declaring the shapes.

V0_TO_V1_FIELDS maps each envelope's v0 field names to the v1
catalog names (contracts/generated/engine-v1.expanded.schema.json;
v1 design-frozen, runtime migration pending). None marks a field
v1 restructures rather than renames — the migration owns those,
never a silent repurpose. Identity entries document that the name
survives the migration.
"""

from typing import Any, Dict, List, Optional, TypedDict


class SubmitCommand(TypedDict, total=False):
    """One admitted call: who, what, with what, under which id."""

    project_id: str
    operation: str
    arguments: Dict[str, Any]
    request_id: str


class SubmitAck(TypedDict, total=False):
    """Admission ack: the execution id plus where it admitted."""

    run_id: str
    snapshot_id: str
    state: str
    approval_state: str
    approval_id: str
    execution_id: str


class EngineEvent(TypedDict, total=False):
    """One retained project event, seq-ordered by cursor."""

    seq: int
    type: str
    actor: str
    data: Dict[str, Any]
    revision: str
    event_cursor: int


class Finding(TypedDict, total=False):
    """One judged violation or observation on a completed run."""

    rule: str
    severity: str
    message: str
    target: str


class FindingPage(TypedDict, total=False):
    """One page of findings, errors first, with counts and cursor."""

    total_counts: Dict[str, int]
    findings: List[Finding]
    next_cursor: Optional[str]
    truncated: bool


class ErrorPayload(TypedDict, total=False):
    """Wire error: stable code, message, itemized fields when named."""

    code: str
    message: str
    fields: List[str]


#: v0 envelope -> {v0 field: v1 field or None when restructured}.
V0_TO_V1_FIELDS = {
    "SubmitCommand": {
        "project_id": "project_id",
        "operation": "task",
        "arguments": "options",
        "request_id": "request_id",
    },
    "SubmitAck": {
        "run_id": "run_id",
        "snapshot_id": "snapshot",
        "state": "state",
        "approval_state": None,
        "approval_id": None,
        "execution_id": None,
    },
    "EngineEvent": {
        "seq": None,
        "type": None,
        "actor": "actor",
        "data": "data",
        "revision": None,
        "event_cursor": "event_cursor",
    },
    "Finding": {
        "rule": "rule",
        "severity": "severity",
        "message": "message",
        "target": "target",
    },
    "FindingPage": {
        "total_counts": None,
        "findings": "findings",
        "next_cursor": "cursor",
        "truncated": None,
    },
    "ErrorPayload": {
        "code": "code",
        "message": "message",
        "fields": "details",
    },
}


def v1_field(envelope, v0_field):
    """v1 name for one v0 envelope field, None when restructured.

    Args:
        envelope: Envelope name (SubmitCommand, SubmitAck,
            EngineEvent, Finding, FindingPage, ErrorPayload).
        v0_field: v0 field name.

    Returns:
        v1 field name, or None where v1 restructures the field.
    """
    return V0_TO_V1_FIELDS[envelope][v0_field]
