"""Resolve registry blocks against the rocket-blocks layout.

The rocket-blocks repo holds one directory per PDK, each with
one entry folder per prebuilt IP block::

    <root>/<pdk>/<entry>/rocket/meta.yaml

Resolution is per-PDK by construction: the PDK names the
top-level directory, so a block registered under ``sky130``
can only ever resolve inside ``<root>/sky130/``. Names that
try to leave that directory (separators, ``..``, absolute
paths) are refused before any filesystem touch, and entry
folder names must be catalogue slugs (lowercase-with-dashes).

The entry contract itself lives in ``entry.schema.json`` (a
byte-identical copy of
``contracts/v1/schemas/ip-entry.schema.json``, which is the
single source). Every resolved entry is verified against that
schema at runtime: found-but-nonconforming entries fail loudly
instead of resolving.
"""

import json
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator
from jsonschema import FormatChecker

from ...interfaces.errors import ContractError

#: Entry metadata path under a block folder.
META_PARTS = ("rocket", "meta.yaml")

#: Catalogue entry folders are lowercase-with-dashes slugs.
_SLUG_RE = r"[a-z0-9]+(?:-[a-z0-9]+)*"

#: Root export id prefixing intra-bundle references.
_ROOT_ID = "urn:rocketeda:engine:v1"


def _need_name(value, what, code):
    """Accept one clean, non-escaping segment or raise the code."""
    if not isinstance(value, str) or not value:
        raise ContractError(code, f"{what} must be non-empty text.")
    if value in (".", "..") or "/" in value or "\\" in value:
        raise ContractError(
            code, f"{what} must be one path segment, got {value!r}."
        )
    if Path(value).is_absolute():
        raise ContractError(
            code, f"{what} must be relative, got {value!r}."
        )
    return value


def _load_entry_schema():
    """Read the bundled entry contract (single source copy)."""
    path = Path(__file__).with_name("entry.schema.json")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ContractError(
            "unknown_ip",
            f"IP entry contract unreadable: {path.name}.",
        ) from exc


def _inline_root_refs(node, defs):
    """Inline intra-bundle urn refs so the module stands alone."""
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith(_ROOT_ID + "#/$defs/"):
            name = ref.rsplit("/", 1)[1]
            try:
                target = defs[name]
            except KeyError:
                raise ContractError(
                    "unknown_ip",
                    f"IP entry contract references unknown {name}.",
                ) from None
            return _inline_root_refs(target, defs)
        return {
            key: _inline_root_refs(value, defs)
            for key, value in node.items()
        }
    if isinstance(node, list):
        return [_inline_root_refs(item, defs) for item in node]
    return node


def _entry_validator():
    """Build the runtime validator for IpEntry mappings."""
    module = _load_entry_schema()
    defs = module.get("$defs", {})
    try:
        entry_schema = _inline_root_refs(defs["IpEntry"], defs)
    except KeyError:
        raise ContractError(
            "unknown_ip", "IP entry contract has no IpEntry."
        ) from None
    return Draft202012Validator(
        entry_schema, format_checker=FormatChecker())


def _check_entry(meta_path, meta, name, version):
    """Refuse found-but-nonconforming entries loudly."""
    if not isinstance(meta, dict):
        raise ContractError(
            "invalid_ip",
            f"IP block metadata malformed: {meta_path}.",
        )
    for error in _entry_validator().iter_errors(meta):
        raise ContractError(
            "invalid_ip",
            f"IP block metadata invalid "
            f"({'/'.join(str(part) for part in error.path) or 'entry'}): "
            f"{error.message}.",
        ) from None
    if meta.get("name") != name:
        raise ContractError(
            "invalid_ip",
            f"IP block metadata names {meta.get('name')!r}, "
            f"addressed {name!r}.",
        )
    declared = meta.get("version")
    if version is not None and declared != version:
        raise ContractError(
            "invalid_ip",
            f"No such IP block version: {name}@{version}.",
        )
    return declared if declared is not None else version


def resolve_block_ref(blocks_root, pdk, name, version=None):
    """Map a registry (pdk, name[, version]) to a blocks entry.

    Args:
        blocks_root: rocket-blocks checkout root directory.
        pdk: Owning PDK id; selects the ``<root>/<pdk>/`` scope.
        name: Catalogue slug naming the entry folder.
        version: Revision label, or None to accept whatever the
            entry metadata declares.

    Returns:
        Mapping with pdk, name, entry (directory text), version,
            and meta (the parsed ``rocket/meta.yaml`` mapping).

    Raises:
        ContractError: invalid_reference for a segment that
            would escape the PDK scope or breaks the catalogue
            slug rule; unknown_ip when the entry or its metadata
            is missing; invalid_ip when the entry is found but
            nonconforming (schema violation, name/version
            disagreement, or an unprovenanced wrapped checkout).
    """
    import re

    clean_pdk = _need_name(pdk, "IP pdk", "invalid_reference")
    clean_name = _need_name(name, "IP block name", "invalid_reference")
    if not re.fullmatch(_SLUG_RE, clean_name):
        raise ContractError(
            "invalid_reference",
            f"IP block name must be a catalogue slug "
            f"(lowercase-with-dashes), got {clean_name!r}.",
        )
    entry = Path(blocks_root) / clean_pdk / clean_name
    meta_path = entry.joinpath(*META_PARTS)
    if not meta_path.is_file():
        raise ContractError(
            "unknown_ip",
            f"No such IP block entry: {clean_pdk}/{clean_name}.",
        )
    try:
        meta = yaml.safe_load(meta_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ContractError(
            "unknown_ip",
            f"IP block entry unreadable: {clean_pdk}/{clean_name}.",
        ) from exc
    resolved_version = _check_entry(
        f"{clean_pdk}/{clean_name}", meta, clean_name, version)
    if (entry / "entry_repo").exists() and not meta.get("upstream"):
        raise ContractError(
            "invalid_ip",
            f"IP block wraps a nested checkout without upstream "
            f"provenance: {clean_pdk}/{clean_name}.",
        )
    return {
        "pdk": clean_pdk,
        "name": clean_name,
        "entry": str(entry),
        "version": resolved_version,
        "meta": meta,
    }
