"""Shared lane helpers: profile loading + cspdk resolution (PDK-CSPDK).

Every lane proof resolves the PDK through docs/pdk/cspdk/profile.yaml
(data, never PDK literals in logic). RED signal: the profile is
missing, so every proof fails on FileNotFoundError until the
profile entry lands.
"""

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = REPO_ROOT / "docs" / "pdk" / "cspdk" / "profile.yaml"
FIXTURES = Path(__file__).parent / "fixtures"
VENDORED_CSPDK = REPO_ROOT / "fixtures" / "upstream" / "cspdk"
PRECLONED_CSPDK = Path("/tmp/pdk-sources/cspdk")


def load_profile():
    """Load the cspdk lane profile (FileNotFoundError on the empty lane)."""
    if not PROFILE_PATH.is_file():
        raise FileNotFoundError(
            f"cspdk lane profile not found: {PROFILE_PATH} "
            "(docs/pdk/cspdk/profile.yaml)."
        )
    text = PROFILE_PATH.read_text()
    try:
        import yaml  # type: ignore
    except ImportError:
        from ruamel.yaml import YAML

        return YAML(typ="safe").load(text)
    return yaml.safe_load(text)


def _has_si340(root):
    return (Path(root) / "cspdk" / "si340" / "__init__.py").is_file()


def find_cspdk_root():
    """Source root owning the profile relpaths (installed or trees).

    Order: installed cspdk package, vendored fixtures/upstream/cspdk
    (scripts/fetch_fixtures.py --only cspdk, integrator-owned), then
    the pre-cloned /tmp/pdk-sources/cspdk tree. Returns None when no
    source is available; callers skip LOUDLY (never fake-green).
    """
    spec = importlib.util.find_spec("cspdk")
    if spec is not None and spec.origin is not None:
        root = Path(spec.origin).parent.parent
        if _has_si340(root):
            return root
    if _has_si340(VENDORED_CSPDK):
        return VENDORED_CSPDK
    if _has_si340(PRECLONED_CSPDK):
        return PRECLONED_CSPDK
    return None


def ensure_cspdk():
    """Import cspdk.si340 from the install or a known tree."""
    try:
        import cspdk.si340  # noqa: F401
        import cspdk

        return cspdk
    except ImportError:
        pass
    root = find_cspdk_root()
    if root is not None and str(root) not in sys.path:
        sys.path.insert(0, str(root))
    import cspdk.si340  # noqa: F401
    import cspdk

    return cspdk
