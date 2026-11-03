"""TEMPLATE-RUNTIME RED — custom project templates load, validate, migrate.

Valid RED = `rocket_engine.project.templates` does not exist yet, so
every test fails on ModuleNotFoundError. Custom templates extend one
versioned base shape (extra areas, custom config) without forking
the engine; unknown keys fail loudly naming the violation, the
engine-owned `engine.` config namespace stays reserved, and older
versions migrate through registered one-step links (future versions
refuse, unlinked steps name the missing migration).
"""

import pytest


def _load():
    import importlib.util
    import sys
    from pathlib import Path

    pkg_dir = (
        Path(__file__).resolve().parent.parent.parent
        / "src"
        / "project"
        / "templates"
    )
    name = "project_templates_red"
    if name in sys.modules:
        return sys.modules[name]
    errors_spec = importlib.util.spec_from_file_location(
        f"{name}.errors", pkg_dir / "errors.py"
    )
    errors = importlib.util.module_from_spec(errors_spec)
    sys.modules[f"{name}.errors"] = errors
    errors_spec.loader.exec_module(errors)
    pkg_spec = importlib.util.spec_from_file_location(
        name, pkg_dir / "__init__.py",
        submodule_search_locations=[str(pkg_dir)],
    )
    module = importlib.util.module_from_spec(pkg_spec)
    sys.modules[name] = module
    pkg_spec.loader.exec_module(module)
    return module


def _valid(version=1):
    return {
        "template_version": version,
        "id": "photonic-demo",
        "base": "default",
        "areas": [{"name": "mzi_array"}],
        "config": {"grid_um": 0.005},
    }


def test_custom_template_loads_and_validates():
    mod = _load()  # RED: missing module
    got = mod.load_template(_valid())
    assert got["template_version"] == mod.TEMPLATE_VERSION
    assert got["areas"] == [{"name": "mzi_array"}]
    assert got["config"] == {"grid_um": 0.005}


def test_custom_template_loads_from_yaml_text():
    mod = _load()  # RED: missing module
    got = mod.loads_template(
        "template_version: 1\nid: photonic-demo\nbase: default\n"
    )
    assert got["id"] == "photonic-demo"


def test_custom_template_rejects_unknown_top_level_key():
    mod = _load()  # RED: missing module
    data = _valid()
    data["forklift"] = True
    with pytest.raises(mod.TemplateError) as unknown:
        mod.load_template(data)
    assert unknown.value.code == "invalid_template"
    assert "forklift" in str(unknown.value)


def test_custom_template_rejects_engine_reserved_config():
    mod = _load()  # RED: missing module
    data = _valid()
    data["config"] = {"engine.policy": "permissive"}
    with pytest.raises(mod.TemplateError) as reserved:
        mod.load_template(data)
    assert reserved.value.code == "invalid_template"
    assert "engine.policy" in str(reserved.value)


def test_custom_template_rejects_nameless_area():
    mod = _load()  # RED: missing module
    data = _valid()
    data["areas"] = [{"label": "no name"}]
    with pytest.raises(mod.TemplateError) as area:
        mod.load_template(data)
    assert area.value.code == "invalid_template"
    assert "areas[0]" in str(area.value)


def test_custom_template_rejects_invalid_yaml():
    mod = _load()  # RED: missing module
    with pytest.raises(mod.TemplateError) as bad:
        mod.loads_template("id: [unclosed\n  - :")
    assert bad.value.code == "invalid_template"


def test_future_template_version_fails_loudly():
    mod = _load()  # RED: missing module
    with pytest.raises(mod.TemplateError) as future:
        mod.load_template(_valid(version=99))
    assert future.value.code == "future_format"


def test_missing_migration_step_fails_loudly():
    mod = _load()  # RED: missing module
    with pytest.raises(mod.TemplateError) as missing:
        mod.load_template(_valid(version=0))
    assert missing.value.code == "missing_migration"


def test_registered_link_migrates_old_template():
    mod = _load()  # RED: missing module
    mod.register_migration(
        0, 1, lambda data: {**data, "template_version": 1}
    )
    try:
        got = mod.load_template(_valid(version=0))
    finally:
        mod.clear_migrations()
    assert got["template_version"] == 1
    assert got["id"] == "photonic-demo"
