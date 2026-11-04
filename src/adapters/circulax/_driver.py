"""Staged circulax sim driver: job JSON in, result envelope JSON on stdout.

The adapter copies this file into the run workdir next to
`circulax_job.json` and executes `python circulax_driver.py
circulax_job.json`. One marker-delimited JSON envelope is printed to stdout
(ROCKETEDA_ENVELOPE_BEGIN/END); chatter outside the markers is
tolerated and stays in logs.

The netlist is built from the project spec (`doc` instances +
connections + transient): nothing is hardcoded — R/C/V, the
topology, the time grid, and the observed port all ride the job.
Only the proven transient path runs (`Circuit.transient` from a
discharged start); DC/AC/harmonic-balance stay refused in the
adapter until a proof lands.

Envelope: `{"ok": true, "circulax_version, "result": {t_s[],
v_V[], final_V, observe, t1_s, points}}` or `{"ok": false, "error":
{code, message, token, line}}`. Exit 0 on sim success, 2 on a
malformed circuit, 3 when circulax is not importable. Anything else
explodes with a traceback and exit 1, which parse() reports as
runner_unavailable rather than mistaking a tool crash for physics.
"""

import json
import re
import sys

_ENVELOPE_BEGIN = "ROCKETEDA_ENVELOPE_BEGIN"
_ENVELOPE_END = "ROCKETEDA_ENVELOPE_END"

_QUOTED_RE = re.compile(r"""['\"]([^'\"]+)['\"]""")

_COMPONENTS = ("vsource", "resistor", "capacitor", "ground")


def _token(doc, message):
    instances = doc.get("instances") or {}
    names = list(instances)
    names.extend(list(_COMPONENTS))
    for name in names:
        if name and re.search(r"\b" + re.escape(name) + r"\b", message):
            return name
    for match in _QUOTED_RE.finditer(message):
        return match.group(1)
    return None


def _find_line(text, token):
    if not token:
        return None
    for number, line in enumerate(text.splitlines(), 1):
        if token in line:
            return number
    return None


def _fail(code, message, token, line):
    print(_ENVELOPE_BEGIN)
    print(
        json.dumps(
            {
                "ok": False,
                "error": {
                    "code": code,
                    "message": message,
                    "token": token,
                    "line": line,
                },
            }
        )
    )
    print(_ENVELOPE_END)


def main(argv):
    # TODO: why is the output stdout??!!!! reserve the json, pass the python object as is back to the adapter level, and it will fanout from there to any active adapter who is responsible for formatting said outputs!!!!
    """Run one staged circulax transient: job JSON in, envelope on stdout.

    Args:
        argv: Argument vector; argv[1] is the staged job JSON path.

    Returns:
        Process exit code: 0 on sim success, 2 on a malformed
            circuit, 3 when circulax is not importable.

    Raises:
        ValueError: Unknown component or bad observe port (raised
            and caught inside main into the invalid_circuit
            envelope — never escapes).
    """
    with open(argv[1], encoding="utf-8") as handle:
        job = json.load(handle)
    text = job.get("text", "")
    doc = job["doc"]
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
        _fail(
            "missing_dependency",
            f"circulax is not importable: {exc} "
            "(uv sync).",
            None,
            None,
        )
        return 3
    try:
        import circulax

        classes = {
            "vsource": VoltageSource,
            "resistor": Resistor,
            "capacitor": Capacitor,
        }
        netlist = kfnl.Netlist()
        for name, inst in doc["instances"].items():
            component = inst["component"]
            if component not in _COMPONENTS:
                raise ValueError(f"Unknown component: {component!r}.")
            netlist.create_inst(
                name=name,
                kcl="",
                component=component,
                settings=dict(inst.get("settings") or {}),
            )
        for left, right in (doc.get("connections") or {}).items():
            left_inst, _, left_port = left.partition(",")
            right_inst, _, right_port = right.partition(",")
            netlist.create_net(
                kfnl.PortRef(left_inst, left_port),
                kfnl.PortRef(right_inst, right_port),
            )
        circuit = compile_circuit(
            netlist,
            {key: classes[key] for key in classes},
        )
        transient = doc["transient"]
        t1 = float(transient["t1_s"])
        points = int(transient["points"])
        dt0 = float(transient.get("dt0_s", 1e-8))
        observe = transient["observe"]
        if observe not in circuit.port_map:
            raise ValueError(f"Unknown observe port: {observe!r}.")
        grid = jnp.linspace(0, t1, points)
        solution = circuit.transient(
            t0=0.0,
            t1=t1,
            dt0=dt0,
            saveat=grid,
            y0=jnp.zeros(circuit.sys_size),
        )
        index = circuit.port_map[observe]
        times = [float(t) for t in solution.ts]
        volts = [float(row[index]) for row in solution.ys]
    except (ValueError, KeyError, TypeError) as exc:
        message = f"{type(exc).__name__}: {exc}"
        token = _token(doc, message)
        _fail("invalid_circuit", message, token, _find_line(text, token))
        return 2
    print(_ENVELOPE_BEGIN)
    print(
        json.dumps(
            {
                "ok": True,
                "circulax_version": getattr(
                    circulax, "__version__", "unknown"
                ),
                "result": {
                    "t_s": times,
                    "v_V": volts,
                    "final_V": volts[-1],
                    "observe": observe,
                    "t1_s": t1,
                    "points": points,
                },
            }
        )
    )
    print(_ENVELOPE_END)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
