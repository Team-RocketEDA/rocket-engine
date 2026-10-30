"""Contract drift check: stub shapes vs engine schemas (FUEL-CONTRACT).

Fuel's mcp-stub pins to the engine's generated contract artifact
(docs/contract.json); this script verifies the pin from either repo.
It extracts stub tool shapes by AST (signatures plus top-level
returned-dict keys — no imports, no stub dependencies), resolves the
artifact's overlap-map engine refs, and fails loudly naming the
skewed field, the missing tool, or the stale pin.

Stdlib-only and single-file: run it from an engine checkout, or from
a fuel checkout against a sibling/path-given engine checkout (never
fork it into fuel — reference the engine copy so the checker itself
cannot drift). Exit 0 green (an unpinned stub warns but stays
green), 1 on drift or a stale pin, 2 on discovery/usage errors.

Usage:
    python scripts/check_contract.py [--engine-root PATH] [--stub-root PATH]
        [--contract PATH] [--pin PATH]
"""

import argparse
import ast
import json
import sys
from pathlib import Path


def _is_tool_decorator(node):
    """True when a decorator is @mcp.tool or @mcp.tool()."""
    if isinstance(node, ast.Call):
        node = node.func
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "tool"
        and isinstance(node.value, ast.Name)
        and node.value.id == "mcp"
    )


def _return_keys(value):
    """(literal keys, dynamic) from one returned expression.

    Dict literals contribute their constant string keys; anything
    opaque (calls, names, starred items, non-constant keys)
    contributes dynamic instead of pretending. IfExp branches (the
    stub's `a if ok else b` replies) and list/tuple-of-dict replies
    recurse.
    """
    if isinstance(value, ast.Dict):
        keys, dynamic = set(), False
        for key in value.keys:
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                keys.add(key.value)
            else:
                dynamic = True
        return keys, dynamic
    if isinstance(value, ast.IfExp):
        body_keys, body_dynamic = _return_keys(value.body)
        else_keys, else_dynamic = _return_keys(value.orelse)
        return body_keys | else_keys, body_dynamic or else_dynamic
    if isinstance(value, (ast.List, ast.Tuple)) and value.elts:
        keys, dynamic = set(), False
        for elt in value.elts:
            if isinstance(elt, ast.Dict):
                sub_keys, sub_dynamic = _return_keys(elt)
                keys |= sub_keys
                dynamic = dynamic or sub_dynamic
            else:
                dynamic = True
        return keys, dynamic
    return set(), True


def extract_stub_shapes(server_path):
    """Tool shapes from a stub server.py, by AST (never imported).

    Args:
        server_path: Path to rocket_stub/server.py (or a fixture
            with the same @mcp.tool surface).

    Returns:
        {tool: {args: {name: {required, annotation}},
        response_keys: sorted literal reply keys, response_dynamic:
        True when some reply builds its dict opaquely}}.
    """
    tree = ast.parse(Path(server_path).read_text(encoding="utf-8"))
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    shapes = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not any(_is_tool_decorator(d) for d in node.decorator_list):
            continue
        positional = list(node.args.posonlyargs) + list(node.args.args)
        if (
            positional
            and isinstance(parents.get(node), ast.ClassDef)
            and positional[0].arg in ("self", "cls")
        ):
            positional = positional[1:]
        required_positional = (
            len(positional) - len(node.args.defaults)
        )
        args = {}
        for index, arg in enumerate(positional):
            annotation = (
                ast.unparse(arg.annotation) if arg.annotation else ""
            )
            args[arg.arg] = {
                "required": index < required_positional,
                "annotation": annotation,
            }
        for arg, default in zip(node.args.kwonlyargs, node.args.kw_defaults):
            annotation = (
                ast.unparse(arg.annotation) if arg.annotation else ""
            )
            args[arg.arg] = {
                "required": default is None,
                "annotation": annotation,
            }
        keys, dynamic = set(), False
        seen_return = False
        for child in ast.walk(node):
            if isinstance(child, ast.Return) and child.value is not None:
                seen_return = True
                sub_keys, sub_dynamic = _return_keys(child.value)
                keys |= sub_keys
                dynamic = dynamic or sub_dynamic
        shapes[node.name] = {
            "args": args,
            "response_keys": sorted(keys),
            "response_dynamic": dynamic or not seen_return,
        }
    return shapes


def engine_ref_present(contract, ref):
    """True when a dotted engine ref resolves inside the contract.

    Path segments descend mappings; a trailing segment against a
    list means membership (envelope key lists). Single source for
    both scripts — scripts/contract.py re-exports this.

    Args:
        contract: Parsed docs/contract.json mapping.
        ref: Dotted ref such as
            envelopes.run_completion.keys.run_id.

    Returns:
        True when the ref's target exists.
    """
    node = contract
    parts = ref.split(".")
    for index, part in enumerate(parts):
        if isinstance(node, dict):
            if part not in node:
                return False
            node = node[part]
        elif isinstance(node, list):
            return index == len(parts) - 1 and part in node
        else:
            return False
    return True


def drift_errors(contract, stub_shapes):
    """Overlap-map violations between contract and stub shapes.

    Every mapping pins one (tool, side, field) against one engine
    ref: a deleted tool, a renamed stub field, or a removed engine
    field each fail naming what went missing. Unmapped stub tools
    are out of scope (fuel-owned or known gaps — see the artifact).

    Args:
        contract: Parsed docs/contract.json mapping.
        stub_shapes: extract_stub_shapes() output for the stub.

    Returns:
        Error strings, empty when every mapping holds.
    """
    errors = []
    for entry in contract["stub_overlap"]["mappings"]:
        tool = entry["stub_tool"]
        field = entry["stub_field"]
        ref = entry["engine_ref"]
        if tool not in stub_shapes:
            errors.append(
                f"contract drift: stub tool '{tool}' is gone "
                f"(contract maps '{ref}' to "
                f"stub.{tool}.{entry['stub_side']}.{field})"
            )
            continue
        if entry["stub_side"] == "request":
            present = field in stub_shapes[tool]["args"]
            where = "argument"
        else:
            present = field in stub_shapes[tool]["response_keys"]
            where = "response key"
        if not present:
            errors.append(
                f"contract drift: stub '{tool}' lost {where} "
                f"'{field}' (contract '{ref}' expects it)"
            )
        if not engine_ref_present(contract, ref):
            errors.append(
                f"contract drift: engine '{ref}' is gone "
                f"(stub '{tool}' still maps {where} '{field}' to it)"
            )
    return errors


def pin_errors(contract, pin):
    """Pin staleness between the stub pin and the contract.

    A missing pin is not an error (pin_warning() covers it loudly);
    a present pin must match both the contract version and the
    schema hash, else the stub is stale and fails here — loudly,
    never silently.

    Args:
        contract: Parsed docs/contract.json mapping.
        pin: Parsed contract.pin mapping, or None when unpinned.

    Returns:
        Error strings, empty when the pin matches or is absent.
    """
    if pin is None:
        return []
    errors = []
    if pin.get("contract_version") != contract["contract_version"]:
        errors.append(
            "stale pin: contract.pin pins "
            f"{pin.get('contract_version')}, engine contract is "
            f"{contract['contract_version']} — re-pin per "
            "docs/fuel-contract.md"
        )
    if pin.get("schema_sha256") != contract["schema_sha256"]:
        errors.append(
            "stale pin: contract.pin pins schema "
            f"{pin.get('schema_sha256')}, engine contract is "
            f"{contract['schema_sha256']} — engine schemas changed; "
            "re-pin per docs/fuel-contract.md"
        )
    return errors


def pin_warning():
    """Loud unpinned-stub notice (green, but not silent)."""
    return (
        "WARNING: stub is not pinned (no contract.pin beside "
        "mcp-stub) — drift shapes checked, version not pinned. "
        "Pin per docs/fuel-contract.md recipe."
    )


def find_engine_root(hint=None):
    """Engine checkout root: hint, cwd walk-up, then script walk-up.

    Args:
        hint: Explicit root (or a file beneath it).

    Returns:
        Root Path holding docs/contract.json, or None.
    """
    candidates = []
    if hint is not None:
        hint = Path(hint)
        candidates.append(hint if hint.is_dir() else hint.parent)
    else:
        candidates.append(Path.cwd())
    script_root = Path(__file__).resolve().parent.parent
    if script_root not in candidates:
        candidates.append(script_root)
    for start in candidates:
        for probe in (start, *start.parents):
            if (probe / "docs" / "contract.json").is_file():
                return probe
    return None


def _as_stub_root(path):
    """Stub root for a path, or None when it names no stub."""
    path = Path(path)
    if path.is_file() and path.name == "server.py":
        path = path.parents[2]
    if (path / "src" / "rocket_stub" / "server.py").is_file():
        return path
    nested = path / "mcp-stub"
    if (nested / "src" / "rocket_stub" / "server.py").is_file():
        return nested
    return None


def find_stub_root(hint=None, engine_root=None):
    """mcp-stub root: hint, cwd walk-up, then engine siblings.

    Args:
        hint: Explicit stub root, fuel checkout root, or the
            stub server.py itself.
        engine_root: Engine checkout root for sibling lookup.

    Returns:
        Stub root Path, or None.
    """
    if hint is not None:
        return _as_stub_root(hint)
    for probe in (Path.cwd(), *Path.cwd().parents):
        found = _as_stub_root(probe)
        if found is not None:
            return found
    if engine_root is not None:
        engine_root = Path(engine_root)
        for sibling in (
            engine_root.parent / "rocket_fuel" / "mcp-stub",
            engine_root.parent / "mcp-stub",
            engine_root / "rocket_fuel" / "mcp-stub",
        ):
            if _as_stub_root(sibling) is not None:
                return sibling
    return None


def main(argv):
    """Run the drift check over an engine/stub pair."""
    parser = argparse.ArgumentParser(description="Contract drift check.")
    parser.add_argument("--engine-root", default=None)
    parser.add_argument("--stub-root", default=None)
    parser.add_argument("--contract", default=None)
    parser.add_argument("--pin", default=None)
    args = parser.parse_args(argv)
    engine_root = find_engine_root(args.engine_root)
    if engine_root is None:
        print(
            "engine root not found (no docs/contract.json up-tree): "
            "pass --engine-root"
        )
        return 2
    contract_path = (
        Path(args.contract)
        if args.contract
        else engine_root / "docs" / "contract.json"
    )
    if not contract_path.is_file():
        print(
            f"no contract at {contract_path}: run "
            "scripts/contract.py --write in the engine checkout first"
        )
        return 2
    stub_root = find_stub_root(args.stub_root, engine_root)
    if stub_root is None:
        print(
            "stub root not found (no mcp-stub up-tree or beside the "
            "engine): pass --stub-root"
        )
        return 2
    server_path = stub_root / "src" / "rocket_stub" / "server.py"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    shapes = extract_stub_shapes(server_path)
    pin_path = Path(args.pin) if args.pin else stub_root / "contract.pin"
    pin = (
        json.loads(pin_path.read_text(encoding="utf-8"))
        if pin_path.is_file()
        else None
    )
    errors = drift_errors(contract, shapes) + pin_errors(contract, pin)
    for error in errors:
        print(error)
    if errors:
        return 1
    digest = contract["schema_sha256"][:12]
    print(
        f"contract OK: {len(contract['stub_overlap']['mappings'])} "
        f"mappings green against {contract['contract_version']} "
        f"(schema {digest}…)"
    )
    if pin is None:
        print(pin_warning())
    else:
        try:
            shown = pin_path.relative_to(Path.cwd())
        except ValueError:
            shown = pin_path
        print(f"pin OK: {shown} matches engine contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
