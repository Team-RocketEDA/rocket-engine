"""PDK-LXT user-supplied-deck flow: gated DRC done honestly.

Valid RED = the stand-in fixture deck does not exist yet, so the flow
tests fail on the missing file. GREEN = a tiny stand-in `.lydrc`
fixture (clearly labelled, never the gated deck) is adopted via
register_pdk and hash-pinned via resolve_deck; the missing-deck path
raises loudly with the unknown_pdk code. Runs in the repo env.
"""

import hashlib
from pathlib import Path

import pytest

LANE = Path(__file__).resolve().parent
FIXTURES = LANE / "fixtures"
STANDIN = FIXTURES / "standin_deck" / "ltoi300.stand-in.lydrc"
FETCH_URL = "https://resources.luxtelligence.ai/request-access?resource=drc"


def _require_fixture():
    assert STANDIN.is_file(), (
        f"missing stand-in deck fixture: {STANDIN} "
        "(GREEN adds it; the gated upstream deck is never faked)"
    )
    text = STANDIN.read_text()
    assert "STAND-IN" in text
    assert FETCH_URL in text
    return text


def test_standin_deck_is_labelled_and_points_at_gate():
    _require_fixture()


def test_user_supplied_deck_flow_register_resolve_hash_pin(tmp_path):
    from rocket_engine.interfaces.pdks import (
        register_pdk,
        resolve_deck,
        verify_pdk,
    )

    _require_fixture()
    engine_root = tmp_path / "root"
    record = register_pdk(
        FIXTURES / "standin_deck", "lxt", "standin-1", engine_root=engine_root
    )
    assert record["verified"] is True
    deck = resolve_deck(
        "lxt", "standin-1", "ltoi300.stand-in.lydrc", engine_root=engine_root
    )
    assert deck["sha256"] == hashlib.sha256(STANDIN.read_bytes()).hexdigest()
    assert verify_pdk("lxt", "standin-1", engine_root=engine_root)["ok"] is True


def test_missing_deck_fails_loudly_with_unknown_pdk(tmp_path):
    from rocket_engine.interfaces.pdks import register_pdk, resolve_deck

    _require_fixture()
    engine_root = tmp_path / "root"
    register_pdk(
        FIXTURES / "standin_deck", "lxt", "standin-1", engine_root=engine_root
    )
    with pytest.raises(Exception) as excinfo:
        resolve_deck("lxt", "standin-1", "ltoi300.lydrc", engine_root=engine_root)
    assert "ltoi300.lydrc" in str(excinfo.value)
    # The lane contract: no deck -> loud unavailability, never
    # fake-green. The store names the missing deck with unknown_pdk;
    # the fetch recipe lives in docs/pdk/lxt/recipe.md (test_profile).
    assert getattr(excinfo.value, "code", "") == "unknown_pdk"


def test_upstream_layers_fixture_present_with_provenance():
    layers = FIXTURES / "ltoi300.layers.yaml"
    assert layers.is_file(), f"missing upstream layers fixture: {layers}"
    text = layers.read_text()
    assert "LT_RIDGE" in text
    assert "[2, 10]" in text
    provenance = FIXTURES / "PROVENANCE.md"
    assert provenance.is_file(), f"missing fixture provenance: {provenance}"
    prov_text = provenance.read_text()
    assert "Luxtelligence/lxt_pdk_gf" in prov_text
    assert "MIT" in prov_text
    assert "d16db6a4882657feb1ce696c16c604ff6cb7ccfa" in prov_text
