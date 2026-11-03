#!/usr/bin/env python3
"""ENGINE-CORRECTNESS gate: one command, one report, one PASS/FAIL.

Runs all four flows (good + all mutations) through the engine,
collects verdicts, writes the correctness report (totals, failed
cases with artifacts, quarantined flakes with refs).

Gate verdict: 4/4 flows green -> PASS, else FAIL. Skip = FAIL with
reason + ref (environment-blocked flows surface as FAIL blocked-env,
never hidden, never fake-green). Exit code 0 iff PASS.

Usage:
    .venv/bin/python scripts/correctness.py [--flow all|digital|analog|photonic|mixed]
        [--design NAME] [--only-good] [--report DIR] [--root PATH]

Report (stable path): tmp/correctness/report.json + report.md, with
per-failure artifacts under tmp/correctness/cases/<case>/.
DEMO-PATH runs this gate as its centerpiece.
"""

import argparse
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

FLOWS = {
    "digital": {"designs": ["serv", "picorv32"]},
    "analog": {"designs": ["bandgap"]},
    "photonic": {"designs": ["mzi"]},
    "mixed": {"designs": ["sdm_rx", "sd_top"]},
}

DESIGN_FLOW = {d: f for f, spec in FLOWS.items() for d in spec["designs"]}

VALIDATE_REF = {
    "digital": "scripts/fetch_fixtures.py; docs/tickets/VALIDATE-D.md",
    "analog": "scripts/fetch_fixtures.py; docs/tickets/VALIDATE-A.md",
    "photonic": "scripts/fetch_fixtures.py --only cspdk; docs/tickets/VALIDATE-P.md",
    "mixed": "scripts/fetch_fixtures.py; docs/tickets/VALIDATE-M.md",
}

NGSPICE_REF = "docs/tickets/NGSPICE-LIVE.md"
B10_REF = "B10-owned tooling"
SAX_REF = "B10-owned tooling (uv sync --group photonic)"

FIXTURE_MARKERS = {
    "serv": ("fixtures/upstream/serv", "rtl/serv_top.v"),
    "picorv32": ("fixtures/upstream/picorv32", "picorv32.v"),
    "bandgap": ("fixtures/upstream/sky130-bandgap",
                "sim/output-voltage-tc/netlist-snapshots/"
                "20260817-015751-13476b7.spice"),
    "mzi": ("fixtures/upstream/cspdk", "tests/gds_ref_si340/mzi.gds"),
    "sdm_rx": ("fixtures/upstream/ttsky-sigma-delta", "rtl/sdm_rx.v"),
    "sd_top": ("fixtures/upstream/ttsky-sigma-delta", "spice/sd_top_pex.spice"),
}

FIXTURE_NOTES = {
    "serv": "fixtures/upstream/serv.md",
    "picorv32": "fixtures/upstream/picorv32.md",
    "bandgap": "fixtures/upstream/sky130-bandgap.md",
    "mzi": "fixtures/upstream/cspdk.md",
    "sdm_rx": "fixtures/upstream/ttsky-sigma-delta.md",
    "sd_top": "fixtures/upstream/ttsky-sigma-delta.md",
}


def _gate_verdict(flow_verdicts):
    """PASS iff every flow verdict is exactly PASS."""
    return "PASS" if all(v == "PASS" for v in flow_verdicts.values()) else "FAIL"


def _need_icarus():
    if shutil.which("iverilog") is None or shutil.which("vvp") is None:
        return ("iverilog/vvp not on PATH", B10_REF)
    return None


def _need_klayout():
    if shutil.which("klayout") is None:
        return ("klayout not on PATH", B10_REF)
    return None


def _need_sax():
    if importlib.util.find_spec("sax") is None:
        return ("sax not installed, uv sync --group photonic", SAX_REF)
    return None


def _need_ngspice():
    if shutil.which("ngspice") is None:
        return ("ngspice not on PATH", NGSPICE_REF)
    return None


def _need_pdk():
    try:
        from rocket_engine.interfaces.paths import slugify
        from rocket_engine.interfaces.pdks import list_pdks, resolve_deck
    except Exception as exc:
        return (f"pdk store unavailable ({exc})", NGSPICE_REF)
    try:
        entries = [e for e in list_pdks()
                   if slugify(e.get("id") or "") == "sky130a"]
    except Exception as exc:
        return (f"sky130 PDK not registered ({exc}; set ROCKETEDA_HOME)",
                NGSPICE_REF)
    if not entries:
        return ("sky130 PDK not registered (set ROCKETEDA_HOME "
                "to a store with sky130A)", NGSPICE_REF)
    first = sorted(entries, key=lambda e: e["revision"])[0]
    try:
        resolve_deck(first["id"], first["revision"],
                     "libs.tech/combined/sky130.lib.spice")
    except Exception as exc:
        return (f"sky130 model lib not resolvable ({exc}; set ROCKETEDA_HOME)",
                NGSPICE_REF)
    return None


def _pdk_entry():
    from rocket_engine.interfaces.paths import slugify
    from rocket_engine.interfaces.pdks import list_pdks

    first = sorted(
        [e for e in list_pdks()
         if slugify(e.get("id") or "") == "sky130a"],
        key=lambda e: e["revision"],
    )[0]
    return {"id": first["id"], "revision": first["revision"]}


def _check_fixture(design, root):
    rel, marker = FIXTURE_MARKERS[design]
    if not (Path(root) / rel / marker).is_file():
        flow = DESIGN_FLOW[design]
        return (f"{design} fixture not fetched ({rel}/{marker})",
                VALIDATE_REF[flow])
    return None


def _case_tool_gate(design, side):
    """Return (reason, ref) if the case cannot run here, else None."""
    if design in ("serv", "picorv32", "sdm_rx"):
        miss = _need_icarus()
        return (f"{design}: {miss[0]}", miss[1]) if miss else None
    if design in ("bandgap", "sd_top"):
        miss = _need_ngspice()
        if miss:
            return (f"{design}: {miss[0]}", miss[1])
        miss = _need_pdk()
        if miss:
            return (f"{design}: {miss[0]}", miss[1])
        return None
    if design == "mzi":
        if side == "layout":
            miss = _need_klayout()
            return (f"mzi layout: {miss[0]}", miss[1]) if miss else None
        miss = _need_sax()
        return (f"mzi optical: {miss[0]}", miss[1]) if miss else None
    raise KeyError(f"unknown design: {design!r}")


def _fixture_pin(design, root):
    root = Path(root)
    note = root / FIXTURE_NOTES[design]
    rev = None
    if note.is_file():
        for line in note.read_text().splitlines():
            if "pinned rev:" in line and "`" in line:
                rev = line.split("`")[1]
    head = None
    fixture_dir = root / FIXTURE_MARKERS[design][0]
    try:
        proc = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                              text=True, timeout=30, cwd=fixture_dir)
        if proc.returncode == 0:
            head = proc.stdout.strip()
    except Exception:
        pass
    return rev, head


def _tool_versions():
    versions = {}
    for binary in ("iverilog", "vvp", "klayout", "ngspice"):
        found = shutil.which(binary)
        versions[binary] = found or "absent"
        if found:
            flag = "--version" if binary in ("ngspice",) else "-V"
            if binary == "klayout":
                flag = "-v"
            try:
                proc = subprocess.run([binary, flag], capture_output=True,
                                      text=True, timeout=30)
                first = (proc.stdout + proc.stderr).splitlines()
                if first:
                    versions[binary] = first[0][:120]
            except Exception:
                pass
    versions["sax"] = "absent"
    if importlib.util.find_spec("sax") is not None:
        try:
            import sax

            versions["sax"] = getattr(sax, "__version__", "present")
        except Exception:
            versions["sax"] = "present"
    return versions


def _engine_run(project, operation, arguments):
    from rocket_engine.composition import Engine

    engine = Engine(project, actor="correctness-gate")
    out = engine.run({"project_id": project, "operation": operation,
                      "arguments": arguments})
    return engine, out


def _hdl_job(staged):
    return {"operation": "run_hdl_test", "sources": staged["sources"],
            "workdir": staged["workdir"], "request": {"timeout_s": staged["timeout_s"]},
            "defines": staged["defines"], "deck": {"tool": "icarus"}}


def _spice_job(staged, pdk):
    return {"operation": "run_spice", "sources": staged["sources"],
            "workdir": staged["workdir"], "request": {"timeout_s": staged["timeout_s"]},
            "measurements": staged["measurements"],
            "analyses": staged["analyses"], "options": staged["options"],
            "params": staged["params"], "corner": staged["corner"],
            "temp_c": staged["temp_c"], "pdk": pdk,
            "deck": {"tool": "ngspice"}}


def _optical_job(staged):
    return {"operation": "run_optical", "sources": staged["sources"],
            "workdir": staged["workdir"], "request": {"timeout_s": staged["timeout_s"]},
            "deck": {"tool": "sax"}}


def _drc_job(staged):
    layout = staged["layout"]
    return {"operation": "run_drc", "tech": layout["tech"],
            "cell": layout["cell"], "gds_file": layout["gds_file"],
            "rules": layout["rules"], "workdir": staged["workdir"],
            "deck": {"tool": "klayout"}}


def _native_text(job, operation):
    """Re-run the adapter once for failure artifacts (native logs)."""
    try:
        if operation == "run_hdl_test":
            from rocket_engine.adapters.hdl_sim import HdlSimAdapter

            native = HdlSimAdapter().execute(job)
            compile_block = native.get("compile") or {}
            run_block = native.get("run") or {}
            return ("=== compile stdout ===\n" + compile_block.get("stdout", "")
                    + "\n=== compile stderr ===\n"
                    + compile_block.get("stderr", "")
                    + "\n=== run stdout ===\n" + run_block.get("stdout", "")
                    + "\n=== run stderr ===\n" + run_block.get("stderr", ""))
        if operation == "run_spice":
            from rocket_engine.adapters.ngspice import NgspiceAdapter

            native = NgspiceAdapter().execute(job)
            return ("=== deck ===\n" + (native.get("deck") or "")
                    + "\n=== stdout ===\n" + (native.get("stdout") or "")
                    + "\n=== stderr ===\n" + (native.get("stderr") or "")
                    + "\n=== log ===\n" + (native.get("log") or ""))
        if operation == "run_optical":
            from rocket_engine.adapters.sax import SaxAdapter

            native = SaxAdapter().execute(job)
            return ("=== stdout ===\n" + (native.get("stdout") or "")
                    + "\n=== stderr ===\n" + (native.get("stderr") or ""))
        if operation == "run_drc":
            from rocket_engine.adapters.drc.klayout import KlayoutDrcAdapter

            native = KlayoutDrcAdapter().execute(job)
            return ("=== stdout ===\n" + (native.get("stdout") or "")
                    + "\n=== stderr ===\n" + (native.get("stderr") or ""))
    except Exception as exc:
        return f"<native re-run failed: {exc}>\n{traceback.format_exc()}"
    return "<unknown operation>"


def _write_artifacts(case_dir, *, verdict, findings, job, operation,
                     staged, design, root, mutation):
    case_dir = Path(case_dir)
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "verdict.json").write_text(
        json.dumps({"verdict": verdict, "findings": findings},
                   indent=2, sort_keys=True) + "\n")
    (case_dir / "native.log").write_text(_native_text(job, operation))
    pinned, head = _fixture_pin(design, root)
    sources = []
    for path in staged.get("sources", []):
        try:
            digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        except Exception:
            digest = "unreadable"
        sources.append({"name": Path(path).name, "sha256": digest})
    layout = staged.get("layout")
    if isinstance(layout, dict) and layout.get("gds_file"):
        try:
            digest = hashlib.sha256(
                Path(layout["gds_file"]).read_bytes()).hexdigest()
        except Exception:
            digest = "unreadable"
        sources.append({"name": Path(layout["gds_file"]).name,
                        "sha256": digest})
    record = {"case": case_dir.name, "design": design,
              "engine": {"operation": operation,
                         "project_id": "correctness-gate"},
              "ingredients": {
                  "fixture": {"pinned_rev": pinned, "actual_head": head},
                  "sources": sorted(sources, key=lambda s: s["name"]),
                  "timeout_s": staged.get("timeout_s"),
                  "solver": {"tool": operation, **_tool_versions()},
                  "mutation": mutation,
              },
              "results": {"verdict": verdict, "findings": findings}}
    (case_dir / "run_record.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n")
    return case_dir


def _check_good(status, findings):
    errors = [f for f in findings if f.get("severity") == "error"]
    return status == "PASS" and not errors


def _check_mutant(status, findings, expected_rules):
    errors = [f for f in findings if f.get("severity") == "error"]
    return (status == "FAIL" and bool(errors)
            and {f["rule"] for f in errors} == set(expected_rules))


def _run_one(root, design, side, staged, job, operation, project):
    engine, out = _engine_run(project, operation, job)
    findings = engine.findings(out["run_id"])["findings"]
    return out.get("verdict", {}), findings


def _enumerate_cases(root, flow, design_filter, only_good):
    from rocket_engine.mutate import OPERATORS

    flows = [flow] if flow != "all" else list(FLOWS)
    cases = []
    for flow_name in flows:
        for design in FLOWS[flow_name]["designs"]:
            if design_filter and design != design_filter:
                continue
            if design == "mzi":
                cases.append({"flow": flow_name, "design": design,
                              "side": "layout", "kind": "good",
                              "case": "mzi-layout-good"})
                cases.append({"flow": flow_name, "design": design,
                              "side": "optical", "kind": "good",
                              "case": "mzi-optical-good"})
                if only_good:
                    continue
                for op, entry in sorted(OPERATORS.items()):
                    if entry.get("design") != "mzi":
                        continue
                    for seed in range(entry["variants"]):
                        cases.append({"flow": flow_name, "design": design,
                                      "side": "optical", "kind": "mutant",
                                      "operator": op, "seed": seed,
                                      "case": f"{op}-{seed}-optical"})
                        cases.append({"flow": flow_name, "design": design,
                                      "side": "layout", "kind": "layout-stays",
                                      "operator": op, "seed": seed,
                                      "case": f"{op}-{seed}-layout"})
                continue
            cases.append({"flow": flow_name, "design": design, "side": None,
                          "kind": "good", "case": f"{design}-good"})
            if only_good:
                continue
            for op, entry in sorted(OPERATORS.items()):
                if entry.get("design") != design:
                    continue
                for seed in range(entry["variants"]):
                    cases.append({"flow": flow_name, "design": design,
                                  "side": None, "kind": "mutant",
                                  "operator": op, "seed": seed,
                                  "case": f"{op}-{seed}"})
    return cases


def run_gate(root, report_dir, flow="all", design=None, only_good=False):
    """Run the gate; write report.json + report.md; return the report."""
    from rocket_engine.mutate import (OPERATORS, apply_operator,
                                      stage_design_extras, stage_good_design)

    root = Path(root)
    report_dir = Path(report_dir)
    cases_dir = report_dir / "cases"
    report_dir.mkdir(parents=True, exist_ok=True)
    cases_dir.mkdir(parents=True, exist_ok=True)

    if flow != "all" and flow not in FLOWS:
        raise KeyError(f"unknown flow: {flow!r}")
    if design is not None and design not in DESIGN_FLOW:
        raise KeyError(f"unknown design: {design!r}")

    cases = _enumerate_cases(root, flow, design, only_good)
    results = []
    for spec in cases:
        case = spec["case"]
        case_design = spec["design"]
        side = spec.get("side")
        kind = spec["kind"]
        flow_name = spec["flow"]
        gated = _check_fixture(case_design, root)
        if gated is None:
            gated = _case_tool_gate(case_design, side)
        if gated is not None:
            reason, ref = gated
            results.append({"case": case, "flow": flow_name,
                            "design": case_design, "kind": kind,
                            "status": "quarantined", "reason": reason,
                            "ref": ref})
            continue
        workdir = Path(tempfile.mkdtemp(prefix="gate_"))
        try:
            try:
                if kind == "good":
                    staged = stage_good_design(case_design, workdir, root)
                    mutation = None
                else:
                    entry = OPERATORS[spec["operator"]]
                    evidence = apply_operator(
                        spec["operator"], workdir, spec["seed"],
                        root / entry["base"])
                    staged = stage_design_extras(case_design, workdir, root)
                    mutation = evidence
            except FileNotFoundError as exc:
                results.append({"case": case, "flow": flow_name,
                                "design": case_design, "kind": kind,
                                "status": "quarantined",
                                "reason": f"fixture piece missing: {exc}",
                                "ref": VALIDATE_REF[flow_name]})
                continue
            except Exception as exc:
                results.append({"case": case, "flow": flow_name,
                                "design": case_design, "kind": kind,
                                "status": "fail",
                                "expected": "stageable",
                                "got": f"staging raised: {exc!r}",
                                "artifacts": None})
                continue
            try:
                if case_design in ("serv", "picorv32", "sdm_rx"):
                    job = _hdl_job(staged)
                    operation = "run_hdl_test"
                elif case_design in ("bandgap", "sd_top"):
                    job = _spice_job(staged, _pdk_entry())
                    operation = "run_spice"
                elif case_design == "mzi" and side == "optical":
                    job = _optical_job(staged)
                    operation = "run_optical"
                else:
                    job = _drc_job(staged)
                    operation = "run_drc"
                verdict, findings = _run_one(
                    root, case_design, side, staged, job, operation,
                    f"gate_{case_design}")
            except Exception as exc:
                results.append({"case": case, "flow": flow_name,
                                "design": case_design, "kind": kind,
                                "status": "fail",
                                "expected": "engine verdict",
                                "got": f"engine raised: {exc!r}",
                                "artifacts": None})
                continue
            status = verdict.get("status")
            if kind == "good" or kind == "layout-stays":
                ok = _check_good(status, findings)
                expected = "PASS"
            else:
                entry = OPERATORS[spec["operator"]]
                ok = _check_mutant(status, findings,
                                   entry["expected_rules"])
                expected = (f"FAIL({','.join(entry['expected_rules'])})")
            if ok:
                results.append({"case": case, "flow": flow_name,
                                "design": case_design, "kind": kind,
                                "status": "pass"})
                continue
            artifacts = _write_artifacts(
                cases_dir / case, verdict=verdict, findings=findings,
                job=job, operation=operation, staged=staged,
                design=case_design, root=root, mutation=mutation)
            results.append({"case": case, "flow": flow_name,
                            "design": case_design, "kind": kind,
                            "status": "fail", "expected": expected,
                            "got": status, "artifacts": str(artifacts)})
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    flows_run = sorted({r["flow"] for r in results})
    flow_verdicts = {}
    for flow_name in flows_run:
        sub = [r for r in results if r["flow"] == flow_name]
        if any(r["status"] == "fail" for r in sub):
            flow_verdicts[flow_name] = "FAIL"
        elif any(r["status"] == "quarantined" for r in sub):
            flow_verdicts[flow_name] = "FAIL:blocked-env"
        elif sub:
            flow_verdicts[flow_name] = "PASS"
        else:
            flow_verdicts[flow_name] = "FAIL:blocked-env"
    verdict = _gate_verdict(flow_verdicts)
    failed_cases = [r for r in results if r["status"] == "fail"]
    quarantines = [r for r in results if r["status"] == "quarantined"]
    report = {
        "verdict": verdict,
        "flows": {name: {"verdict": flow_verdicts[name],
                         "cases": [r for r in results
                                   if r["flow"] == name]}
                  for name in flows_run},
        "totals": {"flows": len(flows_run),
                   "flows_pass": sum(1 for v in flow_verdicts.values()
                                     if v == "PASS"),
                   "cases": len(results),
                   "cases_pass": sum(1 for r in results
                                     if r["status"] == "pass"),
                   "cases_fail": len(failed_cases),
                   "cases_quarantined": len(quarantines)},
        "failed_cases": failed_cases,
        "quarantines": quarantines,
        "artifacts_dir": str(cases_dir),
    }
    (report_dir / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n")
    lines = [f"# Correctness gate: {verdict}", "",
             f"Flows: {report['totals']['flows_pass']}/"
             f"{report['totals']['flows']} green; cases: "
             f"{report['totals']['cases_pass']} pass, "
             f"{report['totals']['cases_fail']} fail, "
             f"{report['totals']['cases_quarantined']} quarantined.", ""]
    for name in flows_run:
        lines.append(f"## {name}: {flow_verdicts[name]}")
        for entry in report["flows"][name]["cases"]:
            if entry["status"] == "pass":
                lines.append(f"- PASS {entry['case']}")
            elif entry["status"] == "fail":
                lines.append(f"- FAIL {entry['case']}: want "
                             f"{entry.get('expected')}, got "
                             f"{entry.get('got')} "
                             f"(artifacts: {entry.get('artifacts')})")
            else:
                lines.append(f"- QUARANTINED {entry['case']}: "
                             f"{entry['reason']} ({entry['ref']})")
        lines.append("")
    (report_dir / "report.md").write_text("\n".join(lines))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="ENGINE-CORRECTNESS gate: all flows, one report.")
    parser.add_argument("--flow", default="all",
                        choices=["all", *FLOWS])
    parser.add_argument("--design", default=None)
    parser.add_argument("--only-good", action="store_true")
    parser.add_argument("--report", default=None)
    parser.add_argument("--root", default=None)
    args = parser.parse_args(argv)
    root = Path(args.root) if args.root else ROOT
    report_dir = Path(args.report) if args.report else root / "tmp" / "correctness"
    report = run_gate(root, report_dir, flow=args.flow,
                      design=args.design, only_good=args.only_good)
    print(f"GATE {report['verdict']}: "
          f"{report['totals']['flows_pass']}/{report['totals']['flows']} "
          f"flows green "
          f"({report['totals']['cases_pass']} pass, "
          f"{report['totals']['cases_fail']} fail, "
          f"{report['totals']['cases_quarantined']} quarantined)")
    for name, spec in report["flows"].items():
        print(f"  {name}: {spec['verdict']}")
    print(f"report: {report_dir / 'report.json'}")
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
