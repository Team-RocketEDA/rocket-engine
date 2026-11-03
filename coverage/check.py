"""Coverage map check command: rerun the op x PDK x tool matrix.

The committed coverage/map.json matrix pins per-cell verdicts from
committed fixtures (correct plus mutated per lane). This command
re-runs every cell through the real adapter parse and rejects a
stale map whose fingerprint no longer matches the tree.

Usage: python coverage/check.py [--map PATH] [--write] [--rerun].
"""

import argparse
import copy
import hashlib
import importlib
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_MAP = Path(__file__).resolve().parent / "map.json"

FINGERPRINTED = [
    "src/workflows/stages.py",
    "src/workflows/capability_plan.py",
    "contracts/v1/catalog/tasks.json",
    "contracts/v1/catalog/tools.json",
]

ADAPTERS = {
    "run_syntax": [("slang", "rocket_engine.adapters.syntax", "SyntaxAdapter")],
    "run_formal": [("sby", "rocket_engine.adapters.formal_sby", "FormalSbyAdapter")],
    "run_drc": [
        ("magic", "rocket_engine.adapters.drc.magic", "MagicDrcAdapter"),
        ("klayout", "rocket_engine.adapters.drc.klayout", "KlayoutDrcAdapter"),
    ],
    "run_lvs": [("netgen", "rocket_engine.adapters.lvs_netgen", "NetgenLvsAdapter")],
    "run_connectivity": [
        (
            "connectgraph",
            "rocket_engine.adapters.connectivity",
            "ConnectivityAdapter",
        )
    ],
    "run_erc": [
        (
            "connectgraph",
            "rocket_engine.adapters.connectivity",
            "ConnectivityAdapter",
        )
    ],
}


def load_map(path=None):
    """Read the committed coverage map document.

    Args:
        path: Map JSON path; the committed map.json when omitted.

    Returns:
        Map document with version, cells, fingerprinted, fingerprint.
    """
    return json.loads(Path(path or DEFAULT_MAP).read_text(encoding="utf-8"))


def compute_fingerprint(cells, fingerprinted=None):
    """Hash the map inputs: workflow tables, catalog, plus cells.

    Args:
        cells: Map cell list in committed form.
        fingerprinted: Repo-relative input files; the FINGERPRINTED
            list when omitted.

    Returns:
        Hex sha256 over the input bytes plus canonical cells JSON.
    """
    digest = hashlib.sha256()
    for rel in fingerprinted or FINGERPRINTED:
        digest.update((REPO / rel).read_bytes())
        digest.update(b"\0")
    digest.update(json.dumps(cells, sort_keys=True).encode("utf-8"))
    return digest.hexdigest()


def verdict(op, parsed):
    """Pass/fail verdict for one parsed adapter result.

    Args:
        op: Engine operation the adapter serves.
        parsed: Adapter parse() result mapping.

    Returns:
        "pass" or "fail".
    """
    if op == "run_lvs":
        return "pass" if parsed.get("match") is True else "fail"
    if op == "run_formal":
        scope = (parsed.get("measurements") or {}).get("scope")
        if parsed.get("total") == 0 and scope in ("proven", "bounded"):
            return "pass"
        return "fail"
    return "pass" if parsed.get("total") == 0 else "fail"


def _resolve_native(native, scratch):
    """Resolve a canned native for a rerun (sources, workdir).

    Args:
        native: Canned native output from the map cell.
        scratch: Scratch dir standing in for the original workdir.

    Returns:
        Native output copy with repo-relative sources made absolute
            and the workdir pointed at the scratch dir.
    """
    resolved = copy.deepcopy(native)
    if "sources" in resolved:
        resolved["sources"] = [
            str(REPO / rel) for rel in resolved["sources"]
        ]
    resolved["workdir"] = str(scratch)
    return resolved


def rerun_cell(cell, scratch):
    """Rerun one map cell through the real adapter parse.

    Args:
        cell: Map cell with op, tool, canned natives, and expected
            verdicts/totals.
        scratch: Scratch dir for workdir-scoped parses (sby).

    Returns:
        Report with the cell id, parsed good/bad results, and any
            problems (empty when the cell pins both directions).
    """
    scratch = Path(scratch)
    scratch.mkdir(parents=True, exist_ok=True)
    entries = [e for e in ADAPTERS.get(cell["op"], []) if e[0] == cell["tool"]]
    if not entries:
        return {"cell": cell["cell"], "problems": [f"no adapter for {cell['op']}"]}
    _, module_name, cls_name = entries[0]
    parse = getattr(importlib.import_module(module_name), cls_name)().parse
    problems = []
    parsed = {}
    for side in ("good", "bad"):
        try:
            result = parse(_resolve_native(cell["native"][side], scratch / side))
        except Exception as exc:  # noqa: BLE001 — rerun reports, never raises
            problems.append(f"{side}: parse raised {type(exc).__name__}: {exc}")
            continue
        parsed[side] = result
        want = cell["expect"][side]
        got_verdict = verdict(cell["op"], result)
        if got_verdict != want["verdict"]:
            problems.append(
                f"{side}: verdict {got_verdict} != expected {want['verdict']}"
            )
        if result.get("total") != want["total"] and cell["op"] != "run_lvs":
            problems.append(
                f"{side}: total {result.get('total')} != expected {want['total']}"
            )
        if cell["op"] == "run_lvs" and result.get("match") != (
            want["verdict"] == "pass"
        ):
            problems.append(f"{side}: match flag disagrees with {want['verdict']}")
    return {"cell": cell["cell"], "parsed": parsed, "problems": problems}


def check(map_path=None):
    """Verify map freshness plus every cell in both directions.

    Args:
        map_path: Map JSON path; the committed map.json when omitted.

    Returns:
        Problem list; empty means the map is fresh and green.
    """
    path = Path(map_path or DEFAULT_MAP)
    doc = json.loads(path.read_text(encoding="utf-8"))
    problems = []
    if doc.get("fingerprint") != compute_fingerprint(doc["cells"]):
        problems.append(
            f"stale map {path}: inputs changed — rerun with --write."
        )
    for cell in doc["cells"]:
        for rel in cell["fixtures"]["good"] + cell["fixtures"]["bad"]:
            if not (REPO / rel).is_file():
                problems.append(f"{cell['cell']}: fixture missing: {rel}")
        with tempfile.TemporaryDirectory(prefix="coverage-") as tmp:
            report = rerun_cell(cell, Path(tmp) / cell["cell"])
        problems.extend(f"{cell['cell']}: {p}" for p in report["problems"])
    return problems


def write_map(map_path=None):
    """Restamp the map fingerprint after intentional input changes.

    Args:
        map_path: Map JSON path; the committed map.json when omitted.

    Returns:
        The stamped fingerprint.
    """
    path = Path(map_path or DEFAULT_MAP)
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["fingerprinted"] = list(FINGERPRINTED)
    doc["fingerprint"] = compute_fingerprint(doc["cells"])
    path.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    return doc["fingerprint"]


def main(argv=None):
    """Run the coverage map check command.

    Args:
        argv: CLI args (map path, --write, --rerun); sys.argv when None.

    Returns:
        Process exit code (0 when the map is fresh and green).
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--map", default=str(DEFAULT_MAP))
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--rerun", action="store_true")
    args = parser.parse_args(argv)
    if args.write:
        print(f"fingerprint: {write_map(args.map)}")
        return 0
    problems = check(args.map)
    if args.rerun or problems:
        doc = load_map(args.map)
        with tempfile.TemporaryDirectory(prefix="coverage-") as tmp:
            for cell in doc["cells"]:
                report = rerun_cell(cell, Path(tmp) / cell["cell"])
                parsed = report.get("parsed", {})
                print(
                    f"{cell['cell']}: "
                    f"good={verdict(cell['op'], parsed.get('good', {}))} "
                    f"bad={verdict(cell['op'], parsed.get('bad', {}))}"
                    if parsed
                    else f"{cell['cell']}: no parse"
                )
    for problem in problems:
        print(f"FAIL: {problem}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
