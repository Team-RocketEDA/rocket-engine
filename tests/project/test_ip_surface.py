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


def _submit(engine, operation, arguments, request_id):
    return engine.submit(
        {
            "project_id": PROJECT,
            "operation": operation,
            "arguments": arguments,
            "request_id": request_id,
        }
    )


def _engine():
    from rocket_engine.composition import Engine

    return Engine(PROJECT, actor="human")


def _sheet(engine, tag=""):
    sheet_out = _submit(engine, "create_sheet", {"name": "top"},
                        f"req-sheet{tag}")
    return sheet_out["receipt"]["sheet"]


def _register(engine, pdk="sky130", name="buck_3v3",
              version="r1", scope="pdk", reason="", tag=""):
    _submit(
        engine, "ip_register",
        {"pdk": pdk, "name": name, "version": version,
         "symbol": f"{name}.sym", "cell": f"{name}.cell",
         "scope": scope, "reason": reason},
        f"req-reg-{pdk}-{name}-{version}{tag}",
    )


def test_vocabulary_carries_instantiate_and_promote():
    from rocket_engine.interfaces.vocabulary import OPERATIONS

    assert {"ip_instantiate", "ip_promote"} <= set(OPERATIONS)


def test_instantiate_roundtrip_keeps_linkage():
    engine = _engine()
    sheet = _sheet(engine)
    _register(engine)
    out = _submit(
        engine, "ip_instantiate",
        {"pdk": "sky130", "name": "buck_3v3", "sheet": sheet,
         "x": 10, "y": 20},
        "req-inst-001",
    )
    receipt = out["receipt"]
    assert receipt["pdk"] == "sky130"
    assert receipt["name"] == "buck_3v3"
    assert receipt["version"] == "r1"
    assert receipt["instance"]
    transition = out["revision_transition"]
    assert transition["to"] != transition["from"]
    assert any(
        event.get("component") == "IpLink"
        for event in receipt.get("events", [])
        if isinstance(event, dict)
    )


def test_instantiate_foreign_pdk_fails_loudly():
    from rocket_engine.project.errors import ProjectError

    engine = _engine()
    sheet = _sheet(engine)
    _register(engine)
    with pytest.raises(ProjectError) as excinfo:
        _submit(
            engine, "ip_instantiate",
            {"pdk": "gf180mcu", "name": "buck_3v3", "sheet": sheet,
             "x": 0, "y": 0},
            "req-inst-foreign",
        )
    assert _code(excinfo) == "pdk_mismatch"


def test_promote_roundtrip_and_unknown_version():
    from rocket_engine.project.errors import ProjectError

    engine = _engine()
    _sheet(engine)
    _register(engine, version="r1", tag="-a")
    _register(engine, version="r2", tag="-b")
    out = _submit(
        engine, "ip_promote",
        {"pdk": "sky130", "name": "buck_3v3", "version": "r2"},
        "req-promote-001",
    )
    assert out["receipt"]["version"] == "r2"
    with pytest.raises(ProjectError) as excinfo:
        _submit(
            engine, "ip_promote",
            {"pdk": "sky130", "name": "buck_3v3", "version": "r9"},
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

    entry = tmp_path / "sky130" / "buck_3v3" / "rocket"
    entry.mkdir(parents=True)
    (entry / "meta.yaml").write_text(
        "name: buck_3v3\nversion: r1\n", encoding="utf-8"
    )
    out = resolve_block_ref(str(tmp_path), "sky130", "buck_3v3")
    assert out["pdk"] == "sky130"
    assert out["name"] == "buck_3v3"
    assert out["entry"] == str(tmp_path / "sky130" / "buck_3v3")


def test_blocks_resolution_missing_entry_fails_loudly(tmp_path):
    from rocket_engine.interfaces.errors import ContractError
    from rocket_engine.project.ip.blocks import resolve_block_ref

    with pytest.raises(ContractError) as excinfo:
        resolve_block_ref(str(tmp_path), "sky130", "no_such_block")
    assert _code(excinfo) == "unknown_ip"


def test_blocks_resolution_refuses_pdk_escape(tmp_path):
    from rocket_engine.interfaces.errors import ContractError
    from rocket_engine.project.ip.blocks import resolve_block_ref

    with pytest.raises(ContractError) as excinfo:
        resolve_block_ref(str(tmp_path), "../other", "buck_3v3")
    assert _code(excinfo) == "invalid_reference"
