"""Canvas compile RED — canvas to SDC/measure-corner/librelane.

Valid RED = `rocket_engine.project.canvas.compile` and `.templates`
and `.integrate` do not exist yet. The compiler is single-source:
a digital canvas compiles to SDC that yosys+opensta accept, an
analog one drives run_spice bounds, librelane fragments carry
density/effort/corners. Per-PDK templates validate clean; the
wizard fills canvas.toml through the generator.
"""

import pytest


def _digital_doc():
    return {
        "schema": "rocketeda/canvas/v1",
        "pdks": [{"scope": "pdk", "id": "sky130A",
                  "revision": "5f09001e4b975ba5d27d99a10ecdf45054a9bd5"}],
        "targets": [{"metric": "clock.frequency", "operator": "ge",
                     "limit": {"value": 100, "unit": "MHz"}}],
        "tools": {"yosys": {"flatten": True}},
        "hdl": {"language": "verilog", "top": "top"},
    }


def test_compile_sdc_from_digital_canvas():
    from rocket_engine.project.canvas.compile import compile_sdc

    sdc = compile_sdc(_digital_doc())
    assert "create_clock" in sdc
    assert "10.0000" in sdc


def test_compile_spice_bounds_from_analog_canvas():
    from rocket_engine.project.canvas.compile import compile_spice_bounds

    doc = {
        "schema": "rocketeda/canvas/v1",
        "pdks": [{"scope": "pdk", "id": "sky130A", "revision": "r1"}],
        "targets": [{"metric": "gain.dc", "operator": "ge",
                     "limit": {"value": 60, "unit": "dB"}}],
        "tools": {"ngspice": {"reltol": 0.001}},
    }
    bounds = compile_spice_bounds(doc)
    assert bounds


def test_compile_librelane_fragment():
    from rocket_engine.project.canvas.compile import compile_librelane

    doc = {"tools": {"librelane": {"density": 0.6,
                                   "effort": "standard",
                                   "corners": ["tt"]}}}
    frag = compile_librelane(doc)
    assert "density" in frag


def test_templates_generate_per_pdk(tmp_path):
    from rocket_engine.project.canvas.templates import generate

    doc = generate("sky130A")
    assert doc["schema"] == "rocketeda/canvas/v1"
    assert doc["pdks"]


def test_templates_all_supported_pdks_validate(tmp_path):
    from rocket_engine.project.canvas.templates import supported_pdks, generate
    from rocket_engine.project.canvas import validate_canvas

    for pdk in supported_pdks():
        doc = generate(pdk)
        out = validate_canvas(doc, tmp_path)
        assert out["config"]


def test_integrate_wizard_creates_canvas(tmp_path):
    from rocket_engine.project.canvas.integrate import wizard_create

    path = wizard_create(tmp_path, "sky130A")
    assert path.is_file()
    assert "canvas.toml" in str(path)
