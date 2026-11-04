"""CIRCULAX-LIVE RED — time-domain transient smoke (RC step).

Valid RED = `rocket_engine.adapters.circulax` does not exist yet, so
every test fails on ModuleNotFoundError. Smallest honest circulax
circuit: a V step driving R + C to GND, compiled via kfnetlist and
run with Circuit.transient from a discharged (y0=zeros) start.
Verified against circulax 0.2.5: good RC (1k/1nF, tau=1us) charges
Vc(1us)=0.6321, Vc(5us)=0.9933 (1-e^-t/tau to 1e-3); slow RC
(100k/1nF, tau=100us) sits at Vc(5us)=0.0488. Good-vs-bad: the same
0.9 V @5us threshold passes the good run and fails the slow run,
both live. Live tests skip (never fake-green) where circulax is
uninstalled; the import-shape test needs no solver.
"""

import importlib.util

import pytest

circulax_present = importlib.util.find_spec("circulax") is not None
needs_circulax = pytest.mark.skipif(
    not circulax_present,
    reason="circulax not installed (uv sync)",
)

CIRCULAX_PIN = "0.2.5"
THRESHOLD_V = 0.9
T1_S = 5e-6


def test_circulax_smoke_helper_exists():
    from rocket_engine.adapters.circulax import (  # RED: missing module
        circulax_version,
        run_rc_step,
    )

    assert callable(run_rc_step)
    assert callable(circulax_version)


@needs_circulax
def test_circulax_reports_proven_solver_version():
    # CIRCULAX-LIVE: the proven solver version is observable per run,
    # not prose — the smoke must name circulax 0.2.5 (uv.lock).
    import circulax

    from rocket_engine.adapters.circulax import circulax_version, run_rc_step

    assert circulax.__version__ == CIRCULAX_PIN
    assert circulax_version() == CIRCULAX_PIN
    assert run_rc_step()["circulax_version"] == CIRCULAX_PIN


@needs_circulax
def test_circulax_transient_rc_charges_to_source():
    from rocket_engine.adapters.circulax import run_rc_step  # RED: missing module

    got = run_rc_step(R=1e3, C=1e-9, V=1.0, t1=T1_S, points=11)
    assert got["t_s"] == pytest.approx([i * 0.5e-6 for i in range(11)], abs=1e-12)
    assert got["vc_V"][2] == pytest.approx(0.6321, abs=1e-3)  # t=1us
    assert got["final_V"] == pytest.approx(0.9933, abs=1e-3)
    assert got["final_V"] > THRESHOLD_V


@needs_circulax
def test_circulax_transient_slow_rc_misses_threshold():
    from rocket_engine.adapters.circulax import run_rc_step  # RED: missing module

    got = run_rc_step(R=100e3, C=1e-9, V=1.0, t1=T1_S, points=11)
    assert got["final_V"] == pytest.approx(0.0488, abs=1e-3)
    assert got["final_V"] < 0.1
    assert got["final_V"] < THRESHOLD_V


@needs_circulax
def test_circulax_helper_matches_raw_solver():
    # Oracle check: helper numbers reproduced against circulax
    # directly, not against the helper under test.
    import jax.numpy as jnp
    import kfnetlist as kfnl
    from circulax import compile_circuit
    from circulax.components.electronic import (
        Capacitor,
        Resistor,
        VoltageSource,
    )

    from rocket_engine.adapters.circulax import run_rc_step  # RED: missing module

    nl = kfnl.Netlist()
    nl.create_inst(name="V1", kcl="", component="vsource", settings={"V": 1.0})
    nl.create_inst(name="R1", kcl="", component="resistor", settings={"R": 1e3})
    nl.create_inst(name="C1", kcl="", component="capacitor", settings={"C": 1e-9})
    nl.create_inst(name="GND", kcl="", component="ground")
    nl.create_net(kfnl.PortRef("V1", "p1"), kfnl.PortRef("R1", "p1"))
    nl.create_net(kfnl.PortRef("V1", "p2"), kfnl.PortRef("GND", "p1"))
    nl.create_net(kfnl.PortRef("R1", "p2"), kfnl.PortRef("C1", "p1"))
    nl.create_net(kfnl.PortRef("C1", "p2"), kfnl.PortRef("GND", "p1"))
    ckt = compile_circuit(
        nl, {"vsource": VoltageSource, "resistor": Resistor, "capacitor": Capacitor}
    )
    ts = jnp.linspace(0, T1_S, 11)
    sol = ckt.transient(t0=0.0, t1=T1_S, dt0=1e-8, saveat=ts, y0=jnp.zeros(ckt.sys_size))
    raw_final = float(sol.ys[-1][ckt.port_map["C1,p1"]])

    got = run_rc_step(R=1e3, C=1e-9, V=1.0, t1=T1_S, points=11)
    assert got["final_V"] == pytest.approx(raw_final, abs=1e-9)
    assert [round(v, 6) for v in got["vc_V"]] == [
        round(float(row[ckt.port_map["C1,p1"]]), 6) for row in sol.ys
    ]
