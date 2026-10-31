"""SETUP-HONESTY: shadow-proof probes, fresh masks, honest reports.

Pins the three faces of false-ready readiness: import shadows
counting as installed (GF-SHADOW), stale test masking hiding a
second solver (circulax alongside sax), and tool-blind planning.
Probe-level tests target the shadow-proof `detect_python`; the
report-level test runs the live `get_capabilities` path with the
patched probe to prove the wiring composes.
"""

import importlib.machinery
import importlib.util
import sys

SHADOW_PKG = "honesty_shadow_pkg"
INSTALLED_PKG = "honesty_installed_pkg"
DISTLESS_PKG = "honesty_distless_pkg"

# Every Python-module solver the setup surface can report: the mask
# must cover all of them or a fresh-machine simulation lies about
# whichever solver the simulation forgot (circulax alongside sax,
# meow for run_em, gdsfactory for generate_views).
PYTHON_SOLVERS = frozenset({"sax", "circulax", "meow", "gdsfactory"})


def _path_prepend(monkeypatch, path):
    monkeypatch.syspath_prepend(str(path))
    importlib.invalidate_caches()


def _shadow_dir(tmp_path, name):
    shadow = tmp_path / "shadow" / name
    shadow.mkdir(parents=True)
    return shadow


def _regular_package(tmp_path, name, version=None):
    root = tmp_path / "site"
    package = root / name
    package.mkdir(parents=True)
    (package / "__init__.py").write_text('MARKER = "honesty"\n')
    if version is not None:
        dist = root / f"{name}-{version}.dist-info"
        dist.mkdir(parents=True)
        (dist / "METADATA").write_text(
            f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n"
        )
    return root


def _mask_python(monkeypatch, names):
    real = importlib.util.find_spec

    def _fake(name, *args, **kwargs):
        if name in names:
            return None
        return real(name, *args, **kwargs)

    monkeypatch.setattr(importlib.util, "find_spec", _fake)


def _bare_path(monkeypatch, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir(exist_ok=True)
    monkeypatch.setenv("PATH", str(empty))


def _submit(engine, arguments):
    return engine.submit(
        {
            "project_id": "setup-honesty",
            "operation": "get_capabilities",
            "arguments": arguments,
            "request_id": "setup-honesty-1",
        }
    )


def test_namespace_shadow_reports_missing(tmp_path, monkeypatch):
    from rocket_engine.interfaces.setup_probes import detect_python

    shadow = _shadow_dir(tmp_path, SHADOW_PKG)
    _path_prepend(monkeypatch, shadow.parent)
    assert SHADOW_PKG not in sys.modules

    spec = importlib.util.find_spec(SHADOW_PKG)
    assert spec is not None and spec.loader is None

    found, missing = detect_python([SHADOW_PKG])
    assert found == {}
    assert missing == [SHADOW_PKG]


def test_installed_package_reports_version(tmp_path, monkeypatch):
    from rocket_engine.interfaces.setup_probes import detect_python

    root = _regular_package(tmp_path, INSTALLED_PKG, version="1.2.3")
    _path_prepend(monkeypatch, root)
    assert INSTALLED_PKG not in sys.modules

    found, missing = detect_python([INSTALLED_PKG])
    assert missing == []
    assert found == {INSTALLED_PKG: "1.2.3"}


def test_absent_module_reports_missing():
    from rocket_engine.interfaces.setup_probes import detect_python

    found, missing = detect_python(["honesty_no_such_module"])
    assert found == {}
    assert missing == ["honesty_no_such_module"]


def test_distless_directory_reports_missing(tmp_path, monkeypatch):
    from rocket_engine.interfaces.setup_probes import detect_python

    root = _regular_package(tmp_path, DISTLESS_PKG, version=None)
    _path_prepend(monkeypatch, root)
    assert DISTLESS_PKG not in sys.modules

    spec = importlib.util.find_spec(DISTLESS_PKG)
    assert spec is not None and spec.loader is not None

    found, missing = detect_python([DISTLESS_PKG])
    assert found == {}
    assert missing == [DISTLESS_PKG]


def test_genuine_toolchain_module_still_found():
    import importlib.metadata

    from rocket_engine.interfaces.setup_probes import detect_python

    found, missing = detect_python(["ruamel.yaml"])
    assert missing == []
    assert found == {"ruamel.yaml": importlib.metadata.version("ruamel.yaml")}


def test_wired_report_honest_under_shadow(tmp_path, monkeypatch):
    from rocket_engine.composition import Engine
    from rocket_engine.interfaces import setup as tracked_setup
    from rocket_engine.interfaces.setup_probes import detect_python

    monkeypatch.setattr(tracked_setup, "_detect_python", detect_python)
    real = importlib.util.find_spec
    shadow = _shadow_dir(tmp_path, "gdsfactory")

    def _shadowed(name, *args, **kwargs):
        if name == "gdsfactory":
            # Only a namespace shadow on the path: loader-less spec,
            # exactly what a stray empty directory resolves to.
            spec = importlib.machinery.ModuleSpec("gdsfactory", None)
            spec.submodule_search_locations = [str(shadow)]
            return spec
        return real(name, *args, **kwargs)

    monkeypatch.setattr(importlib.util, "find_spec", _shadowed)

    report = _submit(
        Engine("setup-honesty", actor="setup-honesty"),
        {"engine_root": str(tmp_path / "nostore")},
    )

    views = report["operations"]["generate_views"]
    assert views["readiness"] == "blocked"
    assert views["tools"]["gdsfactory"]["available"] is False
    assert views["tools"]["gdsfactory"]["missing"] == ["gdsfactory"]
    assert "uv sync --group layout" in views["tools"]["gdsfactory"]["remedy"]


def test_fresh_machine_honest_with_solvers_masked(tmp_path, monkeypatch):
    from rocket_engine.composition import _CRUD_OPERATIONS, Engine
    from rocket_engine.interfaces.vocabulary import OPERATIONS

    engine = Engine("setup-honesty", actor="setup-honesty")
    _bare_path(monkeypatch, tmp_path)
    _mask_python(monkeypatch, PYTHON_SOLVERS)

    report = _submit(engine, {"engine_root": str(tmp_path / "nostore")})

    served = set(_CRUD_OPERATIONS) | {"run_job", "place_cell", "python_execute"}
    assert sorted(report["operations"]) == sorted(OPERATIONS)
    for op, detail in report["operations"].items():
        solvers = engine.solvers_for(op)
        if not solvers:
            if op in served:
                assert detail["readiness"] == "ready", op
                continue
            assert detail["readiness"] == "unsupported", op
            continue
        tools = detail["tools"]
        if tools and all(e["available"] for e in tools.values()):
            assert detail["readiness"] == "ready", op
            continue
        assert detail["readiness"] == "blocked", op
        assert detail["missing"] != [], op
    assert report["store"]["present"] is False
    states = {e["id"]: e["state"] for e in report["catalogue"]["entries"]}
    assert set(states.values()) <= {"missing", "gated"}


def test_optical_blocked_when_sax_and_circulax_masked(tmp_path, monkeypatch):
    from rocket_engine.composition import Engine

    engine = Engine("setup-honesty", actor="setup-honesty")
    _mask_python(monkeypatch, {"sax", "circulax"})

    report = _submit(engine, {"engine_root": str(tmp_path / "nostore")})

    optical = report["operations"]["run_optical"]
    assert optical["readiness"] == "blocked"
    assert optical["tools"]["sax"]["available"] is False
    assert optical["tools"]["circulax"]["available"] is False
    assert "uv sync --group photonic" in optical["tools"]["sax"]["remedy"]
