"""BLOCKS-CONTRACT RED — the catalogue entry contract.

The rocket-blocks catalogue is empty stubs today ("full standard
pending"); this file sets the contract every future entry must
satisfy, with one authoritative machine-checkable source:

  - ``contracts/v1/schemas/ip-entry.schema.json`` owns the
    meta.yaml shape (IpEntry + nested defs, registered in the
    bundle manifest like every other module).
  - ``src/project/ip/blocks.py`` verifies every entry against
    that schema at runtime; the schema file is the single
    source, never a duplicated rule list.
  - Filesystem-level rules the schema cannot see (entry scope,
    slugs, upstream provenance for wrapped checkouts) live in
    ``resolve_block_ref`` with loud refusal codes:
      missing entry -> unknown_ip; found-but-nonconforming ->
      invalid_ip; escaping/ill-shaped address -> invalid_reference.

Valid RED = these fail before the schema/validator lands.
"""

import importlib.util
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
SCHEMA = ROOT / "contracts" / "v1" / "schemas" / "ip-entry.schema.json"


def _code(excinfo):
    return getattr(excinfo.value, "code", None)


def _write_meta(entry_dir, mapping):
    rocket = entry_dir / "rocket"
    rocket.mkdir(parents=True, exist_ok=True)
    (rocket / "meta.yaml").write_text(
        yaml.safe_dump(mapping), encoding="utf-8")


def _resolve(blocks_root, pdk, name, version=None):
    from rocket_engine.project.ip.blocks import resolve_block_ref

    return resolve_block_ref(str(blocks_root), pdk, name, version)


def _valid_meta(name="buck-3v3", version="r1"):
    return {
        "name": name,
        "version": version,
        "kind": "analog",
        "ports": [{"name": "VDD"}, {"name": "VSS"}],
        "links": {"datasheet": "https://example.invalid/buck"},
        "license": "Apache-2.0",
        "upstream": {
            "url": "https://example.invalid/upstream",
            "rev": "abc123",
            "license": "Apache-2.0",
        },
    }


def test_packaged_schema_matches_the_single_source():
    source = (ROOT / "contracts" / "v1" / "schemas"
              / "ip-entry.schema.json").read_bytes()
    packaged = (ROOT / "src" / "project" / "ip"
                / "entry.schema.json").read_bytes()
    assert packaged == source


def test_bundle_carries_the_entry_contract():
    spec = importlib.util.spec_from_file_location(
        "v1_contract", ROOT / "scripts" / "check_v1_contract.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    contract, _manifest, _registry, _derived = module.load_bundle()
    assert "IpEntry" in contract["$defs"]
    assert "IpEntryUpstream" in contract["$defs"]
    assert "IpEntryPort" in contract["$defs"]


def test_resolve_accepts_a_fully_specified_entry(tmp_path):
    entry = tmp_path / "sky130" / "buck-3v3"
    _write_meta(entry, _valid_meta())
    out = _resolve(tmp_path, "sky130", "buck-3v3")
    assert out["entry"] == str(entry)
    assert out["version"] == "r1"
    assert out["meta"]["kind"] == "analog"


def test_resolve_accepts_minimal_identity(tmp_path):
    entry = tmp_path / "sky130" / "buck-3v3"
    _write_meta(entry, {"name": "buck-3v3", "version": "r1"})
    out = _resolve(tmp_path, "sky130", "buck-3v3")
    assert out["meta"] == {"name": "buck-3v3", "version": "r1"}


def test_resolve_refuses_missing_version(tmp_path):
    from rocket_engine.interfaces.errors import ContractError

    entry = tmp_path / "sky130" / "buck-3v3"
    _write_meta(entry, {"name": "buck-3v3"})
    with pytest.raises(ContractError) as excinfo:
        _resolve(tmp_path, "sky130", "buck-3v3")
    assert _code(excinfo) == "invalid_ip"


def test_resolve_refuses_name_disagreement(tmp_path):
    from rocket_engine.interfaces.errors import ContractError

    entry = tmp_path / "sky130" / "buck-3v3"
    _write_meta(entry, {"name": "boost-5v0", "version": "r1"})
    with pytest.raises(ContractError) as excinfo:
        _resolve(tmp_path, "sky130", "buck-3v3")
    assert _code(excinfo) == "invalid_ip"


def test_resolve_refuses_version_disagreement(tmp_path):
    from rocket_engine.interfaces.errors import ContractError

    entry = tmp_path / "sky130" / "buck-3v3"
    _write_meta(entry, _valid_meta(version="r2"))
    with pytest.raises(ContractError) as excinfo:
        _resolve(tmp_path, "sky130", "buck-3v3", version="r1")
    assert _code(excinfo) == "invalid_ip"


def test_resolve_refuses_unprovenanced_wrap(tmp_path):
    from rocket_engine.interfaces.errors import ContractError

    entry = tmp_path / "sky130" / "buck-3v3"
    _write_meta(entry, {"name": "buck-3v3", "version": "r1"})
    (entry / "entry_repo").mkdir(parents=True)
    with pytest.raises(ContractError) as excinfo:
        _resolve(tmp_path, "sky130", "buck-3v3")
    assert _code(excinfo) == "invalid_ip"


def test_resolve_refuses_nameless_port(tmp_path):
    from rocket_engine.interfaces.errors import ContractError

    entry = tmp_path / "sky130" / "buck-3v3"
    meta = _valid_meta()
    meta["ports"] = [{"direction": "in"}]
    _write_meta(entry, meta)
    with pytest.raises(ContractError) as excinfo:
        _resolve(tmp_path, "sky130", "buck-3v3")
    assert _code(excinfo) == "invalid_ip"


def test_resolve_refuses_unknown_top_level_key(tmp_path):
    from rocket_engine.interfaces.errors import ContractError

    entry = tmp_path / "sky130" / "buck-3v3"
    meta = _valid_meta()
    meta["author_nickname"] = "future-seeder"
    _write_meta(entry, meta)
    with pytest.raises(ContractError) as excinfo:
        _resolve(tmp_path, "sky130", "buck-3v3")
    assert _code(excinfo) == "invalid_ip"


def test_resolve_refuses_non_slug_name():
    from rocket_engine.interfaces.errors import ContractError
    from rocket_engine.project.ip.blocks import resolve_block_ref

    with pytest.raises(ContractError) as excinfo:
        resolve_block_ref("/nonexistent", "sky130", "buck_3v3")
    assert _code(excinfo) == "invalid_reference"


def test_python_models_cover_the_entry():
    spec = importlib.util.spec_from_file_location(
        "v1_contract", ROOT / "scripts" / "check_v1_contract.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    contract, _manifest, _registry, _derived = module.load_bundle()
    spec2 = importlib.util.spec_from_file_location(
        "schema_models", ROOT / "scripts" / "schema_models.py")
    models = importlib.util.module_from_spec(spec2)
    spec2.loader.exec_module(models)
    rendered = models.render_python(contract)
    assert "IpEntry" in str(rendered)
