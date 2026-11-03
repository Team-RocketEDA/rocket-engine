"""Postlayout translation RED — klt PEX to vendor sim.

Valid RED = `rocket_engine.adapters.postlayout.translate` does not
exist yet. Real extracted PEX carries klt generic device classes
and is unsimmable as-is; the engine must translate to vendor
models or refuse loudly naming the gap — never a silent sim_fail.
"""

import pytest


def test_translate_maps_klt_devices():
    from rocket_engine.adapters.postlayout.translate import (
        translate_klt_netlist,
    )

    netlist = "X1 a b sky130_klt_nmos W=1 L=0.13\n"
    out, mapping = translate_klt_netlist(netlist, vendor="sky130")
    assert "sky130_fd_pr" in out or "nmos" in out.lower()
    assert mapping


def test_translate_untranslatable_refuses_loudly():
    from rocket_engine.adapters.postlayout.translate import (
        translate_klt_netlist,
    )
    from rocket_engine.adapters.errors import AdapterError

    try:
        translate_klt_netlist("X1 a b klt_exotic_xyz\n", vendor="sky130")
    except AdapterError as exc:
        assert exc.code == "unsupported_operation"
        assert "klt" in str(exc).lower() or "vendor" in str(exc).lower()
    else:
        raise AssertionError("expected loud refusal")


def test_translate_detects_klt_markers():
    from rocket_engine.adapters.postlayout.translate import is_klt_netlist

    assert is_klt_netlist("X1 a b sky130_klt_nmos\n")
    assert not is_klt_netlist(".subckt top a b\nR1 a b 1k\n")
