#!/usr/bin/env python3
"""Scenario harness (mock UI track): scripted CLI scenarios against the real engine.

Each scenario drives ProjectService + ExecutionService through one flow
with a fake ToolAdapter, then asserts verdicts and events. No solvers,
no UI — the mock UI track proves engine behavior headlessly.

Scenario YAML:
    name: <title>
    engine: {project_id, actor: {kind}, revision}
    steps:
      - {submit: {request_id, operation, target, expected_revision?},
         expect_error?: <code>}
      - {dispatch_fake: {exit_code, findings: [{severity, rule, message}]}}
      - {assert_verdict: FAIL}
      - {assert_event: job_queued}

Usage:
    uv run --locked python scripts/scenarios.py scenarios/ [--json] [-q]
"""

import argparse
import json
import sys
from pathlib import Path

from ruamel.yaml import YAML

from rocket_engine.adapters import ToolAdapter
from rocket_engine.execution import ExecutionService
from rocket_engine.project import ProjectService

yaml = YAML(typ="safe")


class FakeAdapter(ToolAdapter):
    """Canned ToolAdapter: proves the port roundtrip without a solver."""

    def __init__(self, canned):
        self._canned = canned

    def capabilities(self, target):
        return {"operations": ["run_drc"], "simulated": True, "target": target}

    def preflight(self, job):
        return {"ready": True}

    def execute(self, job):
        return dict(self._canned)

    def parse(self, native_output):
        return json.dumps({"findings": native_output["findings"]})


def _command_text(project_id, revision, step):
    sub = step["submit"]
    return (
        "schema: rocketeda/tooling/v0.1\n"
        f"request_id: {sub['request_id']}\n"
        f"project_id: {project_id}\n"
        f"expected_revision: \"{sub.get('expected_revision', revision)}\"\n"
        f"operation: {sub['operation']}\n"
        f"target: {{scope: project, id: {sub['target']}, revision: \"r1\"}}\n"
    )


def _run_step(ctx, num, step):
    label = f"step {num} ({next(iter(step))})"
    if "submit" in step:
        sub = step["submit"]
        try:
            ack = ctx["project"].submit(
                _command_text(ctx["project_id"], ctx["revision"], step),
                request_id=sub["request_id"],
            )
        except Exception as exc:
            want = step.get("expect_error")
            if want and getattr(exc, "code", None) == want:
                return None
            raise AssertionError(f"{label}: unexpected error {exc!r}") from exc
        if step.get("expect_error"):
            raise AssertionError(f"{label}: expected error {step['expect_error']}, got ack")
        ctx["ack"] = ack
        ctx["operation"] = sub["operation"]
        ctx["target"] = sub["target"]
        return None
    if "dispatch_fake" in step:
        if "ack" not in ctx:
            raise AssertionError(f"{label}: no submitted ack to dispatch")
        sub = step["dispatch_fake"]
        run = ctx["execution"].dispatch(
            operation=ctx["operation"],
            target=ctx["target"],
            snapshot_id=ctx["ack"]["snapshot_id"],
        )
        adapter = FakeAdapter({"findings": sub.get("findings", [])})
        job = {"run_id": run["run_id"], "operation": ctx["operation"]}
        adapter.preflight(job)
        native = adapter.execute(job)
        ctx["verdict"] = ctx["execution"].evaluate(
            run_id=run["run_id"],
            exit_code=sub.get("exit_code", 0),
            findings_fixture=adapter.parse(native),
        )
        return None
    if "assert_verdict" in step:
        got = (ctx.get("verdict") or {}).get("status")
        if got != step["assert_verdict"]:
            raise AssertionError(f"{label}: verdict {got}, want {step['assert_verdict']}")
        return None
    if "assert_event" in step:
        names = [e["event"] for e in ctx["project"].events_since(0)]
        if step["assert_event"] not in names:
            raise AssertionError(f"{label}: no {step['assert_event']} in {names}")
        return None
    raise AssertionError(f"{label}: unknown step verb")


def run_scenario(path):
    doc = yaml.load(Path(path).read_text())
    engine = doc.get("engine", {})
    ctx = {
        "project_id": engine.get("project_id", "demo"),
        "revision": engine.get("revision", "p12"),
        "project": ProjectService(
            project_id=engine.get("project_id", "demo"),
            actor=engine.get("actor", {"kind": "user"}),
            current_revision=engine.get("revision", "p12"),
        ),
        "execution": ExecutionService(project_id=engine.get("project_id", "demo")),
    }
    failures = []
    for num, step in enumerate(doc.get("steps", []), 1):
        try:
            _run_step(ctx, num, step)
        except AssertionError as exc:
            failures.append(str(exc))
            break
    return {"name": doc.get("name", Path(path).name), "passed": not failures,
            "failures": failures}


def run_all(directory):
    results = [run_scenario(p) for p in sorted(Path(directory).glob("*.yaml"))]
    passed = sum(1 for r in results if r["passed"])
    return {"scenarios": results, "passed": passed, "failed": len(results) - passed}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run engine scenario files.")
    parser.add_argument("directory")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("-q", action="store_true")
    args = parser.parse_args(argv)
    report = run_all(args.directory)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for item in report["scenarios"]:
            status = "PASS" if item["passed"] else "FAIL"
            print(f"{status} {item['name']}")
            if not args.q:
                for failure in item["failures"]:
                    print(f"  - {failure}")
        print(f"{report['passed']} passed, {report['failed']} failed")
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
