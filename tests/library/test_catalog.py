"""B2+B6 RED — I03 granular readiness, I04 PDK isolation, I13 bootstrap.

Tests assume `rocket_engine.library.Catalog`. Valid RED = the import
itself fails.
"""

from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def test_generation_ready_while_lvs_unsupported():
    from rocket_engine.library import Catalog  # RED: missing surface

    catalog = Catalog(root=FIXTURES / "pdks")
    capabilities = catalog.capabilities(pdk_id="example_process", revision="r1")
    assert capabilities["generate_views"]["readiness"] == "ready"
    assert capabilities["run_lvs"]["readiness"] == "unsupported"
    assert "reason" in capabilities["run_lvs"]


def test_same_name_revisions_stay_isolated():
    from rocket_engine.library import Catalog  # RED: missing surface

    catalog = Catalog(root=FIXTURES / "pdks")
    r1 = catalog.resolve(pdk_id="example_process", revision="r1")
    r2 = catalog.resolve(pdk_id="example_process", revision="r2")
    assert r1["source"]["path"] != r2["source"]["path"]
    assert catalog.active_context("job-a") != catalog.active_context("job-b")


def test_register_reuse_promote_without_blanket_pass():
    from rocket_engine.library import Catalog  # RED: missing surface

    catalog = Catalog(root=FIXTURES)
    ref = catalog.register(
        (FIXTURES / "ip" / "block_with_dep.yaml").read_text(), scope="project"
    )
    assert ref["status"] == "UNVERIFIED"
    inst = catalog.instantiate(
        ref, instance_id="arm_a", project_id="second_project"
    )
    assert inst["component"]["revision"] == ref["revision"]
    glob = catalog.promote(ref)
    assert glob["scope"] == "global"
    assert glob["status"] == "UNVERIFIED"
    assert all(
        dep["scope"] == "global" for dep in glob["dependency_closure"]
    )


def test_incompatible_ports_rejected_on_instantiate():
    from rocket_engine.library import Catalog  # RED: missing surface

    catalog = Catalog(root=FIXTURES)
    ref = catalog.register(
        (FIXTURES / "ip" / "block_with_dep.yaml").read_text(), scope="project"
    )
    try:
        catalog.instantiate(
            ref,
            instance_id="bad",
            project_id="second_project",
            connections=[{"port": "no_such_port", "net": "n1"}],
        )
    except Exception as exc:
        assert getattr(exc, "code", None) == "incompatible_port"
    else:
        raise AssertionError("expected incompatible_port")
