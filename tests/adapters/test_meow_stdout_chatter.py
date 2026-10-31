"""MEOW-STDOUT — meow envelope parsing tolerates solver stdout chatter.

tidy3d prints its unwritable-config warning to stdout on import,
which broke the adapter's strict whole-stdout json.loads and
turned 4 healthy live solves into `runner_unavailable`
(docs/work/E2E-REREVIEW/journey-photonic.md FIND-05). Unit tests
below pin the new extractor (`src/adapters/meow/_envelope.py`,
green now); the `test_meow_parse_*` / `test_driver_*` regression
tests pin the wired adapter + driver contract and stay RED until
the integrator applies docs/work/MEOW-STDOUT/report.md.
"""

import importlib.util
import json
import logging
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURES = Path(__file__).parent / "fixtures" / "meow"

# Observed tidy3d import warning, verbatim modulo the home dir: it
# lands on stdout, ahead of the driver envelope (FIND-05).
TIDY3D_CHATTER = (
    "23:03:19 +04 WARNING: Unable to write to "
    "'/home/alrida-ismail/.config/tidy3d'; falling back to temporary "
    "directory.\n"
)


def _load_envelope():
    path = ROOT / "src" / "adapters" / "meow" / "_envelope.py"
    spec = importlib.util.spec_from_file_location(
        "meow_stdout_envelope", path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_adapter():
    path = ROOT / "src" / "adapters" / "meow" / "adapter.py"
    spec = importlib.util.spec_from_file_location(
        "meow_em_adapter_chatter", path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _basis(transmission=1.0, reflection=0.0, modes=2, neff0=2.3108):
    return {
        "num_modes": modes,
        "neff_re": [neff0] + [1.5] * (modes - 1),
        "neff_im": [0.0] * modes,
        "transmission": transmission,
        "reflection": reflection,
        "s21_phase_rad": 0.123,
    }


def _ok_envelope(base, refined):
    return json.dumps(
        {
            "ok": True,
            "meow_version": "0.15.0-canned",
            "tidy3d_version": "2.10.0-canned",
            "result": {
                "wl_um": 1.55,
                "widths_um": [0.5],
                "cell_length_um": 10.0,
                "base": base,
                "refined": refined,
                "convergence": {
                    "dT": abs(refined["transmission"]
                              - base["transmission"]),
                    "dR": abs(refined["reflection"]
                              - base["reflection"]),
                    "dneff": abs(refined["neff_re"][0]
                                 - base["neff_re"][0]),
                },
                "ports": {"left@0": 0, "right@0": 1},
            },
        }
    )


def _matched_native(**over):
    base = _basis(transmission=1.0, reflection=0.0, modes=2)
    refined = _basis(transmission=1.0, reflection=0.0, modes=4)
    native = {
        "exit_code": 0,
        "stdout": _ok_envelope(base, refined),
        "stderr": "",
        "spec": str(FIXTURES / "matched.yml"),
        "spec_text": (FIXTURES / "matched.yml").read_text(),
        "targets": [
            {"metric": "transmission", "min": 0.99},
            {"metric": "reflection", "max": 1.0e-6},
            {"metric": "convergence_dT", "max": 0.01},
        ],
    }
    native.update(over)
    return native


def test_extract_clean_envelope_passes_through():
    mod = _load_envelope()
    envelope = _ok_envelope(_basis(), _basis(modes=4))
    assert mod.extract_envelope(envelope) == json.loads(envelope)


def test_extract_tolerates_warning_prefix():
    mod = _load_envelope()
    envelope = _ok_envelope(_basis(), _basis(modes=4))
    got = mod.extract_envelope(TIDY3D_CHATTER + envelope)
    assert got["ok"] is True
    assert got["result"]["base"]["transmission"] == 1.0


def test_extract_tolerates_chatter_on_both_sides():
    mod = _load_envelope()
    envelope = _ok_envelope(_basis(), _basis(modes=4))
    stdout = "banner v1\n" + envelope + "\ndone in 3.2s\n"
    got = mod.extract_envelope(stdout)
    assert got["ok"] is True
    assert got["meow_version"] == "0.15.0-canned"


def test_extract_markers_beat_decoy_json_in_chatter():
    mod = _load_envelope()
    envelope = _ok_envelope(_basis(), _basis(modes=4))
    stdout = (
        '{"progress": 0.5}\n'
        + mod.BEGIN_MARKER + "\n" + envelope + "\n"
        + mod.END_MARKER + "\n"
    )
    got = mod.extract_envelope(stdout)
    assert got["ok"] is True
    assert got["result"]["base"]["transmission"] == 1.0


def test_extract_unmarked_prefers_envelope_over_decoy():
    mod = _load_envelope()
    envelope = _ok_envelope(_basis(), _basis(modes=4))
    got = mod.extract_envelope('{"progress": 0.5}\n' + envelope)
    assert got["ok"] is True
    assert got["result"]["base"]["transmission"] == 1.0


def test_extract_corrupt_marked_frame_returns_none():
    mod = _load_envelope()
    stdout = mod.BEGIN_MARKER + "\n{nope\n" + mod.END_MARKER + "\n"
    assert mod.extract_envelope(stdout) is None


def test_extract_garbage_returns_none():
    mod = _load_envelope()
    assert mod.extract_envelope("Traceback (most recent call): boom\n") is None
    assert mod.extract_envelope("") is None
    assert mod.extract_envelope(None) is None


def test_extract_preserves_failure_envelopes_through_chatter():
    mod = _load_envelope()
    failed = json.dumps(
        {
            "ok": False,
            "error": {
                "code": "missing_dependency",
                "message": "meow is not importable",
                "token": None,
                "line": None,
            },
        }
    )
    got = mod.extract_envelope(TIDY3D_CHATTER + failed)
    assert got["ok"] is False
    assert got["error"]["code"] == "missing_dependency"


def test_extract_logs_chatter_but_stays_silent_when_clean(caplog):
    mod = _load_envelope()
    envelope = _ok_envelope(_basis(), _basis(modes=4))
    with caplog.at_level(logging.WARNING):
        mod.extract_envelope(envelope)
    assert [r for r in caplog.records if "chatter" in r.message] == []
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        mod.extract_envelope(TIDY3D_CHATTER + envelope)
    hits = [r for r in caplog.records if "chatter" in r.message]
    assert len(hits) == 1
    assert "tidy3d" in hits[0].message


def test_meow_parse_tolerates_tidy3d_stdout_chatter():
    # RED until the wiring patch: strict whole-stdout json.loads
    # raises runner_unavailable on the warning prefix.
    mod = _load_adapter()
    envelope = _ok_envelope(_basis(), _basis(modes=4))
    got = mod.MeowAdapter().parse(
        _matched_native(stdout=TIDY3D_CHATTER + envelope)
    )
    assert got["total"] == 0
    by_name = {m["name"]: m for m in got["measurements"]}
    assert by_name["transmission"]["value"] == 1.0
    assert by_name["transmission"]["status"] == "pass"


def test_meow_parse_prefers_marker_frame_over_decoy_chatter():
    # RED until the wiring patch: the marked envelope must win
    # over a decoy JSON object printed ahead of it.
    envelope_mod = _load_envelope()
    mod = _load_adapter()
    envelope = _ok_envelope(_basis(), _basis(modes=4))
    stdout = (
        '{"progress": 0.5}\n'
        + envelope_mod.BEGIN_MARKER + "\n" + envelope + "\n"
        + envelope_mod.END_MARKER + "\n"
    )
    got = mod.MeowAdapter().parse(_matched_native(stdout=stdout))
    assert got["total"] == 0
    by_name = {m["name"]: m for m in got["measurements"]}
    assert by_name["transmission"]["value"] == 1.0


def test_meow_parse_chatter_without_envelope_still_raises():
    mod = _load_adapter()
    native = _matched_native(stdout=TIDY3D_CHATTER)
    try:
        mod.MeowAdapter().parse(native)
    except Exception as exc:
        assert getattr(exc, "code", None) == "runner_unavailable"
    else:
        raise AssertionError("expected runner_unavailable")


def test_driver_emits_envelope_markers():
    # RED until the wiring patch: the staged driver must frame
    # its envelope between the extractor's marker lines.
    envelope_mod = _load_envelope()
    driver = (
        ROOT / "src" / "adapters" / "meow" / "_driver.py"
    ).read_text()
    assert envelope_mod.BEGIN_MARKER in driver
    assert envelope_mod.END_MARKER in driver
