"""Shared lane helpers: profile loading + ASAP7 source resolution (PDK-ASAP7).

Every lane proof resolves the PDK through docs/pdk/asap7/profile.yaml
(data, never PDK literals in logic). RED signal: the profile is
missing, so every proof fails on FileNotFoundError until the
profile entry lands.

ASAP7 has no pip package and no gdsfactory PDK: sources resolve to
the pre-cloned trees (wrapper docs + separately cloned 7.5-track
stdcell library). Callers skip loudly, never fake-green.
"""

import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = REPO_ROOT / "docs" / "pdk" / "asap7" / "profile.yaml"
FIXTURES = Path(__file__).parent / "fixtures"
PRECLONED_WRAPPER = Path("/tmp/pdk-sources/asap7")
PRECLONED_LIB = Path("/tmp/pdk-sources/asap7sc7p5t_28")


def load_profile():
    """Load the asap7 lane profile (FileNotFoundError on the empty lane)."""
    if not PROFILE_PATH.is_file():
        raise FileNotFoundError(
            f"asap7 lane profile not found: {PROFILE_PATH} "
            "(docs/pdk/asap7/profile.yaml)."
        )
    text = PROFILE_PATH.read_text()
    try:
        import yaml  # type: ignore
    except ImportError:
        from ruamel.yaml import YAML

        return YAML(typ="safe").load(text)
    return yaml.safe_load(text)


def find_wrapper_root():
    """Wrapper repo root (docs + pointers; submodules NOT initialized)."""
    if (PRECLONED_WRAPPER / "README.md").is_file():
        return PRECLONED_WRAPPER
    return None


def find_lib_root():
    """7.5-track stdcell library root (LEF/LIB/GDS/Verilog/techlef)."""
    if (PRECLONED_LIB / "LEF").is_dir() and (PRECLONED_LIB / "GDS").is_dir():
        return PRECLONED_LIB
    return None


def require_tool(name):
    """PATH lookup for a lane tool (loud FileNotFoundError if absent)."""
    exe = shutil.which(name)
    if exe is None:
        raise FileNotFoundError(
            f"lane tool not on PATH: {name} (system read-only input)."
        )
    return exe


def run_klayout_batch(script_text, timeout=300):
    """Run a KLayout batch script (-b -r); returns CompletedProcess."""
    import tempfile

    klayout = require_tool("klayout")
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", prefix="asap7lane_", delete=False
    ) as fh:
        fh.write(script_text)
        script_path = fh.name
    try:
        return subprocess.run(
            [klayout, "-b", "-r", script_path],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    finally:
        Path(script_path).unlink(missing_ok=True)
