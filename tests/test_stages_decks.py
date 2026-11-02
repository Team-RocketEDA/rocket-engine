"""WORKFLOW-COVERAGE RED — stage tables joined to covering decks.

Every stage entrypoint must resolve to a covering deck (op plus
deck.tool plus provision need), a probe-gated deck from live setup
state, or an explicit uncovered marker with a reason — never a
silent gap. The digital lane renders librelane-covered steps,
lint/synth/formal/sta steps, and uncovered steps from the tables
plus live probes. Fails today: stages has no deck join yet.
"""

from rocket_engine.workflows.stages import (
    DECKS,
    STAGES,
    covering_decks,
    flow_cover,
    render_lane,
)


def _engine_solvers():
    from rocket_engine.composition import Engine

    engine = Engine("stages-decks", actor="stages-decks")
    return {op: sorted(tools) for op, tools in engine._solvers.items()}


def test_decks_table_matches_engine_solver_registry():
    assert set(DECKS) == set(_engine_solvers())
    for op, cites in DECKS.items():
        assert {c["tool"] for c in cites} == set(_engine_solvers()[op])


def test_decks_provision_needs_match_solver_deps():
    from rocket_engine.interfaces.setup import SOLVER_DEPS

    for op, cites in DECKS.items():
        for cite in cites:
            spec = SOLVER_DEPS[(op, cite["tool"])]
            assert sorted(spec.get("binaries", []) + spec.get("python", [])) == sorted(
                cite["needs"]
            )


def test_scripted_entrypoints_are_scripted_cites_not_gaps():
    for entry in ("project scripting", "get_capabilities", "ip_instantiate"):
        cites = covering_decks(entry)
        assert len(cites) == 1
        assert cites[0]["kind"] == "scripted"


def test_thermal_has_no_solver_so_it_is_an_uncovered_marker():
    cites = covering_decks("run_thermal")
    assert len(cites) == 1
    assert cites[0]["kind"] == "uncovered"
    assert "run_thermal" in cites[0]["reason"]


def test_every_stage_in_every_flow_resolves_with_no_silent_gap():
    for flow, stages in STAGES.items():
        covered = flow_cover(flow)
        assert [s["id"] for s in covered] == [s["id"] for s in stages]
        for stage in covered:
            assert stage["cover"], stage["id"]
            for cite in stage["cover"]:
                assert cite["kind"] in ("deck", "scripted", "uncovered")
                if cite["kind"] == "uncovered":
                    assert cite["reason"].strip()


def test_digital_lane_render_pins_librelane_and_tool_steps():
    text = render_lane("digital")
    lines = {line.split()[0]: line for line in text.splitlines() if line.strip()}
    assert "librelane" in lines["D11"]
    assert "run_digital_flow" in lines["D12"]
    assert "slang" in lines["D04"] and "run_syntax" in lines["D04"]
    assert "sby" in lines["D08"] and "run_formal" in lines["D08"]
    assert "opensta" in lines["D22"] and "run_timing" in lines["D22"]
    assert "uncovered" not in text


def test_mixed_lane_names_the_thermal_gap():
    text = render_lane("mixed")
    assert "M14" in text
    m14 = [line for line in text.splitlines() if line.startswith("M14")][0]
    assert "uncovered" in m14 and "run_thermal" in m14


def test_blocked_stage_carries_deck_cites_per_blocker():
    from rocket_engine.workflows.capability_plan import plan_from_capabilities

    operations = {
        "run_timing": {
            "readiness": "blocked",
            "reason": "No run_timing tool resolves on this machine.",
            "missing": ["sta"],
            "remedy": "Install the pinned OpenSTA build.",
            "tools": {},
        },
    }
    by_id = {s["id"]: s for s in plan_from_capabilities("mixed", operations)}
    assert by_id["M11"]["readiness"] == "blocked"
    assert by_id["M11"]["blocked_by"] == ["run_timing"]
    decks = {d["tool"] for d in by_id["M11"]["decks"] if d["kind"] == "deck"}
    assert decks == {"opensta"}
    assert by_id["M01"]["readiness"] == "ready"
    assert by_id["M01"]["decks"]
