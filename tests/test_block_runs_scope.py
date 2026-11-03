"""BLOCK-RUNS unit RED — block-scoped run targets.

Tests assume `rocket_engine.execution.block_runs_scope`: target
validation, operation gating (SPICE + syntax first), entity
resolution, component-closure snapshot + hash, job narrowing, and
verdict/provenance stamping. Valid RED = the import itself fails.
"""

import pytest


def _mod():
    from rocket_engine.execution import block_runs_scope  # RED: missing module

    return block_runs_scope


def _blocks():
    return {
        "amp": {
            "id": "amp",
            "sources": ["blocks/amp/amp.spice"],
            "CellLink": {"cell": "sky130:amp", "pinMap": []},
            "params": {"w": "2u"},
            "constraints": {"gain": {"min": 40}},
        },
        "bias": {
            "id": "bias",
            "sources": ["blocks/bias/bias.spice"],
        },
    }


def _code(excinfo):
    return getattr(excinfo.value, "code", None)


# target parsing -----------------------------------------------------


def test_parse_target_none_is_project():
    mod = _mod()
    assert mod.parse_target(None) == {"scope": "project", "id": None}


def test_parse_target_empty_is_project():
    mod = _mod()
    assert mod.parse_target({}) == {"scope": "project", "id": None}


def test_parse_target_block_needs_id():
    mod = _mod()
    assert mod.parse_target({"scope": "block", "id": "amp"}) == {
        "scope": "block",
        "id": "amp",
    }
    with pytest.raises(mod.BlockScopeError) as exc:
        mod.parse_target({"scope": "block"})
    assert _code(exc) == "invalid_target"
    with pytest.raises(mod.BlockScopeError) as exc:
        mod.parse_target({"scope": "block", "id": ""})
    assert _code(exc) == "invalid_target"


def test_parse_target_rejects_unknown_scope_with_named_reason():
    mod = _mod()
    with pytest.raises(mod.BlockScopeError) as exc:
        mod.parse_target({"scope": "die", "id": "amp"})
    assert _code(exc) == "invalid_target"
    assert "project" in str(exc.value) and "block" in str(exc.value)


def test_parse_target_rejects_non_mapping_and_project_id():
    mod = _mod()
    with pytest.raises(mod.BlockScopeError) as exc:
        mod.parse_target("amp")
    assert _code(exc) == "invalid_target"
    with pytest.raises(mod.BlockScopeError) as exc:
        mod.parse_target({"scope": "project", "id": "amp"})
    assert _code(exc) == "invalid_target"


# operation gating: SPICE + syntax first ------------------------------


def test_block_scope_serves_spice_and_syntax_first():
    mod = _mod()
    assert mod.check_operation_scope("run_spice", "block") == "block"
    assert mod.check_operation_scope("run_syntax", "block") == "block"


def test_block_scope_rejects_later_verbs_with_named_reason():
    mod = _mod()
    with pytest.raises(mod.BlockScopeError) as exc:
        mod.check_operation_scope("run_drc", "block")
    assert _code(exc) == "unsupported_scope"
    assert "run_drc" in str(exc.value)


def test_project_scope_serves_every_operation():
    mod = _mod()
    assert mod.check_operation_scope("run_drc", "project") == "project"
    assert mod.check_operation_scope("run_spice", "project") == "project"


# entity resolution ---------------------------------------------------


def test_resolve_block_finds_entity_by_id():
    mod = _mod()
    assert mod.resolve_block("amp", _blocks())["id"] == "amp"


def test_resolve_block_accepts_block_lists():
    mod = _mod()
    blocks = [_blocks()["amp"], _blocks()["bias"]]
    assert mod.resolve_block("bias", blocks)["id"] == "bias"


def test_unknown_block_rejected_with_named_reason():
    mod = _mod()
    with pytest.raises(mod.BlockScopeError) as exc:
        mod.resolve_block("ghost", _blocks())
    assert _code(exc) == "unknown_block"
    assert "ghost" in str(exc.value)


def test_resolve_block_rejects_malformed_store():
    mod = _mod()
    with pytest.raises(mod.BlockScopeError) as exc:
        mod.resolve_block("amp", [{"noid": True}])
    assert _code(exc) == "invalid_block"


# closure snapshot ----------------------------------------------------


def test_snapshot_closure_captures_all_components():
    mod = _mod()
    closure = mod.snapshot_closure(_blocks()["amp"])
    assert closure["block_id"] == "amp"
    assert closure["sources"] == ["blocks/amp/amp.spice"]
    assert closure["celllink"] == {"cell": "sky130:amp", "pinMap": []}
    assert closure["params"] == {"w": "2u"}
    assert closure["constraints"] == {"gain": {"min": 40}}


def test_snapshot_closure_defaults_missing_components():
    mod = _mod()
    closure = mod.snapshot_closure(_blocks()["bias"])
    assert closure["celllink"] is None
    assert closure["params"] == {}
    assert closure["constraints"] == {}


def test_snapshot_closure_copies_and_never_mutates_storage():
    mod = _mod()
    block = _blocks()["amp"]
    before = dict(block)
    closure = mod.snapshot_closure(block)
    closure["sources"].append("evil.spice")
    closure["params"]["w"] = "evil"
    assert block == before


def test_snapshot_closure_runs_celllink_resolver_when_given():
    mod = _mod()
    seen = []

    def fake_resolver(block, variant):
        seen.append((block["id"], variant))
        return {"cell": "sky130:amp", "pinMap": [], "variant": variant}

    closure = mod.snapshot_closure(
        _blocks()["amp"], resolve_celllink=fake_resolver, variant="fast"
    )
    assert seen == [("amp", "fast")]
    assert closure["celllink_resolved"]["cell"] == "sky130:amp"
    assert closure["variant"] == "fast"


def test_snapshot_closure_rejects_bad_sources():
    mod = _mod()
    with pytest.raises(mod.BlockScopeError) as exc:
        mod.snapshot_closure({"id": "amp", "sources": "nope.spice"})
    assert _code(exc) == "invalid_block"


def test_closure_hash_stable_and_content_addressed():
    mod = _mod()
    first = mod.snapshot_closure(_blocks()["amp"])
    second = mod.snapshot_closure(_blocks()["amp"])
    assert mod.closure_hash(first) == mod.closure_hash(second)
    second["params"]["w"] = "9u"
    assert mod.closure_hash(first) != mod.closure_hash(second)


# job narrowing -------------------------------------------------------


def test_narrow_job_replaces_sources_with_closure():
    mod = _mod()
    closure = mod.snapshot_closure(_blocks()["amp"])
    job = {"operation": "run_syntax", "sources": ["top.sv", "other.sv"]}
    narrowed = mod.narrow_job_for_block(job, closure)
    assert narrowed["sources"] == ["blocks/amp/amp.spice"]
    assert narrowed["operation"] == "run_syntax"
    assert narrowed["block_scope"]["block_id"] == "amp"
    assert job["sources"] == ["top.sv", "other.sv"]


def test_narrow_job_records_closure_hash():
    mod = _mod()
    closure = mod.snapshot_closure(_blocks()["amp"])
    narrowed = mod.narrow_job_for_block({"operation": "run_spice"}, closure)
    assert narrowed["block_scope"]["closure_hash"] == mod.closure_hash(closure)


# verdict + provenance -------------------------------------------------


def test_scope_provenance_cites_run_revision_block_deck():
    mod = _mod()
    deck = {"tool": "ngspice"}
    scope = mod.scope_provenance(
        run_id="r1", revision="p12", block_id="amp", deck=deck
    )
    assert scope == {
        "run_id": "r1",
        "revision": "p12",
        "block_id": "amp",
        "deck": {"tool": "ngspice"},
    }
    deck["tool"] = "evil"
    assert scope["deck"] == {"tool": "ngspice"}


def test_scope_provenance_rejects_empty_citation_fields():
    mod = _mod()
    with pytest.raises(mod.BlockScopeError) as exc:
        mod.scope_provenance(run_id="", revision="p12", block_id="amp", deck={})
    assert _code(exc) == "invalid_target"


def test_stamp_verdict_records_scope_without_mutating():
    mod = _mod()
    verdict = {"status": "PASS", "finding_counts": {}}
    scope = {"run_id": "r1", "revision": "p12", "block_id": "amp", "deck": {}}
    stamped = mod.stamp_verdict(verdict, scope)
    assert stamped["status"] == "PASS"
    assert stamped["scope"] == scope
    assert "scope" not in verdict


def test_stamp_verdict_rejects_scope_missing_citation():
    mod = _mod()
    with pytest.raises(mod.BlockScopeError) as exc:
        mod.stamp_verdict({"status": "PASS"}, {"block_id": "amp"})
    assert _code(exc) == "invalid_block"


def test_build_scope_record_binds_provenance_hash_closure():
    mod = _mod()
    closure = mod.snapshot_closure(_blocks()["amp"])
    record = mod.build_scope_record(
        run_id="r1",
        revision="p12",
        block_id="amp",
        deck={"tool": "slang"},
        closure=closure,
    )
    assert record["provenance"]["block_id"] == "amp"
    assert record["provenance"]["deck"] == {"tool": "slang"}
    assert record["closure_hash"] == mod.closure_hash(closure)
    assert record["closure"] == closure
    record["closure"]["sources"].append("evil")
    assert closure["sources"] == ["blocks/amp/amp.spice"]


def test_build_scope_record_refuses_foreign_closure():
    mod = _mod()
    closure = mod.snapshot_closure(_blocks()["bias"])
    with pytest.raises(mod.BlockScopeError) as exc:
        mod.build_scope_record(
            run_id="r1",
            revision="p12",
            block_id="amp",
            deck={},
            closure=closure,
        )
    assert _code(exc) == "invalid_block"
