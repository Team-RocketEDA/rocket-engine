"""ADAPTER-PARSE-HARDEN RED — marker-delimited envelopes survive chatter.

Sax, circulax, and gdsfactory parse whole-stdout strictly today, so any
solver warning breaks the envelope (E2E-REREVIEW FIND-09). Valid RED =
chattered driver stdout fails today with runner_unavailable; GREEN =
the shared helper extracts the framed envelope and warnings stay in
the native stdout for the Engine run log. Canned envelopes only — no
live solver needed.
"""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent

PREFIX = (
    "23:03:19 +04 WARNING: Unable to write to "
    "'/home/alrida-ismail/.config/tidy3d'; "
    "falling back to temporary directory.\n"
)
SUFFIX = "solver progress: 100% done\n"


def _sax_ok():
    return {
        "ok": True,
        "sax_version": "0.18.2-canned",
        "result": {
            "wavelength_nm": [1540.0, 1550.0, 1560.0],
            "transmission": {"in0>out1": [1.0, 1.0, 1.0]},
            "ports": ["in0", "out1"],
        },
    }


def _sax_native(stdout):
    return {
        "exit_code": 0,
        "stdout": stdout,
        "stderr": "",
        "spec": "mzi.yml",
        "spec_text": "targets:\n",
        "targets": [
            {"from": "in0", "to": "out1", "at_nm": 1550.0, "min_db": -0.5}
        ],
    }


def _circulax_ok():
    grid = [i * 5e-6 / 10 for i in range(11)]
    curve = [0.9933 * (i + 1) / 11 for i in range(11)]
    curve[-1] = 0.9933
    return {
        "ok": True,
        "circulax_version": "0.2.5-canned",
        "result": {
            "t_s": grid,
            "v_V": curve,
            "final_V": curve[-1],
            "observe": "C1,p1",
            "t1_s": grid[-1],
            "points": len(grid),
        },
    }


def _circulax_native(stdout):
    return {
        "exit_code": 0,
        "stdout": stdout,
        "stderr": "",
        "spec": "good_rc.yml",
        "spec_text": "targets:\n",
        "observe": "C1,p1",
        "targets": [{"at_s": 5e-6, "min_V": 0.9}],
    }


def _views_ok():
    return {
        "ok": True,
        "gdsfactory_version": "9.51.0-canned",
        "result": {
            "recipe": "build_cells",
            "active_pdk": "cornerstone_si340",
            "cspdk_version": "2.1.0-canned",
            "mappings": [
                {
                    "source": "mzi",
                    "component": "mzi",
                    "ports": ["o1", "o2"],
                    "n_polygons": 42,
                    "bbox_um": [[0.0, 0.0], [10.0, 5.0]],
                }
            ],
            "artifacts": [
                {
                    "kind": "pins",
                    "cell": "mzi",
                    "path": "/tmp/work/mzi.pins.json",
                },
                {
                    "kind": "obstructions",
                    "cell": "mzi",
                    "path": "/tmp/work/mzi.obstructions.json",
                },
            ],
            "diagnostics": {"roundtrip_match": None, "notes": []},
        },
    }


def _views_native(stdout):
    return {
        "exit_code": 0,
        "stdout": stdout,
        "stderr": "",
        "recipe": "build_cells",
        "spec": "mzi_views.yml",
        "spec_text": "cells:\n",
        "sources": ["mzi_views.yml"],
    }


def test_envelope_roundtrip():
    from rocket_engine.adapters.envelope import (
        emit_envelope,
        extract_envelope,
    )

    payload = {"ok": True, "result": {"a": 1}}
    assert extract_envelope(emit_envelope(payload), tool="sax") == payload


def test_envelope_legacy_clean_parses():
    from rocket_engine.adapters.envelope import extract_envelope

    payload = {"ok": True, "result": {"a": 1}}
    assert extract_envelope(json.dumps(payload), tool="sax") == payload


def test_envelope_marked_chatter_parses():
    from rocket_engine.adapters.envelope import (
        emit_envelope,
        extract_envelope,
    )

    payload = {"ok": True, "result": {"a": 1}}
    stdout = PREFIX + emit_envelope(payload) + SUFFIX
    assert extract_envelope(stdout, tool="sax") == payload


def test_envelope_unmarked_chatter_parses():
    from rocket_engine.adapters.envelope import extract_envelope

    payload = {"ok": True, "result": {"a": 1}}
    stdout = PREFIX + json.dumps(payload) + "\n" + SUFFIX
    assert extract_envelope(stdout, tool="sax") == payload


def test_envelope_garbage_raises():
    from rocket_engine.adapters.envelope import extract_envelope

    try:
        extract_envelope("definitely not a driver envelope\n", tool="sax")
    except Exception as exc:
        assert getattr(exc, "code", None) == "runner_unavailable"
    else:
        raise AssertionError("expected runner_unavailable for garbage")


def test_envelope_wrong_shape_raises():
    from rocket_engine.adapters.envelope import extract_envelope

    try:
        extract_envelope(json.dumps({"foo": 1}), tool="sax")
    except Exception as exc:
        assert getattr(exc, "code", None) == "runner_unavailable"
    else:
        raise AssertionError("expected runner_unavailable for non-envelope")


def test_envelope_begin_without_end_raises():
    from rocket_engine.adapters.envelope import (
        ENVELOPE_BEGIN,
        extract_envelope,
    )

    stdout = ENVELOPE_BEGIN + "\n" + json.dumps({"ok": True}) + "\n"
    try:
        extract_envelope(stdout, tool="sax")
    except Exception as exc:
        assert getattr(exc, "code", None) == "runner_unavailable"
    else:
        raise AssertionError("expected runner_unavailable for truncated")


def test_envelope_bytes_decode():
    from rocket_engine.adapters.envelope import extract_envelope

    payload = {"ok": True, "result": {"a": 1}}
    raw = (PREFIX + json.dumps(payload) + "\n").encode("utf-8")
    assert extract_envelope(raw, tool="sax") == payload


def test_sax_parse_marked_chatter():
    from rocket_engine.adapters.envelope import emit_envelope
    from rocket_engine.adapters.sax import SaxAdapter

    stdout = PREFIX + emit_envelope(_sax_ok()) + SUFFIX
    result = SaxAdapter().parse(_sax_native(stdout))
    assert result["total"] == 0
    assert result["measurements"][0]["status"] == "pass"
    assert PREFIX.strip() in stdout


def test_sax_parse_unmarked_chatter():
    from rocket_engine.adapters.sax import SaxAdapter

    stdout = PREFIX + json.dumps(_sax_ok()) + "\n" + SUFFIX
    result = SaxAdapter().parse(_sax_native(stdout))
    assert result["total"] == 0
    assert result["measurements"][0]["status"] == "pass"


def test_sax_parse_error_envelope_with_chatter():
    from rocket_engine.adapters.envelope import emit_envelope
    from rocket_engine.adapters.sax import SaxAdapter

    payload = {
        "ok": False,
        "error": {
            "code": "invalid_circuit",
            "message": "KeyError: 'ghost'",
            "token": "ghost",
            "line": 9,
        },
    }
    stdout = PREFIX + emit_envelope(payload) + SUFFIX
    result = SaxAdapter().parse(_sax_native(stdout))
    assert result["total"] == 1
    assert result["violations"][0]["line"] == 9


def test_sax_parse_garbage_still_raises():
    from rocket_engine.adapters.sax import SaxAdapter

    try:
        SaxAdapter().parse(_sax_native("definitely not an envelope\n"))
    except Exception as exc:
        assert getattr(exc, "code", None) == "runner_unavailable"
    else:
        raise AssertionError("expected runner_unavailable for garbage")


def test_circulax_parse_marked_chatter():
    from rocket_engine.adapters.circulax.adapter import CirculaxAdapter
    from rocket_engine.adapters.envelope import emit_envelope

    stdout = PREFIX + emit_envelope(_circulax_ok()) + SUFFIX
    result = CirculaxAdapter().parse(_circulax_native(stdout))
    assert result["total"] == 0
    assert result["measurements"][0]["status"] == "pass"


def test_circulax_parse_unmarked_chatter():
    from rocket_engine.adapters.circulax.adapter import CirculaxAdapter

    stdout = PREFIX + json.dumps(_circulax_ok()) + "\n" + SUFFIX
    result = CirculaxAdapter().parse(_circulax_native(stdout))
    assert result["total"] == 0
    assert result["measurements"][0]["status"] == "pass"


def test_circulax_parse_error_envelope_with_chatter():
    from rocket_engine.adapters.circulax.adapter import CirculaxAdapter
    from rocket_engine.adapters.envelope import emit_envelope

    payload = {
        "ok": False,
        "error": {
            "code": "invalid_circuit",
            "message": "KeyError: 'ghost'",
            "token": "ghost",
            "line": 7,
        },
    }
    stdout = PREFIX + emit_envelope(payload) + SUFFIX
    result = CirculaxAdapter().parse(_circulax_native(stdout))
    assert result["total"] == 1
    assert result["violations"][0]["rule"] == "circuit"


def test_circulax_parse_garbage_still_raises():
    from rocket_engine.adapters.circulax.adapter import CirculaxAdapter

    try:
        CirculaxAdapter().parse(
            _circulax_native("Traceback (most recent call last): boom\n")
        )
    except Exception as exc:
        assert getattr(exc, "code", None) == "runner_unavailable"
    else:
        raise AssertionError("expected runner_unavailable for garbage")


def test_views_parse_marked_chatter():
    from rocket_engine.adapters.envelope import emit_envelope
    from rocket_engine.adapters.gdsfactory.adapter import (
        GdsfactoryViewsAdapter,
    )

    stdout = PREFIX + emit_envelope(_views_ok()) + SUFFIX
    result = GdsfactoryViewsAdapter().parse(_views_native(stdout))
    assert result["total"] == 0
    assert result["mappings"][0]["component"] == "mzi"


def test_views_parse_unmarked_chatter():
    from rocket_engine.adapters.gdsfactory.adapter import (
        GdsfactoryViewsAdapter,
    )

    stdout = PREFIX + json.dumps(_views_ok()) + "\n" + SUFFIX
    result = GdsfactoryViewsAdapter().parse(_views_native(stdout))
    assert result["total"] == 0
    assert result["mappings"][0]["component"] == "mzi"


def test_views_parse_error_envelope_with_chatter():
    from rocket_engine.adapters.envelope import emit_envelope
    from rocket_engine.adapters.gdsfactory.adapter import (
        GdsfactoryViewsAdapter,
    )

    payload = {
        "ok": False,
        "error": {
            "code": "invalid_cell",
            "message": "Unknown cell 'ghost'.",
            "token": "ghost",
            "line": 4,
        },
    }
    stdout = PREFIX + emit_envelope(payload) + SUFFIX
    result = GdsfactoryViewsAdapter().parse(_views_native(stdout))
    assert result["total"] == 1
    assert result["violations"][0]["rule"] == "views.unknown_cell"


def test_views_parse_garbage_still_raises():
    from rocket_engine.adapters.gdsfactory.adapter import (
        GdsfactoryViewsAdapter,
    )

    try:
        GdsfactoryViewsAdapter().parse(
            _views_native("Traceback (most recent call last): boom\n")
        )
    except Exception as exc:
        assert getattr(exc, "code", None) == "runner_unavailable"
    else:
        raise AssertionError("expected runner_unavailable for garbage")


def test_sax_driver_frames_envelope():
    text = (ROOT / "src" / "adapters" / "sax" / "_driver.py").read_text()
    assert "ROCKETEDA_ENVELOPE_BEGIN" in text
    assert "ROCKETEDA_ENVELOPE_END" in text


def test_circulax_driver_frames_envelope():
    text = (
        ROOT / "src" / "adapters" / "circulax" / "_driver.py"
    ).read_text()
    assert "ROCKETEDA_ENVELOPE_BEGIN" in text
    assert "ROCKETEDA_ENVELOPE_END" in text


def test_views_driver_frames_envelope():
    text = (
        ROOT / "src" / "adapters" / "gdsfactory" / "_driver.py"
    ).read_text()
    assert "ROCKETEDA_ENVELOPE_BEGIN" in text
    assert "ROCKETEDA_ENVELOPE_END" in text
