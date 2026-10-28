"""Strict YAML 1.2 validation (I01). Gate every external byte here."""

import math

from ruamel.yaml import YAML

from .errors import ContractError

MAX_DOCUMENT_BYTES = 1_000_000
MAX_NESTING_DEPTH = 100

REQUIRED_TOP_LEVEL = ("schema", "kind", "id", "revision", "scope", "description")
ALLOWED_TOP_LEVEL = frozenset(
    {
        "schema", "kind", "id", "revision", "scope", "description",
        "domains", "ports", "parameters", "models", "top", "pdks",
        "constraints", "schematic", "layout", "symbol", "source",
        "objects", "cross_sections", "files", "decks", "license",
        "origin", "tags",
    }
)


def _reject_composition_tricks(node):
    """Anchors, aliases, and merge keys are forbidden (I01)."""
    if type(node).__name__ == "AliasNode" or getattr(node, "anchor", None):
        raise ContractError("invalid_yaml", "Anchors and aliases are not allowed.")
    value = getattr(node, "value", None)
    if isinstance(value, list) and value and isinstance(value[0], tuple):
        for key, item in value:
            if getattr(key, "value", None) == "<<":
                raise ContractError("invalid_yaml", "Merge keys are not allowed.")
            _reject_composition_tricks(key)
            _reject_composition_tricks(item)
    elif isinstance(value, list):
        for item in value:
            _reject_composition_tricks(item)


def _reject_nonfinite_and_depth(data, depth=0):
    if depth > MAX_NESTING_DEPTH:
        raise ContractError("invalid_yaml", "Document nesting exceeds the limit.")
    if isinstance(data, float) and (math.isnan(data) or math.isinf(data)):
        raise ContractError("invalid_yaml", "Non-finite scalars are not allowed.")
    if isinstance(data, dict):
        for item in data.values():
            _reject_nonfinite_and_depth(item, depth + 1)
    elif isinstance(data, list):
        for item in data:
            _reject_nonfinite_and_depth(item, depth + 1)


def validate_document(text):
    """Parse and strictly validate one YAML record. Returns the mapping."""
    if not isinstance(text, str):
        raise ContractError("invalid_yaml", "Document must be text.")
    if len(text.encode("utf-8")) > MAX_DOCUMENT_BYTES:
        raise ContractError("invalid_yaml", "Document exceeds the size limit.")
    yaml = YAML(typ="safe")
    try:
        node = yaml.compose(text)
    except Exception as exc:
        raise ContractError("invalid_yaml", f"YAML composition failed: {exc}") from exc
    _reject_composition_tricks(node)
    try:
        data = yaml.load(text)
    except Exception as exc:
        raise ContractError("invalid_yaml", f"YAML load failed: {exc}") from exc
    if not isinstance(data, dict):
        raise ContractError("invalid_yaml", "Top level must be a mapping.")
    for key in REQUIRED_TOP_LEVEL:
        if key not in data:
            raise ContractError("invalid_yaml", f"Missing required field: {key}.")
    for key in data:
        if key not in ALLOWED_TOP_LEVEL:
            raise ContractError("invalid_yaml", f"Unknown field: {key}.")
    _reject_nonfinite_and_depth(data)
    return data
