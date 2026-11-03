"""IP-SURFACE RED — Step 8 wiring seam.

The ip_* lane logic lives in ``src/project/ip/lifecycle.py``
(``tests/project/test_ip_lifecycle.py`` covers it). This file
covers the SURFACE the Step 8 acceptance demands and which is
still missing:

  - Vocabulary: ``ip_instantiate`` / ``ip_promote`` are OPERATIONS.
  - Engine: both ride submit-immediate (register/instantiate/
    promote precedent), returning new revision + events; a
    foreign-PDK instantiate of a per-PDK block fails loudly
    with ``pdk_mismatch``; promoting an unknown version fails
    with ``unknown_ip``.
  - ``behavior-invariants.yaml`` at the repo root formalizes the
    per-PDK invariant (RULING-01).
  - ``src/project/ip/blocks.py`` resolves a registered
    (pdk, name[, version]) against the rocket-blocks layout
    (``<root>/<pdk>/<entry>/rocket/meta.yaml``); a missing entry
    fails loudly; an entry outside its PDK directory is refused.

Valid RED = these fail on the pre-slice engine (unwired names,
missing files).
"""

from pathlib import Path

import pytest

PROJECT = "analog_demo"

ROOT = Path(__file__).resolve().parent.parent.parent


def _code(excinfo):
    return getattr(excinfo.value, "code", None)


class _Session:
    """One isolated engine plus head-threaded submit."""

    def __init__(self, tmp_path):
        from rocket_engine.composition import Engine

        self.engine = Engine(
            PROJECT, actor="human", engine_root=tmp_path)
        out = self.engine.submit(
            {
                "project_id": PROJECT,
                "operation": "create_project",
                "arguments": {"new_project_id": PROJECT},
                "request_id": "req-session-create",
            }
        )
        self.head = out["current_revision"]

    def submit(self, operation, arguments, request_id):
        args = dict(arguments)
        args["expected_revision"] = self.head
        out = self.engine.submit(
            {
                "project_id": PROJECT,
                "operation": operation,
                "arguments": args,
                "request_id": request_id,
            }
        )
        self.head = out["current_revision"]
        return out


def _sheet(session, tag=""):
    out = session.submit("create_sheet", {"name": "top"},
                         f"req-sheet{tag}")
    return out["receipt"]["sheet"]


def _register(session, pdk="sky130", name="buck-3v3",
              version="r1", scope="pdk", reason="", tag=""):
    session.submit(
        "ip_register",
        {"pdk": pdk, "name": name, "version": version,
         "symbol": f"{name}.sym", "cell": f"{name}.cell",
         "scope": scope, "reason": reason},
        f"req-reg-{pdk}-{name}-{version}{tag}",
    )


def test_vocabulary_carries_instantiate_and_promote():
    from rocket_engine.interfaces.vocabulary import OPERATIONS

    assert {"ip_instantiate", "ip_promote"} <= set(OPERATIONS)


def test_instantiate_roundtrip_keeps_linkage(tmp_path):
    session = _Session(tmp_path)
    sheet = _sheet(session)
    _register(session)
    out = session.submit(
        "ip_instantiate",
        {"pdk": "sky130", "name": "buck-3v3", "sheet": sheet,
         "x": 10, "y": 20},
        "req-inst-001",
    )
    receipt = out["receipt"]
    assert receipt["pdk"] == "sky130"
    assert receipt["name"] == "buck-3v3"
    assert receipt["version"] == "r1"
    assert receipt["instance"]
    transition = out["revision_transition"]
    assert transition["to"] != transition["from"]
    assert any(
        event.get("component") == "IpLink"
        for event in receipt.get("events", [])
        if isinstance(event, dict)
    )


def test_instantiate_foreign_pdk_fails_loudly(tmp_path):
    from rocket_engine.project.errors import ProjectError

    session = _Session(tmp_path)
    sheet = _sheet(session)
    _register(session)
    with pytest.raises(ProjectError) as excinfo:
        session.submit(
            "ip_instantiate",
            {"pdk": "gf180mcu", "name": "buck-3v3", "sheet": sheet,
             "x": 0, "y": 0},
            "req-inst-foreign",
        )
    assert _code(excinfo) in ("unknown_ip", "pdk_mismatch")


def test_promote_roundtrip_and_unknown_version(tmp_path):
    from rocket_engine.project.errors import ProjectError

    session = _Session(tmp_path)
    _sheet(session)
    _register(session, version="r1", tag="-a")
    _register(session, version="r2", tag="-b")
    out = session.submit(
        "ip_promote",
        {"pdk": "sky130", "name": "buck-3v3", "version": "r2"},
        "req-promote-001",
    )
    assert out["receipt"]["version"] == "r2"
    with pytest.raises(ProjectError) as excinfo:
        session.submit(
            "ip_promote",
            {"pdk": "sky130", "name": "buck-3v3", "version": "r9"},
            "req-promote-unknown",
        )
    assert _code(excinfo) == "unknown_ip"


def test_behavior_invariants_yaml_states_per_pdk():
    import yaml

    path = ROOT / "behavior-invariants.yaml"
    assert path.is_file(), "behavior-invariants.yaml missing at repo root"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    text = str(data)
    assert "per-PDK" in text or "per_pdk" in text
    assert "IpLink" in text or "linkage" in text


def test_blocks_resolution_maps_registry_to_layout(tmp_path):
    from rocket_engine.project.ip.blocks import resolve_block_ref

    entry = tmp_path / "sky130" / "buck-3v3" / "rocket"
    entry.mkdir(parents=True)
    (entry / "meta.yaml").write_text(
        "name: buck-3v3\nversion: r1\n", encoding="utf-8"
    )
    out = resolve_block_ref(str(tmp_path), "sky130", "buck-3v3")
    assert out["pdk"] == "sky130"
    assert out["name"] == "buck-3v3"
    assert out["entry"] == str(tmp_path / "sky130" / "buck-3v3")


def test_blocks_resolution_missing_entry_fails_loudly(tmp_path):
    from rocket_engine.interfaces.errors import ContractError
    from rocket_engine.project.ip.blocks import resolve_block_ref

    with pytest.raises(ContractError) as excinfo:
        resolve_block_ref(str(tmp_path), "sky130", "no-such-block")
    assert _code(excinfo) == "unknown_ip"


def test_blocks_resolution_refuses_pdk_escape(tmp_path):
    from rocket_engine.interfaces.errors import ContractError
    from rocket_engine.project.ip.blocks import resolve_block_ref

    with pytest.raises(ContractError) as excinfo:
        resolve_block_ref(str(tmp_path), "../other", "buck-3v3")
    assert _code(excinfo) == "invalid_reference"
