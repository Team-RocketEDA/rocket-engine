"""Fail if engine code imports cloud clients (local-only rule).

gsim drags gdsfactoryplus in as a transitive dep; MEOW pulls
tidy3d. Both ride unused — this guard keeps them off every engine
hot path. Usage: python scripts/check_no_cloud.py [paths...]
"""

import ast
import sys
from pathlib import Path

FORBIDDEN_TOP_LEVELS = frozenset({"gdsfactoryplus", "tidy3d"})
# gcloud is also forbidden: it is the Plus cloud-job entrypoint.
FORBIDDEN_BASENAMES = frozenset({"gcloud"})


def scan_file(path):
    """[(file, lineno, module)] for forbidden imports in one file."""
    path = Path(path)
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return []
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module] if node.module else []
        else:
            continue
        for name in names:
            top = (name or "").split(".")[0]
            base = (name or "").split(".")[-1]
            if top in FORBIDDEN_TOP_LEVELS or base in FORBIDDEN_BASENAMES:
                hits.append((str(path), node.lineno, name))
    return hits


def scan(roots):
    """All hits under the given roots (files or dirs), sorted."""
    hits = []
    for root in roots:
        root = Path(root)
        files = [root] if root.is_file() else sorted(root.rglob("*.py"))
        for path in files:
            hits.extend(scan_file(path))
    return sorted(hits)


def main(argv):
    roots = argv[1:] or ["src", "scripts"]
    hits = scan(roots)
    for path, lineno, name in hits:
        print(f"{path}:{lineno}: forbidden cloud import: {name}")
    return 1 if hits else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
