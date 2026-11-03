"""V1 tools binding: the catalog is complete and honestly qualified.

TDD RED: no v1 binding proof exists yet. GREEN pins the TOOLS
verdict from outside the Engine (composition/vocabulary stay
untouched): the canonical contract gate passes, every mvp task is
bound to a provider or carries its explicit T-28 reason, the
provision report never fakes readiness, and unknown or deferred
task names are refused loudly instead of silently queued.
"""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "contracts" / "v1" / "catalog"

# T-28 ruling (see docs/tickets/API-V1-TOOLS.md): mvp tasks with no
# provider that must NOT be staffed until ruled. Reasons recorded
# here, never silently dropped.
EXPECTED_UNBOUND_MVP = {
    "workflow.analog": "orchestrated workflow; no single provider claims it",
    "workflow.photonic": "orchestrated workflow; no single provider claims it",
    "simulate.cosim": "SEAM-COSIM Backlog ruling; do not staff until ruled",
    "analyze.measurements": "no provider at all; do not staff until ruled",
}


def _catalog(name):
    return json.loads((CATALOG / name).read_text())


def _check_module():
    spec = importlib.util.spec_from_file_location(
        "v1_contract_check", ROOT / "scripts" / "check_v1_contract.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_canonical_contract_gate_passes():
    checker = _check_module()
    contract, manifest, registry, _ = checker.load_bundle()
    positives, negatives = checker.check(contract, manifest, registry)
    assert positives > 0 and negatives > 0


def test_every_mvp_task_is_bound_or_explicitly_reasoned():
    tasks = _catalog("tasks.json")
    tools = _catalog("tools.json")
    mvp = {name: item for name, item in tasks.items()
           if item.get("delivery") == "mvp"}
    assert mvp
    for name, item in sorted(mvp.items()):
        if not item["providers"]:
            assert name in EXPECTED_UNBOUND_MVP, (
                f"mvp task {name} lost its provider with no recorded reason")
            continue
        for tool in item["providers"]:
            assert tool in tools, f"task {name} names unknown tool {tool}"
            assert name in tools[tool]["tasks"], (
                f"tool {tool} does not list task {name} back")
    assert set(item for item in mvp if not mvp[item]["providers"]) == set(
        EXPECTED_UNBOUND_MVP)


def test_tools_list_their_tasks_back():
    tasks = _catalog("tasks.json")
    tools = _catalog("tools.json")
    for tool, item in sorted(tools.items()):
        for name in item["tasks"]:
            assert tool in tasks[name]["tools"], (
                f"inconsistent tool/task association: {tool}/{name}")


def test_asic_closure_stays_librelane_led():
    tasks = _catalog("tasks.json")
    assert "librelane" in tasks["implement.asic"]["providers"]


def test_capability_report_never_fakes_readiness():
    from rocket_engine.composition import Engine

    engine = Engine("v1-tools-probe", actor="v1-tools-test")
    operations = engine.capabilities()["operations"]
    for name in ("run_drc", "run_spice", "run_synth", "run_lvs",
                 "run_view_sync", "run_cosim", "run_antenna"):
        entry = operations[name]
        assert entry["readiness"] in ("ready", "blocked", "unsupported")
        if entry["readiness"] == "ready":
            if entry["tools"]:
                for tool, detail in entry["tools"].items():
                    assert detail["available"] is True, (
                        f"{name}/{tool} claims ready while unavailable")
            else:
                assert entry.get("reason"), (
                    f"{name} claims ready with no tool or reason evidence")
        else:
            assert entry.get("reason"), f"{name} is unready with no reason"


def test_deferred_task_names_are_refused_loudly_not_queued():
    from rocket_engine.composition import Engine
    from rocket_engine.project.errors import ProjectError

    engine = Engine("v1-tools-probe", actor="v1-tools-test")
    for name in ("implement.fpga", "simulate.em", "simulate.thermal",
                 "simulate.device", "simulate.cosim", "analyze.measurements"):
        try:
            engine.submit({"project_id": "v1-tools-probe", "operation": name,
                           "arguments": {}, "request_id": f"v1-tools-{name}"})
        except ProjectError as err:
            assert err.code == "unsupported_operation", (name, err.code)
        else:
            raise AssertionError(f"deferred task name {name} was admitted")
