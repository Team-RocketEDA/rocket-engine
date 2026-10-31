"""Staged generate_views driver: job JSON in, result envelope JSON on stdout.

The adapter copies this file into the run workdir next to
`gf_views_job.json` and executes `python gf_views_driver.py
gf_views_job.json`. Exactly one JSON document is printed to stdout;
solver warnings go to stderr untouched.

Every recipe consumes project inputs from the job: view-spec cells +
params, project GDS paths, and the optional project pin map. Nothing
is hardcoded — the PDK, the cell list, the export filenames, and the
macro pin/obstruction bindings all ride the job.

Envelope: `{"ok": true, "gdsfactory_version, "result": {recipe,
active_pdk, cspdk_version, mappings[], artifacts[], diagnostics}}` or
`{"ok": false, "error": {code, message, token, line}}`. Exit 0 on
success, 2 on a bad cell/spec/source/format, 3 when gdsfactory or the
named PDK is not importable. Anything else explodes with a traceback
and exit 1, which parse() reports as runner_unavailable rather than
mistaking a tool crash for layout.
"""

import json
import sys
from pathlib import Path

_BOUNDARY_NOTE = (
    "GDS import alone does not reconstruct macro pins/obstructions "
    "(PRD boundary note); bind a project pin_map to publish them."
)
_BUILD_NOTE = (
    "Cell builds carry no macro obstructions; bind a project "
    "pin_map at import to publish them."
)


def _fail(code, message, token, line):
    print(
        json.dumps(
            {
                "ok": False,
                "error": {
                    "code": code,
                    "message": message,
                    "token": token,
                    "line": line,
                },
            }
        )
    )


def _find_line(text, token):
    if not token:
        return None
    for number, line in enumerate((text or "").splitlines(), 1):
        if token in line:
            return number
    return None


def _polygons(comp):
    return sum(len(polys) for polys in comp.get_polygons().values())


def _bbox(comp):
    box = comp.bbox()
    return [
        [float(box.left), float(box.bottom)],
        [float(box.right), float(box.top)],
    ]


def _ports(comp):
    try:
        ports = list(comp.ports)
    except Exception:
        return [], []
    names = []
    details = []
    for port in ports:
        try:
            name = port.name
        except Exception:
            continue
        names.append(name)
        try:
            center = port.center
            middle = [float(center[0]), float(center[1])]
        except Exception:
            middle = None
        try:
            layer = str(port.layer)
        except Exception:
            layer = None
        details.append(
            {"name": name, "center_um": middle, "layer": layer}
        )
    return sorted(names), details


def _mapping(source, comp):
    names, _ = _ports(comp)
    return {
        "source": source,
        "component": comp.name,
        "ports": names,
        "n_polygons": _polygons(comp),
        "bbox_um": _bbox(comp),
    }


def _write_json(path, payload):
    Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(Path(path).resolve())


def _pins_artifact(comp, bound, fallback):
    _, details = _ports(comp)
    if bound is None:
        return {
            "cell": comp.name,
            "source": fallback["source"],
            "reconstructed": fallback["reconstructed"],
            "boundary_note": fallback["boundary_note"],
            "pins": details,
        }
    pins = [
        {
            "name": name,
            "layer": dict(spec).get("layer"),
            "x_um": dict(spec).get("x_um"),
            "y_um": dict(spec).get("y_um"),
        }
        for name, spec in (bound.get("pins") or {}).items()
    ]
    return {
        "cell": comp.name,
        "source": "project-pin-map",
        "reconstructed": True,
        "boundary_note": None,
        "pins": pins,
    }


def _obstructions_artifact(comp, bound, fallback):
    if bound is None:
        return {
            "cell": comp.name,
            "source": fallback["source"],
            "reconstructed": fallback["reconstructed"],
            "boundary_note": fallback["boundary_note"],
            "obstructions": [],
        }
    return {
        "cell": comp.name,
        "source": "project-pin-map",
        "reconstructed": True,
        "boundary_note": None,
        "obstructions": list(bound.get("obstructions") or []),
    }


def _publish(comp, bound, artifacts, fallback):
    pins_path = _write_json(
        f"{comp.name}.pins.json",
        _pins_artifact(comp, bound, fallback["pins"]),
    )
    obs_path = _write_json(
        f"{comp.name}.obstructions.json",
        _obstructions_artifact(comp, bound, fallback["obstructions"]),
    )
    artifacts.append(
        {"kind": "pins", "cell": comp.name, "path": pins_path}
    )
    artifacts.append(
        {"kind": "obstructions", "cell": comp.name, "path": obs_path}
    )


def _activate(doc, cspdk_path):
    import gdsfactory as gf

    if doc is None:
        return gf, "", None
    pdk = doc.get("pdk", "generic")
    if pdk == "generic":
        gf.gpdk.PDK.activate()
        return gf, "generic", None
    if cspdk_path is not None:
        root = str(Path(cspdk_path).expanduser())
        if root not in sys.path:
            sys.path.insert(0, root)
    try:
        import cspdk
        from cspdk.si340 import activate_pdk
    except ImportError as exc:
        raise _MissingCspdk(str(exc)) from exc
    activate_pdk()
    from gdsfactory.pdk import get_active_pdk

    active = get_active_pdk()
    return gf, active.name, getattr(cspdk, "__version__", "unknown")


class _MissingCspdk(Exception):
    pass


def _build_cell(gf, entry):
    from gdsfactory.pdk import get_active_pdk

    active = get_active_pdk()
    cell = entry.get("cell")
    try:
        factory = active.cells[cell]
    except KeyError:
        raise _BadCell(
            f"Unknown cell {cell!r} in PDK {active.name!r}.", cell
        ) from None
    params = entry.get("params") or {}
    try:
        return factory(**params)
    except TypeError as exc:
        raise _BadCell(
            f"Bad params for cell {cell!r}: {exc}.", cell
        ) from exc


class _BadCell(Exception):
    def __init__(self, message, token):
        super().__init__(message)
        self.token = token


def _export_name(exports, index, component, extension):
    if isinstance(exports, list) and index < len(exports):
        name = (exports[index] or {}).get("filename")
        if isinstance(name, str) and name:
            return name
    return f"{component}{extension}"


_BUILT_FALLBACK = {
    "pins": {
        "source": "built-ports",
        "reconstructed": True,
        "boundary_note": None,
    },
    "obstructions": {
        "source": "built-ports",
        "reconstructed": False,
        "boundary_note": _BUILD_NOTE,
    },
}

_IMPORTED_FALLBACK = {
    "pins": {
        "source": "gds-ports",
        "reconstructed": False,
        "boundary_note": _BOUNDARY_NOTE,
    },
    "obstructions": {
        "source": "gds-ports",
        "reconstructed": False,
        "boundary_note": _BOUNDARY_NOTE,
    },
}


def _run_build(gf, doc):
    mappings = []
    artifacts = []
    for entry in doc["cells"]:
        comp = _build_cell(gf, entry)
        mappings.append(_mapping(entry["cell"], comp))
        _publish(comp, None, artifacts, _BUILT_FALLBACK)
    return mappings, artifacts, None, []


def _run_export(gf, doc, extension, writer):
    mappings = []
    artifacts = []
    notes = []
    matches = []
    exports = doc.get("exports") or []
    for index, entry in doc["cells"]:
        comp = _build_cell(gf, entry)
        mappings.append(_mapping(entry["cell"], comp))
        _publish(comp, None, artifacts, _BUILT_FALLBACK)
        filename = _export_name(exports, index, comp.name, extension)
        writer(comp, filename)
        path = str(Path(filename).resolve())
        artifacts.append(
            {"kind": "layout", "cell": comp.name, "path": path}
        )
        if extension == ".gds":
            mirror = gf.import_gds(filename)
            match = (
                mirror.name == comp.name
                and _polygons(mirror) == _polygons(comp)
                and _bbox(mirror) == _bbox(comp)
            )
            matches.append(match)
            notes.append(f"readback {filename}: match={match}.")
        else:
            notes.append(
                f"wrote {filename} ({Path(filename).stat().st_size} "
                "bytes, no readback probe for oasis)."
            )
    roundtrip = all(matches) if matches else None
    return mappings, artifacts, roundtrip, notes


def _run_import(gf, job):
    mappings = []
    artifacts = []
    pin_cells = (job.get("pin_map_doc") or {}).get("cells") or {}
    for source in job.get("gds_sources") or []:
        try:
            comp = gf.import_gds(source)
        except Exception as exc:
            raise _BadSource(
                f"Cannot import GDS {source}: {exc}.", source
            ) from exc
        mappings.append(_mapping(Path(source).name, comp))
        _publish(comp, pin_cells.get(comp.name), artifacts,
                 _IMPORTED_FALLBACK)
    if not mappings:
        raise _BadSource("Import found no GDS sources.", None)
    return mappings, artifacts, None, []


class _BadSource(Exception):
    def __init__(self, message, token):
        super().__init__(message)
        self.token = token


def main(argv):
    """Run one staged views job: job JSON in, envelope on stdout.

    Args:
        argv: Argument vector; argv[1] is the staged job JSON path.

    Returns:
        Process exit code: 0 on success, 2 on a bad
            cell/spec/source/format, 3 when gdsfactory or the named
            PDK is not importable.

    Raises:
        ValueError: Bad recipe or bad pin-map reference (raised and
            caught inside main into the error envelope — never
            escapes).
    """
    with open(argv[1], encoding="utf-8") as handle:
        job = json.load(handle)
    text = job.get("text", "")
    doc = job.get("doc")
    try:
        gf, active_pdk, cspdk_ver = _activate(doc, job.get("cspdk_path"))
    except ImportError as exc:
        _fail(
            "missing_dependency",
            f"gdsfactory is not importable: {exc} "
            "(uv sync --group layout).",
            None,
            None,
        )
        return 3
    except _MissingCspdk as exc:
        _fail(
            "missing_dependency",
            f"cspdk.si340 is not importable: {exc} "
            "(scripts/fetch_fixtures.py --only cspdk).",
            None,
            None,
        )
        return 3
    try:
        recipe = job.get("recipe")
        if recipe == "build_cells":
            mappings, artifacts, roundtrip, notes = _run_build(gf, doc)
        elif recipe == "export_gds":
            mappings, artifacts, roundtrip, notes = _run_export(
                gf, doc, ".gds", lambda comp, name: comp.write_gds(name)
            )
        elif recipe == "export_oasis":
            writer = getattr(gf.Component, "write_oas", None)
            if writer is None:
                raise ValueError(
                    "OASIS export needs Component.write_oas, absent "
                    f"in gdsfactory {getattr(gf, '__version__', '?')}."
                )
            mappings, artifacts, roundtrip, notes = _run_export(
                gf, doc, ".oas", lambda comp, name: comp.write_oas(name)
            )
        elif recipe == "import_gds":
            mappings, artifacts, roundtrip, notes = _run_import(gf, job)
        else:
            raise ValueError(f"Unknown recipe: {recipe!r}.")
    except _BadCell as exc:
        _fail("invalid_cell", str(exc), exc.token,
              _find_line(text, exc.token))
        return 2
    except _BadSource as exc:
        _fail("unreadable_source", str(exc), exc.token,
              _find_line(text, exc.token))
        return 2
    except ValueError as exc:
        _fail("unsupported_format", str(exc), recipe,
              _find_line(text, recipe))
        return 2
    print(
        json.dumps(
            {
                "ok": True,
                "gdsfactory_version": getattr(
                    gf, "__version__", "unknown"
                ),
                "result": {
                    "recipe": recipe,
                    "active_pdk": active_pdk,
                    "cspdk_version": cspdk_ver,
                    "mappings": mappings,
                    "artifacts": artifacts,
                    "diagnostics": {
                        "roundtrip_match": roundtrip,
                        "notes": notes,
                    },
                },
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
