"""Symbol-to-cell linkage contract (CELL-LINK).

A custom block is useless until its schematic symbol binds the
layout cell that implements it. The CellLink component is that
binding, stored on the Block entity alongside SymbolRef, with
KiCad's symbol-to-footprint relationship as the model: the link
is plain text on the symbol, filters are advisory, and variants
alter resolution, never storage.

Schema (all edit-time validated by validate_celllink, which never
checks cell existence — an unknown cell is a run error, never an
edit error):

- ``cell``: opaque ``"pdklib:cell"`` string (KiCad LIB_ID analog).
  Missing or empty means unlinked; run/export skips such blocks.
- ``pinMap``: ordered explicit ``[{symPin, cellPin}]`` list. Pins
  absent from the map resolve to themselves (identity default);
  each symbol pin names a single target (no fanout).
- ``cellFilters``: advisory ``[glob, ...]`` list with KiCad
  chooser semantics, consulted by the cell picker only.
- ``variantOverrides``: ``{name: {cell?, pinEdits?}}`` sparse
  differentials. The stored link itself is the one default
  variant (``variant=None``); ``REFERENCE`` always resolves it.

Resolution has one chokepoint per question — resolve_pin,
resolve_cell, resolve_link — and one run/export entry point,
resolve_run, which emits ``(cell, pinMap, variant)`` per block
instance only when the resolved cell is non-empty.
"""

import re

from .errors import ContractError

#: Reserved variant selector resolving the stored base link. It can
#: never name an override: the reference stays immutable no matter
#: which variants a link carries.
REFERENCE = "REFERENCE"

_LINK_KEYS = frozenset({"cell", "pinMap", "cellFilters", "variantOverrides"})
_PIN_KEYS = frozenset({"symPin", "cellPin"})
_OVERRIDE_KEYS = frozenset({"cell", "pinEdits"})

__all__ = [
    "REFERENCE",
    "CellLinkError",
    "collect_erc",
    "match_cell_filters",
    "resolve_cell",
    "resolve_link",
    "resolve_pin",
    "resolve_run",
    "validate_celllink",
]


class CellLinkError(Exception):
    """Cell-link run failure with a stable machine code.

    Raised when a stored link cannot run — the cell it names is
    unknown — never at edit time. Editing stays free; the run
    names the block and the cell so the fix is mechanical.

    Args:
        code: Stable machine-readable error code.
        message: Human-readable detail.
        fields: Itemized fields, when the error names any.
    """

    def __init__(self, code, message, fields=None):
        super().__init__(message)
        self.code = code
        self.fields = fields or []


def _need_str(value, what):
    if not isinstance(value, str):
        raise ContractError(
            "invalid_celllink", f"{what} must be a string, got {value!r}."
        )
    return value


def _need_nonempty_str(value, what):
    _need_str(value, what)
    if not value:
        raise ContractError("invalid_celllink", f"{what} must not be empty.")
    return value


def validate_celllink(link):
    """Validate a CellLink component mapping at edit time.

    Checks shape only — key sets, string types, single-target
    pins, well-formed overrides — and returns a normalized copy
    with defaults filled. Cell existence is never checked here:
    any cell text, however unknown, passes validation.

    Args:
        link: CellLink mapping with cell, pinMap, cellFilters,
            and variantOverrides keys.

    Returns:
        Normalized CellLink copy (defaults filled, storage
        untouched).

    Raises:
        ContractError: invalid_celllink for any shape violation.
    """
    if not isinstance(link, dict):
        raise ContractError(
            "invalid_celllink", f"CellLink must be a mapping, got {link!r}."
        )
    for key in link:
        if key not in _LINK_KEYS:
            raise ContractError("invalid_celllink", f"Unknown CellLink key: {key}.")
    cell = _need_str(link.get("cell", ""), "cell")
    pin_map = link.get("pinMap", [])
    if not isinstance(pin_map, list):
        raise ContractError("invalid_celllink", "pinMap must be a list.")
    seen = set()
    clean_pins = []
    for entry in pin_map:
        if not isinstance(entry, dict):
            raise ContractError(
                "invalid_celllink", f"pinMap entries must be mappings, got {entry!r}."
            )
        for key in entry:
            if key not in _PIN_KEYS:
                raise ContractError(
                    "invalid_celllink", f"Unknown pinMap key: {key}."
                )
        sym_pin = _need_nonempty_str(entry.get("symPin"), "symPin")
        cell_pin = _need_nonempty_str(entry.get("cellPin"), "cellPin")
        if sym_pin in seen:
            raise ContractError(
                "invalid_celllink",
                f"symPin {sym_pin!r} names more than one target.",
            )
        seen.add(sym_pin)
        clean_pins.append({"symPin": sym_pin, "cellPin": cell_pin})
    filters = link.get("cellFilters", [])
    if not isinstance(filters, list):
        raise ContractError("invalid_celllink", "cellFilters must be a list.")
    for pattern in filters:
        _need_str(pattern, "cellFilters entry")
    overrides = link.get("variantOverrides", {})
    if not isinstance(overrides, dict):
        raise ContractError("invalid_celllink", "variantOverrides must be a mapping.")
    clean_overrides = {}
    for name, override in overrides.items():
        _need_nonempty_str(name, "variant name")
        if name == REFERENCE:
            raise ContractError(
                "invalid_celllink",
                f"Variant {REFERENCE!r} is reserved for the stored base link.",
            )
        if not isinstance(override, dict):
            raise ContractError(
                "invalid_celllink", f"Variant {name!r} must be a mapping."
            )
        for key in override:
            if key not in _OVERRIDE_KEYS:
                raise ContractError(
                    "invalid_celllink", f"Unknown variant key: {key}."
                )
        clean = {}
        if "cell" in override:
            clean["cell"] = _need_nonempty_str(
                override["cell"], f"variant {name!r} cell"
            )
        pin_edits = override.get("pinEdits", {})
        if not isinstance(pin_edits, dict):
            raise ContractError(
                "invalid_celllink", f"Variant {name!r} pinEdits must be a mapping."
            )
        clean_edits = {}
        for sym_pin, cell_pin in pin_edits.items():
            _need_nonempty_str(sym_pin, f"variant {name!r} symPin")
            _need_nonempty_str(cell_pin, f"variant {name!r} cellPin")
            clean_edits[sym_pin] = cell_pin
        clean["pinEdits"] = clean_edits
        clean_overrides[name] = clean
    return {
        "cell": cell,
        "pinMap": clean_pins,
        "cellFilters": list(filters),
        "variantOverrides": clean_overrides,
    }


def _block_link(block):
    if not isinstance(block, dict):
        raise ContractError(
            "invalid_celllink", f"Block must be a mapping, got {block!r}."
        )
    link = block.get("CellLink", {})
    return validate_celllink(link)


def _override_for(link, variant):
    if variant is None or variant == REFERENCE:
        return None
    if not isinstance(variant, str) or not variant:
        raise ContractError(
            "unknown_variant", f"Variant must be a non-empty string, got {variant!r}."
        )
    try:
        return link["variantOverrides"][variant]
    except KeyError:
        known = sorted(link["variantOverrides"])
        raise ContractError(
            "unknown_variant",
            f"Unknown variant {variant!r}; known variants: {known}.",
        ) from None


def _effective_pin_map(link, override):
    effective = {entry["symPin"]: entry["cellPin"] for entry in link["pinMap"]}
    if override is not None:
        effective.update(override["pinEdits"])
    ordered = []
    for entry in link["pinMap"]:
        ordered.append(
            {"symPin": entry["symPin"], "cellPin": effective[entry["symPin"]]}
        )
    base_pins = {entry["symPin"] for entry in link["pinMap"]}
    for sym_pin in sorted(effective):
        if sym_pin not in base_pins:
            ordered.append({"symPin": sym_pin, "cellPin": effective[sym_pin]})
    return ordered


def resolve_pin(block, sym_pin, variant=None):
    """Resolve one symbol pin to its cell pin (the pin chokepoint).

    Explicit pinMap entries win, variant pinEdits overlay them,
    and unlisted pins resolve to themselves (identity default).
    A block without a CellLink resolves every pin to itself.

    Args:
        block: Block mapping carrying the CellLink component.
        sym_pin: Symbol pin to resolve.
        variant: Variant name selecting its overrides; None and
            REFERENCE resolve the stored base link.

    Returns:
        Resolved cell-pin name.

    Raises:
        ContractError: invalid_celllink for a malformed block or
            link, unknown_variant for a variant the link does not
            define.
    """
    _need_nonempty_str(sym_pin, "sym_pin")
    link = _block_link(block)
    override = _override_for(link, variant)
    if override is not None and sym_pin in override["pinEdits"]:
        return override["pinEdits"][sym_pin]
    for entry in link["pinMap"]:
        if entry["symPin"] == sym_pin:
            return entry["cellPin"]
    return sym_pin


def resolve_cell(block, variant=None):
    """Resolve the cell implementing a block under a variant.

    Args:
        block: Block mapping carrying the CellLink component.
        variant: Variant name selecting its overrides; None and
            REFERENCE resolve the stored base link.

    Returns:
        Effective cell text ("" when the block is unlinked).

    Raises:
        ContractError: invalid_celllink for a malformed block or
            link, unknown_variant for a variant the link does not
            define.
    """
    link = _block_link(block)
    override = _override_for(link, variant)
    if override is not None and "cell" in override:
        return override["cell"]
    return link["cell"]


def resolve_link(block, variant=None):
    """Resolve the full (cell, pinMap, variant) link for a block.

    The variant selector echoes through verbatim so run/export
    records cite which resolution they carry. Resolution copies:
    the stored link is never mutated.

    Args:
        block: Block mapping carrying the CellLink component.
        variant: Variant name selecting its overrides; None and
            REFERENCE resolve the stored base link.

    Returns:
        Mapping with the effective cell, the ordered effective
        pinMap (base order kept, edits applied in place, added
        pins appended sorted), and the variant selector.

    Raises:
        ContractError: invalid_celllink for a malformed block or
            link, unknown_variant for a variant the link does not
            define.
    """
    link = _block_link(block)
    override = _override_for(link, variant)
    cell = link["cell"]
    if override is not None and "cell" in override:
        cell = override["cell"]
    return {
        "cell": cell,
        "pinMap": _effective_pin_map(link, override),
        "variant": variant,
    }


def _wildcard_to_regex(pattern):
    parts = []
    for char in pattern:
        if char == "*":
            parts.append(".*")
        elif char == "?":
            parts.append(".")
        else:
            parts.append(re.escape(char))
    return "".join(parts)


def _match_part(pattern, text):
    return (
        re.fullmatch(_wildcard_to_regex(pattern), text, flags=re.IGNORECASE)
        is not None
    )


def match_cell_filters(cell, filters):
    """Match a cell against advisory KiCad chooser filters.

    Empty filters match everything; otherwise entries combine
    with OR. Matching is case-insensitive and anchored (a bare
    word is not a substring — say ``*word*``). ``:`` splits the
    library from the cell: a pattern without a library part
    matches the cell part only, while ``lib:cell`` requires both
    halves to match. Spaces sanitize to ``_`` on both sides.

    Args:
        cell: Opaque cell text to test.
        filters: Advisory glob list from the CellLink.

    Returns:
        True when the cell passes the chooser filters.

    Raises:
        ContractError: invalid_celllink for a non-string cell or
            a malformed filter list.
    """
    _need_str(cell, "cell")
    if not isinstance(filters, list):
        raise ContractError("invalid_celllink", "cellFilters must be a list.")
    if not filters:
        return True
    candidate = cell.replace(" ", "_")
    cand_lib, _, cand_cell = candidate.partition(":")
    if ":" not in candidate:
        cand_lib, cand_cell = "", candidate
    for pattern in filters:
        _need_str(pattern, "cellFilters entry")
        scrubbed = pattern.replace(" ", "_")
        if ":" in scrubbed:
            pat_lib, _, pat_cell = scrubbed.partition(":")
            if _match_part(pat_lib, cand_lib) and _match_part(pat_cell, cand_cell):
                return True
        elif _match_part(scrubbed, cand_cell):
            return True
    return False


def collect_erc(link):
    """Collect the ERC view of a link: cell text plus filters.

    ERC checks read this; they never enforce it — collection
    reports unknown cells and filters as-is instead of failing.

    Args:
        link: CellLink mapping to collect from.

    Returns:
        Mapping with the cell text and the advisory filters.

    Raises:
        ContractError: invalid_celllink for a malformed link.
    """
    clean = validate_celllink(link)
    return {"cell": clean["cell"], "filters": clean["cellFilters"]}


def resolve_run(blocks, known_cells, variant=None):
    """Resolve run/export records for block instances.

    Resolves ``(cell, pinMap, variant)`` per block and emits only
    the non-empty links: blocks without a CellLink, or with an
    empty cell, are skipped. A resolved cell outside known_cells
    fails the run with a named reason — never at edit time.

    Args:
        blocks: Block mappings, each with an id and an optional
            CellLink component.
        known_cells: Available cell names the run may target.
        variant: Variant name applied to every block; None and
            REFERENCE resolve each stored base link.

    Returns:
        Emission records in input order, each with block, cell,
        pinMap, and variant keys.

    Raises:
        ContractError: invalid_block for a malformed block
            entry, unknown_variant for a variant a link does not
            define.
        CellLinkError: unknown_cell naming the block and cell
            when a resolved cell is not available to the run.
    """
    if not isinstance(blocks, (list, tuple)):
        raise ContractError("invalid_block", "Blocks must be a list.")
    available = set(known_cells)
    records = []
    for block in blocks:
        if not isinstance(block, dict):
            raise ContractError(
                "invalid_block", f"Block must be a mapping, got {block!r}."
            )
        block_id = block.get("id")
        if not isinstance(block_id, str) or not block_id:
            raise ContractError(
                "invalid_block", "Each block needs a non-empty string id."
            )
        resolved = resolve_link(block, variant=variant)
        if not resolved["cell"]:
            continue
        if resolved["cell"] not in available:
            raise CellLinkError(
                "unknown_cell",
                f"Block {block_id!r} links unknown cell "
                f"{resolved['cell']!r} (variant {variant!r}); "
                "link it to an available cell and rerun.",
            )
        records.append(
            {
                "block": block_id,
                "cell": resolved["cell"],
                "pinMap": resolved["pinMap"],
                "variant": resolved["variant"],
            }
        )
    return records
