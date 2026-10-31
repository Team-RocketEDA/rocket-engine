"""Shared lane helpers: profile loading + gf180mcu resolution (PDK-GF180).

Every lane proof resolves the PDK through docs/pdk/gf180/profile.yaml
(data, never PDK literals in logic). RED signal: the profile is
missing, so every proof fails on FileNotFoundError until the
profile entry lands.
"""

import importlib.util
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = REPO_ROOT / "docs" / "pdk" / "gf180" / "profile.yaml"
FIXTURES = Path(__file__).parent / "fixtures"
LANE_ID = "gf180"


def load_profile():
    """Load the gf180 lane profile (FileNotFoundError on the empty lane)."""
    if not PROFILE_PATH.is_file():
        raise FileNotFoundError(
            f"gf180 lane profile not found: {PROFILE_PATH} "
            "(docs/pdk/gf180/profile.yaml)."
        )
    import yaml

    return yaml.safe_load(PROFILE_PATH.read_text())


def pdk_root():
    """gf180mcu package dir: installed import first, else $PDK_GF180_SRC."""
    spec = importlib.util.find_spec("gf180mcu")
    if spec is not None and spec.origin:
        return Path(spec.origin).resolve().parent
    env = os.environ.get("PDK_GF180_SRC")
    if env:
        p = Path(env)
        if (p / "gf180mcu" / "__init__.py").is_file():
            return (p / "gf180mcu").resolve()
        if p.name == "gf180mcu" and (p / "__init__.py").is_file():
            return p.resolve()
    return None


def require_pdk():
    """Resolve + import-enable gf180mcu, or skip LOUDLY (never fake-green)."""
    root = pdk_root()
    if root is None:
        pytest.skip(
            "gf180 lane live: need gf180mcu 1.0.0 (pip, see "
            "docs/pdk/gf180/recipe.md) or $PDK_GF180_SRC pointing at the "
            "gdsfactory/gf180mcu source tree."
        )
    parent = str(root.parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)
    return root
