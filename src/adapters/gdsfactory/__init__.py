"""Gdsfactory layout smoke: import + build + cspdk attach + GDS roundtrip.

Smallest honest layout proof: gdsfactory 9.51.0 (uv.lock pin)
builds a generic straight and — with the vendored cspdk si340
PDK attached (rev 3323b17b, version 2.1.0) — the cornerstone
MZI, then a GDS write/read roundtrip preserves cell name,
polygon count, and bbox. Solver imports stay lazy so bare envs
fail loud (`missing_dependency`), never fake-green. The cspdk
tree is git-ignored vendor data: pass `cspdk_path`
(`scripts/fetch_fixtures.py --only cspdk`) where the package
is not installed. The full layout Engine adapter is
GdsfactoryViewsAdapter (generate_views, adapter.py); this smoke is
its qualification fixture.
"""

import sys
import tempfile
from pathlib import Path

from ..errors import AdapterError

GF_PIN = "9.51.0"
CSPDK_PIN = "2.1.0"
CSPDK_PDK = "cspdk.si340"


def gdsfactory_version():
    """Proven layout version, observable per run (uv.lock pin).

    Returns:
        Installed gdsfactory version, or "unknown" when the package
            carries no version attribute.

    Raises:
        AdapterError: missing_dependency when gdsfactory is not
            importable.
    """
    try:
        import gdsfactory as gf
    except ImportError as exc:
        raise AdapterError(
            "missing_dependency",
            f"gdsfactory is not importable: {exc} "
            "(uv sync --group layout).",
        ) from exc
    return getattr(gf, "__version__", "unknown")


def _ensure_cspdk(cspdk_path=None):
    """Import cspdk.si340 from the install or a vendored tree."""
    try:
        from cspdk.si340 import activate_pdk  # noqa: F401
        import cspdk

        return cspdk
    except ImportError:
        pass
    if cspdk_path is not None:
        root = str(Path(cspdk_path).expanduser())
        if root not in sys.path:
            sys.path.insert(0, root)
    try:
        from cspdk.si340 import activate_pdk  # noqa: F401
        import cspdk

        return cspdk
    except ImportError as exc:
        raise AdapterError(
            "missing_dependency",
            f"cspdk.si340 is not importable: {exc} "
            "(scripts/fetch_fixtures.py --only cspdk).",
        ) from exc


def cspdk_version(cspdk_path=None):
    """Vendored PDK version, observable per run (fetch pin).

    Args:
        cspdk_path: Vendored cspdk tree to import from when the
            package is not installed.

    Returns:
        Installed cspdk version, or "unknown" when the package
            carries no version attribute.

    Raises:
        AdapterError: missing_dependency when cspdk.si340 is not
            importable from either source.
    """
    return getattr(_ensure_cspdk(cspdk_path), "__version__", "unknown")


def _bbox_um(comp):
    box = comp.bbox()
    return [[float(box.left), float(box.bottom)],
            [float(box.right), float(box.top)]]


def _polygon_total(comp):
    return sum(len(polys) for polys in comp.get_polygons().values())


def run_layout_smoke(*, cell="mzi", pdk=CSPDK_PDK, cspdk_path=None,
                     gds_path=None):
    """Run the layout smoke live; return the build + roundtrip evidence.

    Returns `{gdsfactory_version, cspdk_version|None, active_pdk,
    cell, component, ports[], n_polygons, bbox_um, gds_path,
    roundtrip_cell, roundtrip_polygons, roundtrip_bbox_um,
    roundtrip_match}` — plain strings/floats, JSON-friendly.
    `pdk="generic"` builds from the gpdk cell library (no cspdk
    needed); otherwise the cspdk si340 PDK is attached first.

    Args:
        cell: Cell name to build from the active PDK.
        pdk: PDK to attach ("generic" skips cspdk).
        cspdk_path: Vendored cspdk tree when the package is not
            installed.
        gds_path: GDS output path; a temp file when omitted.

    Returns:
        Build + roundtrip evidence mapping (versions, ports,
            polygon counts, bboxes, roundtrip match).

    Raises:
        AdapterError: invalid_command on bad parameters or an
            unknown cell, missing_dependency where
            gdsfactory/cspdk are uninstalled.
    """
    if not isinstance(cell, str) or not cell:
        raise AdapterError(
            "invalid_command",
            f"Layout smoke needs a cell name, got {cell!r}.",
        )
    try:
        import gdsfactory as gf
    except ImportError as exc:
        raise AdapterError(
            "missing_dependency",
            f"gdsfactory is not importable: {exc} "
            "(uv sync --group layout).",
        ) from exc
    if pdk == "generic":
        gf.gpdk.PDK.activate()
        cspdk_ver = None
    else:
        cspdk = _ensure_cspdk(cspdk_path)
        cspdk_ver = getattr(cspdk, "__version__", "unknown")
        from cspdk.si340 import activate_pdk

        activate_pdk()
    from gdsfactory.pdk import get_active_pdk

    active = get_active_pdk()
    try:
        factory = active.cells[cell]
    except KeyError as exc:
        raise AdapterError(
            "invalid_command",
            f"Unknown cell {cell!r} in PDK {active.name!r}.",
        ) from exc
    comp = factory()
    ports = sorted(port.name for port in comp.ports)
    n_polygons = _polygon_total(comp)
    bbox = _bbox_um(comp)
    if gds_path is None:
        with tempfile.NamedTemporaryFile(
            suffix=".gds", prefix=f"gf_smoke_{cell}_", delete=False
        ) as handle:
            gds_path = handle.name
    comp.write_gds(gds_path)
    mirror = gf.import_gds(gds_path)
    rt_polygons = _polygon_total(mirror)
    rt_bbox = _bbox_um(mirror)
    match = (
        mirror.name == comp.name
        and rt_polygons == n_polygons
        and rt_bbox == bbox
    )
    return {
        "gdsfactory_version": getattr(gf, "__version__", "unknown"),
        "cspdk_version": cspdk_ver,
        "active_pdk": active.name,
        "cell": cell,
        "component": comp.name,
        "ports": ports,
        "n_polygons": n_polygons,
        "bbox_um": bbox,
        "gds_path": str(gds_path),
        "roundtrip_cell": mirror.name,
        "roundtrip_polygons": rt_polygons,
        "roundtrip_bbox_um": rt_bbox,
        "roundtrip_match": match,
    }
