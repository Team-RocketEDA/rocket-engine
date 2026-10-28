"""B1 RED — I02 references and units.

Tests assume `rocket_engine.interfaces.resolve_reference` plus the
connection check it backs. Valid RED = the import itself fails.
"""

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "refs"


def _code(excinfo):
    return getattr(excinfo.value, "code", None)


def test_scoped_same_names_resolve_exactly():
    from rocket_engine.interfaces import resolve_reference  # RED: missing surface

    project = resolve_reference(
        {"scope": "project", "id": "heater_arm", "revision": "r7"},
        root=FIXTURES,
    )
    glob = resolve_reference(
        {"scope": "global", "id": "heater_arm", "revision": "r1"},
        root=FIXTURES,
    )
    assert project["revision"] == "r7"
    assert glob["revision"] == "r1"
    assert project is not glob


def test_unknown_reference_errors_with_exact_ref():
    from rocket_engine.interfaces import resolve_reference  # RED: missing surface

    with pytest.raises(Exception) as excinfo:
        resolve_reference(
            {"scope": "project", "id": "no_such_block", "revision": "r1"},
            root=FIXTURES,
        )
    assert _code(excinfo) == "invalid_reference"
    assert "no_such_block" in str(excinfo.value)


def test_symlink_escape_rejected(tmp_path):
    from rocket_engine.interfaces import resolve_reference  # RED: missing surface

    outside = tmp_path / "outside.yaml"
    outside.write_text("schema: rocketeda/v0.1\nkind: component\nid: sneaky\n")
    link = tmp_path / "root" / "evil.yaml"
    link.parent.mkdir()
    link.symlink_to(outside)
    with pytest.raises(Exception) as excinfo:
        resolve_reference(
            {"scope": "project", "id": "evil", "revision": "r1"},
            root=link.parent,
            path="evil.yaml",
        )
    assert _code(excinfo) == "invalid_reference"


def test_incompatible_units_rejected():
    from rocket_engine.interfaces import check_connection  # RED: missing surface

    with pytest.raises(Exception) as excinfo:
        check_connection(
            (FIXTURES / "unit_mismatch.yaml").read_text(),
            endpoint_a=("self", "o1"),
            endpoint_b=("self", "o2"),
        )
    assert _code(excinfo) == "incompatible_port"
