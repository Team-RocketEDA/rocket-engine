"""Executable RED contracts for deferred local task boundaries.

These exercise the current public HTTP adapter and real Engine. They use no
native tools, fake success data, skip, or xfail. They pin v1 discovery and a
pre-admission delivery refusal; they do not qualify deferred physics solvers.
"""

import copy
import json
from pathlib import Path

import pytest

from rocket_engine.adapters.http import HttpTransport
from rocket_engine.composition import Engine

ROOT = Path(__file__).resolve().parents[2]
PROJECT = "deferred_contract"
DEFERRED = [
    ("implement.fpga", "off_mvp"),
    ("simulate.em", "post_mvp"),
    ("simulate.thermal", "post_mvp"),
    ("simulate.device", "post_mvp"),
]


def _task_request(task):
    """Reuse a canonical task example instead of inventing a parallel shape."""
    examples = json.loads((ROOT / "v1/examples/accepted.json").read_text())
    for example in examples:
        value = example["value"]
        if (example["schema"] == "#/$defs/Request"
                and value.get("method") == "run"
                and value.get("params", {}).get("task") == task):
            request = copy.deepcopy(value)
            request["request_id"] = "deferred-" + task.replace(".", "-")
            request["params"]["target"] = {"project_id": PROJECT, "kind": "project"}
            return request
    raise AssertionError(f"Canonical contract lacks the expected task example: {task}")


@pytest.mark.parametrize("task,delivery", DEFERRED)
def test_deferred_task_describes_delivery_and_schemas(task, delivery):
    """A future v1 provider describes deferred work without importing a solver."""
    engine = Engine(PROJECT, actor="contract-test")
    request = {
        "protocol": "rocketeda/v1",
        "request_id": "describe-" + task.replace(".", "-"),
        "method": "describe",
        "params": {"subject": "task", "name": task},
    }
    response = HttpTransport(engine).handle(json.dumps(request))
    assert response["method"] == "describe"
    descriptor = next(item for item in response["data"]["items"]
                      if item["name"] == task)
    assert descriptor["delivery"] == delivery
    assert descriptor["availability"]["state"] != "ready"
    assert response["data"]["schema"]


@pytest.mark.parametrize("task,delivery", DEFERRED)
def test_deferred_task_is_refused_before_native_execution(task, delivery):
    """The MVP refuses defined deferred tasks through the typed v1 boundary."""
    engine = Engine(PROJECT, actor="contract-test")
    response = HttpTransport(engine).handle(json.dumps(_task_request(task)))
    error = response["error"]
    assert error["code"] == "capability_unavailable"
    assert error["admitted"] is False
    assert error["retryable"] is False
    assert any(detail["code"] == "deferred_task"
               and delivery in detail["message"] for detail in error["details"])
