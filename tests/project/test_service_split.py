"""REFACTOR-SERVICE: service surface over cohesive subpackages.

Split evidence: the project command surface lives in
``src/project/service.py`` as a thin surface, cohesive
ledger machinery lives in the nested ``src/project/ledger/``
subpackage, and the public ``ProjectService`` API is unchanged.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
LEDGER = ROOT / "src" / "project" / "ledger"


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
    from rocket_engine.project import ProjectService
    from rocket_engine.project.service import ProjectService as ViaService

    assert ProjectService is ViaService
    expected = {
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
    missing = expected - set(dir(ProjectService))
    assert not missing, f"ProjectService lost methods: {sorted(missing)}"
