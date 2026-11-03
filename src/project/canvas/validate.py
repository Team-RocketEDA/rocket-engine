"""Canvas loading, validation, closure hashing, and emission.

A validated canvas is the design intent the compiler (COMPILE
slice) consumes: this module proves the file exists, is
versioned, names only known metrics and knobs with checked
units, pins its PDK revisions, and hashes its delegated content
into the run closure. Anything violating a rule fails loudly
naming the rule and the section — never silent, never a merge.

Seam: `load_project_canvas` reads and validates the project
`canvas.toml` but does not hook project creation or submit
validation — the adapt lane wires those call sites (and the I28
run closure) through `validate_canvas`/`canvas_closure`. The
`[meta]` section from early ticket prose is superseded by the
frozen contract: `technology`/`pdks` carry the revision pin, and
unknown top-level sections are rejected.
"""

import hashlib
import json
import math
import tomllib
from pathlib import Path, PurePosixPath

from ...interfaces.paths import PathError, join_contained
from .schema import (
    GENERIC_TOOL_KNOBS,
    HDL_LANGUAGES,
    KNOWN_METRICS,
    KNOWN_UNITS,
    OPERATORS,
    REF_SCOPES,
    TOOL_KNOBS,
    ui_schema,
)

CANVAS_FILENAME = "canvas.toml"
LEGACY_FILENAME = "canvas.cst"
CANVAS_VERSION = "rocketeda/canvas/v1"

_TOP_LEVEL = frozenset(
    {"schema", "hdl", "technology", "pdks", "targets", "tools",
     "references"}
)
_REQUIRED_TOP = ("schema", "pdks", "targets", "tools")

CANVAS_SCHEMA = ui_schema()


class CanvasError(Exception):
    """Canvas violation with a stable machine code.

    Args:
        code: Stable machine-readable rule code.
        message: Human detail naming the rule and the section.
    """

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _fail(code, section, detail):
    raise CanvasError(code, f"canvas.{section}: {detail}.")


def _need_mapping(value, section, code="bad_shape"):
    if not isinstance(value, dict):
        _fail(code, section, f"must be a mapping, got {value!r}")


def _check_ref(ref, section, require_revision=True):
    _need_mapping(ref, section, code="bad_ref")
    scope = ref.get("scope")
    if scope not in REF_SCOPES:
        _fail("bad_ref", section,
              f"scope must be one of {sorted(REF_SCOPES)}, "
              f"got {scope!r} (rule ref-shape)")
    ident = ref.get("id")
    if not isinstance(ident, str) or not ident:
        _fail("bad_ref", section,
              "id must be a non-empty string (rule ref-shape)")
    revision = ref.get("revision")
    if scope == "project" and revision is None:
        project = ref.get("project_id")
        if not isinstance(project, str) or not project:
            _fail("bad_ref", section,
                  "project refs need project_id without a revision "
                  "(rule ref-shape)")
        return
    if not isinstance(revision, str) or not revision:
        _fail("unpinned_revision", section,
              "revision must be a non-empty pin (rule revision-pinned)")
    extra = set(ref) - {"scope", "id", "revision", "project_id"}
    if extra:
        _fail("bad_ref", section,
              f"unknown ref keys {sorted(extra)} (rule ref-shape)")


def _check_quantity(value, section, allowed_units=None, note=None):
    _need_mapping(value, section, code="bad_limit")
    tail = f" for {note}" if note else ""
    number = value.get("value")
    if (
        isinstance(number, bool)
        or not isinstance(number, (int, float))
        or not math.isfinite(number)
    ):
        _fail("bad_limit", section,
              f"value must be a finite number, got {number!r}{tail} "
              "(rule units-checked)")
    unit = value.get("unit")
    universe = allowed_units if allowed_units is not None else KNOWN_UNITS
    if not isinstance(unit, str) or unit not in universe:
        _fail("bad_unit", section,
              f"unit {unit!r}{tail} not in {sorted(universe)} "
              "(rule units-checked)")
    extra = set(value) - {"value", "unit"}
    if extra:
        _fail("bad_limit", section,
              f"unknown limit keys {sorted(extra)} (rule units-checked)")


def _check_target(target, index):
    section = f"targets[{index}]"
    _need_mapping(target, section, code="bad_target")
    metric = target.get("metric")
    if metric not in KNOWN_METRICS:
        _fail("unknown_metric", f"{section}.metric",
              f"unknown metric {metric!r}; register it in "
              "schema.KNOWN_METRICS (rule known-metrics)")
    operator = target.get("operator")
    if operator not in OPERATORS:
        _fail("bad_operator", f"{section}.operator",
              f"operator must be one of {list(OPERATORS)}, "
              f"got {operator!r} (rule known-operators)")
    if "limit" not in target:
        _fail("bad_limit", f"{section}.limit",
              "limit is required (rule units-checked)")
    _, units = KNOWN_METRICS[metric]
    _check_quantity(target["limit"], f"{section}.limit",
                    allowed_units=units,
                    note=f"metric {metric!r}")
    required = target.get("required", True)
    if not isinstance(required, bool):
        _fail("bad_required", f"{section}.required",
              f"required must be a bool, got {required!r}")
    extra = set(target) - {"metric", "operator", "limit", "required",
                           "target"}
    if extra:
        _fail("bad_target", section,
              f"unknown target keys {sorted(extra)}")


def _check_knob_value(tool, knob, spec, value, section):
    kind = spec["kind"]
    if kind == "ref":
        _check_ref(value, section, require_revision=True)
    elif kind == "text":
        if not isinstance(value, str) or not value:
            _fail("bad_knob", section,
                  "must be non-empty text (rule known-knobs)")
    elif kind == "hash":
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(c not in "0123456789abcdef" for c in value)
        ):
            _fail("bad_knob", section,
                  "must be a 64-hex sha256 (rule known-knobs)")
    elif kind == "boolean":
        if not isinstance(value, bool):
            _fail("bad_knob", section,
                  f"must be a bool, got {value!r} (rule known-knobs)")
    elif kind == "number":
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            _fail("bad_knob", section,
                  f"must be a finite number, got {value!r} "
                  "(rule units-checked)")
        low = spec.get("min_exclusive")
        if low is not None and not value > low:
            _fail("bad_knob", section,
                  f"must exceed {low}, got {value} (rule knob-bounds)")
        high = spec.get("max")
        if high is not None and not value <= high:
            _fail("bad_knob", section,
                  f"must be at most {high}, got {value} "
                  "(rule knob-bounds)")
    elif kind == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            _fail("bad_knob", section,
                  f"must be an int, got {value!r} (rule known-knobs)")
        if not spec["min"] <= value <= spec["max"]:
            _fail("bad_knob", section,
                  f"must be {spec['min']}..{spec['max']}, got "
                  f"{value} (rule knob-bounds)")
    elif kind == "enum":
        if value not in spec["values"]:
            _fail("bad_knob", section,
                  f"must be one of {list(spec['values'])}, "
                  f"got {value!r} (rule known-knobs)")
    elif kind == "string_list":
        if (
            not isinstance(value, list)
            or not value
            or any(not isinstance(item, str) or not item
                   for item in value)
        ):
            _fail("bad_knob", section,
                  "must be a non-empty list of text "
                  "(rule known-knobs)")
    elif kind == "quantity":
        _check_quantity(value, section,
                        allowed_units=spec.get("units"))


def _resolve_contained(project_root, relpath, section):
    if not isinstance(relpath, str) or not relpath:
        _fail("bad_ref", section,
              "path must be non-empty text (rule refs-contained)")
    parsed = PurePosixPath(relpath)
    if parsed.is_absolute() or ".." in parsed.parts:
        _fail("path_escape", section,
              f"path escapes the project: {relpath!r} "
              "(rule refs-contained)")
    try:
        resolved = join_contained(str(project_root), relpath)
    except PathError as exc:
        _fail("path_escape", section,
              f"{relpath!r} escapes the project ({exc}) "
              "(rule refs-contained)")
    if not resolved.is_file():
        _fail("missing_ref", section,
              f"no such project file: {relpath!r} "
              "(rule refs-contained)")
    digest = hashlib.sha256()
    with open(resolved, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return parsed.as_posix(), digest.hexdigest()


def _check_tools(tools, project_root, refs):
    _need_mapping(tools, "tools", code="bad_tools")
    for name, entry in tools.items():
        section = f"tools.{name}"
        _need_mapping(entry, section, code="bad_tool")
        known = TOOL_KNOBS.get(name)
        allowed = known if known is not None else {
            knob: {"kind": "generic"} for knob in GENERIC_TOOL_KNOBS
        }
        for knob in entry:
            if knob not in allowed:
                _fail("unknown_knob", f"{section}.{knob}",
                      f"unknown knob for tool {name!r}; register it "
                      "in schema.TOOL_KNOBS (rule known-knobs)")
        spec = allowed
        for knob, value in entry.items():
            kind = spec[knob]["kind"]
            if kind == "generic":
                if knob == "profile":
                    _check_ref(value, section)
                elif knob in ("configuration",):
                    if not isinstance(value, str) or not value:
                        _fail("bad_knob", section,
                              "must be non-empty text")
                elif knob == "sha256":
                    _check_knob_value(name, knob, {"kind": "hash"},
                                      value, section)
                continue
            _check_knob_value(name, knob, spec[knob], value,
                              f"{section}.{knob}")
        inline = {
            knob for knob in entry
            if knob not in ("profile", "sha256", "configuration")
        }
        if "configuration" in entry and inline:
            _fail("duplicate_configuration", section,
                  f"inline knobs {sorted(inline)} conflict with "
                  "delegated configuration; keep one "
                  "(rule single-source)")
        if "configuration" in entry:
            rel, digest = _resolve_contained(
                project_root, entry["configuration"], section)
            refs.append({"path": rel, "sha256": digest})


def validate_canvas(doc, project_root):
    """Validate a parsed canvas document against the schema.

    Args:
        doc: Parsed `canvas.toml` mapping.
        project_root: Project dir delegated refs resolve inside;
            refs stay contained or fail loud.

    Returns:
        Validated config mapping plus the closure: refs (path,
            sha256) and closure_hash pinning the intent.

    Raises:
        CanvasError: The first rule violated, naming the rule
            and the section (bad_schema, unknown_metric,
            bad_unit, unknown_knob, duplicate_configuration,
            unpinned_revision, path_escape, missing_ref, ...).
    """
    _need_mapping(doc, "", code="bad_shape")
    unknown = set(doc) - _TOP_LEVEL
    if unknown:
        _fail("unknown_section", sorted(unknown)[0],
              f"unknown top-level section "
              f"(rule schema-closed): {sorted(unknown)}")
    for key in _REQUIRED_TOP:
        if key not in doc:
            _fail("missing_section", key,
                  "required by the v1 canvas contract "
                  "(rule schema-closed)")
    if doc["schema"] != CANVAS_VERSION:
        _fail("bad_schema", "schema",
              f"must be {CANVAS_VERSION!r}, got "
              f"{doc['schema']!r} (rule schema-version)")
    refs = []
    # An empty table (`[technology]` with only comments) carries no
    # claim, so it reads as absent; anything stated validates fully.
    if doc.get("hdl"):
        _need_mapping(doc["hdl"], "hdl", code="bad_hdl")
        language = doc["hdl"].get("language")
        if language not in HDL_LANGUAGES:
            _fail("bad_hdl", "hdl.language",
                  f"language must be one of {list(HDL_LANGUAGES)}, "
                  f"got {language!r} (rule one-dialect)")
        top = doc["hdl"].get("top")
        if top is not None and (not isinstance(top, str) or not top):
            _fail("bad_hdl", "hdl.top",
                  "top must be non-empty text (rule one-dialect)")
        extra = set(doc["hdl"]) - {"language", "top"}
        if extra:
            _fail("bad_hdl", "hdl",
                  f"unknown hdl keys {sorted(extra)}")
    if doc.get("technology"):
        _check_ref(doc["technology"], "technology")
    pdks = doc["pdks"]
    if not isinstance(pdks, list):
        _fail("bad_pdks", "pdks", "must be a list (rule pdk-pinned)")
    for index, ref in enumerate(pdks):
        _check_ref(ref, f"pdks[{index}]")
    targets = doc["targets"]
    if not isinstance(targets, list):
        _fail("bad_targets", "targets",
              "must be a list (rule known-metrics)")
    for index, target in enumerate(targets):
        _check_target(target, index)
    _check_tools(doc["tools"], project_root, refs)
    references = doc.get("references", [])
    if not isinstance(references, list):
        _fail("bad_references", "references",
              "must be a list (rule refs-contained)")
    for index, entry in enumerate(references):
        section = f"references[{index}]"
        _need_mapping(entry, section, code="bad_ref")
        if "path" not in entry or not isinstance(entry["path"], str):
            _fail("bad_ref", section,
                  "path is required text (rule refs-contained)")
        rel, digest = _resolve_contained(
            project_root, entry["path"], section)
        pinned = entry.get("sha256")
        if pinned is not None and pinned != digest:
            _fail("ref_changed", section,
                  f"{rel!r} changed under its pin "
                  f"(rule drift-loud): have {digest}")
        refs.append({"path": rel, "sha256": digest})
        extra = set(entry) - {"path", "sha256"}
        if extra:
            _fail("bad_ref", section,
                  f"unknown reference keys {sorted(extra)}")
    config = {
        "schema": doc["schema"],
        "pdks": doc["pdks"],
        "targets": doc["targets"],
        "tools": doc["tools"],
    }
    if doc.get("hdl"):
        config["hdl"] = doc["hdl"]
    if doc.get("technology"):
        config["technology"] = doc["technology"]
    if "references" in doc:
        config["references"] = doc["references"]
    refs.sort(key=lambda entry: entry["path"])
    return {"config": config, "closure": canvas_closure(refs)}


def canvas_closure(refs):
    """Hash pinned refs into a run-closure identity.

    The hash is content-addressed and key-order stable, mirroring
    the block-run closure: equal intents hash equally, so a rerun
    after a sibling edit proves isolation by hashing differently.

    Args:
        refs: Sorted ref entries (path, sha256).

    Returns:
        Closure mapping with refs and closure_hash (hex sha256
            over the canonical JSON encoding).
    """
    canonical = json.dumps(
        refs, sort_keys=True, separators=(",", ":"), default=str
    )
    return {
        "refs": [dict(entry) for entry in refs],
        "closure_hash": hashlib.sha256(
            canonical.encode("utf-8")).hexdigest(),
    }


def load_project_canvas(project_root, filename=CANVAS_FILENAME):
    """Load, validate, and close over a project's canvas file.

    Args:
        project_root: Project dir holding `canvas.toml`.
        filename: Canvas filename; explicit migration only, so
            the legacy name never loads here.

    Returns:
        Mapping with path, config (validated), and closure
            (canvas_sha256 over the raw bytes, refs, and
            closure_hash pinning canvas plus refs).

    Raises:
        CanvasError: canvas_missing for no canvas file,
            conflicting_canvas when a legacy `canvas.cst` sits
            beside `canvas.toml`, bad_toml for unparsable text,
            or whatever `validate_canvas` raises.
    """
    root = Path(project_root)
    legacy = root / LEGACY_FILENAME
    if legacy.is_file():
        _fail("conflicting_canvas", LEGACY_FILENAME,
              f"{LEGACY_FILENAME} and {filename} both exist; "
              "migrate explicitly, never both "
              "(rule explicit-migration)")
    path = root / filename
    if not path.is_file():
        _fail("canvas_missing", filename,
              f"no {filename} in {root} (rule canvas-exists)")
    raw = path.read_bytes()
    try:
        doc = tomllib.loads(raw.decode("utf-8"))
    except Exception as exc:
        _fail("bad_toml", filename,
              f"does not parse as TOML ({exc}) (rule toml-shape)")
    validated = validate_canvas(doc, root)
    refs = list(validated["closure"]["refs"])
    closure = dict(validated["closure"])
    closure["canvas_sha256"] = hashlib.sha256(raw).hexdigest()
    closure["closure_hash"] = hashlib.sha256(
        json.dumps(
            {"canvas_sha256": closure["canvas_sha256"],
             "refs": refs},
            sort_keys=True, separators=(",", ":"),
            default=str,
        ).encode("utf-8")).hexdigest()
    return {
        "path": str(path),
        "config": validated["config"],
        "closure": closure,
    }


def dump_canvas_toml(doc):
    """Serialize a canvas mapping to canonical TOML text.

    The project-creation wizard writes through here, so a filled
    canvas always round-trips through `validate_canvas`.

    Args:
        doc: Canvas mapping (nested mappings, lists of mappings
            for pdks/targets/references, scalars otherwise).

    Returns:
        TOML text with `schema` first and stable key order.

    Raises:
        CanvasError: bad_value for values TOML cannot carry
            (None, NaN/inf, or unknown types).
    """
    lines = []

    def emit_scalar(value, section):
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, int):
            return str(value)
        if isinstance(value, float):
            if not math.isfinite(value):
                _fail("bad_value", section,
                      "TOML cannot carry NaN/inf (rule toml-shape)")
            text = repr(value)
            return text if "." in text or "e" in text else text + ".0"
        if isinstance(value, str):
            escaped = (
                value.replace("\\", "\\\\")
                .replace('"', '\\"')
                .replace("\n", "\\n")
                .replace("\t", "\\t")
            )
            return f'"{escaped}"'
        _fail("bad_value", section,
              f"TOML cannot carry {type(value).__name__} "
              "(rule toml-shape)")

    def emit_table(mapping, prefix, section):
        # Scalars first: a sub-table header re-points every later
        # key, so parent keys must precede `[table.child]` lines.
        for key in sorted(mapping):
            value = mapping[key]
            if isinstance(value, dict):
                continue
            if isinstance(value, list) and value and all(
                isinstance(item, dict) for item in value
            ):
                continue
            if isinstance(value, list):
                items = ", ".join(
                    emit_scalar(item, f"{section}.{key}")
                    for item in value
                )
                lines.append(f"{key} = [{items}]")
            else:
                lines.append(
                    f"{key} = {emit_scalar(value, f'{section}.{key}')}"
                )
        for key in sorted(mapping):
            value = mapping[key]
            if isinstance(value, dict):
                lines.append(f"[{prefix}{key}]")
                emit_table(value, f"{prefix}{key}.",
                           f"{section}.{key}")
            elif isinstance(value, list) and value and all(
                isinstance(item, dict) for item in value
            ):
                for item in value:
                    lines.append(f"[[{prefix}{key}]]")
                    emit_table(item, f"{prefix}{key}.",
                               f"{section}.{key}")

    top_scalars = {}
    top_tables = {}
    for key in doc:
        value = doc[key]
        # Empty lists are scalars (`key = []`); emitting them after
        # a `[table]` header would re-point them into that table.
        if isinstance(value, dict) or (
            isinstance(value, list) and value and all(
                isinstance(item, dict) for item in value
            )
        ):
            top_tables[key] = value
        else:
            top_scalars[key] = value
    ordered = {}
    if "schema" in top_scalars:
        ordered["schema"] = top_scalars.pop("schema")
    ordered.update(sorted(top_scalars.items()))
    for key, value in ordered.items():
        if isinstance(value, list):
            items = ", ".join(
                emit_scalar(item, key) for item in value
            )
            lines.append(f"{key} = [{items}]")
        else:
            lines.append(f"{key} = {emit_scalar(value, key)}")
    if ordered and top_tables:
        lines.append("")
    first = True
    order = ["hdl", "technology", "pdks", "targets", "tools",
             "references"]
    names = order + sorted(set(top_tables) - set(order))
    for key in names:
        if key not in top_tables:
            continue
        if not first:
            lines.append("")
        first = False
        value = top_tables[key]
        if isinstance(value, dict):
            lines.append(f"[{key}]")
            emit_table(value, f"{key}.", key)
        elif isinstance(value, list) and value and all(
            isinstance(item, dict) for item in value
        ):
            for item in value:
                lines.append(f"[[{key}]]")
                emit_table(item, f"{key}.", key)
        else:
            items = ", ".join(
                emit_scalar(item, key) for item in value
            )
            lines.append(f"{key} = [{items}]")
    return "\n".join(lines) + "\n"
