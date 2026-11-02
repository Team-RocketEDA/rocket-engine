"""Error type for adapter violations. Carries a stable machine code.

The v0->v1 code table lives here too: every v0 engine code maps to
its v1 catalog code (or None where v1 has no counterpart) plus the
HTTP status the transports serve. Statuses for mapped codes follow
contracts/v1/catalog/errors.json exactly (RULING-02: v1 wins); the
parity test pins that. Emitted payloads keep the v0 code — fidelity
to what the engine raised — while the status comes from this table.
"""


class AdapterError(Exception):
    """Adapter violation with a stable machine code.

    Args:
        code: Stable machine-readable error code.
        message: Human-readable detail.
        fields: Itemized fields, when the error names any.
    """

    def __init__(self, code, message, fields=None):
        super().__init__(message)
        self.code = code
        self.fields = fields or []


#: v0 code -> (v1 catalog code or None, HTTP status). None marks a
#: v0-only row: no v1 counterpart exists, so the v0 code is served
#: with the tabled status. Unknown codes default to 400 with the
#: v0 code kept — stable engine codes are client-caused; uncoded
#: crashes are 500s handled separately, never through this table.
_CODE_TABLE = {
    # Approvals: run-state conflicts.
    "approval_denied": ("invalid_run_state", 409),
    "approval_expired": ("invalid_run_state", 409),
    "approval_forbidden": ("invalid_run_state", 409),
    "approval_invalid": ("invalid_run_state", 409),
    "approval_pending": ("invalid_run_state", 409),
    # Conflicts.
    "request_conflict": ("request_conflict", 409),
    "resync_required": ("read_set_incomplete", 409),
    "revision_conflict": ("revision_conflict", 409),
    "console_busy": ("request_conflict", 409),
    "coalesced_run_lost": ("request_conflict", 409),
    # Duplicates.
    "component_exists": ("duplicate_configuration", 422),
    "project_exists": ("duplicate_configuration", 422),
    # Capabilities and runtime.
    "missing_dependency": ("capability_unavailable", 422),
    "isolation_unavailable": ("runtime_unavailable", 503),
    "runner_unavailable": ("runtime_unavailable", 503),
    # Malformed input.
    "invalid_address": ("invalid_request", 400),
    "invalid_arguments": ("invalid_request", 400),
    "invalid_cell": ("invalid_request", 400),
    "invalid_command": ("invalid_request", 400),
    "invalid_component": ("invalid_request", 400),
    "invalid_data": ("invalid_request", 400),
    "invalid_document": ("invalid_request", 400),
    "invalid_entity": ("invalid_request", 400),
    "invalid_kind": ("invalid_request", 400),
    "invalid_ledger": ("invalid_request", 400),
    "invalid_path": ("invalid_request", 400),
    "invalid_policy": ("invalid_request", 400),
    "invalid_predicate": ("invalid_request", 400),
    "invalid_project": ("invalid_request", 400),
    "invalid_reference": ("invalid_request", 400),
    "invalid_run_param": ("invalid_request", 400),
    "invalid_run_request": ("invalid_request", 400),
    "invalid_schema": ("invalid_request", 400),
    "invalid_yaml": ("invalid_request", 400),
    "unknown_run_param": ("invalid_request", 400),
    "type_mismatch": ("invalid_request", 400),
    "empty_cell": ("invalid_request", 400),
    "empty_entry": ("invalid_request", 400),
    "empty_policy": ("invalid_request", 400),
    "future_format": ("invalid_request", 400),
    "gitignore_mismatch": ("invalid_request", 400),
    "batch_unreadable": ("invalid_request", 400),
    "cell_unreadable": ("invalid_request", 400),
    "path_escape": ("invalid_request", 400),
    # Unknown ids.
    "not_found": ("not_found", 404),
    "missing_entry": ("not_found", 404),
    "missing_policy": ("not_found", 404),
    "unknown_cell": ("not_found", 404),
    "unknown_component": ("not_found", 404),
    "unknown_document": ("not_found", 404),
    "unknown_entity": ("not_found", 404),
    "unknown_request": ("not_found", 404),
    "unknown_revision": ("not_found", 404),
    "unknown_run": ("not_found", 404),
    "unknown_topic": ("not_found", 404),
    # Unsupported (semantic, not malformed).
    "unsupported_operation": ("unknown_task", 422),
    "unsupported_version": ("unknown_task", 422),
    # v0-only rows: no v1 counterpart; status is the contract.
    "cross_project_denied": (None, 403),
    "cross_origin_denied": (None, 403),
    "backfill_readonly": (None, 403),
    "pool_full": (None, 429),
    "server_busy": (None, 503),
    "body_too_large": (None, 413),
    "unsupported_media_type": (None, 415),
    "method_not_allowed": (None, 405),
    "credential_revoked": (None, 500),
    "credential_unknown": (None, 500),
    "non_loopback_bind_denied": (None, 500),
    "internal_error": ("internal_error", 500),
}

#: v0 code -> v1 catalog code (None where v1 has no counterpart).
V0_TO_V1 = {code: v1 for code, (v1, _) in _CODE_TABLE.items()}

#: Codes that ask the client to back off (served with Retry-After).
_RETRYABLE = frozenset({"pool_full", "server_busy"})


def status_for_code(code):
    """HTTP status for one v0 error code.

    Args:
        code: Stable v0 error code.

    Returns:
        Tabled status, or 400 for an unlisted code (the code is
        still emitted — the table has a gap, not the engine).
    """
    return _CODE_TABLE.get(code, (None, 400))[1]


def v1_for_code(code):
    """v1 catalog code for one v0 error code, if one exists.

    Args:
        code: Stable v0 error code.

    Returns:
        v1 code, or None where v1 has no counterpart.
    """
    return _CODE_TABLE.get(code, (None, 400))[0]


def retry_after_for(code, seconds):
    """Retry-After value for one v0 code, when the client must wait.

    Args:
        code: Stable v0 error code.
        seconds: Backoff the transport advertises.

    Returns:
        Seconds as a string for pool_full/server_busy, else None.
    """
    if code in _RETRYABLE:
        return str(seconds)
    return None


def error_payload(exc):
    """Wire payload for one failure: code + message + fields.

    Coded engine errors serialize untouched (fields only when the
    error names any); uncoded crashes become a generic internal
    error — raw exception text never crosses the wire.

    Args:
        exc: Raised failure.

    Returns:
        Mapping with code and message, plus fields when present.
    """
    code = getattr(exc, "code", None)
    if code is None:
        return {"code": "internal_error",
                "message": "Internal engine error."}
    payload = {"code": code, "message": str(exc) or code}
    fields = getattr(exc, "fields", None)
    if fields:
        payload["fields"] = list(fields)
    return payload
