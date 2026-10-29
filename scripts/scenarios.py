#!/usr/bin/env python3
"""Scenario harness (mock UI track): scripted MCP-client scenarios.

Each scenario submits through McpTransport into the real Engine, then
either dispatches a canned FakeAdapter (fake track) or runs a live
solver on a fixture cell (live track), then asserts verdicts/events.

Scenario YAML:
    name: <title>
    engine: {project_id, actor: {kind}, revision}
    steps:
      - {submit: {request_id, operation, target, expected_revision?},
         expect_error?: <code>}
      - {dispatch_fake: {exit_code, findings: [{severity, rule, message}]}}
      - {run_live: {cell, tech, backend?, rules?}}
      - {assert_verdict: FAIL}
      - {assert_event: job_queued}

Live scenarios need the real tool (magic for run_drc) and fail loudly
without it. Fixture cells resolve under tests/adapters/fixtures/drc/.

Usage:
    uv run --locked python scripts/scenarios.py scenarios/ [--json] [-q]
"""

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

from ruamel.yaml import YAML

from rocket_engine.adapters import ToolAdapter
from rocket_engine.adapters.mcp import McpTransport
from rocket_engine.composition import Engine

ROOT = Path(__file__).resolve().parent.parent
DRC_FIXTURES = ROOT / "tests" / "adapters" / "fixtures" / "drc"
DRC_KL_FIXTURES = ROOT / "tests" / "adapters" / "fixtures" / "drc_kl"
DRC_SKY130_FIXTURES = ROOT / "tests" / "adapters" / "fixtures" / "drc_sky130"
HDL_FIXTURES = ROOT / "tests" / "adapters" / "fixtures" / "hdl"
KL_RULES = {"layer": [1, 0], "width_um": 3.0, "space_um": 3.0}
SKY130_PDK_ID = "sky130a"
SKY130_DECK_REL = "libs.tech/klayout/drc/sky130A.lydrc"

_BACKENDS = {
    "magic": {
        "fixtures": DRC_FIXTURES,
        "ext": ".mag",
        "tech": "scmos",
        "file_key": "cell_file",
        "deck": None,
    },
    "klayout": {
        "fixtures": DRC_KL_FIXTURES,
        "ext": ".gds",
        "tech": "synthetic-kl",
        "file_key": "gds_file",
        "deck": "klayout",
        "rules": KL_RULES,
    },
    "klayout_sky130": {
        "fixtures": DRC_SKY130_FIXTURES,
        "ext": ".gds",
        "tech": "sky130A",
        "file_key": "gds_file",
        "deck": "klayout",
        "sky130_deck": True,
    },
}

yaml = YAML(typ="safe")


class FakeAdapter(ToolAdapter):
    """Canned ToolAdapter: canned findings in the violations shape."""

    def __init__(self, canned):
        self._canned = canned

    def capabilities(self, target):
        return {"operations": ["run_drc"], "simulated": True, "target": target}

    def preflight(self, job):
        return {"ready": True}

    def execute(self, job):
        return dict(self._canned)

    def parse(self, native_output):
        violations = [
            {
                "rule": finding["rule"],
                "message": finding.get("message", finding["rule"]),
                "severity": finding.get("severity", "error"),
            }
            for finding in native_output.get("findings", [])
        ]
        return {"total": len(violations), "violations": violations}


def _submit_envelope(project_id, revision, step):
    sub = step["submit"]
    return json.dumps(
        {
            "jsonrpc": "2.0",
            "id": sub["request_id"],
            "method": "tools/call",
            "params": {
                "name": sub["operation"],
                "arguments": {
                    "project_id": project_id,
                    "expected_revision": sub.get("expected_revision", revision),
                    "target": {
                        "scope": "project",
                        "id": sub["target"],
                        "revision": "r1",
                    },
                },
            },
        }
    )


def _require_ack(ctx, label):
    if "ack" not in ctx:
        raise AssertionError(f"{label}: no submitted ack to dispatch")


def _resolve_sky130_deck(label):
    try:
        from rocket_engine.interfaces.pdks import list_pdks, resolve_deck
    except Exception as exc:
        raise AssertionError(f"{label}: pdk store unavailable: {exc}") from exc
    try:
        entries = list_pdks()
    except Exception as exc:
        raise AssertionError(
            f"{label}: sky130 PDK not registered ({exc}); "
            "set ROCKETEDA_HOME to a store with sky130a."
        ) from exc
    want_rev = os.environ.get("SKY130_PDK_REVISION")
    candidates = [e for e in entries if e.get("id") == SKY130_PDK_ID]
    if want_rev:
        candidates = [e for e in candidates if e.get("revision") == want_rev]
    if not candidates:
        raise AssertionError(
            f"{label}: sky130 PDK not registered; "
            "set ROCKETEDA_HOME to a store with sky130a."
        )
    entry = sorted(candidates, key=lambda e: e["revision"])[0]
    try:
        hit = resolve_deck(entry["id"], entry["revision"], SKY130_DECK_REL)
    except Exception as exc:
        raise AssertionError(f"{label}: cannot resolve sky130 deck: {exc}") from exc
    return hit["path"]


def _run_live_hdl(ctx, label, sub):
    sources = sub.get("sources")
    if not sources:
        raise AssertionError(f"{label}: hdl run_live needs sources")
    workdir = Path(tempfile.mkdtemp(prefix="scen_live_"))
    ctx["tmpdirs"].append(workdir)
    staged = []
    for name in sources:
        fixture = HDL_FIXTURES / name
        if not fixture.is_file():
            raise AssertionError(f"{label}: no fixture for source {name}")
        dest = workdir / fixture.name
        shutil.copy(fixture, dest)
        staged.append(str(dest))
    out = ctx["engine"].run(
        {
            "project_id": ctx["project_id"],
            "operation": ctx["operation"],
            "arguments": {
                "sources": staged,
                "workdir": str(workdir),
                "deck": {"tool": "icarus"},
            },
            "snapshot_id": ctx["ack"]["snapshot_id"],
        }
    )
    ctx["verdict"] = out["verdict"]
    return None


def _run_step(ctx, num, step):
    label = f"step {num} ({next(iter(step))})"
    if "submit" in step:
        try:
            ack = ctx["transport"].handle(
                _submit_envelope(ctx["project_id"], ctx["revision"], step)
            )
        except Exception as exc:
            want = step.get("expect_error")
            if want and getattr(exc, "code", None) == want:
                return None
            raise AssertionError(f"{label}: unexpected error {exc!r}") from exc
        if step.get("expect_error"):
            raise AssertionError(f"{label}: expected error {step['expect_error']}, got ack")
        ctx["ack"] = ack
        ctx["operation"] = step["submit"]["operation"]
        ctx["target"] = step["submit"]["target"]
        return None
    if "dispatch_fake" in step:
        _require_ack(ctx, label)
        sub = step["dispatch_fake"]
        ctx["engine"].register_solver(
            ctx["operation"],
            FakeAdapter({"findings": sub.get("findings", [])}),
            tool="fake",
        )
        out = ctx["engine"].run(
            {"project_id": ctx["project_id"], "operation": ctx["operation"],
             "arguments": {"deck": {"tool": "fake"}},
             "snapshot_id": ctx["ack"]["snapshot_id"]}
        )
        ctx["verdict"] = out["verdict"]
        return None
    if "run_live" in step:
        _require_ack(ctx, label)
        sub = step["run_live"]
        backend = sub.get("backend", "magic")
        if backend == "hdl":
            return _run_live_hdl(ctx, label, sub)
        try:
            table = _BACKENDS[backend]
        except KeyError:
            raise AssertionError(f"{label}: unknown backend {backend}") from None
        fixture = table["fixtures"] / f"{sub['cell']}{table['ext']}"
        if not fixture.is_file():
            raise AssertionError(f"{label}: no fixture for cell {sub['cell']}")
        workdir = Path(tempfile.mkdtemp(prefix="scen_live_"))
        ctx["tmpdirs"].append(workdir)
        layout_file = workdir / fixture.name
        shutil.copy(fixture, layout_file)
        arguments = {
            "tech": sub.get("tech", table["tech"]),
            "cell": sub["cell"],
            table["file_key"]: str(layout_file),
            "workdir": str(workdir),
        }
        if table["deck"] is not None:
            arguments["deck"] = {"tool": table["deck"]}
        if "rules" in table:
            arguments["rules"] = sub.get("rules", table["rules"])
        if table.get("sky130_deck"):
            arguments["deck_file"] = _resolve_sky130_deck(label)
        out = ctx["engine"].run(
            {
                "project_id": ctx["project_id"],
                "operation": ctx["operation"],
                "arguments": arguments,
                "snapshot_id": ctx["ack"]["snapshot_id"],
            }
        )
        ctx["verdict"] = out["verdict"]
        return None
    if "assert_verdict" in step:
        got = (ctx.get("verdict") or {}).get("status")
        if got != step["assert_verdict"]:
            raise AssertionError(f"{label}: verdict {got}, want {step['assert_verdict']}")
        return None
    if "assert_event" in step:
        names = [e["event"] for e in ctx["engine"].events_since(0)]
        if step["assert_event"] not in names:
            raise AssertionError(f"{label}: no {step['assert_event']} in {names}")
        return None
    raise AssertionError(f"{label}: unknown step verb")


def run_scenario(path):
    doc = yaml.load(Path(path).read_text())
    engine = doc.get("engine", {})
    project_id = engine.get("project_id", "demo")
    live = Engine(
        project_id=project_id,
        actor=engine.get("actor", {"kind": "user"}),
        catalog_root=".",
    )
    ctx = {
        "project_id": project_id,
        "revision": engine.get("revision", "p12"),
        "engine": live,
        "transport": McpTransport(live, project_id=project_id),
        "tmpdirs": [],
    }
    failures = []
    try:
        for num, step in enumerate(doc.get("steps", []), 1):
            try:
                _run_step(ctx, num, step)
            except AssertionError as exc:
                failures.append(str(exc))
                break
    finally:
        for tmpdir in ctx["tmpdirs"]:
            shutil.rmtree(tmpdir, ignore_errors=True)
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
