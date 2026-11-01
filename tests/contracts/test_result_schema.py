"""Result contract jobs for headless tools and Electron renderers.

These exercise the canonical schema boundary. They do not claim solver/provider
conformance, which is independently qualified against real fixture outputs.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("v1_contract", ROOT / "scripts/check_v1_contract.py")
CONTRACT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONTRACT)


@pytest.fixture(scope="module")
def contract():
    """Load the one canonical source bundle."""
    return CONTRACT.load_contract()


def check(contract, name, value):
    """Validate one typed producer/consumer payload."""
    assert name in contract["$defs"], f"Missing typed result contract: {name}"
    return list(CONTRACT.validator(contract, "#/$defs/" + name).iter_errors(value))


def pinned(name="data"):
    """Build an immutable fixture reference."""
    return {"scope": "project", "id": name, "revision": "r1"}


def axis(name, unit, samples):
    """Build an explicitly unit-bearing continuous axis."""
    return {"id": name, "name": name, "quantity": name, "unit": unit,
            "kind": "continuous", "scale": "linear", "values": samples}


def series(analysis="tran", complex_values=False):
    """Build a circuit-analysis series with a real or complex signal."""
    axis_name, unit = {"tran": ("time", "s"), "dc": ("vin", "V"),
                       "ac": ("frequency", "Hz")}[analysis]
    signal = {"id": "out", "name": "v(out)", "quantity": "voltage", "unit": "V",
              "values": {"storage": "inline", "dtype": "complex128" if complex_values else "float64",
                         "shape": [3], "data": [{"real": 1.0, "imag": 0.0},
                                                {"real": 0.5, "imag": -0.5},
                                                {"real": 0.0, "imag": -1.0}] if complex_values else [0.0, 0.5, 1.0]}}
    return {"id": "result-series", "kind": "series", "analysis": analysis,
            "axes": [axis(axis_name, unit, [1.0, 2.0, 3.0])], "signals": [signal],
            "conditions": []}


@pytest.mark.parametrize("analysis,complex_values", [("dc", False), ("ac", True), ("tran", False)])
def test_circuit_analyses_preserve_axes_units_and_complex_samples(contract, analysis, complex_values):
    """DC/AC/transient share typed arrays without reducing AC to a screenshot."""
    assert not check(contract, "Dataset", series(analysis, complex_values))


def test_ac_complex_values_require_both_real_and_imaginary(contract):
    """An incomplete complex number cannot silently become a real trace."""
    value = series("ac", True)
    del value["signals"][0]["values"]["data"][0]["imag"]
    assert check(contract, "Dataset", value)


def test_data_axes_require_units(contract):
    """Renderers never guess whether an axis represents seconds or hertz."""
    value = series()
    del value["axes"][0]["unit"]
    assert check(contract, "Dataset", value)


def test_optical_spectrum_is_valid_without_a_heatmap(contract):
    """A wavelength sweep is a trace, independent of solver brand."""
    value = series()
    value["analysis"] = "optical.sparameters"
    value["axes"] = [axis("wavelength", "um", [1.50, 1.55, 1.60])]
    value["signals"][0].update(name="S21", quantity="power_ratio", unit="1")
    assert not check(contract, "Dataset", value)


def test_optical_matrix_has_explicit_row_column_coordinates(contract):
    """A heatmap requires an actual matrix and labeled coordinate axes."""
    value = {"id": "s-matrix", "kind": "matrix", "axes": [
        {"id": "input", "name": "Input port", "quantity": "port", "unit": "1",
         "kind": "categorical", "scale": "linear", "values": ["o1", "o2"]},
        {"id": "output", "name": "Output port", "quantity": "port", "unit": "1",
         "kind": "categorical", "scale": "linear", "values": ["o1", "o2"]}],
        "quantity": "scattering", "unit": "1", "values": {"storage": "inline",
        "dtype": "complex128", "shape": [2, 2], "data": [
            {"real": 0.0, "imag": 0.0}, {"real": 0.9, "imag": -0.1},
            {"real": 0.9, "imag": -0.1}, {"real": 0.0, "imag": 0.0}]}, "conditions": []}
    assert not check(contract, "Dataset", value)


def test_tables_carry_typed_columns_and_units(contract):
    """Measurements and implementation reports use typed columns."""
    value = {"id": "timing", "kind": "table", "row_count": 2,
             "columns": [{"id": "path", "name": "Path", "dtype": "utf8", "unit": "1", "data": ["a/b", "c/d"]},
                         {"id": "slack", "name": "Slack", "dtype": "float64", "unit": "ns", "data": [0.2, -0.1]}],
             "conditions": []}
    assert not check(contract, "Dataset", value)


def test_empty_drc_marker_collection_is_real_data(contract):
    """Zero DRC violations is an empty marker list, not fake success prose."""
    value = {"id": "drc", "kind": "markers", "view": "layout", "coordinate_unit": "um",
             "markers": [], "conditions": []}
    assert not check(contract, "Dataset", value)


def test_drc_markers_retain_rule_and_source_geometry(contract):
    """A violation can cross-probe the exact cell/layer and polygon."""
    value = {"id": "drc", "kind": "markers", "view": "layout", "coordinate_unit": "um",
             "markers": [{"id": "m1", "finding_id": "finding-1", "rule": "m1.space",
                          "severity": "error", "message": "Metal spacing", "source": pinned("amp-cell"),
                          "layer": pinned("metal1"), "geometry": {"type": "polygon", "points": [
                              {"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 0.0}, {"x": 0.0, "y": 1.0}]}}],
             "conditions": []}
    assert not check(contract, "Dataset", value)


def test_digital_waveforms_preserve_unknown_and_high_impedance(contract):
    """Digital x/z values are not coerced into analog samples."""
    value = {"id": "hdl", "kind": "digital", "time_unit": "ns",
             "signals": [{"id": "bus", "name": "dut.bus", "width": 2,
                          "transitions": [{"time": 0, "value": "xx"}, {"time": 10, "value": "01"},
                                          {"time": 20, "value": "zz"}]}], "conditions": []}
    assert not check(contract, "Dataset", value)


def test_large_buffers_have_typed_chunk_metadata(contract):
    """The renderer retrieves bounded chunks using immutable refs and hashes."""
    value = series()
    value["signals"][0]["values"] = {"storage": "chunked", "dtype": "float64", "shape": [3],
        "order": "C", "chunks": [{"artifact": pinned("trace-chunk"), "sha256": "a" * 64,
                                 "offset": [0], "shape": [3], "format": "arrow"}]}
    assert not check(contract, "Dataset", value)


def test_unknown_chunk_format_is_rejected(contract):
    """A frontend never runs an arbitrary codec supplied by a tool payload."""
    value = series()
    value["signals"][0]["values"] = {"storage": "chunked", "dtype": "float64", "shape": [3],
        "order": "C", "chunks": [{"artifact": pinned("trace-chunk"), "sha256": "a" * 64,
                                 "offset": [0], "shape": [3], "format": "javascript"}]}
    assert check(contract, "Dataset", value)


def test_plot_bindings_are_data_descriptors_not_ui_code(contract):
    """Plot metadata chooses stable signals and transforms, not HTML/components."""
    value = {"id": "ac-plot", "kind": "traces", "dataset_id": "result-series", "x_axis": "frequency",
             "traces": [{"signal": "out", "transform": "magnitude_db", "axis": "left"}]}
    assert not check(contract, "DataView", value)
    value["html"] = "<script>render()</script>"
    assert check(contract, "DataView", value)


def test_task_edges_use_typed_refs_and_named_ports(contract):
    """Task chaining declares artifact type/schema and upstream identity."""
    value = {"port": "netlist", "kind": "artifact", "ref": pinned("netlist-1"),
             "schema": "rocketeda/netlist/v1", "format": "verilog", "producer_run_id": "synth-1"}
    assert not check(contract, "TaskInput", value)
    value["command"] = "parse terminal log"
    assert check(contract, "TaskInput", value)


def test_task_contract_declares_both_input_and_output_ports(contract):
    """A tool cannot advertise an untyped opaque result bag."""
    value = {"task": "synthesize.hdl", "inputs": [{"name": "rtl", "kind": "source",
             "schema": "rocketeda/source/v1", "formats": ["verilog"], "required": True, "many": True}],
             "outputs": [{"name": "netlist", "kind": "artifact", "schema": "rocketeda/netlist/v1",
             "formats": ["verilog"], "required": True, "many": False}]}
    assert not check(contract, "TaskContract", value)


def test_strict_json_ingest_rejects_nonfinite_samples(tmp_path):
    """NaN/Infinity are represented by explicit missing samples, never JSON numbers."""
    path = tmp_path / "nonfinite.json"
    path.write_text('{"values": [NaN]}')
    with pytest.raises(ValueError, match="Non-finite"):
        CONTRACT.read_json(path)


def test_stage_and_hierarchy_results_have_tree_data(contract):
    """Stage and grouped-violation trees are basic data, not custom report pages."""
    value = {"id": "asic-stages", "kind": "tree", "root_ids": ["build"],
             "nodes": [{"id": "build", "name": "ASIC build", "kind": "stage", "status": "completed"},
                       {"id": "sta", "parent_id": "build", "name": "Timing", "kind": "stage",
                        "status": "completed", "values": [{"name": "worst_slack", "value": {"value": 0.2, "unit": "ns"}}]}],
             "conditions": []}
    assert not check(contract, "Dataset", value)
    assert not check(contract, "DataView", {"id": "build-tree", "kind": "tree", "dataset_id": "asic-stages"})
