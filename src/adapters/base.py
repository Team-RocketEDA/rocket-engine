"""Shared transport helpers: JSON parsing and project-scope enforcement."""

import json

from .errors import AdapterError


def parse_json(text):
    try:
        data = json.loads(text)
    except Exception as exc:
        raise AdapterError("invalid_command", f"Cannot parse request: {exc}") from exc
    if not isinstance(data, dict):
        raise AdapterError("invalid_command", "Request must be a JSON object.")
    return data


def enforce_scope(envelope_project, bound_project):
    if bound_project is not None and envelope_project != bound_project:
        raise AdapterError(
            "cross_project_denied",
            f"Bound to {bound_project}, got {envelope_project}.",
        )
