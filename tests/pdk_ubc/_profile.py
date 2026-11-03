"""Shared lane helpers: profile loading + ubcpdk resolution (PDK-UBC).

Every lane proof resolves the PDK through docs/pdk/ubc/profile.yaml
(data, never PDK literals in logic). RED signal: the profile is
missing, so every proof fails on FileNotFoundError until the
profile entry lands.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = REPO_ROOT / "docs" / "pdk" / "ubc" / "profile.yaml"
FIXTURES = Path(__file__).parent / "fixtures"
VENDORED_UBC = REPO_ROOT / "fixtures" / "upstream" / "ubc"
PRECLONED_UBC = Path("/tmp/pdk-sources/ubc")


def load_profile():
    """Load the ubc lane profile (FileNotFoundError on the empty lane)."""
    if not PROFILE_PATH.is_file():
        raise FileNotFoundError(
            f"ubc lane profile not found: {PROFILE_PATH} "
            "(docs/pdk/ubc/profile.yaml)."
        )
    text = PROFILE_PATH.read_text()
    try:
        import yaml  # type: ignore
    except ImportError:
        from ruamel.yaml import YAML

        return YAML(typ="safe").load(text)
    return yaml.safe_load(text)


def find_ubc_root():
    """Source root owning the profile relpaths (installed or trees).

    Order: installed ubcpdk package, vendored fixtures/upstream/ubc
    (scripts/fetch_fixtures.py --only ubc, integrator-owned), then
    the pre-cloned /tmp/pdk-sources/ubc tree. Returns None when no
    source is available (callers skip loudly, never fake-green).
    """
    import importlib.util

    spec = importlib.util.find_spec("ubcpdk")
    if spec is not None and spec.origin:
        # <root>/ubcpdk/__init__.py -> <root>
        return Path(spec.origin).resolve().parents[1]
    for candidate in (VENDORED_UBC, PRECLONED_UBC):
        if (candidate / "ubcpdk" / "__init__.py").is_file():
            return candidate
    return None


def ensure_ubc():
    """Import ubcpdk from the install or a source tree (loud if absent)."""
    import importlib.util
    import sys

    if importlib.util.find_spec("ubcpdk") is None:
        root = find_ubc_root()
        if root is None:
            raise ImportError(
                "ubcpdk is not importable: no installed package and no "
                f"source tree at {VENDORED_UBC} or {PRECLONED_UBC} "
                '(uv pip install "ubcpdk==3.3.5").'
            )
        sys.path.insert(0, str(root))
    import ubcpdk

    return ubcpdk
