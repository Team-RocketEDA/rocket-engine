"""APPLY-CONTEXT RED — atomic session apply-context (ADR-016).

The context object does not exist yet: no `project.edit`
block, no sink primitives, no atomic exit, no generation-bound
shared session object. Valid RED = these fail on the pre-slice
engine (missing module / missing bindings).
"""

import pytest


def _ctxmod():
    from rocket_engine.execution.pyexec import apply_context

    return apply_context


def _session(generation="g1"):
    mod = _ctxmod()
    emitted = []
    return mod.ApplySession(
        emit=emitted.append,
        project_id="demo",
        console_id="c1",
        generation=generation,
        pdk_name="sky130",
        activate_pdk=lambda name: "activated:" + name,
        resolve_layer=lambda spec: (1, 0),
    ), emitted


def _component(name="mzi", ports=(), children=()):
    class FakePorts:
        def __init__(self, names):
            self._names = list(names)

        def __iter__(self):
            return iter(self._names)

    class FakeComponent:
        def __init__(self):
            self.name = name
            self.ports = FakePorts(ports)
            self.insts = list(children)

    return FakeComponent()


def test_clean_exit_lands_one_batch():
    session, emitted = _session()
    with session.edit("stage"):
        session.cell(_component(), "mzi")
        session.rect((1, 0), (0, 0, 10, 5))
    assert len(emitted) == 1
    batch = emitted[0]
    assert batch["label"] == "stage"
    assert [i["kind"] for i in batch["intents"]] == ["cell", "rect"]
    assert batch["envelope"].startswith("rocket apply")


def test_exception_drops_everything():
    session, emitted = _session()
    with pytest.raises(RuntimeError):
        with session.edit("doomed"):
            session.cell(_component(), "mzi")
            raise RuntimeError("boom")
    assert emitted == []


def test_outside_block_is_scratch():
    session, emitted = _session()
    handle = session.cell(_component(), "scratch-cell")
    assert handle.scratch is True
    assert emitted == []


def test_nesting_submits_once_at_outermost_exit():
    session, emitted = _session()
    with session.edit("outer"):
        session.cell(_component(), "a")
        with session.edit("inner"):
            session.cell(_component(), "b")
        assert emitted == []
    assert len(emitted) == 1
    assert [i["name"] for i in emitted[0]["intents"]
            if i["kind"] == "cell"] == ["a", "b"]


def test_reset_retires_context():
    session, _ = _session(generation="g1")
    session.retire()
    with pytest.raises(Exception) as excinfo:
        with session.edit("stale"):
            pass
    assert "retired" in str(excinfo.value).lower()


def test_instance_as_direct_argument_refused():
    session, emitted = _session()

    class FakeInstance:
        _gf_kind = "Instance"

    with pytest.raises(Exception) as excinfo:
        with session.edit("bad"):
            session.cell(FakeInstance(), "nope")
    assert "Instance" in str(excinfo.value)
    assert emitted == []


def test_unknown_layer_fails_loudly():
    mod = _ctxmod()

    def resolve(spec):
        raise mod.UnknownLayer(spec)

    session = mod.ApplySession(
        emit=lambda batch: None,
        project_id="demo",
        console_id="c1",
        generation="g1",
        pdk_name="sky130",
        activate_pdk=lambda name: name,
        resolve_layer=resolve,
    )
    with pytest.raises(Exception) as excinfo:
        with session.edit("layers"):
            session.rect("no-such-layer", (0, 0, 1, 1))
    assert "no-such-layer" in str(excinfo.value)


def test_envelope_identity_on_batch():
    session, emitted = _session()
    with session.edit("env-label"):
        session.rect((1, 0), (0, 0, 1, 1))
    assert "env-label" in emitted[0]["envelope"]


def test_pdk_autoactivated_and_provenance_recorded():
    activated = []
    mod = _ctxmod()
    session = mod.ApplySession(
        emit=lambda batch: None,
        project_id="demo",
        console_id="c1",
        generation="g1",
        pdk_name="sky130",
        activate_pdk=activated.append,
        resolve_layer=lambda spec: (1, 0),
    )
    with session.edit("prov"):
        session.cell(_component(), "mzi")
    assert activated == ["sky130"]
    assert session.last_batch["intents"][0]["pdk"] == "sky130"


def test_exit_receipt_carries_evidence(tmp_path):
    from rocket_engine.composition import Engine

    engine = Engine("apply-demo", actor="tester",
                    engine_root=str(tmp_path))
    session, _ = _session()
    with session.edit("land"):
        session.rect((1, 0), (0, 0, 10, 5))
    receipt = engine.apply_batch(session.last_batch)
    assert receipt["revision"]
    assert receipt["landed"] == ["rect"]
    assert receipt["revision"] != "p12"
