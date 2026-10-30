"""ENGINE-SETUP RED — get_capabilities wiring + provision catalogue.

Tests assume `rocket_engine.interfaces.setup` with:
  CATALOGUE_VERSION, SetupError, load_catalogue, catalogue_state,
  report_capabilities; plus `Engine.submit(get_capabilities)` wired
through `Engine.capabilities`. Valid RED = the import itself fails:
the surface does not exist yet.

Policy under test (docs/tickets/ENGINE-SETUP.md + F12/I32):
  per-solver availability from adapters' capabilities() + tool
  resolution; PDK/deck install state via the store; cloud entries
  BYOC-gated without keys, never attempting network. Everything
  reports honestly; nothing installs or phones home: the query is
  read-only (no store skeleton, no writes) and cloud-gated entries
  never touch the network.
"""

import importlib.util
import os
import re
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

# Canonical sky130A deck relpaths (scripts/scenarios.py): the deck
# rows the catalogue tracks for the provisionable PDK.
DECK_RELS = [
    "libs.tech/klayout/drc/sky130A.lydrc",
    "libs.tech/magic/sky130A.tech",
    "libs.tech/combined/sky130.lib.spice",
    "libs.tech/netgen/sky130A_setup.tcl",
]

MESHER_BANNER = """NETGEN-6.2.2401
Developed by Joachim Schoeberl at
2010-xxxx Vienna University of Technology
2006-2010 RWTH Aachen University
1996-2006 Johannes Kepler University Linz
"""


def _bindir(tmp_path, names, banner=None):
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    for name in names:
        stub = bindir / name
        if banner is not None:
            stub.write_text(
                "#!/bin/sh\n"
                'if [ "$1" = "-help" ]; then\n'
                f"printf '%s' {banner!r}\n"
                "exit 0\n"
                "fi\n"
                "echo 'not the LVS netgen' >&2\n"
                "exit 1\n",
                encoding="utf-8",
            )
        else:
            stub.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        stub.chmod(0o755)
    return bindir


def _bare_path(monkeypatch, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir(exist_ok=True)
    monkeypatch.setenv("PATH", str(empty))
    return empty


def _no_sax(monkeypatch):
    real = importlib.util.find_spec

    def _fake(name, *args, **kwargs):
        if name == "sax":
            return None
        return real(name, *args, **kwargs)

    monkeypatch.setattr(importlib.util, "find_spec", _fake)


def _no_network(monkeypatch):
    def _boom(*args, **kwargs):
        raise AssertionError("network attempted during capabilities report")

    monkeypatch.setattr(socket, "socket", _boom)


def _make_tiny_sky130a(base):
    for rel in DECK_RELS:
        target = base / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"# tiny {rel}\n", encoding="utf-8")
    return base


def _submit(engine, arguments=None):
    return engine.submit(
        {
            "project_id": "setup-probe",
            "operation": "get_capabilities",
            "arguments": arguments or {},
            "request_id": "setup-probe-1",
        }
    )


def _engine():
    from rocket_engine.composition import Engine  # RED: unwired query

    return Engine("setup-probe", actor="setup-probe")


def test_catalogue_loads_versioned_entries():
    from rocket_engine.interfaces.setup import (  # RED: missing surface
        CATALOGUE_VERSION,
        load_catalogue,
    )

    catalogue = load_catalogue()
    assert catalogue["catalogue_version"] == CATALOGUE_VERSION
    entries = catalogue["entries"]
    assert entries != []
    ids = [entry["id"] for entry in entries]
    assert len(ids) == len(set(ids))
    for entry in entries:
        assert entry["kind"] in ("tool", "python", "pdk", "cloud"), entry
        assert entry["label"].strip(), entry
        assert entry["remedy"].strip(), entry
        assert entry["recipe"].strip(), entry


def test_catalogue_covers_install_sh_probes():
    from rocket_engine.interfaces.setup import load_catalogue  # RED: missing

    probed = set()
    for line in (ROOT / "scripts" / "install.sh").read_text().splitlines():
        match = re.match(r"probe (\S+)", line)
        if match:
            probed.add(match.group(1))
    assert probed != set()
    covered = set()
    for entry in load_catalogue()["entries"]:
        covered.update(entry.get("binaries") or [])
    assert probed <= covered, probed - covered


def test_submit_get_capabilities_is_wired(tmp_path, monkeypatch):
    engine = _engine()  # RED: unsupported_operation
    _bare_path(monkeypatch, tmp_path)
    _no_sax(monkeypatch)

    report = _submit(engine, {"engine_root": str(tmp_path / "nostore")})

    assert sorted(report) == ["catalogue", "cloud", "decks", "operations", "pdks", "store"]
    assert report["catalogue"]["entries"] != []


def test_fresh_machine_names_every_missing_tool_with_remedy(tmp_path, monkeypatch):
    engine = _engine()  # RED: unwired query
    _bare_path(monkeypatch, tmp_path)
    _no_sax(monkeypatch)
    _no_network(monkeypatch)

    report = _submit(engine, {"engine_root": str(tmp_path / "nostore")})

    from rocket_engine.composition import _CRUD_OPERATIONS
    from rocket_engine.interfaces.vocabulary import OPERATIONS

    served = set(_CRUD_OPERATIONS) | {"run_job"}
    assert sorted(report["operations"]) == sorted(OPERATIONS)
    for op, detail in report["operations"].items():
        solvers = engine.solvers_for(op)
        if not solvers:
            if op in served:
                assert detail["readiness"] == "ready", op
                continue
            assert detail["readiness"] == "unsupported", op
            assert "No solver registered" in detail["reason"], op
            continue
        assert detail["readiness"] == "blocked", op
        assert detail["missing"] != [], op
        assert detail["remedy"].strip(), op
        for tool, entry in detail["tools"].items():
            assert entry["available"] is False, (op, tool)
            assert entry["missing"] != [], (op, tool)
            assert entry["remedy"].strip(), (op, tool)
            for name in entry["missing"]:
                assert name.lower() in entry["remedy"].lower(), (op, tool, name)
    assert report["pdks"] == []
    assert report["store"]["present"] is False
    assert report["store"]["remedy"].strip()
    assert all(d["state"] == "missing" for d in report["decks"])
    states = {e["id"]: e["state"] for e in report["catalogue"]["entries"]}
    assert states != {}
    assert set(states.values()) <= {"missing", "gated"}
    # The report itself imports no cloud clients (diff, not global
    # state: earlier suites may legitimately import tidy3d).
    before_modules = set(sys.modules)
    _submit(engine, {"engine_root": str(tmp_path / "nostore")})
    assert {"gdsfactoryplus", "tidy3d"} & (set(sys.modules) - before_modules) == set()


def test_single_tool_install_flips_exactly_its_state(tmp_path, monkeypatch):
    engine = _engine()  # RED: unwired query
    _bare_path(monkeypatch, tmp_path)
    _no_sax(monkeypatch)
    args = {"engine_root": str(tmp_path / "nostore")}

    before = {
        e["id"]: e["state"] for e in _submit(engine, args)["catalogue"]["entries"]
    }
    bindir = _bindir(tmp_path, ["magic"])
    monkeypatch.setenv("PATH", str(bindir))
    report = _submit(engine, args)

    after = {e["id"]: e["state"] for e in report["catalogue"]["entries"]}
    flipped = [i for i in after if before[i] != after[i]]
    assert flipped == ["magic"], flipped
    assert after["magic"] == "installed"
    assert report["operations"]["run_extraction"]["readiness"] == "ready"
    # run_drc is ready via its magic default while klayout stays
    # per-tool unavailable: readiness is any-available, detail is per-tool.
    assert report["operations"]["run_drc"]["readiness"] == "ready"
    assert report["operations"]["run_drc"]["tools"]["magic"]["available"] is True
    assert report["operations"]["run_drc"]["tools"]["klayout"]["available"] is False
    assert report["operations"]["run_lvs"]["readiness"] == "blocked"


def test_single_pdk_register_flips_exactly_its_state(tmp_path, monkeypatch):
    from rocket_engine.interfaces.pdks import register_pdk

    engine = _engine()  # RED: unwired query
    _bare_path(monkeypatch, tmp_path)
    _no_sax(monkeypatch)
    root = tmp_path / "root"
    args = {"engine_root": str(root)}

    before = {
        e["id"]: e["state"] for e in _submit(engine, args)["catalogue"]["entries"]
    }
    register_pdk(_make_tiny_sky130a(tmp_path / "tiny"), "sky130A", "r1",
                 engine_root=root)
    report = _submit(engine, args)

    after = {e["id"]: e["state"] for e in report["catalogue"]["entries"]}
    flipped = [i for i in after if before[i] != after[i]]
    assert flipped == ["pdk-sky130A"], flipped
    assert after["pdk-sky130A"] == "installed"
    assert [p["id"] for p in report["pdks"]] == ["sky130A"]
    decks = [d for d in report["decks"] if d["revision"] == "r1"]
    assert sorted(d["rel"] for d in decks) == sorted(DECK_RELS)
    assert all(d["state"] == "installed" and d["sha256"] for d in decks)


def test_netgen_impostor_reports_blocked_with_cause(tmp_path, monkeypatch):
    engine = _engine()  # RED: unwired query
    bindir = _bindir(tmp_path, ["netgen"], banner=MESHER_BANNER)
    monkeypatch.setenv("PATH", str(bindir))
    _no_sax(monkeypatch)

    report = _submit(engine, {"engine_root": str(tmp_path / "nostore")})

    lvs = report["operations"]["run_lvs"]
    assert lvs["readiness"] == "blocked"
    assert lvs["tools"]["netgen"]["available"] is False
    assert "impostor" in lvs["tools"]["netgen"]["remedy"]
    assert "NGSPICE-LIVE" in lvs["tools"]["netgen"]["remedy"]


def test_sax_absent_reports_photonic_remedy(tmp_path, monkeypatch):
    engine = _engine()  # RED: unwired query
    _no_sax(monkeypatch)

    report = _submit(engine, {"engine_root": str(tmp_path / "nostore")})

    optical = report["operations"]["run_optical"]
    assert optical["readiness"] == "blocked"
    assert optical["tools"]["sax"]["available"] is False
    assert "sax not installed" in optical["tools"]["sax"]["remedy"]
    assert "uv sync --group photonic" in optical["tools"]["sax"]["remedy"]


def test_cloud_entries_gated_without_keys_and_no_network(tmp_path, monkeypatch):
    engine = _engine()  # RED: unwired query
    _bare_path(monkeypatch, tmp_path)
    _no_sax(monkeypatch)
    _no_network(monkeypatch)

    report = _submit(engine, {"engine_root": str(tmp_path / "nostore")})

    assert report["cloud"] != {}
    for service, entry in report["cloud"].items():
        assert entry["status"] == "gated", service
        assert entry["key_state"] == "missing", service
        assert "CLOUD-AUTH" in entry["remedy"], service


def test_capabilities_pass_through_adapter_reports(tmp_path, monkeypatch):
    engine = _engine()  # RED: unwired query
    _bare_path(monkeypatch, tmp_path)
    _no_sax(monkeypatch)

    report = _submit(
        engine, {"target": "probe", "engine_root": str(tmp_path / "nostore")}
    )

    seen = 0
    for op, solvers in report["operations"].items():
        for tool, entry in solvers["tools"].items():
            adapter = engine.solvers_for(op)[tool]
            assert entry["capability"] == adapter.capabilities("probe")
            seen += 1
    assert seen > 0


def test_unregistered_operations_report_unsupported(tmp_path, monkeypatch):
    engine = _engine()  # RED: unwired query
    _bare_path(monkeypatch, tmp_path)
    _no_sax(monkeypatch)

    report = _submit(engine, {"engine_root": str(tmp_path / "nostore")})

    orphans = [
        op for op, detail in report["operations"].items()
        if detail["readiness"] == "unsupported"
    ]
    assert "run_formal" in orphans
    assert "run_em" in orphans
    for op in orphans:
        assert report["operations"][op]["tools"] == {}
        assert "No solver registered" in report["operations"][op]["reason"]


def test_engine_served_operations_report_ready(tmp_path, monkeypatch):
    from rocket_engine.composition import _CRUD_OPERATIONS

    engine = _engine()
    _bare_path(monkeypatch, tmp_path)
    _no_sax(monkeypatch)

    report = _submit(engine, {"engine_root": str(tmp_path / "nostore")})

    for op in set(_CRUD_OPERATIONS) | {"run_job"}:
        detail = report["operations"][op]
        assert detail["readiness"] == "ready", op
        assert detail["tools"] == {}, op
        assert "no solver needed" in detail["reason"], op


def test_query_reads_without_creating_store(tmp_path, monkeypatch):
    engine = _engine()  # RED: unwired query
    _bare_path(monkeypatch, tmp_path)
    _no_sax(monkeypatch)
    root = tmp_path / "nostore"

    _submit(engine, {"engine_root": str(root)})

    assert not root.exists()


def test_solver_without_detection_spec_fails_loudly(tmp_path, monkeypatch):
    from rocket_engine.interfaces.setup import SetupError  # RED: missing

    class _Emx:
        def capabilities(self, target):
            return {"operations": ["run_em"], "tool": "emx"}

    engine = _engine()
    engine.register_solver("run_em", _Emx(), tool="emx")
    _bare_path(monkeypatch, tmp_path)
    _no_sax(monkeypatch)

    try:
        _submit(engine, {"engine_root": str(tmp_path / "nostore")})
    except SetupError as exc:
        assert exc.code == "unknown_solver"
        assert "emx" in str(exc)
    else:
        raise AssertionError("expected unknown_solver for spec-less tool")
