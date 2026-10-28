"""Process-data RED — entrypoints resolve, required stages stay required.

Workflows ships data, not behavior, so these tests assume the data
surface `rocket_engine.workflows.STAGES` plus `entrypoint_for`. Valid
RED = the import itself fails. No fixtures: the module's own tables
are the data under test (they do not exist yet).
"""


def test_every_entrypoint_names_a_cataloged_operation():
    from rocket_engine.workflows import STAGES  # RED: missing surface

    cataloged = {
        "generate_views", "run_hdl_test", "run_formal", "run_syntax",
        "run_connectivity", "run_drc", "run_lvs", "run_erc", "run_spice",
        "run_optical", "run_digital_flow", "run_timing", "run_extraction",
        "run_post_layout", "run_em", "run_thermal", "python_execute",
        "run_view_sync",
    }
    scripted = {"project scripting", "get_capabilities", "ip_instantiate"}
    for flow in ("digital", "analog", "photonic", "mixed"):
        for stage in STAGES[flow]:
            for entry in stage["entrypoints"]:
                assert entry in cataloged | scripted, (flow, stage["id"], entry)


def test_required_stages_declare_evidence_fields():
    from rocket_engine.workflows import STAGES  # RED: missing surface

    for flow in ("digital", "analog", "photonic", "mixed"):
        for stage in STAGES[flow]:
            assert stage["id"] and stage["step"] and stage["evidence"], stage
            assert stage["when"], stage["id"]


def test_missing_backend_keeps_stage_required():
    from rocket_engine.workflows import applicable_stages  # RED: missing surface

    stages = applicable_stages(
        flow="digital", available_backends={"run_syntax", "run_hdl_test"}
    )
    drc = next(s for s in stages if s["id"] == "D25")
    assert drc["required"] is True
    assert drc["readiness"] in ("unavailable", "unsupported", "blocked")
