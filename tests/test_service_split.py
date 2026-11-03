"""REFACTOR-SERVICE root gate: service surface + store-port seam.

The project command surface lives in ``src/project/service.py``
as a thin surface over cohesive nested subpackages (ledger
machinery in ``src/project/ledger/``), stores bind behind the
``src/ops/ports.py`` seam (never imported straight from
interfaces/), and the public ``ProjectService`` API — including
the Wave-3 editor/testbench verbs — is unchanged in shape.
"""

from pathlib import Path

from rocket_engine.project import ProjectService
from rocket_engine.project.service import ProjectService as ViaService

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "src" / "project" / "ledger"

EXPECTED = {
    "submit", "snapshot", "events_since", "list_projects",
    "create_project", "list_docs", "read_doc", "write_doc",
    "delete_doc", "apply_mutations", "rewind", "create_entity",
    "set_component", "attach_component", "detach_component",
    "delete_entity", "get_component", "components_of",
    "entities_with", "world_snapshot", "read_settings",
    "write_settings", "resolved_config", "place_wire",
    "place_junction", "connect_endpoint", "move_wire",
    "split_wire", "delete_wire", "delete_junction",
    "materialize_nets", "append_run_event", "append_replay_event",
    "log_coalesced_request", "command_for",
}

WAVE3_OPS = [
    "apply_transaction", "create_shape",
    "create_sheet", "place_instance", "bind_block",
    "create_symbol", "create_cell", "map_pins",
    "ip_register", "ip_instantiate", "ip_promote",
    "bind_layers", "annotate",
    "create_testbench", "regenerate_testbench",
]

WAVE3_READS = [
    "entity_revision", "erc_report", "graph_report", "probe_report",
    "plot_report", "netlist_report", "capability_report",
    "testbench_report",
]


def test_ledger_subpackage_exists():
    """Cohesive ledger machinery lives in a nested subpackage."""
    assert LEDGER.is_dir(), "src/project/ledger/ subpackage is missing"
    for module in (
        "shared.py",
        "events.py",
        "snapshots.py",
        "docs.py",
        "entities.py",
        "runs.py",
        "wires.py",
    ):
        assert (LEDGER / module).is_file(), f"ledger/{module} is missing"


def test_project_service_api_intact():
    """ProjectService keeps its full public method set."""
    assert ProjectService is ViaService
    missing = set(EXPECTED) - set(dir(ProjectService))
    assert not missing, f"ProjectService lost methods: {sorted(missing)}"


def test_wave3_verbs_on_project_service():
    """Wave-3 editor/testbench verbs are ProjectService methods."""
    for name in WAVE3_OPS + WAVE3_READS:
        assert callable(getattr(ProjectService, name, None)), name


def test_stores_bind_behind_ports():
    """Service consumes stores through the ops ports seam."""
    from rocket_engine.ops import ports

    assert ports.ecs is not None
    assert ports.settings is not None
    assert ports.wireplace is not None
    assert ports.layers is not None
    import rocket_engine.project.service as service_module

    assert service_module.ecs is ports.ecs
    assert service_module.settings_store is ports.settings
    assert service_module.wireplace is ports.wireplace
