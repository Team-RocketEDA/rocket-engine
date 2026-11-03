"""CANVAS-CST-CORE: canvas.toml schema, validation, project integration.

RED: `src/project/canvas/` does not exist yet — every import below
fails until the module lands. The compiler (SDC/decks/templates)
is CANVAS-CST-COMPILE scope and is deliberately absent here.
"""

import hashlib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
WAVEFORM_CANVAS = REPO.parent / "waveform-generator" / "canvas.toml"
PHOTONIC_CANVAS = REPO.parent / "photonic_matmul" / "canvas.toml"

LIBRELANE_PROFILE = {
    "scope": "engine",
    "id": "librelane-profile",
    "revision": "r1",
}


def _canvas():
    from rocket_engine.project.canvas import (  # RED: missing module
        CanvasError,
        load_project_canvas,
    )

    return load_project_canvas, CanvasError


def _base_doc(**overrides):
    doc = {
        "schema": "rocketeda/canvas/v1",
        "hdl": {"language": "verilog", "top": "waveform_gen"},
        "technology": {
            "scope": "pdk", "id": "sky130A", "revision": "r1",
        },
        "pdks": [
            {"scope": "pdk", "id": "sky130A", "revision": "r1"},
        ],
        "targets": [
            {
                "metric": "clock.frequency",
                "operator": "ge",
                "required": True,
                "limit": {"value": 50.0, "unit": "MHz"},
            },
        ],
        "tools": {"librelane": {"profile": dict(LIBRELANE_PROFILE)}},
        "references": [],
    }
    doc.update(overrides)
    return doc


def _write_canvas(tmp_path, doc):
    from rocket_engine.project.canvas import (  # RED: missing module
        dump_canvas_toml,
    )

    (tmp_path / "canvas.toml").write_text(
        dump_canvas_toml(doc), encoding="utf-8"
    )
    return tmp_path


def test_waveform_demo_canvas_validates_clean():
    """Shipped demo intent validates: the happy path is real TOML."""
    load_project_canvas, _ = _canvas()
    assert WAVEFORM_CANVAS.is_file()
    loaded = load_project_canvas(WAVEFORM_CANVAS.parent)
    assert loaded["config"]["hdl"]["language"] == "verilog"
    assert loaded["closure"]["closure_hash"]
    assert len(loaded["closure"]["closure_hash"]) == 64


def test_photonic_canvas_without_hdl_validates():
    """Photonic-only intent (no authored HDL) validates clean."""
    load_project_canvas, _ = _canvas()
    assert PHOTONIC_CANVAS.is_file()
    loaded = load_project_canvas(PHOTONIC_CANVAS.parent)
    assert "hdl" not in loaded["config"]


def test_closure_hash_is_stable_and_content_addressed(tmp_path):
    load_project_canvas, _ = _canvas()
    root = _write_canvas(tmp_path, _base_doc())
    first = load_project_canvas(root)
    second = load_project_canvas(root)
    assert first["closure"] == second["closure"]
    assert (
        first["closure"]["canvas_sha256"]
        == hashlib.sha256(
            (root / "canvas.toml").read_bytes()
        ).hexdigest()
    )


def test_unknown_metric_fails_loud_naming_rule(tmp_path):
    load_project_canvas, CanvasError = _canvas()
    doc = _base_doc(targets=[
        {
            "metric": "vibes.overall",
            "operator": "ge",
            "limit": {"value": 11.0, "unit": "MHz"},
        },
    ])
    root = _write_canvas(tmp_path, doc)
    with pytest.raises(CanvasError) as caught:
        load_project_canvas(root)
    assert caught.value.code == "unknown_metric"
    assert "targets" in str(caught.value)


def test_wrong_unit_fails_loud_naming_rule(tmp_path):
    load_project_canvas, CanvasError = _canvas()
    doc = _base_doc(targets=[
        {
            "metric": "clock.frequency",
            "operator": "ge",
            "limit": {"value": 50.0, "unit": "V"},
        },
    ])
    root = _write_canvas(tmp_path, doc)
    with pytest.raises(CanvasError) as caught:
        load_project_canvas(root)
    assert caught.value.code == "bad_unit"
    assert "clock.frequency" in str(caught.value)


def test_unknown_tool_knob_rejected(tmp_path):
    load_project_canvas, CanvasError = _canvas()
    tools = {"librelane": {"profile": dict(LIBRELANE_PROFILE), "turbo": True}}
    root = _write_canvas(tmp_path, _base_doc(tools=tools))
    with pytest.raises(CanvasError) as caught:
        load_project_canvas(root)
    assert caught.value.code == "unknown_knob"
    assert "librelane" in str(caught.value)


def test_duplicate_inline_and_delegated_config_rejected(tmp_path):
    """Inline knobs plus a delegated file is an error, never a merge."""
    load_project_canvas, CanvasError = _canvas()
    (tmp_path / "librelane.yaml").write_text(
        "density: 0.45\n", encoding="utf-8"
    )
    tools = {
        "librelane": {
            "profile": dict(LIBRELANE_PROFILE),
            "density": 0.45,
            "configuration": "./librelane.yaml",
        },
    }
    root = _write_canvas(tmp_path, _base_doc(tools=tools))
    with pytest.raises(CanvasError) as caught:
        load_project_canvas(root)
    assert caught.value.code == "duplicate_configuration"


def test_delegated_config_enters_closure(tmp_path):
    load_project_canvas, _ = _canvas()
    (tmp_path / "librelane.yaml").write_text(
        "density: 0.45\n", encoding="utf-8"
    )
    tools = {
        "librelane": {
            "profile": dict(LIBRELANE_PROFILE),
            "configuration": "./librelane.yaml",
        },
    }
    root = _write_canvas(tmp_path, _base_doc(tools=tools))
    loaded = load_project_canvas(root)
    refs = {
        entry["path"]: entry
        for entry in loaded["closure"]["refs"]
    }
    assert refs["librelane.yaml"]["sha256"] == hashlib.sha256(
        b"density: 0.45\n"
    ).hexdigest()


def test_edited_ref_changes_closure_and_missing_ref_fails(tmp_path):
    load_project_canvas, CanvasError = _canvas()
    (tmp_path / "librelane.yaml").write_text(
        "density: 0.45\n", encoding="utf-8"
    )
    tools = {
        "librelane": {
            "profile": dict(LIBRELANE_PROFILE),
            "configuration": "./librelane.yaml",
        },
    }
    root = _write_canvas(tmp_path, _base_doc(tools=tools))
    before = load_project_canvas(root)["closure"]["closure_hash"]
    (tmp_path / "librelane.yaml").write_text(
        "density: 0.5\n", encoding="utf-8"
    )
    after = load_project_canvas(root)["closure"]["closure_hash"]
    assert after != before
    (tmp_path / "librelane.yaml").unlink()
    with pytest.raises(CanvasError) as caught:
        load_project_canvas(root)
    assert caught.value.code == "missing_ref"


def test_escaping_ref_rejected(tmp_path):
    load_project_canvas, CanvasError = _canvas()
    tools = {
        "librelane": {
            "profile": dict(LIBRELANE_PROFILE),
            "configuration": "../escape.yaml",
        },
    }
    root = _write_canvas(tmp_path, _base_doc(tools=tools))
    with pytest.raises(CanvasError) as caught:
        load_project_canvas(root)
    assert caught.value.code == "path_escape"


def test_conflicting_legacy_canvas_rejected(tmp_path):
    """canvas.cst + canvas.toml is an error; migration is explicit."""
    load_project_canvas, CanvasError = _canvas()
    root = _write_canvas(tmp_path, _base_doc())
    (tmp_path / "canvas.cst").write_text(
        "legacy\n", encoding="utf-8"
    )
    with pytest.raises(CanvasError) as caught:
        load_project_canvas(root)
    assert caught.value.code == "conflicting_canvas"


def test_unpinned_pdk_revision_rejected(tmp_path):
    load_project_canvas, CanvasError = _canvas()
    doc = _base_doc(pdks=[{"scope": "pdk", "id": "sky130A"}])
    root = _write_canvas(tmp_path, doc)
    with pytest.raises(CanvasError) as caught:
        load_project_canvas(root)
    assert caught.value.code == "unpinned_revision"


def test_ui_schema_covers_every_section_and_knob():
    """The UI renders from the schema alone: every section present."""
    from rocket_engine.project.canvas import (  # RED: missing module
        CANVAS_SCHEMA,
        KNOWN_METRICS,
        TOOL_KNOBS,
    )

    sections = {s["name"] for s in CANVAS_SCHEMA["sections"]}
    assert {
        "schema", "hdl", "technology", "pdks", "targets",
        "tools", "references",
    } <= sections
    assert set(KNOWN_METRICS) >= {
        "clock.frequency", "supply.voltage", "dac.resolution",
        "dac.dnl", "dac.inl",
    }
    assert {"librelane", "ngspice", "yosys"} <= set(TOOL_KNOBS)
