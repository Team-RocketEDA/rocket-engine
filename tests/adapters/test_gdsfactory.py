"""GF-SMOKE RED — gdsfactory layout smoke (import + build + cspdk + GDS roundtrip).

Valid RED = `rocket_engine.adapters.gdsfactory` does not exist yet, so
every test fails on ModuleNotFoundError. Smallest honest layout
proof: import gdsfactory 9.51.0 (uv.lock pin), build a generic
straight, attach the vendored cspdk si340 PDK (rev 3323b17b,
version 2.1.0) and build its MZI, then GDS write/read roundtrip
with polygon-count + bbox equality. Live tests skip (never
fake-green) where gdsfactory/cspdk are uninstalled; the
import-shape and validation tests need no solver.
"""

import importlib.util
from pathlib import Path

import pytest

gf_present = importlib.util.find_spec("gdsfactory") is not None
needs_gf = pytest.mark.skipif(
    not gf_present,
    reason="gdsfactory not installed (uv sync --group layout)",
)

REPO_ROOT = Path(__file__).resolve().parents[2]
VENDORED_CSPDK = REPO_ROOT / "fixtures" / "upstream" / "cspdk"
cspdk_present = (
    importlib.util.find_spec("cspdk") is not None
    or (VENDORED_CSPDK / "cspdk" / "si340" / "__init__.py").exists()
)
needs_cspdk = pytest.mark.skipif(
    not (gf_present and cspdk_present),
    reason="cspdk si340 unavailable (scripts/fetch_fixtures.py --only cspdk)",
)

GF_PIN = "9.51.0"
CSPDK_PIN = "2.1.0"


def test_gdsfactory_smoke_helper_exists():
    from rocket_engine.adapters.gdsfactory import (  # RED: missing module
        cspdk_version,
        gdsfactory_version,
        run_layout_smoke,
    )

    assert callable(run_layout_smoke)
    assert callable(gdsfactory_version)
    assert callable(cspdk_version)


def test_gdsfactory_rejects_bad_parameters():
    from rocket_engine.adapters.errors import AdapterError
    from rocket_engine.adapters.gdsfactory import (  # RED: missing module
        run_layout_smoke,
    )

    with pytest.raises(AdapterError) as empty_cell:
        run_layout_smoke(cell="")
    assert empty_cell.value.code == "invalid_command"
    with pytest.raises(AdapterError) as null_cell:
        run_layout_smoke(cell=None)
    assert null_cell.value.code == "invalid_command"


@needs_gf
def test_gdsfactory_reports_proven_solver_version():
    # GF-SMOKE: the proven layout version is observable per run,
    # not prose — the smoke must name gdsfactory 9.51.0 (uv.lock).
    import gdsfactory as gf

    from rocket_engine.adapters.gdsfactory import gdsfactory_version

    assert gf.__version__ == GF_PIN
    assert gdsfactory_version() == GF_PIN


@needs_gf
def test_gdsfactory_builds_generic_component():
    from rocket_engine.adapters.gdsfactory import run_layout_smoke  # RED

    got = run_layout_smoke(cell="straight", pdk="generic")
    assert got["gdsfactory_version"] == GF_PIN
    assert got["active_pdk"] == "generic"
    assert got["ports"]
    assert got["n_polygons"] > 0


@needs_cspdk
def test_gdsfactory_attaches_cspdk_cells():
    from rocket_engine.adapters.gdsfactory import run_layout_smoke  # RED

    got = run_layout_smoke(cell="mzi", cspdk_path=str(VENDORED_CSPDK))
    assert got["cspdk_version"] == CSPDK_PIN
    assert got["active_pdk"] == "cornerstone_si340"
    assert got["cell"] == "mzi"
    assert sorted(got["ports"]) == ["o1", "o2", "o3"]
    assert got["n_polygons"] > 0


@needs_cspdk
def test_gdsfactory_gds_roundtrip_preserves_layout(tmp_path):
    from rocket_engine.adapters.gdsfactory import run_layout_smoke  # RED

    gds = tmp_path / "mzi.gds"
    got = run_layout_smoke(
        cell="mzi", cspdk_path=str(VENDORED_CSPDK), gds_path=str(gds)
    )
    assert gds.exists()
    assert got["roundtrip_cell"] == got["component"]
    assert got["roundtrip_polygons"] == got["n_polygons"]
    assert got["roundtrip_bbox_um"] == got["bbox_um"]
    assert got["roundtrip_match"] is True


@needs_cspdk
def test_gdsfactory_rejects_unknown_cell():
    from rocket_engine.adapters.errors import AdapterError
    from rocket_engine.adapters.gdsfactory import run_layout_smoke  # RED

    with pytest.raises(AdapterError) as unknown:
        run_layout_smoke(cell="no_such_cell", cspdk_path=str(VENDORED_CSPDK))
    assert unknown.value.code == "invalid_command"
