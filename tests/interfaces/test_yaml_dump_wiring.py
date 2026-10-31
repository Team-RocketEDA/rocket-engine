"""RUAMEL-DUMPER wiring — integrator-run AFTER the wiring patch lands.

These tests prove the Engine writes its YAML command identities
and findings through fresh dumpers (docs/work/RUAMEL-DUMPER/
wiring.patch): a failed dump raises loudly and later writes keep
distinct non-empty identities, so ledger idempotency never
collapses onto hollow text. ProjectService dumps are pinned
fresh as well (verified: its writer already dumps per call).

Before the patch they skip loudly (shared Engine dumper); after
it they run real Engine submissions through the write path.
"""

from pathlib import Path

import pytest


def _patched():
    """True once the wiring patch removes the shared Engine dumper."""
    from rocket_engine import composition

    source = Path(composition.__file__).read_text(encoding="utf-8")
    return "self._yaml.dump" not in source


def _submit(engine, project, operation, arguments, request_id):
    return engine.submit(
        {
            "project_id": project,
            "operation": operation,
            "arguments": arguments,
            "request_id": request_id,
        }
    )


def _head(engine, project):
    return _submit(
        engine, project, "get_project_snapshot", {}, "req-rd-head"
    )["current_revision"]


def _write(engine, project, path, content, request_id, extra=None):
    arguments = {
        "path": path, "content": content,
        "expected_revision": _head(engine, project),
    }
    if extra:
        arguments.update(extra)
    return _submit(engine, project, "write_doc", arguments, request_id)


def _texts(engine):
    return {
        rid: text for rid, (text, _ack)
        in engine._project._requests.items()
    }


def test_engine_poison_then_valid_write_keeps_identity():
    if not _patched():
        pytest.skip("wiring patch not applied: shared Engine dumper")
    from rocket_engine.composition import Engine

    project = "ruamel-dumper-demo"
    engine = Engine(project, actor="probe")
    _write(engine, project, "before.txt", "hi", "req-rd-before")
    with pytest.raises(Exception):
        _write(engine, project, "bad.txt", "x", "req-rd-poison",
               extra={"unrepresentable": object()})
    _write(engine, project, "after.txt", "hi2", "req-rd-after")
    texts = _texts(engine)
    assert texts["req-rd-before"] != ""
    assert texts["req-rd-after"] != ""
    assert texts["req-rd-before"] != texts["req-rd-after"]


def test_engine_poison_then_reuse_conflicts():
    if not _patched():
        pytest.skip("wiring patch not applied: shared Engine dumper")
    from rocket_engine.composition import Engine
    from rocket_engine.project.errors import ProjectError

    project = "ruamel-dumper-reuse"
    engine = Engine(project, actor="probe")
    _write(engine, project, "a.txt", "hi", "req-rd-reuse")
    with pytest.raises(Exception):
        _write(engine, project, "bad.txt", "x", "req-rd-poison",
               extra={"unrepresentable": object()})
    with pytest.raises(ProjectError) as excinfo:
        _write(engine, project, "other.txt", "zzz", "req-rd-reuse")
    assert excinfo.value.code == "request_conflict"


def test_engine_happy_path_bytes_unchanged():
    if not _patched():
        pytest.skip("wiring patch not applied: shared Engine dumper")
    from rocket_engine.composition import Engine
    from rocket_engine.interfaces.runparams import validate_run_request
    from rocket_engine.interfaces.yaml_dump import dump_yaml_text

    project = "ruamel-dumper-bytes"
    engine = Engine(project, actor="probe")
    head = _head(engine, project)
    _submit(
        engine, project, "write_doc",
        {"path": "a.txt", "content": "hi",
         "expected_revision": head},
        "req-rd-bytes",
    )
    stored = _texts(engine)["req-rd-bytes"]
    # RUN-PARAMS freezes `request` to all defaults on every submit
    # before the identity dump, so the admitted arguments carry it.
    admitted = {
        "path": "a.txt", "content": "hi",
        "expected_revision": head,
        "request": validate_run_request(None),
    }
    assert stored == dump_yaml_text(
        {"operation": "write_doc", "arguments": admitted}
    )


def test_project_service_dumps_use_fresh_dumpers():
    if not _patched():
        pytest.skip("wiring patch not applied: shared Engine dumper")
    from rocket_engine.project import service

    source = Path(service.__file__).read_text(encoding="utf-8")
    assert "self._yaml.dump" not in source
