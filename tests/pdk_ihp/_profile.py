"""Shared lane helpers: profile loading + IHP resolution (PDK-IHP).

Every lane proof resolves the PDK through docs/pdk/ihp/profile.yaml
(data, never PDK literals in logic). RED signal: the profile is
missing, so every proof fails on FileNotFoundError until the
profile entry lands.
"""

import importlib.util
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = REPO_ROOT / "docs" / "pdk" / "ihp" / "profile.yaml"
FIXTURES = Path(__file__).parent / "fixtures"


def load_profile():
    """Load the IHP lane profile (FileNotFoundError on the empty lane)."""
    if not PROFILE_PATH.is_file():
        raise FileNotFoundError(
            f"IHP lane profile not found: {PROFILE_PATH} "
            "(docs/pdk/ihp/profile.yaml)."
        )
    text = PROFILE_PATH.read_text()
    try:
        import yaml  # type: ignore
    except ImportError:
        from ruamel.yaml import YAML

        return YAML(typ="safe").load(text)
    return yaml.safe_load(text)


def ihp_root():
    """Root owning the profile relpaths: installed ihp package or $IHP_SOURCE.

    Returns None when neither is available (callers skip loudly).
    """
    spec = importlib.util.find_spec("ihp")
    if spec is not None and spec.origin:
        # <root>/ihp/__init__.py -> <root>
        return Path(spec.origin).resolve().parent.parent
    env = os.environ.get("IHP_SOURCE")
    if env:
        return Path(env)
    return None


def require_ihp_root():
    """Resolve the IHP tree or skip loudly (never fake-green)."""
    import pytest

    root = ihp_root()
    if root is None or not (root / "ihp" / "__init__.py").is_file():
        pytest.skip(
            "ihp tree unavailable (pip install ihp-gdsfactory==2.0.1 "
            "or set IHP_SOURCE to the SG13G2 wrapper checkout)"
        )
    return root
