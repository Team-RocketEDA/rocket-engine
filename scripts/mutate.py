#!/usr/bin/env python3
"""MUTATE-HARNESS runner: list/apply/recheck mutation operators.

Every operator stages scratch COPIES under tmp/scratch (never the
fixture trees), mutates the copy from its seed, and — under `recheck`
— runs the engine end-to-end on the good and mutated copies.

Usage:
    python scripts/mutate.py list
    python scripts/mutate.py apply --operator digital_reset_break --seed 0
    python scripts/mutate.py recheck --operator layout_drc_violation --seed 1

`recheck` exits 0 when the flip is proven (good PASS, mutated
expected-FAIL), 1 on a verdict mismatch, and 2 when the needed tool
is absent (QUARANTINED with a ticket ref, never fake-green).
"""

import argparse
import importlib.util
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from rocket_engine.composition import Engine  # noqa: E402
from rocket_engine.mutate import (  # noqa: E402
    OPERATORS,
    apply_operator,
    copy_base_files,
    stage_design_extras,
)

QUARANTINE_REF = {
    "ngspice": "docs/tickets/NGSPICE-LIVE.md",
    "netgen": "docs/tickets/NGSPICE-LIVE.md",
    "icarus": "B10-owned tooling",
    "magic": "B10-owned tooling",
    "sax": "B10-owned tooling (uv sync --group photonic)",
}

_MEASUREMENTS = [
    {"name": "vout", "expr": "v(out)", "unit": "V", "min": 1.199, "max": 1.201}
]


def _need(binary, operator):
    if shutil.which(binary) is None:
        ref = QUARANTINE_REF.get(binary, "B10-owned tooling")
        return f"QUARANTINED {operator}: {binary} not on PATH ({ref})"
    return None


def _tool_gate(operator):
    entry = OPERATORS[operator]
    op = entry["operation"]
    if op == "run_hdl_test":
        for binary in ("iverilog", "vvp"):
            miss = _need(binary, operator)
            if miss:
                return miss.replace(binary, "iverilog/vvp")
    elif op == "run_spice":
        miss = _need("ngspice", operator)
        if miss:
            return miss
        if entry.get("design") == "bandgap":
            try:
                from rocket_engine.interfaces.pdks import list_pdks, resolve_deck

                entries = [e for e in list_pdks() if e.get("id") == "sky130a"]
                if not entries:
                    raise LookupError("no sky130a entry")
                first = sorted(entries, key=lambda e: e["revision"])[0]
                resolve_deck(
                    first["id"],
                    first["revision"],
                    "libs.tech/combined/sky130.lib.spice",
                )
            except Exception as exc:
                return (
                    f"QUARANTINED {operator}: sky130 model lib not resolvable "
                    f"({exc}; set ROCKETEDA_HOME; docs/tickets/NGSPICE-LIVE.md)"
                )
        return None
    elif op == "run_drc":
        return _need("magic", operator)
    elif op == "run_lvs":
        miss = _need("netgen", operator)
        if miss:
            return miss
        try:
            from rocket_engine.interfaces.pdks import list_pdks, resolve_deck

            entries = [
                e for e in list_pdks() if e.get("id") == "sky130a"
            ]
            if not entries:
                raise LookupError("no sky130a entry")
            first = sorted(entries, key=lambda e: e["revision"])[0]
            resolve_deck(
                first["id"],
                first["revision"],
                "libs.tech/netgen/sky130A_setup.tcl",
            )
        except Exception as exc:
            return (
                f"QUARANTINED {operator}: sky130 LVS setup not resolvable "
                f"({exc}; set ROCKETEDA_HOME; docs/tickets/NGSPICE-LIVE.md)"
            )
    elif op == "run_optical":
        if importlib.util.find_spec("sax") is None:
            return (
                f"QUARANTINED {operator}: sax not installed "
                f"({QUARANTINE_REF['sax']})"
            )
    return None


def _job(operator, dest, extra=None):
    entry = OPERATORS[operator]
    op = entry["operation"]
    workdir = str(dest)
    if op == "run_hdl_test":
        design = entry.get("design")
        if design is not None:
            staged = stage_design_extras(design, dest, ROOT)
            return {
                "sources": staged["sources"],
                "workdir": staged["workdir"],
                "timeout_s": staged["timeout_s"],
                "defines": staged["defines"],
                "deck": {"tool": "icarus"},
            }
        return {
            "sources": [str(dest / "counter.v"), str(dest / "tb_pass.v")],
            "workdir": workdir,
            "deck": {"tool": "icarus"},
        }
    if op == "run_spice":
        design = entry.get("design")
        if design == "bandgap":
            staged = stage_design_extras(design, dest, ROOT)
            return {
                "sources": staged["sources"],
                "workdir": staged["workdir"],
                "timeout_s": staged["timeout_s"],
                "measurements": staged["measurements"],
                "analyses": staged["analyses"],
                "options": staged["options"],
                "params": staged["params"],
                "corner": staged["corner"],
                "temp_c": staged["temp_c"],
                "pdk": (extra or {})["pdk"],
                "deck": {"tool": "ngspice"},
            }
        return {
            "sources": [str(dest / "rc_divider.spice")],
            "workdir": workdir,
            "analyses": ["op"],
            "measurements": list(_MEASUREMENTS),
            "deck": {"tool": "ngspice"},
        }
    if op == "run_drc":
        return {
            "tech": "scmos",
            "cell": "good",
            "cell_file": str(dest / "good.mag"),
            "workdir": workdir,
        }
    if op == "run_lvs":
        return {
            "layout_spice": str(dest / "layout.spice"),
            "schematic_spice": str(dest / "schematic.spice"),
            "setup_file": (extra or {})["setup_file"],
            "workdir": workdir,
            "deck": {"tool": "netgen"},
        }
    if op == "run_optical":
        return {
            "sources": [str(dest / "mzi.yml")],
            "workdir": workdir,
            "deck": {"tool": "sax"},
        }
    raise KeyError(f"no job builder for {op}")


def _engine_run(project, operation, arguments):
    engine = Engine(project, actor="mutate-recheck")
    out = engine.run(
        {"project_id": project, "operation": operation, "arguments": arguments}
    )
    return engine, out


def cmd_list(_args):
    for name in sorted(OPERATORS):
        entry = OPERATORS[name]
        rules = ",".join(entry["expected_rules"])
        print(
            f"{name}: {entry['operation']} "
            f"PASS->>{entry['expected_verdict']}({rules}) — {entry['doc']}"
        )
    return 0


def cmd_apply(args):
    dest = Path(args.dest or (ROOT / "tmp" / "scratch" / f"{args.operator}-{args.seed}"))
    evidence = apply_operator(
        args.operator, dest, args.seed, ROOT / OPERATORS[args.operator]["base"]
    )
    print(json.dumps(evidence, indent=2))
    return 0


def cmd_recheck(args):
    try:
        entry = OPERATORS[args.operator]
    except KeyError:
        print(f"unknown operator: {args.operator}", file=sys.stderr)
        return 1
    gated = _tool_gate(args.operator)
    if gated:
        print(gated, file=sys.stderr)
        print(json.dumps({"operator": args.operator, "status": "QUARANTINED",
                          "reason": gated}))
        return 2
    base = Path(args.dest or (ROOT / "tmp" / "scratch" / f"{args.operator}-{args.seed}"))
    good_dir = base / "good"
    good_dir.mkdir(parents=True, exist_ok=True)
    copy_base_files(entry, ROOT / entry["base"], good_dir)
    evidence = apply_operator(
        args.operator, base / "mut", args.seed, ROOT / entry["base"]
    )
    extra = None
    if entry["operation"] == "run_lvs":
        from rocket_engine.interfaces.pdks import list_pdks, resolve_deck

        first = sorted(
            [e for e in list_pdks() if e.get("id") == "sky130a"],
            key=lambda e: e["revision"],
        )[0]
        hit = resolve_deck(
            first["id"], first["revision"], "libs.tech/netgen/sky130A_setup.tcl"
        )
        extra = {"setup_file": hit["path"]}
    if entry.get("design") == "bandgap":
        from rocket_engine.interfaces.pdks import list_pdks

        first = sorted(
            [e for e in list_pdks() if e.get("id") == "sky130a"],
            key=lambda e: e["revision"],
        )[0]
        extra = {"pdk": {"id": first["id"], "revision": first["revision"]}}
    _, good_out = _engine_run(
        "mutate_good", entry["operation"], _job(args.operator, good_dir, extra)
    )
    engine, mut_out = _engine_run(
        "mutate_bad", entry["operation"], _job(args.operator, base / "mut", extra)
    )
    good_status = (good_out.get("verdict") or {}).get("status")
    mut_status = (mut_out.get("verdict") or {}).get("status")
    found = engine.findings(mut_out["run_id"])["findings"]
    hit_rule = any(
        evidence["expected_rule"] in f.get("rule", "") for f in found
    )
    proven = (
        good_status == "PASS"
        and mut_status == entry["expected_verdict"]
        and hit_rule
    )
    print(json.dumps({
        "operator": args.operator,
        "seed": args.seed,
        "good": good_status,
        "mutated": mut_status,
        "expected_rule": evidence["expected_rule"],
        "rule_seen": hit_rule,
        "proven": proven,
    }, indent=2))
    return 0 if proven else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description="MUTATE-HARNESS runner.")
    sub = parser.add_subparsers(dest="verb", required=True)
    sub.add_parser("list", help="print the operator→verdict map")
    apply_p = sub.add_parser("apply", help="stage copies and mutate")
    apply_p.add_argument("--operator", required=True)
    apply_p.add_argument("--seed", type=int, default=0)
    apply_p.add_argument(
        "--dest", default=None,
        help="staging dir (default tmp/scratch/<operator>-<seed>)",
    )
    recheck_p = sub.add_parser("recheck", help="apply + engine recheck e2e")
    recheck_p.add_argument("--operator", required=True)
    recheck_p.add_argument("--seed", type=int, default=0)
    recheck_p.add_argument(
        "--dest", default=None,
        help="staging dir (default tmp/scratch/<operator>-<seed>)",
    )
    args = parser.parse_args(argv)
    if args.verb == "list":
        return cmd_list(args)
    if args.verb == "apply":
        return cmd_apply(args)
    return cmd_recheck(args)


if __name__ == "__main__":
    sys.exit(main())
