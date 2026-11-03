"""I29 merged delivery: PRD-name aliases + caps/paging + transport serving.

RED: `src/interfaces/apig_assets.py` has no PRD aliases
(`list_pdk_assets`/`get_pdk_asset`), no size cap, and no
limit/cursor paging yet — every test below fails until the module
lands them. Canonical `list_assets`/`serve_asset` behavior is
pinned by `tests/test_apig_assets.py` and must not regress.
"""

import base64
import hashlib
import importlib.util
from pathlib import Path

import pytest

from rocket_engine.composition import Engine
from rocket_engine.interfaces.errors import ContractError

ROOT = Path(__file__).resolve().parent.parent

SYM_BYTES = (
    b"v {xschem version=3.4.4 file_version=1.2}\n"
    b"K {type=subcircuit\n"
    b"format=\"@name @pinlist @model\"\n"
    b"template=\"name=x1\"\n"
    b"}\n")
ODD_BYTES = b"\x00\xffbinary\x00tail\nno-trailing-newline"


def _load_assets():
    spec = importlib.util.spec_from_file_location(
        "apig_assets_prd", ROOT / "src" / "interfaces" / "apig_assets.py"
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


def test_prd_aliases_mirror_canonical_payloads(pdk_root):
    """PRD names ride alongside canonical names with identical payloads."""
    assets = _load_assets()
    served = assets.get_pdk_asset(
        "demopdk", "r1", "inv.sym", engine_root=pdk_root
    )
    canonical = assets.serve_asset(
        "demopdk", "r1", "inv.sym", engine_root=pdk_root
    )
    assert served == canonical
    assert base64.b64decode(served["content_b64"]) == SYM_BYTES
    listing = assets.list_pdk_assets("demopdk", "r1", engine_root=pdk_root)
    canonical_listing = assets.list_assets(
        "demopdk", "r1", engine_root=pdk_root
    )
    assert listing == canonical_listing
    assert "inv.sym" in [e["path"] for e in listing["files"]]


def test_serve_asset_refuses_over_cap(pdk_root):
    """Size caps fail loudly instead of encoding unbounded bulk."""
    assets = _load_assets()
    with pytest.raises(ContractError) as caught:
        assets.serve_asset(
            "demopdk", "r1", "inv.sym", engine_root=pdk_root, max_bytes=4
        )
    assert caught.value.code == "too_large"
    assert "max_bytes" in str(caught.value).lower()
    with pytest.raises(ContractError) as caught:
        assets.get_pdk_asset(
            "demopdk", "r1", "inv.sym", engine_root=pdk_root, max_bytes=4
        )
    assert caught.value.code == "too_large"


def test_list_assets_pages_with_limit_cursor(pdk_root):
    """Bulk listings page with limit/cursor and an opaque next cursor."""
    assets = _load_assets()
    first = assets.list_assets(
        "demopdk", "r1", engine_root=pdk_root, limit=2
    )
    assert [e["path"] for e in first["files"]] == [
        "inv.sym", "manifest.yaml",
    ]
    assert first["count"] == 4
    assert first["next_cursor"] is not None
    second = assets.list_assets(
        "demopdk", "r1", engine_root=pdk_root, limit=2,
        cursor=first["next_cursor"],
    )
    assert [e["path"] for e in second["files"]] == [
        "odd.bin", "xschem/inv.sym",
    ]
    assert second["count"] == 4
    assert second["next_cursor"] is None
    walked = first["files"] + second["files"]
    full = assets.list_assets("demopdk", "r1", engine_root=pdk_root)
    assert walked == full["files"]
    assert full["next_cursor"] is None


def test_list_assets_rejects_bad_paging_shape(pdk_root):
    """Malformed limit/cursor values fail loudly, never silently clip."""
    assets = _load_assets()
    for bad in (0, -1, "two", True, 10 ** 9):
        with pytest.raises(ContractError) as caught:
            assets.list_assets(
                "demopdk", "r1", engine_root=pdk_root, limit=bad
            )
        assert caught.value.code == "invalid_command"
    for bad in ("nope", "-1", "1.5", 7):
        with pytest.raises(ContractError) as caught:
            assets.list_assets(
                "demopdk", "r1", engine_root=pdk_root, limit=2, cursor=bad
            )
        assert caught.value.code == "invalid_command"


def _engine_with_assets(root):
    from rocket_engine.adapters import api as gateway

    engine = Engine("i29serve", actor="test", engine_root=root)
    return engine, gateway


def test_transport_round_trip_list_then_serve(tmp_path):
    """Engine submit path: bulk list then cell serve, verbatim bytes."""
    root = tmp_path / "eng"
    base = root / "pdks" / "demopdk" / "r1"
    (base / "xschem").mkdir(parents=True)
    (base / "inv.sym").write_bytes(SYM_BYTES)
    engine, gateway = _engine_with_assets(root)
    listing = gateway.submit(
        engine, "i29serve", "list_assets",
        {"pdk_id": "demopdk", "revision": "r1",
         "engine_root": str(root)},
    )
    assert "inv.sym" in [e["path"] for e in listing["files"]]
    served = gateway.submit(
        engine, "i29serve", "serve_asset",
        {"pdk_id": "demopdk", "revision": "r1", "path": "inv.sym",
         "engine_root": str(root)},
    )
    assert base64.b64decode(served["content_b64"]) == SYM_BYTES
    assert served["sha256"] == hashlib.sha256(SYM_BYTES).hexdigest()
    by_path = {e["path"]: e for e in listing["files"]}
    assert by_path["inv.sym"]["sha256"] == served["sha256"]


def test_prd_alias_wiring_seam_documented():
    """Adapt-lane seam: aliases reach transports via vocabulary + wiring.

    The alias functions live in `apig_assets` (this lane). Until the
    adapt lane catalogs `list_pdk_assets`/`get_pdk_asset` in the
    vocabulary and composition wiring, transports gate them out by
    name — this test pins the seam instead of faking the wiring.
    """
    from rocket_engine.interfaces import vocabulary

    assets = _load_assets()
    assert set(assets.PRD_ALIASES) == {
        "list_pdk_assets", "get_pdk_asset",
    }
    assert assets.PRD_ALIASES["list_pdk_assets"] == "list_assets"
    assert assets.PRD_ALIASES["get_pdk_asset"] == "serve_asset"
    missing = [
        name for name in assets.PRD_ALIASES
        if name not in vocabulary.QUERIES
    ]
    assert sorted(missing) == sorted(assets.PRD_ALIASES), (
        "adapt lane has wired the aliases; move this coverage to a "
        "live transport alias test and delete the seam pin: "
        f"{missing}"
    )
