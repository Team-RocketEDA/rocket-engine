"""PDK-CSPDK lane proof: SAX-over-cspdk sim, golden 1550 nm (RED-first).

Follows the PDK's own sample (cspdk/si340/samples/
circuit_simulations_sc340.py): sax.circuit over the si340 MZI netlist
with PDK.models. RED = the lane profile is missing, so the sim fails
before any solver runs. GREEN = the strip C-band MZI
(delta_length=10) reproduces the pinned 1550 nm transmission pair.
Skips LOUDLY (never fake-green) where sax/gdsfactory/cspdk are
uninstalled.
"""

import importlib.util

import pytest

from ._profile import ensure_cspdk, load_profile

sax_present = importlib.util.find_spec("sax") is not None
gf_present = importlib.util.find_spec("gdsfactory") is not None
needs_sim = pytest.mark.skipif(
    not (sax_present and gf_present),
    reason="sax/gdsfactory not installed (photonic + layout groups)",
)

WL_UM = 1.55
T_CROSS_1550 = 0.8140825560639245
T_BAR_1550 = 0.05688103389215629


def _simulate_1550():
    load_profile()  # RED gate: the lane profile owns this proof.
    ensure_cspdk()
    import sax

    from cspdk.si340 import PDK, cells

    PDK.activate()
    assert len(PDK.models) == 39
    circuit, _ = sax.circuit(
        cells.mzi_sc(delta_length=10.0).get_netlist(), models=PDK.models
    )
    return circuit(wl=WL_UM)


@needs_sim
def test_si340_mzi_sax_cross_transmission():
    import jax.numpy as jnp

    S = _simulate_1550()
    assert float(jnp.abs(S["o1", "o2"]) ** 2) == pytest.approx(
        T_CROSS_1550, rel=1e-6
    )


@needs_sim
def test_si340_mzi_sax_bar_transmission():
    import jax.numpy as jnp

    S = _simulate_1550()
    assert float(jnp.abs(S["o1", "o3"]) ** 2) == pytest.approx(
        T_BAR_1550, rel=1e-6
    )
