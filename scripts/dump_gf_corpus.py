"""Dump the full gdsfactory/kfactory/gplugins module tree to JSON.

Usage (run where gdsfactory is installed — the sandbox has no gf module):
    python rocket-engine/scripts/dump_gf_corpus.py [output.json]

Output: {"packages": {name: version|None}, "symbols": [...], "errors": [...]}
Each symbol: {module, qualname, kind, origin, signature, doc}.
kind is coarse L1: CLASS | FUNC | PARAM (standalone module-level
parameters/constants/settings — not class parameters).
"""

import inspect
import json
import pkgutil
import sys

PACKAGES = ("gdsfactory", "kfactory", "gplugins")


def firstline(doc):
    if not doc:
        return None
    for line in doc.strip().splitlines():
        line = line.strip()
        if line:
            return line[:200]
    return None


def main(out_path):
    symbols = []
    errors = []
    versions = {}
    for pkg_name in PACKAGES:
        try:
            pkg = __import__(pkg_name)
        except Exception as exc:  # noqa: BLE001 — record, don't stop
            versions[pkg_name] = None
            errors.append({"module": pkg_name, "error": f"import: {exc!r}"})
            continue
        versions[pkg_name] = getattr(pkg, "__version__", None)
        modules = [pkg.__name__] + [
            m.name for m in pkgutil.walk_packages(pkg.__path__, pkg.__name__ + ".")
        ]
        for mod_name in modules:
            try:
                __import__(mod_name)
                mod = sys.modules[mod_name]
            except Exception as exc:  # noqa: BLE001
                errors.append({"module": mod_name, "error": f"import: {exc!r}"})
                continue
            try:
                members = inspect.getmembers(mod)
            except Exception as exc:  # noqa: BLE001
                errors.append({"module": mod_name, "error": f"members: {exc!r}"})
                continue
            for name, obj in members:
                if name.startswith("_") and name != "__version__":
                    continue
                if inspect.isclass(obj):
                    kind = "CLASS"
                elif inspect.isroutine(obj):
                    kind = "FUNC"
                elif inspect.ismodule(obj):
                    continue
                else:
                    kind = "PARAM"
                try:
                    sig = str(inspect.signature(obj)) if kind == "FUNC" else None
                except (TypeError, ValueError):
                    sig = None
                symbols.append(
                    {
                        "module": mod_name,
                        "qualname": name,
                        "kind": kind,
                        "origin": getattr(obj, "__module__", None),
                        "signature": sig,
                        "doc": firstline(inspect.getdoc(obj)),
                    }
                )
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(
            {"packages": versions, "symbols": symbols, "errors": errors},
            fh,
            indent=1,
        )
    print(f"{len(symbols)} symbols, {len(errors)} errors -> {out_path}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "docs/work/gdsfactory-corpus.json")
