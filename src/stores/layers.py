"""Layer stackup + preset serving for the viewer and 3D (LAYER-SERVING).

The engine is the queryable rendering authority: per-PDK Stackup
(ordered layers, metal/tech grouping, enabled set, colors, Z
heights) served read-only from PDK truth, plus LAYER_PRESET
records mirroring KiCad's `{layers, renderLayers, flip, active}`
with built-ins (All/None/All-metal/Top/Bottom), user
save/overwrite/delete, and explicit apply. Viewer rows derive
from the same schemas.

PDK truth (sky130A in MVP): the registered store entry's KLayout
tech files — `.lyp` (layer order, colors, valid/visible flags),
`.lyt` (tech name, database unit), and the xsection `.xs` script
(film thicknesses for Z heights). Files resolve through
PDK-STORE's hash-checked `resolve_deck`, so drift fails loudly
instead of rendering stale fab data. Missing xsect serves
`z_complete=False` with a reason — the 3D adapter must refuse to
render heights, never invent them. The PDK remains truth: every
call re-parses and returns fresh objects, and no API mutates a
stackup (no user fork in MVP).
"""

import ast
import copy
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from ..interfaces.errors import ContractError
from ..interfaces.paths import join_contained, slugify
from ..interfaces.pdks import PdkError, list_pdks, resolve_deck

STACKUP_VERSION = 1
PRESET_VERSION = 1

BUILTIN_PRESETS = ("All", "None", "All-metal", "Top", "Bottom")

GROUPS = ("metal", "via", "frontend", "tech", "other")

# PDK slug -> store relpaths for the stackup sources. Only sky130A in
# MVP; a PDK without an entry raises unknown_stackup (loud, with the
# remedy to extend this table — never a silent empty stackup).
STACKUP_FILES = {
    "sky130a": {
        "lyp": "libs.tech/klayout/tech/sky130A.lyp",
        "lyt": "libs.tech/klayout/tech/sky130A.lyt",
        "xsect": "libs.tech/klayout/tech/xsect/sky130.xs",
    },
}

_METAL_BASES = frozenset({"li1", "met1", "met2", "met3", "met4", "met5"})
_VIA_BASES = frozenset({"licon1", "mcon", "via", "via2", "via3", "via4"})
_FRONTEND_BASES = frozenset({
    "diff", "tap", "nwell", "pwell", "dnwell", "poly", "nsdm", "psdm",
    "rpm", "urpm", "npc", "hvntm", "hvi", "hvtr", "hvtp", "lvtn",
    "tunm", "ldntm", "pwbm", "pwde",
})
_TECH_BASES = frozenset({"capm", "cap2m", "pad", "nsm", "prBoundary"})

# Top-side preset: the top metal plus back-end tech layers.
_TOP_BASES = frozenset({"met5", "capm", "cap2m", "pad", "nsm", "prBoundary"})

# Viewer aids carried on every preset (KiCad's renderLayers analogue:
# non-stackup toggles the viewer owns). Unknown keys pass through so
# the viewer can evolve without an engine change.
_RENDER_DEFAULT = {"grid": True, "cellframe": True, "labels": True, "rulers": True}

# Idents that must resolve for z_complete (conductors + contacts).
_Z_REQUIRED = (
    "poly", "li1", "met1", "met2", "met3", "met4", "met5",
    "licon1", "mcon", "via", "via2", "via3", "via4",
)

_XS_INPUT_RE = re.compile(
    r"""^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*layer\(\s*"(\d+)\s*/\s*(\d+)"\s*\)"""
)
_XS_ASSIGN_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+?)\s*$")
_XS_ARITH_CHARS = re.compile(r"[0-9A-Za-z_+\-*/(). \t]+")

_BINOPS = (ast.Add, ast.Sub, ast.Mult, ast.Div)


class LayerServingError(ContractError):
    """Layer-serving violation with a stable machine code.

    Args:
        code: Stable machine-readable error code.
        message: Human-readable detail.
        fields: Itemized fields, when the error names any.
    """


def _group_of(base):
    if base in _METAL_BASES:
        return "metal"
    if base in _VIA_BASES:
        return "via"
    if base in _FRONTEND_BASES:
        return "frontend"
    if base in _TECH_BASES:
        return "tech"
    return "other"


def _child_text(node, tag, default=None):
    child = node.find(tag)
    if child is None or child.text is None:
        return default
    return child.text.strip()


def parse_lyp(text):
    """Parse a KLayout .lyp layer-properties file.

    Args:
        text: Raw .lyp XML text.

    Returns:
        Mapping with file-order entries (name, label, base,
            purpose, layer, datatype, frame, fill, valid,
            visible, order) plus the entry count.

    Raises:
        LayerServingError: invalid_stackup for malformed XML, a
            missing name/source, a bad source, or zero entries.
    """
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise LayerServingError(
            "invalid_stackup", f"Cannot parse .lyp layer properties: {exc}."
        ) from exc
    if root.tag != "layer-properties":
        raise LayerServingError(
            "invalid_stackup",
            f".lyp root must be layer-properties, got {root.tag!r}.",
        )
    entries = []
    for order, node in enumerate(root.findall("properties")):
        label = _child_text(node, "name")
        if not label:
            raise LayerServingError(
                "invalid_stackup", ".lyp entry without a name."
            )
        source = _child_text(node, "source")
        if not source:
            raise LayerServingError(
                "invalid_stackup", f".lyp entry without a source: {label}."
            )
        try:
            layer_s, rest = source.split("@", 1)[0].split("/", 1)
            layer, datatype = int(layer_s), int(rest.split("@", 1)[0])
        except (ValueError, IndexError):
            raise LayerServingError(
                "invalid_stackup",
                f".lyp entry has a bad source {source!r}: {label}.",
            ) from None
        head = label.rsplit(" - ", 1)[0]
        if "." in head:
            base, purpose = head.split(".", 1)
        else:
            base, purpose = head, ""
        entries.append({
            "name": f"{base}.{purpose}" if purpose else base,
            "label": label,
            "base": base,
            "purpose": purpose,
            "layer": layer,
            "datatype": datatype,
            "frame": _child_text(node, "frame-color", "") or "",
            "fill": _child_text(node, "fill-color", "") or "",
            "valid": _child_text(node, "valid", "true") == "true",
            "visible": _child_text(node, "visible", "true") == "true",
            "order": order,
        })
    if not entries:
        raise LayerServingError(
            "invalid_stackup", ".lyp carries no <properties> entries."
        )
    return {"entries": entries, "count": len(entries)}


def parse_lyt(text):
    """Parse a KLayout .lyt technology file (tech name + dbu).

    Args:
        text: Raw .lyt XML text.

    Returns:
        Mapping with tech, dbu_um, and layer_properties.

    Raises:
        LayerServingError: invalid_stackup for malformed XML, a
            missing tech name, or a missing/bad dbu.
    """
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise LayerServingError(
            "invalid_stackup", f"Cannot parse .lyt technology: {exc}."
        ) from exc
    if root.tag != "technology":
        raise LayerServingError(
            "invalid_stackup",
            f".lyt root must be technology, got {root.tag!r}.",
        )
    tech = _child_text(root, "name")
    if not tech:
        raise LayerServingError("invalid_stackup", ".lyt carries no tech name.")
    try:
        dbu = float(_child_text(root, "dbu", ""))
    except (TypeError, ValueError):
        raise LayerServingError(
            "invalid_stackup", ".lyt carries no numeric dbu."
        ) from None
    return {
        "tech": tech,
        "dbu_um": dbu,
        "layer_properties": _child_text(root, "layer-properties_file"),
    }


def _strip_xs_comment(line):
    in_string = False
    for index, char in enumerate(line):
        if char == '"':
            in_string = not in_string
        elif char == "#" and not in_string:
            return line[:index]
    return line


def _eval_xs_arith(node, values, where):
    if isinstance(node, ast.Expression):
        return _eval_xs_arith(node.body, values, where)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.Name):
        if node.id not in values:
            raise LayerServingError(
                "invalid_stackup",
                f".xs references unknown variable {node.id!r} in {where}.",
            )
        return values[node.id]
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        operand = _eval_xs_arith(node.operand, values, where)
        return operand if isinstance(node.op, ast.UAdd) else -operand
    if isinstance(node, ast.BinOp) and isinstance(node.op, _BINOPS):
        left = _eval_xs_arith(node.left, values, where)
        right = _eval_xs_arith(node.right, values, where)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        try:
            return left / right
        except ZeroDivisionError:
            raise LayerServingError(
                "invalid_stackup", f".xs divides by zero in {where}."
            ) from None
    return None


def _xs_spans(values):
    """Z spans from evaluated xsect variables (sky130 recipe).

    shortcut: the recipe assumes the klayoutmatthias sky130
    xsection variable shape (li/mN bottoms, ild/mN thicknesses);
    generalize when a second PDK ships xsect.
    """
    need = values.get
    spans = {}

    def _put(ident, base, top, thick, source):
        if base is None or top is None or thick is None:
            return
        spans[ident] = {
            "z_base_um": base,
            "z_top_um": top,
            "thickness_um": thick,
            "z_source": f"xsect:{source}",
        }

    gox, poly_t = need("gox_thickness"), need("poly_thickness")
    _put("poly", gox,
         gox + poly_t if gox is not None and poly_t is not None else None,
         poly_t, "gox_thickness..+poly_thickness")
    li_bottom, li_t = need("li_bottom"), need("li_thickness")
    _put("li1", li_bottom,
         li_bottom + li_t if li_bottom is not None and li_t is not None else None,
         li_t, "li_bottom..+li_thickness")
    bottoms = {n: need(f"m{n}_bottom") for n in range(1, 6)}
    thick = {n: need(f"m{n}_thickness") for n in range(1, 6)}
    for n in range(1, 6):
        ident = f"met{n}"
        base, thick_n = bottoms[n], thick[n]
        _put(ident, base,
             base + thick_n if base is not None and thick_n is not None else None,
             thick_n, f"m{n}_bottom..+m{n}_thickness")
    _put("licon1", 0.0, li_bottom, li_bottom, "0..li_bottom")
    chain = [
        ("mcon", li_bottom, bottoms[1], "li_bottom..m1_bottom"),
        ("via", bottoms[1], bottoms[2], "m1_bottom..m2_bottom"),
        ("via2", bottoms[2], bottoms[3], "m2_bottom..m3_bottom"),
        ("via3", bottoms[3], bottoms[4], "m3_bottom..m4_bottom"),
        ("via4", bottoms[4], bottoms[5], "m4_bottom..m5_bottom"),
    ]
    for ident, base, top, source in chain:
        _put(ident, base, top,
             top - base if base is not None and top is not None else None,
             source)
    capm_depth, capm_t = need("capm_depth"), need("capm_thickness")
    if capm_depth is not None and capm_t is not None and bottoms[4] is not None:
        top = bottoms[4] - capm_depth
        _put("capm", top - capm_t, top, capm_t,
             "m4_bottom-capm_depth-capm_thickness..")
    cap2m_depth, cap2m_t = need("cap2m_depth"), need("cap2m_thickness")
    if cap2m_depth is not None and cap2m_t is not None and bottoms[5] is not None:
        top = bottoms[5] - cap2m_depth
        _put("cap2m", top - cap2m_t, top, cap2m_t,
             "m5_bottom-cap2m_depth-cap2m_thickness..")
    return spans


def parse_xsect(text):
    """Parse a KLayout xsection script (inputs + thicknesses + spans).

    Single-line statements only: `ident = layer("L/D")` inputs and
    pure-arithmetic assignments evaluate; process calls (mask,
    grow, deposit, output, ...) are skipped, never executed.

    Args:
        text: Raw .xs script text.

    Returns:
        Mapping with inputs ({(layer, datatype): ident}),
            values ({variable: float}), and spans ({ident: Z
            span record}).

    Raises:
        LayerServingError: invalid_stackup when compound
            arithmetic references an unknown variable or divides
            by zero (bare aliases to undefined process handles
            are skipped, never numbers).
    """
    inputs = {}
    pending = []
    for raw in (text or "").splitlines():
        line = _strip_xs_comment(raw).strip()
        if not line:
            continue
        match = _XS_INPUT_RE.match(line)
        if match:
            ident, layer, datatype = match.groups()
            inputs.setdefault((int(layer), int(datatype)), ident)
            continue
        assign = _XS_ASSIGN_RE.match(line)
        if not assign or _XS_INPUT_RE.match(line):
            continue
        ident, expr = assign.groups()
        if "(" in expr or ")" in expr:
            continue  # process code (calls), not arithmetic
        # Bare attribute reads (no call) fall through to the AST shape
        # check below, which skips them as non-arithmetic; float
        # literals legitimately contain dots, so dots never skip.
        if _XS_ARITH_CHARS.fullmatch(expr) is None:
            continue
        try:
            tree = ast.parse(expr, mode="eval")
        except SyntaxError:
            continue
        pending.append((ident, expr, tree))
    values = {}
    remaining = list(pending)
    while remaining:
        progressed = False
        still = []
        for ident, expr, tree in remaining:
            try:
                value = _eval_xs_arith(tree, values, f"{ident} = {expr}")
            except LayerServingError:
                still.append((ident, expr, tree))
                continue
            if value is None:
                continue  # non-arithmetic shape; process code
            values[ident] = value
            progressed = True
        remaining = still
        if not progressed:
            compound = [line for line in still
                        if not isinstance(line[2].body, ast.Name)]
            if not compound:
                break  # bare aliases to process handles; not numbers
            ident, expr, tree = compound[0]
            _eval_xs_arith(tree, values, f"{ident} = {expr}")
            raise LayerServingError(  # pragma: no cover (the eval raises)
                "invalid_stackup", f".xs cannot evaluate {ident} = {expr}."
            )
    return {"inputs": inputs, "values": values, "spans": _xs_spans(values)}


def build_stackup(pdk_id, revision, lyp_text, lyt_text=None,
                  xsect_text=None, source=None):
    """Assemble one read-only Stackup record from PDK file texts.

    Args:
        pdk_id: Canonical PDK display id (echoed in the record).
        revision: PDK revision pin (echoed in the record).
        lyp_text: Raw .lyp layer-properties text (required).
        lyt_text: Raw .lyt technology text; tech/dbu stay None
            when omitted.
        xsect_text: Raw .xs xsection text; heights stay None
            with z_complete=False when omitted.
        source: Provenance mapping (kind + relpaths/hashes);
            {"kind": "inline"} when omitted.

    Returns:
        Fresh Stackup record (ordered layers, enabled set,
            groups, z_complete + reason); every call returns
            independent objects — mutating a record never
            affects later calls.

    Raises:
        LayerServingError: invalid_stackup for a bad id/rev, a
            duplicate layer name, or any unparseable file.
    """
    if not isinstance(pdk_id, str) or not pdk_id.strip():
        raise LayerServingError("invalid_stackup", "Stackup needs a PDK id.")
    if not isinstance(revision, str) or not revision.strip():
        raise LayerServingError("invalid_stackup", "Stackup needs a revision.")
    entries = parse_lyp(lyp_text)["entries"]
    # Same head on different GDS (e.g. sky130A's four `boundary`
    # entries) disambiguates with @L/D on every colliding entry;
    # same head on the SAME GDS is a corrupt duplicate, loud.
    by_head = {}
    for entry in entries:
        by_head.setdefault(entry["name"], []).append(entry)
    for head, group in by_head.items():
        if len(group) == 1:
            continue
        gdss = {(entry["layer"], entry["datatype"]) for entry in group}
        if len(gdss) != len(group):
            raise LayerServingError(
                "invalid_stackup",
                f"Duplicate layer name in .lyp: {head}.",
            )
        for entry in group:
            entry["name"] = (
                f"{head}@{entry['layer']}/{entry['datatype']}"
            )
    tech = parse_lyt(lyt_text) if lyt_text is not None else {
        "tech": None, "dbu_um": None, "layer_properties": None,
    }
    parsed_xs = parse_xsect(xsect_text) if xsect_text is not None else None
    spans = (parsed_xs or {}).get("spans") or {}
    inputs = (parsed_xs or {}).get("inputs") or {}
    layers = []
    for entry in entries:
        ident = inputs.get((entry["layer"], entry["datatype"]))
        span = spans.get(ident) if ident else None
        layers.append({
            "name": entry["name"],
            "label": entry["label"],
            "base": entry["base"],
            "purpose": entry["purpose"],
            "gds": [entry["layer"], entry["datatype"]],
            "group": _group_of(entry["base"]),
            "color": {"frame": entry["frame"], "fill": entry["fill"]},
            "visible": entry["visible"],
            "enabled": entry["valid"],
            "z_base_um": span["z_base_um"] if span else None,
            "z_top_um": span["z_top_um"] if span else None,
            "thickness_um": span["thickness_um"] if span else None,
            "z_source": span["z_source"] if span else None,
            "stack_index": None,
        })
    ranked = sorted(
        (index for index, layer in enumerate(layers)
         if layer["z_base_um"] is not None),
        key=lambda i: (layers[i]["z_base_um"], i),
    )
    for rank, index in enumerate(ranked):
        layers[index]["stack_index"] = rank
    missing = [ident for ident in _Z_REQUIRED if ident not in spans]
    if xsect_text is None:
        z_reason = "no xsect served: 3D heights unavailable (no guess served)"
    elif missing:
        z_reason = f"incomplete xsect spans for: {', '.join(missing)}"
    else:
        z_reason = ""
    groups = {
        group: [layer["name"] for layer in layers if layer["group"] == group]
        for group in GROUPS
    }
    return {
        "stackup_version": STACKUP_VERSION,
        "pdk_id": pdk_id,
        "revision": revision,
        "source": copy.deepcopy(source) if source is not None else {"kind": "inline"},
        "tech": tech["tech"],
        "dbu_um": tech["dbu_um"],
        "layers": layers,
        "order": "file",
        "enabled": [layer["name"] for layer in layers if layer["enabled"]],
        "groups": groups,
        "z_complete": not missing and xsect_text is not None,
        "z_missing": missing,
        "z_reason": z_reason,
    }


def get_stackup_from_dir(pdk_id, revision, pdk_dir):
    """Serve a Stackup by parsing a plain PDK tree directory.

    Args:
        pdk_id: Canonical PDK display id (selects the relpath map).
        revision: Revision label echoed in the record (the dir is
            not a store entry, so nothing verifies it).
        pdk_dir: PDK tree root holding the mapped relpaths.

    Returns:
        Fresh Stackup record with pdk-dir provenance.

    Raises:
        LayerServingError: unknown_stackup for an unmapped PDK or
            a missing .lyp; invalid_stackup for unparseable files.
    """
    mapping = STACKUP_FILES.get(slugify(pdk_id))
    if mapping is None:
        raise LayerServingError(
            "unknown_stackup",
            f"No layer stackup mapping for PDK {pdk_id!r}; mapped: "
            f"{sorted(STACKUP_FILES)}.",
        )
    base = Path(pdk_dir)
    lyp_path = join_contained(base, mapping["lyp"])
    if not lyp_path.is_file():
        raise LayerServingError(
            "unknown_stackup",
            f"No stackup .lyp for PDK {pdk_id!r}: {mapping['lyp']} not found.",
        )
    texts = {"lyp_text": lyp_path.read_text(encoding="utf-8")}
    source = {"kind": "pdk-dir", "dir": str(base), "lyp": mapping["lyp"]}
    for key in ("lyt", "xsect"):
        path = join_contained(base, mapping[key])
        if path.is_file():
            texts[f"{key}_text"] = path.read_text(encoding="utf-8")
            source[key] = mapping[key]
    return build_stackup(pdk_id, revision, source=source, **texts)


def get_stackup(pdk_id, revision=None, engine_root=None):
    """Serve a Stackup from a registered PDK store entry.

    Args:
        pdk_id: Canonical display id (either spelling resolves).
        revision: Revision pin; the newest registered revision
            when omitted (echoed in the record — explicit pins
            stay recommended for runs).
        engine_root: Explicit store root; resolved when omitted.

    Returns:
        Fresh Stackup record with pdk-store provenance (relpaths
            plus manifest-verified sha256).

    Raises:
        PdkError: unknown_pdk for a missing store/id/revision or
            .lyp deck, pdk_drift for a tampered file.
        LayerServingError: unknown_stackup for a PDK with no
            stackup mapping.
    """
    try:
        entries = list_pdks(engine_root=engine_root)
    except ContractError as exc:
        raise PdkError(
            "unknown_pdk", f"Unknown PDK: {pdk_id}@{revision} ({exc})."
        ) from exc
    slug = slugify(pdk_id)
    candidates = [e for e in entries if slugify(e.get("id") or "") == slug]
    if revision is None:
        revisions = sorted(e["revision"] for e in candidates)
        if not revisions:
            raise PdkError(
                "unknown_pdk", f"Unknown PDK: {pdk_id} (no store entry)."
            )
        revision = revisions[-1]
    else:
        candidates = [e for e in candidates if e.get("revision") == revision]
        if not candidates:
            raise PdkError(
                "unknown_pdk", f"Unknown PDK: {pdk_id}@{revision} (no store entry)."
            )
    mapping = STACKUP_FILES.get(slug)
    if mapping is None:
        raise LayerServingError(
            "unknown_stackup",
            f"No layer stackup mapping for PDK {pdk_id!r}; mapped: "
            f"{sorted(STACKUP_FILES)}.",
        )
    entry = candidates[0]
    lyp_hit = resolve_deck(entry["id"], revision, mapping["lyp"],
                           engine_root=engine_root)
    texts = {"lyp_text": Path(lyp_hit["path"]).read_text(encoding="utf-8")}
    sha256 = {mapping["lyp"]: lyp_hit["sha256"]}
    source = {
        "kind": "pdk-store",
        "store_path": entry["path"],
        "lyp": mapping["lyp"],
    }
    for key in ("lyt", "xsect"):
        try:
            hit = resolve_deck(entry["id"], revision, mapping[key],
                               engine_root=engine_root)
        except PdkError as exc:
            if exc.code != "unknown_pdk":
                raise
            continue  # optional source absent: served degraded, with reason
        texts[f"{key}_text"] = Path(hit["path"]).read_text(encoding="utf-8")
        sha256[mapping[key]] = hit["sha256"]
        source[key] = mapping[key]
    source["sha256"] = sha256
    return build_stackup(entry["id"], revision, source=source, **texts)


def _extreme_drawing(layers, visible, want_max):
    drawing = [layer for layer in layers
               if layer["purpose"] == "drawing"
               and layer["stack_index"] is not None
               and visible.get(layer["name"], False)]
    if not drawing:
        return None
    key = (lambda layer: (layer["stack_index"], layer["name"]))
    return (max if want_max else min)(drawing, key=key)["name"]


def builtin_preset(stackup, name):
    """Compute one built-in LAYER_PRESET from a Stackup.

    All covers every PDK-enabled layer, None hides all, All-metal
    covers the metal + via groups, Top covers the top metal plus
    back-end tech (flip=False, active = topmost visible drawing),
    Bottom covers the frontend group (flip=True, active = lowest
    visible drawing). Without heights the Top/Bottom active stays
    None.

    Args:
        stackup: Stackup record the preset resolves against.
        name: Built-in preset name (see BUILTIN_PRESETS).

    Returns:
        Fresh preset record (preset_version, name, builtin,
            stackup_ref, full layers map, renderLayers, flip,
            active).

    Raises:
        LayerServingError: unknown_preset for a non-built-in name.
    """
    if name not in BUILTIN_PRESETS:
        raise LayerServingError(
            "unknown_preset",
            f"Unknown built-in preset {name!r}; built-ins: "
            f"{', '.join(BUILTIN_PRESETS)}.",
        )
    layers = stackup["layers"]
    if name == "All":
        visible = {layer["name"]: layer["enabled"] for layer in layers}
    elif name == "None":
        visible = {layer["name"]: False for layer in layers}
    elif name == "All-metal":
        visible = {
            layer["name"]: layer["enabled"] and layer["group"] in ("metal", "via")
            for layer in layers
        }
    elif name == "Top":
        visible = {
            layer["name"]: layer["enabled"] and layer["base"] in _TOP_BASES
            for layer in layers
        }
    else:
        visible = {
            layer["name"]: layer["enabled"] and layer["group"] == "frontend"
            for layer in layers
        }
    if name == "Top":
        active = _extreme_drawing(layers, visible, True)
    elif name == "Bottom":
        active = _extreme_drawing(layers, visible, False)
    else:
        active = None
    return {
        "preset_version": PRESET_VERSION,
        "name": name,
        "builtin": True,
        "stackup_ref": {
            "pdk_id": stackup["pdk_id"], "revision": stackup["revision"],
        },
        "layers": visible,
        "renderLayers": dict(_RENDER_DEFAULT),
        "flip": name == "Bottom",
        "active": active,
    }


class PresetStore:
    """In-memory user layer presets plus the computed built-ins.

    Built-ins compute from the stackup on every apply (never stale,
    never overwritten, never deleted). User presets validate
    against the stackup at save and at apply: stale names fail
    loudly instead of half-applying.
    """

    def __init__(self):
        self._user = {}

    def save(self, stackup, name, layers, render_layers=None,
             flip=False, active=None, overwrite=False):
        """Save a user preset (sparse visibility map + view state).

        Missing names default to hidden (KiCad LSET semantics: the
        map is the visible set); apply() resolves the full map.

        Args:
            stackup: Stackup record names validate against.
            name: Preset name (stored stripped; built-in names
                are reserved).
            layers: Sparse {layer name: visible} map.
            render_layers: {toggle: bool} viewer aids; the
                default set when omitted (unknown keys pass
                through for viewer evolution).
            flip: View-from-bottom flag.
            active: Active layer name, or None.
            overwrite: Replace an existing user preset of the
                same name instead of conflicting.

        Returns:
            Stored preset record (builtin False).

        Raises:
            LayerServingError: invalid_preset for a bad name,
                unknown layer names, or a bad render/flip/active
                shape; preset_conflict for a built-in name or an
                existing user preset without overwrite.
        """
        known = {layer["name"] for layer in stackup["layers"]}
        if not isinstance(name, str) or not name.strip():
            raise LayerServingError("invalid_preset", "Preset needs a name.")
        stored = name.strip()
        if stored in BUILTIN_PRESETS:
            raise LayerServingError(
                "preset_conflict",
                f"Built-in preset {stored!r} cannot be overwritten.",
            )
        if not isinstance(layers, dict):
            raise LayerServingError("invalid_preset", "Preset layers must be a map.")
        unknown = sorted(n for n in layers if n not in known)
        if unknown:
            raise LayerServingError(
                "invalid_preset",
                f"Preset {stored!r} names unknown layers: "
                f"{', '.join(unknown)}.",
            )
        for layer_name, value in layers.items():
            if type(value) is not bool:
                raise LayerServingError(
                    "invalid_preset",
                    f"Preset {stored!r} layer {layer_name!r} must be a bool.",
                )
        if render_layers is None:
            render = dict(_RENDER_DEFAULT)
        else:
            if not isinstance(render_layers, dict):
                raise LayerServingError(
                    "invalid_preset", "Preset renderLayers must be a map."
                )
            for key, value in render_layers.items():
                if not isinstance(key, str) or not key or type(value) is not bool:
                    raise LayerServingError(
                        "invalid_preset",
                        f"Preset {stored!r} renderLayers must map names to bools.",
                    )
            render = dict(render_layers)
        if type(flip) is not bool:
            raise LayerServingError(
                "invalid_preset", f"Preset {stored!r} flip must be a bool."
            )
        if active is not None and active not in known:
            raise LayerServingError(
                "invalid_preset",
                f"Preset {stored!r} names unknown active layer {active!r}.",
            )
        if stored in self._user and not overwrite:
            raise LayerServingError(
                "preset_conflict",
                f"Preset {stored!r} already exists (overwrite to replace).",
            )
        record = {
            "preset_version": PRESET_VERSION,
            "name": stored,
            "builtin": False,
            "stackup_ref": {
                "pdk_id": stackup["pdk_id"], "revision": stackup["revision"],
            },
            "layers": dict(layers),
            "renderLayers": render,
            "flip": flip,
            "active": active,
        }
        self._user[stored] = record
        return copy.deepcopy(record)

    def delete(self, name):
        """Delete one user preset (built-ins are undeletable).

        Args:
            name: Preset name to delete.

        Returns:
            Deletion record with the deleted name.

        Raises:
            LayerServingError: preset_conflict for a built-in
                name; unknown_preset for a missing user preset.
        """
        if name in BUILTIN_PRESETS:
            raise LayerServingError(
                "preset_conflict", f"Built-in preset {name!r} cannot be deleted."
            )
        if name not in self._user:
            raise LayerServingError("unknown_preset", f"Unknown preset {name!r}.")
        del self._user[name]
        return {"deleted": name}

    def list_presets(self):
        """List built-in plus user preset names.

        Returns:
            Name records (name + builtin), built-ins first in
                pinned order, then user presets sorted.
        """
        records = [{"name": name, "builtin": True} for name in BUILTIN_PRESETS]
        records += [
            {"name": name, "builtin": False} for name in sorted(self._user)
        ]
        return records

    def apply(self, stackup, name):
        """Explicitly apply one preset to a Stackup.

        Args:
            stackup: Stackup record the preset resolves against
                (echoed as stackup_ref).
            name: Built-in or user preset name.

        Returns:
            Full preset record with the complete layers map,
                renderLayers, flip, and active.

        Raises:
            LayerServingError: unknown_preset for a missing name;
                invalid_preset when a user preset names layers
                the stackup no longer serves.
        """
        if name in BUILTIN_PRESETS:
            return builtin_preset(stackup, name)
        if name not in self._user:
            raise LayerServingError("unknown_preset", f"Unknown preset {name!r}.")
        stored = self._user[name]
        known = {layer["name"] for layer in stackup["layers"]}
        unknown = sorted(n for n in stored["layers"] if n not in known)
        if unknown:
            raise LayerServingError(
                "invalid_preset",
                f"Preset {name!r} names layers this stackup no longer "
                f"serves: {', '.join(unknown)}.",
            )
        if stored["active"] is not None and stored["active"] not in known:
            raise LayerServingError(
                "invalid_preset",
                f"Preset {name!r} names an active layer this stackup no "
                f"longer serves: {stored['active']!r}.",
            )
        return {
            "preset_version": PRESET_VERSION,
            "name": name,
            "builtin": False,
            "stackup_ref": {
                "pdk_id": stackup["pdk_id"], "revision": stackup["revision"],
            },
            "layers": {
                layer["name"]: stored["layers"].get(layer["name"], False)
                for layer in stackup["layers"]
            },
            "renderLayers": copy.deepcopy(stored["renderLayers"]),
            "flip": stored["flip"],
            "active": stored["active"],
        }


def viewer_rows(stackup, visibility=None, active=None):
    """Render viewer rows for a Stackup (visibility + color + active).

    Args:
        stackup: Stackup record rows derive from.
        visibility: Sparse {layer name: visible} overrides over
            the PDK defaults; all defaults when omitted.
        active: Active layer name, or None.

    Returns:
        Page with stackup_ref, flip False, the active name, and
            file-order rows (name, label, gds, group, purpose,
            color, visible, active, enabled, stack_index, Z).

    Raises:
        LayerServingError: invalid_visibility for unknown layer
            names or a non-bool/non-map shape.
    """
    known = {layer["name"] for layer in stackup["layers"]}
    if visibility is None:
        overrides = {}
    else:
        if not isinstance(visibility, dict):
            raise LayerServingError(
                "invalid_visibility", "Visibility overrides must be a map."
            )
        unknown = sorted(n for n in visibility if n not in known)
        if unknown:
            raise LayerServingError(
                "invalid_visibility",
                f"Unknown layers in visibility: {', '.join(unknown)}.",
            )
        for layer_name, value in visibility.items():
            if type(value) is not bool:
                raise LayerServingError(
                    "invalid_visibility",
                    f"Visibility for {layer_name!r} must be a bool.",
                )
        overrides = visibility
    if active is not None and active not in known:
        raise LayerServingError(
            "invalid_visibility", f"Unknown active layer {active!r}."
        )
    rows = []
    for layer in stackup["layers"]:
        rows.append({
            "name": layer["name"],
            "label": layer["label"],
            "gds": list(layer["gds"]),
            "group": layer["group"],
            "purpose": layer["purpose"],
            "color": dict(layer["color"]),
            "visible": overrides.get(layer["name"], layer["visible"]),
            "active": layer["name"] == active,
            "enabled": layer["enabled"],
            "stack_index": layer["stack_index"],
            "z_base_um": layer["z_base_um"],
            "z_top_um": layer["z_top_um"],
        })
    return {
        "stackup_ref": {
            "pdk_id": stackup["pdk_id"], "revision": stackup["revision"],
        },
        "flip": False,
        "active": active,
        "rows": rows,
    }


def viewer_rows_for_preset(store, stackup, name, overrides=None, active=None):
    """Render viewer rows with one preset explicitly applied.

    Args:
        store: PresetStore holding user presets.
        stackup: Stackup record rows derive from.
        name: Built-in or user preset name.
        overrides: Sparse {layer name: visible} wins over the
            preset map; never clears the preset flip.
        active: Active layer override; the preset active when
            omitted.

    Returns:
        Page with stackup_ref, preset name, flip, active, and
            file-order rows.

    Raises:
        LayerServingError: unknown_preset for a missing preset;
            invalid_preset for a stale user preset;
            invalid_visibility for bad overrides/active.
    """
    preset = store.apply(stackup, name)
    merged = dict(preset["layers"])
    if overrides:
        merged.update(overrides)
    page = viewer_rows(
        stackup,
        visibility=merged,
        active=preset["active"] if active is None else active,
    )
    page["flip"] = preset["flip"]
    page["preset"] = name
    return page


__all__ = [
    "BUILTIN_PRESETS",
    "GROUPS",
    "PRESET_VERSION",
    "STACKUP_FILES",
    "STACKUP_VERSION",
    "LayerServingError",
    "PresetStore",
    "build_stackup",
    "builtin_preset",
    "get_stackup",
    "get_stackup_from_dir",
    "parse_lyp",
    "parse_lyt",
    "parse_xsect",
    "viewer_rows",
    "viewer_rows_for_preset",
]
