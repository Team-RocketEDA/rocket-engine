"""Split lock for composition.py (REFACTOR-COMPOSITION).

composition.py (2585 lines) approaches the 3000-line architecture
limit. It must decompose into a thin Engine surface plus a cohesive
``rocket_engine.ops`` subpackage, with the public API and the
api_spec AST seams byte-identical.
"""

from pathlib import Path

import pytest

import rocket_engine.composition as comp
from rocket_engine.composition import Engine

SRC = Path(__file__).resolve().parents[1] / "src"

PUBLIC_METHODS = [
    "snapshot", "events_since", "capabilities", "submit",
    "catalog_cells", "register_cells", "serve_asset", "list_assets",
    "boot_report", "resume_survivor", "discard_survivor",
    "resume_all_retryable", "replay_pending", "resolve_python_approval",
    "python_console", "cancel_job", "job_status", "check_results",
    "plan_checks", "design_completion", "run_logs", "job_kinds",
    "layer_stackup", "layer_rows", "layer_presets", "layer_preset_save",
    "layer_preset_delete", "layer_preset_apply", "log_text",
    "register_solver", "solvers_for", "findings", "resolve_celllinks",
    "run",
]

WAVE3_METHODS = [
    "deferred_submit", "deferred_pump", "deferred_status",
    "deferred_wait", "runtime_events", "runtime_cancel",
]

OPS_MODULES = ["submit", "queries", "runs", "gates"]

WAVE3_OPS = [
    "apply_transaction", "create_shape",
    "create_sheet", "place_instance", "bind_block",
    "create_symbol", "create_cell", "map_pins",
    "ip_register", "ip_instantiate", "ip_promote",
    "bind_layers", "annotate",
    "create_testbench", "regenerate_testbench",
]

WAVE3_QUERIES = [
    "read_entity_revision", "list_sheets", "get_sheet", "get_instance",
    "instances_on_sheet", "list_symbols", "get_symbol", "get_cell",
    "list_layers", "check_capability", "ip_search", "ip_get",
    "connection_graph", "net_occurrences", "xprobe", "resolve_pin",
    "plot_export", "erc_check", "write_netlist", "update_netlist",
    "list_testbenches", "describe_testbench",
]


def test_composition_comfortably_under_limit():
    """composition.py stays well clear of the 3000-line limit."""
    lines = (SRC / "composition.py").read_text().count("\n") + 1
    assert lines < 2000, f"composition.py has {lines} lines"


def test_ops_subpackage_exists_and_small():
    """Each ops mixin module exists and stays under 1000 lines."""
    for name in OPS_MODULES:
        path = SRC / "ops" / f"{name}.py"
        assert path.exists(), f"missing {path}"
        lines = path.read_text().count("\n") + 1
        assert lines < 1000, f"{path} has {lines} lines"


def test_engine_public_api_intact():
    """Every public Engine method survives the split."""
    for name in PUBLIC_METHODS:
        assert callable(getattr(Engine, name, None)), name


def test_api_spec_seams_live_in_composition():
    """Module tables api_spec AST-parses stay defined in composition."""
    assert comp._CRUD_OPERATIONS
    assert comp.QUERY_METHODS
    assert comp.QUERY_ENGINE_METHODS
    assert "_run_queued" in Engine.__dict__ or hasattr(Engine, "_run_queued")


def test_wave3_editor_verbs_in_vocabulary():
    """Wave-3 editor/testbench verbs are cataloged operations/queries."""
    from rocket_engine.interfaces.vocabulary import OPERATIONS, QUERIES

    for name in WAVE3_OPS:
        assert name in OPERATIONS, name
    for name in WAVE3_QUERIES:
        assert name in QUERIES, name


def test_wave3_verbs_served_by_submit():
    """Every Wave-3 verb is served (never unsupported_operation)."""
    from rocket_engine.composition import Engine
    from rocket_engine.project.errors import ProjectError

    engine = Engine("wave3-probe", actor="probe")
    for name in WAVE3_OPS + WAVE3_QUERIES:
        try:
            engine.submit({
                "project_id": "wave3-probe", "operation": name,
                "arguments": {}, "request_id": f"probe-{name}",
            })
        except ProjectError as exc:
            assert exc.code != "unsupported_operation", name


def test_wave3_deferred_surface_exists():
    """Engine owns the Wave-3 deferred runtime surface."""
    for name in WAVE3_METHODS:
        assert callable(getattr(Engine, name, None)), name


def test_wave3_deferred_prompt_ack_then_merge():
    """Deferred submit acknowledges promptly; pump merges completion."""
    from rocket_engine.composition import Engine
    from rocket_engine.execution.apig.submit import merge_ack_completion

    engine = Engine("wave3-deferred", actor="probe")
    head = engine.snapshot()["current_revision"]
    handle = engine.deferred_submit(
        "run_syntax",
        {"cell": "top", "expected_revision": head},
        request_id="wave3-req-1",
    )
    assert handle.run_id
    assert handle.receipt["admitted"] is True
    assert "verdict" not in handle.receipt
    engine.deferred_pump()
    completion = handle.wait(timeout=30)
    assert completion["state"] == "completed"
    merged = merge_ack_completion(handle.receipt, completion)
    assert merged["run_id"] == handle.run_id
    assert merged["verdict"] is not None


def test_wave3_deferred_rejects_unknown_operation():
    """Deferred submit refuses uncataloged operations loudly."""
    from rocket_engine.composition import Engine
    from rocket_engine.project.errors import ProjectError

    engine = Engine("wave3-deferred-unknown", actor="probe")
    with pytest.raises(ProjectError) as excinfo:
        engine.deferred_submit("no_such_op", {})
    assert excinfo.value.code == "unsupported_operation"


def test_wave3_ops_modules_stay_small():
    """New ops mixins exist and stay under the module-size rule."""
    for name in ("editors", "deferred", "ports"):
        path = SRC / "ops" / f"{name}.py"
        assert path.exists(), f"missing {path}"
        lines = path.read_text().count("\n") + 1
        assert lines < 1000, f"{path} has {lines} lines"
