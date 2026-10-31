"""Shared lane helpers: profile loading + sky130 resolution (PDK-SKY130GF).

Every lane proof resolves the PDK through docs/pdk/sky130gf/profile.yaml
(data, never PDK literals in logic). RED signal: the profile is
missing, so every proof fails on FileNotFoundError until the
profile entry lands.

Standalone by design: no rocket_engine imports, so the lane suite
runs both under the repo venv (live proofs skip when the pip
package is absent — never fake-green) and under a scratch env
with the pinned pip package (full green).
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = REPO_ROOT / "docs" / "pdk" / "sky130gf" / "profile.yaml"
FIXTURES = Path(__file__).parent / "fixtures"


def load_profile():
    """Load the sky130gf lane profile (FileNotFoundError on the empty lane)."""
    if not PROFILE_PATH.is_file():
        raise FileNotFoundError(
            f"sky130gf lane profile not found: {PROFILE_PATH} "
            "(docs/pdk/sky130gf/profile.yaml)."
        )
    text = PROFILE_PATH.read_text()
    try:
        import yaml  # type: ignore
    except ImportError:
        from ruamel.yaml import YAML

        return YAML(typ="safe").load(text)
    return yaml.safe_load(text)


def sky130_root():
    """Site-packages root owning the profile relpaths, or None if absent."""
    import importlib.util

    spec = importlib.util.find_spec("sky130")
    if spec is None or spec.origin is None:
        return None
    # <root>/sky130/__init__.py -> <root>
    return Path(spec.origin).resolve().parents[1]


def bbox_list(cell):
    """[xmin, ymin, xmax, ymax] floats for a gdsfactory component."""
    box = cell.bbox()
    return [float(box.left), float(box.bottom), float(box.right), float(box.top)]


def polygon_count(cell):
    """Total polygon count across all layers of a gdsfactory component."""
    polys = cell.get_polygons()
    if isinstance(polys, dict):
        return sum(len(v) for v in polys.values())
    return len(polys)
