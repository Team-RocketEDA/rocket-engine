"""Scoped reference resolution and connection checks (I02).

Resolution assumes a validated store: files here were accepted by
validate_document at ingestion. The scan therefore uses a plain safe
load and skips anything outside the root or unparseable.
"""

from pathlib import Path

from ruamel.yaml import YAML

from .documents import validate_document
from .errors import ContractError


def _matches(doc, ref):
    return (
        isinstance(doc, dict)
        and doc.get("scope") == ref.get("scope")
        and doc.get("id") == ref.get("id")
        and doc.get("revision") == ref.get("revision")
    )


def _scan(root):
    yaml = YAML(typ="safe")
    for path in sorted(root.rglob("*.yaml")):
        try:
            path.resolve().relative_to(root)
        except ValueError:
            continue
        try:
            doc = yaml.load(path.read_text())
        except Exception:
            continue
        if isinstance(doc, dict):
            yield doc


def resolve_reference(ref, root, path=None):
    """Resolve an exact {scope, id, revision} reference inside root."""
    root = Path(root).resolve()
    if path is not None:
        target = (root / path).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            raise ContractError(
                "invalid_reference", f"Reference escapes store root: {path}."
            ) from None
        try:
            doc = YAML(typ="safe").load(target.read_text())
        except Exception as exc:
            raise ContractError("invalid_yaml", f"Cannot load {path}: {exc}") from exc
        if _matches(doc, ref):
            return doc
        raise ContractError("invalid_reference", f"No match at path: {path}.")
    for doc in _scan(root):
        if _matches(doc, ref):
            return doc
    raise ContractError(
        "invalid_reference",
        f"Unknown reference: {ref.get('scope')}/{ref.get('id')}@{ref.get('revision')}.",
    )


def check_connection(text, endpoint_a, endpoint_b):
    """Check two endpoints for unit/port compatibility."""
    data = validate_document(text)
    ports = data.get("ports", {})

    def _wavelength_unit(endpoint):
        _, port = endpoint
        if port not in ports:
            raise ContractError("invalid_reference", f"Unknown port: {port}.")
        props = ports[port].get("properties", {})
        return props.get("wavelength", {}).get("unit")

    unit_a = _wavelength_unit(endpoint_a)
    unit_b = _wavelength_unit(endpoint_b)
    if unit_a and unit_b and unit_a != unit_b:
        raise ContractError(
            "incompatible_port",
            f"Incompatible wavelength units: {unit_a} vs {unit_b}.",
        )
    return {"compatible": True}
