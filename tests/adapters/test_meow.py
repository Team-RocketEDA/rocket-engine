"""MEOW-LIVE RED — EME smoke (strip-waveguide S-matrix) + locality probe.

Valid RED = `rocket_engine.adapters.meow` does not exist yet, so
every test fails on ModuleNotFoundError. Smallest honest EME
circuit: a 500x220nm Si strip on SiO2 at 1550nm, 2 modes solved
with meow's tidy3d FDE backend, cascaded over a 10um cell with
meow's SAX EME backend. Verified against meow 0.15.0: matched
guide transmits T=1.0/R=0.0; an abrupt 0.5->1.0um width step
drops the fundamental to T=0.877/R=0.0009 — the good-vs-bad
signal. The locality probe runs the same smoke with
`socket.connect` amputated: GREEN proves no cloud call on the
default path. Live tests skip (never fake-green) where meow is
uninstalled; the import-shape and validation tests need no
solver.
"""

import importlib.util

import pytest

meow_present = importlib.util.find_spec("meow") is not None
needs_meow = pytest.mark.skipif(
    not meow_present,
    reason="meow not installed (uv sync)",
)

MEOW_PIN = "0.15.0"
TIDY3D_PIN = "2.10.0"
NEFF_TE0 = 2.3108
WL_UM = 1.55
CELL_UM = 10.0


def test_meow_smoke_helper_exists():
    from rocket_engine.adapters.meow import (  # RED: missing module
        meow_version,
        run_eme_smoke,
        tidy3d_version,
    )

    assert callable(run_eme_smoke)
    assert callable(meow_version)
    assert callable(tidy3d_version)


def test_meow_rejects_bad_parameters():
    from rocket_engine.adapters.errors import AdapterError
    from rocket_engine.adapters.meow import run_eme_smoke  # RED: missing module

    with pytest.raises(AdapterError) as bad_width:
        run_eme_smoke(widths_um=[0.5, -1.0])
    assert bad_width.value.code == "invalid_command"
    with pytest.raises(AdapterError) as bad_modes:
        run_eme_smoke(widths_um=[0.5], num_modes=0)
    assert bad_modes.value.code == "invalid_command"


@needs_meow
def test_meow_reports_proven_solver_version():
    # MEOW-LIVE: the proven solver versions are observable per run,
    # not prose — the smoke must name meow 0.15.0 over tidy3d
    # 2.10.0 (uv.lock). tidy3d's version is read from installed
    # metadata: engine code never imports the cloud client.
    import meow

    from rocket_engine.adapters.meow import meow_version, tidy3d_version

    assert meow.__version__ == MEOW_PIN
    assert meow_version() == MEOW_PIN
    assert tidy3d_version() == TIDY3D_PIN


@needs_meow
def test_meow_matched_guide_transmits():
    from rocket_engine.adapters.meow import run_eme_smoke  # RED: missing module

    got = run_eme_smoke(widths_um=[0.5])
    assert got["meow_version"] == MEOW_PIN
    assert got["tidy3d_version"] == TIDY3D_PIN
    assert got["neff_re"][0] == pytest.approx(NEFF_TE0, abs=5e-3)
    assert got["transmission"] == pytest.approx(1.0, abs=1e-6)
    assert got["reflection"] == pytest.approx(0.0, abs=1e-9)


@needs_meow
def test_meow_mismatched_interface_drops_transmission():
    from rocket_engine.adapters.meow import run_eme_smoke  # RED: missing module

    got = run_eme_smoke(widths_um=[0.5, 1.0])
    assert got["transmission"] == pytest.approx(0.877, abs=0.02)
    assert got["transmission"] < 0.95
    assert got["reflection"] > 0.0
    assert got["transmission"] + got["reflection"] < 1.0


@needs_meow
def test_meow_cascade_phase_matches_analytic():
    # Plumbing oracle: the cascaded S21 phase must equal the
    # analytic propagation phase 2*pi*neff*L/wl (mod 2pi),
    # computed here from the reported neff, not via meow.
    import numpy as np

    from rocket_engine.adapters.meow import run_eme_smoke  # RED: missing module

    got = run_eme_smoke(widths_um=[0.5])
    expected = (2 * np.pi * got["neff_re"][0] / WL_UM * CELL_UM) % (2 * np.pi)
    delta = abs((got["s21_phase_rad"] - expected + np.pi) % (2 * np.pi) - np.pi)
    assert delta == pytest.approx(0.0, abs=1e-9)


@needs_meow
def test_meow_smoke_runs_with_network_blocked(monkeypatch):
    # Locality probe: with socket connects amputated, the smoke
    # must still pass — no cloud call on the default path.
    import socket

    from rocket_engine.adapters.meow import run_eme_smoke  # RED: missing module

    def _no_network(*args, **kwargs):
        raise AssertionError("network connect attempted on smoke path")

    monkeypatch.setattr(socket.socket, "connect", _no_network)
    got = run_eme_smoke(widths_um=[0.5])
    assert got["transmission"] == pytest.approx(1.0, abs=1e-6)
