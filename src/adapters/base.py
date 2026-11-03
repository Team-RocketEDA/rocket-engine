"""Shared transport helpers: JSON parsing and project-scope enforcement."""

import json

from .errors import AdapterError


def parse_json(text):
    """Parse one JSON object request; reject anything else loudly.

    Args:
        text: Raw request text, expected to be one JSON object.

    Returns:
        Parsed request mapping.

    Raises:
        AdapterError: invalid_command when the text is not JSON or
            not an object.
    """
    try:
        data = json.loads(text)
    except Exception as exc:
        raise AdapterError("invalid_command", f"Cannot parse request: {exc}") from exc
    if not isinstance(data, dict):
        raise AdapterError("invalid_command", "Request must be a JSON object.")
    return data


def enforce_scope(envelope_project, bound_project):
    """Deny envelopes outside the bound project; allow unbound use.

    Args:
        envelope_project: Project id carried by the envelope.
        bound_project: Project this transport is bound to, or None
            for unbound (any envelope passes).

    Raises:
        AdapterError: cross_project_denied for an envelope outside
            the bound scope — denied, never routed.
    """
    if bound_project is not None and envelope_project != bound_project:
        raise AdapterError(
            "cross_project_denied",
            f"Bound to {bound_project}, got {envelope_project}.",
        )
