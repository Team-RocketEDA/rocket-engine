"""PDK-UBC RED — lane proof: ebeam MZI build with golden expectations.

Valid RED = the lane profile does not exist yet, so the proof
fails on FileNotFoundError before touching any solver. GREEN
builds the profile's proof cell (ubcpdk mzi, delta_length=10)
and pins the goldens: pdk ubcpdk, ports o1..o4, 34 polygons,
the reference bbox, an exact-geometry GDS roundtrip, and
agreement with the lane fixture (upstream reference MZI GDS,
MIT). Skips LOUDLY (never fake-green) where gdsfactory/ubcpdk
are absent.

Note: the engine layout smoke (run_layout_smoke) is cspdk-wired
today, so the lane builds through ubcpdk directly; generalizing
the smoke is a shared-change request in docs/pdk/ubc/report.md.
"""

import hashlib
import importlib.util

import pytest

from ._profile import FIXTURES, PRECLONED_UBC, VENDORED_UBC, ensure_ubc, load_profile

FIXTURE_SHA256 = (
    "722b1aea10ea00c6046c97e08188ee6a604a31a72baeedea0f89b1f57fbc1bb1"
)
FIXTURE_SIZE = 24676

gf_present = importlib.util.find_spec("gdsfactory") is not None
ubc_present = (
    importlib.util.find_spec("ubcpdk") is not None
    or (VENDORED_UBC / "ubcpdk" / "__init__.py").is_file()
    or (PRECLONED_UBC / "ubcpdk" / "__init__.py").is_file()
)
needs_lane = pytest.mark.skipif(
    not (gf_present and ubc_present),
    reason="ubc lane live: need gdsfactory (uv sync --group layout) + "
    'ubcpdk 3.3.5 (pip) or a source tree '
    "(fixtures/upstream/ubc, scripts/fetch_fixtures.py --only ubc)",
)


def _fixture():
    gds = FIXTURES / "mzi_ref.gds"
    if not gds.is_file():
        raise FileNotFoundError(f"ubc lane fixture not found: {gds}.")
    data = gds.read_bytes()
    assert hashlib.sha256(data).hexdigest() == FIXTURE_SHA256
    assert len(data) == FIXTURE_SIZE
    return gds


def _polygons(comp):
    return sum(len(polys) for polys in comp.get_polygons().values())


def _bbox(comp):
    box = comp.bbox()
    return [
        [float(box.left), float(box.bottom)],
        [float(box.right), float(box.top)],
    ]


def _assert_bbox(got, want):
    flat_got = [c for corner in got for c in corner]
    flat_want = [c for corner in want for c in corner]
    assert flat_got == pytest.approx(flat_want)


@needs_lane
def test_lane_mzi_build_matches_goldens(tmp_path):
    import gdsfactory as gf

    profile = load_profile()  # RED: missing profile.yaml
    proof = profile["proofs"]["layout"]
    ubcpdk = ensure_ubc()
    assert ubcpdk.__version__ == profile["pins"]["ubcpdk"]
    assert gf.__version__ == profile["pins"]["gdsfactory"]

    ubcpdk.PDK.activate()
    comp = ubcpdk.PDK.cells[proof["cell"]](delta_length=10.0)
    assert gf.get_active_pdk().name == "ubcpdk"
    assert sorted(p.name for p in comp.ports) == proof["ports"]
    assert _polygons(comp) == proof["n_polygons"]
    _assert_bbox(_bbox(comp), proof["bbox_um"])

    gds_path = tmp_path / "lane_mzi.gds"
    comp.write_gds(gds_path)
    mirror = gf.import_gds(gds_path)
    assert mirror.name == comp.name
    assert _polygons(mirror) == proof["n_polygons"]
    _assert_bbox(_bbox(mirror), proof["bbox_um"])


@needs_lane
def test_lane_fixture_matches_built_mzi():
    import gdsfactory as gf

    profile = load_profile()  # RED: missing profile.yaml
    proof = profile["proofs"]["layout"]
    ubcpdk = ensure_ubc()
    ubcpdk.PDK.activate()
    comp = ubcpdk.PDK.cells[proof["cell"]](delta_length=10.0)
    ref = gf.import_gds(_fixture())
    assert _polygons(ref) == proof["n_polygons"]
    assert _polygons(ref) == _polygons(comp)
    _assert_bbox(_bbox(ref), _bbox(comp))
