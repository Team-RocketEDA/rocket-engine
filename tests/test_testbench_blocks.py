"""TESTBENCH-COMPONENT RED — scoped SPICE/HDL/cocotb blocks + templates.

TDD RED: valid RED = `rocket_engine.project.testbench` does not
exist, so every import below fails. GREEN implements
`src/project/testbench/blocks.py` (scoped DUT targets, stale
links, harness exclusion, simulator gates) plus
`src/project/testbench/templates.py` (editable SPICE/HDL/cocotb
sources with provenance) against the ENGINE-ECS entity seam —
no network, no subprocess beyond PATH probes, no invented pins.
"""

import pytest

from rocket_engine.project.errors import ProjectError
from rocket_engine.project.service import ProjectService


def _service(tmp_path):
    """Fresh durable project service for one test."""
    return ProjectService(
        project_id="bench_demo", actor="test",
        engine_root=str(tmp_path),
    )


def _head(service):
    """Live head revision of one service."""
    return service.snapshot()["current_revision"]


def _entity(service, head, kind="cell", components=None, tag="e"):
    """Mint one entity with optional components at the head."""
    return service.create_entity(
        f"req-{tag}-{head}-{id(service):x}-{len(tag)}",
        f"create {kind} at {head}",
        kind=kind, components=components or {},
        expected_revision=head,
    )


def _sheet(service, head, name, tag="s"):
    """Mint one schematic sheet entity carrying a Sheet component."""
    return _entity(
        service, head, kind="sheet",
        components={"Sheet": {"name": name, "title": name}},
        tag=f"{tag}-{name}",
    )


def _instance(service, head, sheet, symbol, ref="", tag="i"):
    """Mint one schematic instance on a sheet."""
    return _entity(
        service, head, kind="instance",
        components={
            "Instance": {
                "sheet": sheet, "symbol": symbol, "x": 0, "y": 0,
                "rotation": 0, "mirror": False,
                "properties": {}, "ref": ref,
            }
        },
        tag=f"{tag}-{symbol}-{ref or 'plain'}",
    )


def _symbol(service, head, name):
    """Mint one project-owned symbol definition."""
    return _entity(
        service, head, kind="symbol",
        components={"Symbol": {"name": name, "pins": []}},
        tag=f"sym-{name}",
    )


def _blocks():
    """Load the testbench blocks module (RED when missing)."""
    import importlib

    return importlib.import_module(
        "rocket_engine.project.testbench.blocks"
    )


def _templates():
    """Load the testbench templates module (RED when missing)."""
    import importlib

    return importlib.import_module(
        "rocket_engine.project.testbench.templates"
    )


def _scope(tmp_path):
    """One DUT scope: sheet with parent instance + child instance."""
    service = _service(tmp_path)
    top = _sheet(service, _head(service), "top", tag="top")["entity"]
    _symbol(service, _head(service), "amp")
    parent = _instance(
        service, _head(service), top, "amp", ref="X1", tag="parent",
    )["entity"]
    child = _instance(
        service, _head(service), top, "amp", ref="X2", tag="child",
    )["entity"]
    return service, top, parent, child


def test_template_kinds_render_with_provenance():
    """All three template kinds render editable source + provenance."""
    templates = _templates()
    interface = {
        "pins": [{"name": "in", "direction": "input"}],
        "digest": "d" * 12,
    }
    harness = {"stimulus": "v(in) pulse", "load": "50ohm"}
    for kind in ("spice", "hdl", "cocotb"):
        rendered = templates.render(kind, interface, harness)
        assert rendered["source"]
        assert rendered["digest"]
        assert rendered["provenance"]["kind"] == kind
        assert rendered["provenance"]["template_version"]


def test_template_render_never_invents_pins():
    """Render carries only materialized pins, no guessed resets."""
    templates = _templates()
    rendered = templates.render(
        "spice", {"pins": [], "digest": "e" * 12}, {},
    )
    assert "reset" not in rendered["source"].lower()
    assert "vdd" not in rendered["source"].lower()


def test_template_unknown_kind_refuses():
    """Unknown template kinds fail loudly instead of guessing."""
    templates = _templates()
    with pytest.raises(Exception) as excinfo:
        templates.render("systemc", {"pins": []}, {})
    assert getattr(excinfo.value, "code", "") == "invalid_kind"


def test_create_block_pins_dut_and_template(tmp_path):
    """Create stores the block, DUT digest, and template provenance."""
    blocks = _blocks()
    service, _top, parent, _child = _scope(tmp_path)
    receipt = blocks.create_block(
        service, "req-tb-1", "create testbench tb1",
        name="tb1", kind="spice",
        targets={"primary": parent, "additional": []},
        probes=[], harness={},
        expected_revision=_head(service),
    )
    assert receipt["testbench"]
    record = service.get_component(
        receipt["testbench"], "Testbench")["data"]
    assert record["dut_digest"]
    assert record["template"]["kind"] == "spice"
    assert record["fresh"] is True


def test_sibling_and_deep_descendant_targets_land(tmp_path):
    """Sibling instances and deep descendants are legal DUTs."""
    blocks = _blocks()
    service, _top, parent, child = _scope(tmp_path)
    receipt = blocks.create_block(
        service, "req-tb-sib", "create sibling bench",
        name="sib", kind="hdl",
        targets={"primary": parent, "additional": [child]},
        probes=[], harness={},
        expected_revision=_head(service),
    )
    assert receipt["testbench"]


def test_ancestor_target_refused(tmp_path):
    """An ancestor of the primary is an illegal DUT target."""
    blocks = _blocks()
    service, top, parent, _child = _scope(tmp_path)
    with pytest.raises(Exception) as excinfo:
        blocks.create_block(
            service, "req-tb-anc", "create ancestor bench",
            name="anc", kind="spice",
            targets={"primary": parent, "additional": [top]},
            probes=[], harness={},
            expected_revision=_head(service),
        )
    assert getattr(excinfo.value, "code", "") in (
        "illegal_scope", "invalid_target", "overlapping_targets",
    )


def test_overlapping_dut_targets_rejected(tmp_path):
    """Duplicate DUT targets overlap and are refused."""
    blocks = _blocks()
    service, _top, parent, _child = _scope(tmp_path)
    with pytest.raises(Exception) as excinfo:
        blocks.create_block(
            service, "req-tb-over", "create overlapping bench",
            name="over", kind="spice",
            targets={"primary": parent, "additional": [parent]},
            probes=[], harness={},
            expected_revision=_head(service),
        )
    assert getattr(excinfo.value, "code", "") in (
        "overlapping_targets", "invalid_target",
    )


def test_unrelated_scope_target_rejected(tmp_path):
    """A target outside the DUT scope is refused."""
    blocks = _blocks()
    service, _top, parent, _child = _scope(tmp_path)
    far_sheet = _sheet(service, _head(service), "far", tag="far")["entity"]
    with pytest.raises(Exception) as excinfo:
        blocks.create_block(
            service, "req-tb-far", "create far bench",
            name="far", kind="spice",
            targets={"primary": parent, "additional": [far_sheet]},
            probes=[], harness={},
            expected_revision=_head(service),
        )
    assert getattr(excinfo.value, "code", "") in (
        "illegal_scope", "invalid_target", "unknown_target",
    )


def test_reused_symbol_occurrences_disambiguate(tmp_path):
    """Two placements of one symbol are distinct DUT occurrences."""
    blocks = _blocks()
    service, _top, parent, child = _scope(tmp_path)
    assert parent != child
    first = blocks.create_block(
        service, "req-tb-r1", "create first reuse bench",
        name="reuse1", kind="cocotb",
        targets={"primary": parent, "additional": []},
        probes=[], harness={},
        expected_revision=_head(service),
    )
    second = blocks.create_block(
        service, "req-tb-r2", "create second reuse bench",
        name="reuse2", kind="cocotb",
        targets={"primary": child, "additional": []},
        probes=[], harness={},
        expected_revision=_head(service),
    )
    assert first["testbench"] != second["testbench"]


def test_out_of_closure_probe_rejected(tmp_path):
    """Probes outside the DUT closure are refused."""
    blocks = _blocks()
    service, _top, parent, _child = _scope(tmp_path)
    far = _sheet(service, _head(service), "far", tag="farprobe")["entity"]
    with pytest.raises(Exception) as excinfo:
        blocks.create_block(
            service, "req-tb-probe", "create probed bench",
            name="probed", kind="spice",
            targets={"primary": parent, "additional": []},
            probes=[{"entity": far}],
            harness={},
            expected_revision=_head(service),
        )
    assert getattr(excinfo.value, "code", "") in (
        "illegal_scope", "invalid_target",
    )


def test_source_edits_preserved_by_regenerate(tmp_path):
    """Regenerate never overwrites an edited source in place."""
    blocks = _blocks()
    service, _top, parent, _child = _scope(tmp_path)
    receipt = blocks.create_block(
        service, "req-tb-edit", "create editable bench",
        name="edit", kind="spice",
        targets={"primary": parent, "additional": []},
        probes=[], harness={},
        expected_revision=_head(service),
    )
    bench = receipt["testbench"]
    service.set_component(
        bench, "Testbench",
        {**service.get_component(bench, "Testbench")["data"],
         "source": "* hand edit"},
        "req-tb-handedit", "hand edit source",
        expected_revision=_head(service),
    )
    service.set_component(
        parent, "Instance",
        {**service.get_component(parent, "Instance")["data"],
         "symbol": "amp_v2"},
        "req-tb-drift", "drift the DUT interface",
        expected_revision=_head(service),
    )
    regenerated = blocks.regenerate_block(
        service, "req-tb-regen", "regenerate bench",
        testbench=bench,
        expected_revision=_head(service),
    )
    live = service.get_component(bench, "Testbench")["data"]
    assert live["source"] == "* hand edit"
    assert regenerated["candidate_source"] != "* hand edit"
    assert regenerated["differs_from_live"] is True


def test_stale_link_blocks_run(tmp_path):
    """Hierarchy edits mark the link stale and block the run."""
    blocks = _blocks()
    service, _top, parent, _child = _scope(tmp_path)
    receipt = blocks.create_block(
        service, "req-tb-stale", "create stale bench",
        name="stale", kind="spice",
        targets={"primary": parent, "additional": []},
        probes=[], harness={},
        expected_revision=_head(service),
    )
    bench = receipt["testbench"]
    service.set_component(
        parent, "Instance",
        {**service.get_component(parent, "Instance")["data"],
         "symbol": "amp_v2"},
        "req-tb-drift", "drift the DUT interface",
        expected_revision=_head(service),
    )
    with pytest.raises(Exception) as excinfo:
        blocks.assert_runnable(service, bench)
    assert getattr(excinfo.value, "code", "") == "stale_link"


def test_generated_source_saved_in_project(tmp_path):
    """The generated source is saved as a project document."""
    blocks = _blocks()
    service, _top, parent, _child = _scope(tmp_path)
    receipt = blocks.create_block(
        service, "req-tb-doc", "create documented bench",
        name="saved", kind="spice",
        targets={"primary": parent, "additional": []},
        probes=[], harness={},
        expected_revision=_head(service),
    )
    record = service.get_component(
        receipt["testbench"], "Testbench")["data"]
    saved = service.read_doc(record["source_path"])
    assert saved["content"] == record["source"]


def test_harness_excluded_from_netlist_pins(tmp_path):
    """Harness instances never leak into production net pins."""
    blocks = _blocks()
    service, _top, parent, _child = _scope(tmp_path)
    receipt = blocks.create_block(
        service, "req-tb-hx", "create harness bench",
        name="hx", kind="spice",
        targets={"primary": parent, "additional": []},
        probes=[], harness={"instances": ["harness_driver"]},
        expected_revision=_head(service),
    )
    record = service.get_component(
        receipt["testbench"], "Testbench")["data"]
    pins = [
        {"instance": parent, "pin": "in", "net": "n1"},
        {"instance": "harness_driver", "pin": "out", "net": "n1"},
    ]
    kept = blocks.design_net_pins(record, pins)
    assert {row["instance"] for row in kept} == {parent}


def test_simulator_gate_loud_blocked_without_fakes(tmp_path):
    """Missing simulators report BLOCKED-needs-host, never green."""
    blocks = _blocks()
    for kind, tool in (("spice", "ngspice"), ("hdl", "icarus")):
        gate = blocks.probe_simulator(kind)
        assert gate["tool"] == tool
        if gate["available"]:
            assert gate["verdict"] == "ready"
        else:
            assert gate["verdict"] == "BLOCKED-needs-host"
            assert gate["remedy"]
