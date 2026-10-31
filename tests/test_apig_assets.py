"""API-GENERALIZE (c) raw asset serving I29: verbatim PDK bytes + hash identity.

RED: src/interfaces/apig_assets.py does not exist yet; the loader below
fails until the module lands.
"""

import base64
import hashlib
import importlib.util
from pathlib import Path

import pytest

from rocket_engine.interfaces.errors import ContractError

ROOT = Path(__file__).resolve().parent.parent

SYM_BYTES = (
    b"v {xschem version=3.4.4 file_version=1.2}\n"
    b"K {type=subcircuit\n"
    b"format=\"@name @pinlist @model\"\n"
    b"template=\"name=x1\"\n"
    b"}\n"
)
ODD_BYTES = b"\x00\xffbinary\x00tail\nno-trailing-newline"


def _load_assets():
    spec = importlib.util.spec_from_file_location(
        "apig_assets", ROOT / "src" / "interfaces" / "apig_assets.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def pdk_root(tmp_path):
    base = tmp_path / "pdks" / "demopdk" / "r1"
    (base / "xschem").mkdir(parents=True)
    (base / "inv.sym").write_bytes(SYM_BYTES)
    (base / "xschem" / "inv.sym").write_bytes(SYM_BYTES + b"* variant\n")
    (base / "odd.bin").write_bytes(ODD_BYTES)
    (base / "manifest.yaml").write_text(
        "id: demopdk\ndisplay_id: DemoPDK\nrevision: r1\n", encoding="utf-8"
    )
    return tmp_path


def test_serve_single_sym_is_verbatim_with_hash_identity(pdk_root):
    assets = _load_assets()
    served = assets.serve_asset("demopdk", "r1", "inv.sym", engine_root=pdk_root)
    assert base64.b64decode(served["content_b64"]) == SYM_BYTES
    assert served["sha256"] == hashlib.sha256(SYM_BYTES).hexdigest()
    assert served["size"] == len(SYM_BYTES)
    assert served["path"] == "inv.sym"
    assert served["pdk_id"] == "demopdk"
    assert served["revision"] == "r1"


def test_serve_preserves_odd_bytes_without_conversion(pdk_root):
    assets = _load_assets()
    served = assets.serve_asset("demopdk", "r1", "odd.bin", engine_root=pdk_root)
    assert base64.b64decode(served["content_b64"]) == ODD_BYTES
    assert served["sha256"] == hashlib.sha256(ODD_BYTES).hexdigest()


def test_serve_nested_path_and_display_id(pdk_root):
    assets = _load_assets()
    served = assets.serve_asset(
        "DemoPDK", "r1", "xschem/inv.sym", engine_root=pdk_root
    )
    assert served["path"] == "xschem/inv.sym"
    assert served["display_id"] == "DemoPDK"
    assert base64.b64decode(served["content_b64"]).endswith(b"* variant\n")


def test_serve_refuses_escape_missing_and_directories(pdk_root):
    assets = _load_assets()
    for bad in ("../r1/inv.sym", "/inv.sym", "xschem/../../r1", ".."):
        with pytest.raises(ContractError) as caught:
            assets.serve_asset("demopdk", "r1", bad, engine_root=pdk_root)
        assert caught.value.code == "invalid_reference"
    with pytest.raises(ContractError) as caught:
        assets.serve_asset("demopdk", "r1", "nope.sym", engine_root=pdk_root)
    assert caught.value.code == "invalid_reference"
    with pytest.raises(ContractError) as caught:
        assets.serve_asset("demopdk", "r1", "xschem", engine_root=pdk_root)
    assert caught.value.code == "invalid_reference"
    with pytest.raises(ContractError) as caught:
        assets.serve_asset("ghostpdk", "r1", "inv.sym", engine_root=pdk_root)
    assert caught.value.code == "invalid_reference"


def test_list_assets_covers_every_granularity(pdk_root):
    assets = _load_assets()
    listing = assets.list_assets("demopdk", "r1", engine_root=pdk_root)
    paths = [entry["path"] for entry in listing["files"]]
    assert paths == sorted(paths)
    assert "inv.sym" in paths
    assert "xschem/inv.sym" in paths
    assert "odd.bin" in paths
    by_path = {entry["path"]: entry for entry in listing["files"]}
    assert by_path["inv.sym"]["sha256"] == hashlib.sha256(SYM_BYTES).hexdigest()
    assert by_path["inv.sym"]["size"] == len(SYM_BYTES)
    assert listing["count"] == len(listing["files"])
    narrowed = assets.list_assets(
        "demopdk", "r1", prefix="xschem", engine_root=pdk_root
    )
    assert [entry["path"] for entry in narrowed["files"]] == ["xschem/inv.sym"]


def test_manifest_gives_stable_bulk_identity(pdk_root):
    assets = _load_assets()
    first = assets.asset_manifest("demopdk", "r1", engine_root=pdk_root)
    second = assets.asset_manifest("demopdk", "r1", engine_root=pdk_root)
    assert first["tree_sha256"] == second["tree_sha256"]
    assert first["count"] == len(first["files"])
    (pdk_root / "pdks" / "demopdk" / "r1" / "inv.sym").write_bytes(SYM_BYTES + b"x")
    third = assets.asset_manifest("demopdk", "r1", engine_root=pdk_root)
    assert third["tree_sha256"] != first["tree_sha256"]
