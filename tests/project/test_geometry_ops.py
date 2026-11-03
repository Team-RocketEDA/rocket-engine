"""LAYOUT-EDIT RED — typed geometry ops + snap grids.

Valid RED = src/project/geometry/*.py do not exist yet, so the
loader below fails.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SRC = ROOT / "src" / "project"


def _load(name, rel):
    path = SRC / rel
    assert path.is_file(), f"RED: missing owned module {path}"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def mods():
    ops = _load("geometry_ops_red", "geometry/ops.py")
    snap = _load("geometry_snap_red", "geometry/snap.py")
    return ops, snap


def _service(tmp_path):
    from rocket_engine.project.service import ProjectService
    return ProjectService(
        project_id="layout_demo", actor={"kind": "user"},
        engine_root=str(tmp_path),
    )


def test_rect_create_query_edit_reload(tmp_path, mods):
    ops, _ = mods
    service = _service(tmp_path)
    created = ops.create_shape(
        service, "req-geom-1", "draw rect",
        shape_type="rect", layer="lyr-met1",
        data={"x": 0, "y": 0, "w": 100, "h": 50},
        units="nm",
    )
    entity = created["entity"]
    got = ops.read_shape(service, entity)
    assert got["shape_type"] == "rect"
    ops.update_shape(
        service, "req-geom-2", "grow rect", entity,
        data={"x": 0, "y": 0, "w": 200, "h": 50},
        expected_entity_revision=got["entity_revision"],
    )
    assert ops.read_shape(service, entity)["data"]["w"] == 200


def test_stale_revision_fails_without_overwrite(tmp_path, mods):
    ops, _ = mods
    service = _service(tmp_path)
    created = ops.create_shape(
        service, "req-geom-3", "draw rect",
        shape_type="rect", layer="lyr-met1",
        data={"x": 0, "y": 0, "w": 10, "h": 10},
    )
    entity = created["entity"]
    with pytest.raises(Exception) as excinfo:
        ops.update_shape(
            service, "req-geom-4", "stale edit", entity,
            data={"x": 0, "y": 0, "w": 99, "h": 99},
            expected_entity_revision=999,
        )
    assert getattr(excinfo.value, "code", None) == "revision_conflict"
    assert ops.read_shape(service, entity)["data"]["w"] == 10


def test_snap_grids_stay_separate(mods):
    _, snap = mods
    assert snap.snap_to_grid(103, 10) == 100
    assert snap.snap_to_grid(107, 10) == 110
    assert snap.quantize_storage(100.4, "nm") == 100
    assert snap.quantize_storage(100.6, "nm") == 101
    verdict = snap.check_mfg_grid({"x": 3, "y": 0}, 5)
    assert verdict["state"] == "violation"
    assert verdict["authored"] == {"x": 3, "y": 0}


def test_copy_move_preserve_identity_chain(tmp_path, mods):
    ops, _ = mods
    service = _service(tmp_path)
    created = ops.create_shape(
        service, "req-geom-5", "draw poly",
        shape_type="polygon", layer="lyr-met1",
        data={"points": [[0, 0], [10, 0], [10, 10]]},
    )
    entity = created["entity"]
    moved = ops.move_shape(
        service, "req-geom-6", "nudge", entity, dx=5, dy=0,
    )
    assert moved["entity"] == entity
    copied = ops.copy_shape(service, "req-geom-7", "dup", entity)
    assert copied["entity"] != entity
    assert (copied["shape_type"], copied["layer"]) == ("polygon", "lyr-met1")
