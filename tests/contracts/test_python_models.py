"""Consumer tests for schema-derived Pydantic types, not provider readiness."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest
from pydantic import BaseModel, ValidationError

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('contract_checker_models', ROOT / 'scripts/check_v1_contract.py')
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


def load_models(tmp_path_factory):
    """Load a fresh generated package exactly as a Python consumer would."""
    target = tmp_path_factory.mktemp('python-consumer')
    outputs = checker.render(checker.load_contract())
    assert 'python/__init__.py' in outputs, 'Canonical contract must generate Pydantic consumer models'
    for name, data in outputs.items():
        if not name.startswith('python/'):
            continue
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data)
    name = 'rocket_contract_test_models'
    package = target / 'python'
    module_spec = importlib.util.spec_from_file_location(name, package / '__init__.py', submodule_search_locations=[str(package)])
    module = importlib.util.module_from_spec(module_spec)
    sys.modules[name] = module
    module_spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def models(tmp_path_factory):
    return lambda: load_models(tmp_path_factory)


def test_boundary_quantity_is_a_typed_pydantic_model(models):
    models = models()
    value = models.Quantity.model_validate({'value': 1.8, 'unit': 'V'})
    assert isinstance(value, BaseModel)
    assert value.value == 1.8
    assert value.model_dump(mode='json', by_alias=True, exclude_unset=True) == {'value': 1.8, 'unit': 'V'}


@pytest.mark.parametrize('payload', [
    {'value': '1.8', 'unit': 'V'},
    {'value': 1.8, 'unit': 'V', 'unexpected': True},
    {'value': float('nan'), 'unit': 'V'},
    {'value': float('inf'), 'unit': 'V'},
])
def test_python_boundary_preserves_strict_wire_contract(models, payload):
    models = models()
    with pytest.raises((ValidationError, ValueError)):
        models.Quantity.model_validate(payload)


def test_missing_and_null_do_not_collapse(models):
    models = models()
    model = models.Availability.model_validate({'state': 'unknown', 'installed': None, 'qualified': False, 'reasons': []})
    assert model.model_dump(mode='json', by_alias=True, exclude_unset=True)['installed'] is None
    with pytest.raises((ValidationError, ValueError)):
        models.Availability.model_validate({'state': 'unknown', 'qualified': False, 'reasons': []})


def test_task_request_rejects_wrong_tool_despite_structural_typing(models):
    models = models()
    with pytest.raises((ValidationError, ValueError)):
        models.RunStart.model_validate({'action': 'start', 'target': {'project_id': 'chip', 'kind': 'project'}, 'task': 'simulate.spice', 'tool': 'yosys', 'options': {'analysis': 'op'}})


def test_exported_api_round_trips_without_null_padding(models):
    models = models()
    request = {'protocol': 'rocketeda/v1', 'request_id': 'describe-1', 'method': 'describe', 'params': {}}
    value = models.DescribeRequest.model_validate(request)
    assert json.loads(value.model_dump_json(by_alias=True, exclude_unset=True)) == request
