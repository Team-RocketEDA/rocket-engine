"""Split lock for composition.py (REFACTOR-COMPOSITION).

composition.py (2585 lines) approaches the 3000-line architecture
limit. It must decompose into a thin Engine surface plus a cohesive
``rocket_engine.ops`` subpackage, with the public API and the
api_spec AST seams byte-identical.
"""

from pathlib import Path

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

OPS_MODULES = ["submit", "queries", "runs", "gates"]


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
