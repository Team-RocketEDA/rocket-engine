"""B1 RED — I01 strict native YAML.

Every test imports the validator surface that GREEN must create
(`rocket_engine.interfaces.validate_document`) and asserts rejection
BEFORE any import, install, mutation, or execution. Valid RED = the
import itself fails: the surface does not exist yet.

Limit-boundary cases (nesting depth, document size) are generated
inline: they test a numeric limit, not a document shape, so a repo
fixture would pin an arbitrary constant.
"""

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def _code(excinfo):
    return getattr(excinfo.value, "code", None)


def test_valid_records_accepted():
    from rocket_engine.interfaces import validate_document  # RED: missing surface

    for name in ("component.yaml", "project.yaml", "pdk.yaml"):
        doc = validate_document((FIXTURES / "valid" / name).read_text())
        assert doc["id"] in ("straight_soi", "optical_demo", "example_process")


def test_duplicate_keys_rejected():
    from rocket_engine.interfaces import validate_document  # RED: missing surface

    with pytest.raises(Exception) as excinfo:
        validate_document((FIXTURES / "invalid" / "duplicate_keys.yaml").read_text())
    assert _code(excinfo) == "invalid_yaml"


def test_custom_tags_rejected():
    from rocket_engine.interfaces import validate_document  # RED: missing surface

    with pytest.raises(Exception) as excinfo:
        validate_document((FIXTURES / "invalid" / "custom_tag.yaml").read_text())
    assert _code(excinfo) == "invalid_yaml"


def test_aliases_and_merge_keys_rejected():
    from rocket_engine.interfaces import validate_document  # RED: missing surface

    with pytest.raises(Exception) as excinfo:
        validate_document((FIXTURES / "invalid" / "alias_merge.yaml").read_text())
    assert _code(excinfo) == "invalid_yaml"


def test_composition_fixtures_rejected_by_composition_guard():
    from ruamel.yaml import YAML

    from rocket_engine.interfaces import validate_document
    from rocket_engine.interfaces.documents import (
        ALLOWED_TOP_LEVEL,
        REQUIRED_TOP_LEVEL,
    )

    cases = (
        ("alias_merge.yaml", "Anchors and aliases are not allowed."),
        ("merge_key.yaml", "Merge keys are not allowed."),
    )
    for name, guard_message in cases:
        text = (FIXTURES / "invalid" / name).read_text()
        shape = YAML(typ="safe").load(text)
        assert isinstance(shape, dict), name
        assert set(REQUIRED_TOP_LEVEL) <= set(shape), name
        assert set(shape) <= set(ALLOWED_TOP_LEVEL), name
        with pytest.raises(Exception) as excinfo:
            validate_document(text)
        assert _code(excinfo) == "invalid_yaml", name
        assert guard_message in str(excinfo.value), name


def test_deep_nesting_rejected():
    from rocket_engine.interfaces import validate_document  # RED: missing surface

    payload = "level:\n" + "  level:\n" * 1200 + "    id: too-deep\n"
    with pytest.raises(Exception) as excinfo:
        validate_document(payload)
    assert _code(excinfo) == "invalid_yaml"


def test_nonfinite_scalars_rejected():
    from rocket_engine.interfaces import validate_document  # RED: missing surface

    with pytest.raises(Exception) as excinfo:
        validate_document((FIXTURES / "invalid" / "nonfinite.yaml").read_text())
    assert _code(excinfo) == "invalid_yaml"


def test_unknown_fields_rejected():
    from rocket_engine.interfaces import validate_document  # RED: missing surface

    with pytest.raises(Exception) as excinfo:
        validate_document((FIXTURES / "invalid" / "unknown_field.yaml").read_text())
    assert _code(excinfo) == "invalid_yaml"


def test_oversize_document_rejected():
    from rocket_engine.interfaces import validate_document  # RED: missing surface

    payload = "schema: rocketeda/v0.1\npadding: " + "x" * 2_000_000 + "\n"
    with pytest.raises(Exception) as excinfo:
        validate_document(payload)
    assert _code(excinfo) == "invalid_yaml"
