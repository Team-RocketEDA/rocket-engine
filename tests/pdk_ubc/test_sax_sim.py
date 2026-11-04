"""PDK-UBC RED — lane proof: SAX-over-ubcpdk sim with goldens.

Valid RED = the lane profile does not exist yet, so the proof
fails on FileNotFoundError before touching any solver. GREEN
runs sax.circuit(netlist, models=PDK.models) on the ebeam MZI
(delta_length 10 and 100) and pins the 1550 nm transmission
goldens (sax 0.18.2, ubcpdk 3.3.5, 32 models). Skips LOUDLY
where sax/gdsfactory/ubcpdk are absent.
"""

import importlib.util

import pytest

from ._profile import PRECLONED_UBC, VENDORED_UBC, ensure_ubc, load_profile

sax_present = importlib.util.find_spec("sax") is not None
gf_present = importlib.util.find_spec("gdsfactory") is not None
ubc_present = (
    importlib.util.find_spec("ubcpdk") is not None
    or (VENDORED_UBC / "ubcpdk" / "__init__.py").is_file()
    or (PRECLONED_UBC / "ubcpdk" / "__init__.py").is_file()
)
needs_lane = pytest.mark.skipif(
    not (sax_present and gf_present and ubc_present),
    reason="ubc lane optical live: need sax (uv sync) + "
    "gdsfactory (uv sync) + ubcpdk 3.3.5 (pip) or a "
    "source tree (fixtures/upstream/ubc, "
    "scripts/fetch_fixtures.py --only ubc)",
)

# Goldens: |S|^2 at 1550 nm for mzi(delta_length), sax 0.18.2,
# ubcpdk 3.3.5 models (32). o1/o2 = splitter side; o3/o4 =
# combiner side. Coupler models interpolate the PDK's .nc tables
# (semi-analytical, documented "use at your own risk"), so these
# pin the models' behavior, not foundry data.
GOLDENS = {
    10.0: {"o1>o3": 0.18527868264398265, "o1>o4": 0.7948270469902452},
    100.0: {"o1>o3": 0.021840364329025166, "o1>o4": 0.9547455489516119},
}


def _simulate(delta_length):
    import jax.numpy as jnp
    import sax

    ubcpdk = ensure_ubc()
    ubcpdk.PDK.activate()
    assert len(ubcpdk.PDK.models) == 32
    comp = ubcpdk.PDK.cells["mzi"](delta_length=delta_length)
    circuit, _ = sax.circuit(comp.get_netlist(), models=ubcpdk.PDK.models)
    scatter = circuit(wl=jnp.asarray([1.55]))
    out = {}
    for from_port in ("o1", "o2", "o3", "o4"):
        for to_port in ("o1", "o2", "o3", "o4"):
            out[f"{from_port}>{to_port}"] = float(
                jnp.abs(scatter[from_port, to_port])[0] ** 2
            )
    return out


@needs_lane
def test_lane_sax_mzi_matches_goldens():
    profile = load_profile()  # RED: missing profile.yaml
    assert profile["proofs"]["optical"]["model"] == "ubcpdk PDK.models"
    assert profile["proofs"]["optical"]["circuit"] == "mzi"
    assert profile["proofs"]["optical"]["at_nm"] == 1550.0
    for delta_length, want in GOLDENS.items():
        got = _simulate(delta_length)
        for pair, golden in want.items():
            assert got[pair] == pytest.approx(golden, rel=1e-9), (
                delta_length,
                pair,
            )
        # Reciprocity + isolation/reflection structure of the stack.
        assert got["o3>o1"] == pytest.approx(got["o1>o3"], rel=1e-12)
        assert got["o4>o1"] == pytest.approx(got["o1>o4"], rel=1e-12)
        assert got["o1>o1"] == pytest.approx(0.0, abs=1e-12)
        assert got["o1>o2"] == pytest.approx(0.0, abs=1e-12)
