"""Circulax time-domain smoke: smallest honest RC transient.

A V step driving R + C to GND, compiled via kfnetlist and run with
`Circuit.transient` from a discharged (`y0=zeros`) start. Verified
against circulax 0.2.5: good RC (1k/1nF, tau=1us) charges
Vc(1us)=0.6321, Vc(5us)=0.9933; slow RC (100k/1nF) sits at 0.0488.
The same 0.9 V @5us threshold passes the good run and fails the slow
run — the good-vs-bad signal. Solver imports stay lazy so bare envs
fail loud (`missing_dependency`), never fake-green. A full
`deck.tool: circulax` Engine adapter is follow-up, out of scope.
"""

from ..errors import AdapterError

CIRCULAX_PIN = "0.2.5"


def circulax_version():
    """Proven solver version, observable per run (uv.lock pin).

    Returns:
        Installed circulax version, or "unknown" when the package
            carries no version attribute.

    Raises:
        AdapterError: missing_dependency when circulax is not
            importable.
    """
    try:
        import circulax
    except ImportError as exc:
        raise AdapterError(
            "missing_dependency",
            f"circulax is not importable: {exc} "
            "(uv sync --group photonic).",
        ) from exc
    return getattr(circulax, "__version__", "unknown")


def run_rc_step(*, R=1e3, C=1e-9, V=1.0, t1=5e-6, points=11, dt0=1e-8):
    """Run the RC step transient live; return the cap voltage trace.

    Args:
        R: Resistance in ohms (positive).
        C: Capacitance in farads (positive).
        V: Step voltage in volts.
        t1: End time in seconds (positive).
        points: Samples on the grid (at least 2).
        dt0: Initial solver step in seconds (positive).

    Returns:
        `{circulax_version, R, C, V, t_s[], vc_V[], final_V}` —
            plain floats, JSON-friendly.

    Raises:
        AdapterError: invalid_command on bad parameters,
            missing_dependency where circulax is uninstalled.
    """
    if not R > 0 or not C > 0 or not t1 > 0 or not dt0 > 0:
        raise AdapterError(
            "invalid_command",
            f"RC step needs positive R/C/t1/dt0, got R={R!r} C={C!r} "
            f"t1={t1!r} dt0={dt0!r}.",
        )
    if not isinstance(points, int) or points < 2:
        raise AdapterError(
            "invalid_command", f"RC step needs points >= 2, got {points!r}."
        )
    try:
        import jax.numpy as jnp
        import kfnetlist as kfnl
        from circulax import compile_circuit
        from circulax.components.electronic import (
            Capacitor,
            Resistor,
            VoltageSource,
        )
    except ImportError as exc:
        raise AdapterError(
            "missing_dependency",
            f"circulax is not importable: {exc} "
            "(uv sync --group photonic).",
        ) from exc
    netlist = kfnl.Netlist()
    netlist.create_inst(name="V1", kcl="", component="vsource", settings={"V": V})
    netlist.create_inst(name="R1", kcl="", component="resistor", settings={"R": R})
    netlist.create_inst(name="C1", kcl="", component="capacitor", settings={"C": C})
    netlist.create_inst(name="GND", kcl="", component="ground")
    netlist.create_net(kfnl.PortRef("V1", "p1"), kfnl.PortRef("R1", "p1"))
    netlist.create_net(kfnl.PortRef("V1", "p2"), kfnl.PortRef("GND", "p1"))
    netlist.create_net(kfnl.PortRef("R1", "p2"), kfnl.PortRef("C1", "p1"))
    netlist.create_net(kfnl.PortRef("C1", "p2"), kfnl.PortRef("GND", "p1"))
    circuit = compile_circuit(
        netlist,
        {"vsource": VoltageSource, "resistor": Resistor, "capacitor": Capacitor},
    )
    grid = jnp.linspace(0, t1, points)
    solution = circuit.transient(
        t0=0.0, t1=t1, dt0=dt0, saveat=grid, y0=jnp.zeros(circuit.sys_size)
    )
    cap = circuit.port_map["C1,p1"]
    times = [float(t) for t in solution.ts]
    voltages = [float(row[cap]) for row in solution.ys]
    return {
        "circulax_version": circulax_version(),
        "R": R,
        "C": C,
        "V": V,
        "t_s": times,
        "vc_V": voltages,
        "final_V": voltages[-1],
    }
