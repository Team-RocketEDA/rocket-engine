"""Fail if enforced endpoints lack Google-style docstrings (ADR-003).

Docstrings are the API contract source: one text feeds human docs,
machine schemas, and MCP help. This guard keeps the contract honest
the way the no-cloud guard keeps cloud imports off the hot path.

Checked (public callables in enforced files only):
- a docstring with a one-line summary,
- an Args: section naming every parameter (when it takes any),
- a Returns: section (when it returns a value),
- a Raises: section (when its body can raise).

Public classes need a summary line; constructor params belong in
the class docstring by convention (see AGENTS.md). `Caution:` is
mandated by AGENTS.md where an endpoint bites but is conditional
by nature, so the guard does not require it.

Usage: python scripts/check_docstrings.py [paths...]
With no paths, scans the enforced-files manifest below. Slice
API-GEN-A enforces the composition root, the op dispatcher, and
the transport/CLIMCP surface; solver adapters migrate in API-GEN-B.
"""

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Repo-relative manifest: only these files are enforced this slice.
# Entries may be paths or globs; only *.py files are scanned.
ENFORCED = (
    "src/composition.py",
    "src/execution/dispatch.py",
    "src/adapters/mcp/__init__.py",
    "src/adapters/mcp/server.py",
    "src/adapters/ipc/__init__.py",
    "src/adapters/http/__init__.py",
    "src/adapters/cli/*.py",
)

_SECTIONS = frozenset({
    "Args:", "Returns:", "Raises:", "Caution:", "Attributes:",
    "Example:", "Examples:", "Note:", "Notes:", "Yields:",
})

_FUNCTION_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef)


def enforced_files(root=None):
    """Manifest entries expanded to existing .py files, sorted."""
    root = Path(root) if root is not None else ROOT
    files = []
    for entry in ENFORCED:
        if "*" in entry:
            files.extend(p for p in sorted(root.glob(entry)) if p.is_file())
        else:
            candidate = root / entry
            if candidate.is_file():
                files.append(candidate)
    return sorted(p for p in files if p.suffix == ".py")


def _own_nodes(func):
    """Statements of one function, never descending into nested defs."""
    stack = list(func.body)
    while stack:
        node = stack.pop()
        yield node
        for child in ast.iter_child_nodes(node):
            if isinstance(child, _FUNCTION_TYPES + (ast.Lambda,)):
                continue
            stack.append(child)


def _returns_value(func):
    for node in _own_nodes(func):
        if isinstance(node, ast.Return) and node.value is not None:
            if isinstance(node.value, ast.Constant) and node.value.value is None:
                continue
            return True
    return False


def _raises(func):
    return any(isinstance(n, ast.Raise) for n in _own_nodes(func))


def _params(func, is_method):
    names = [a.arg for a in list(func.args.posonlyargs) + list(func.args.args)]
    names += [a.arg for a in func.args.kwonlyargs]
    if func.args.vararg is not None:
        names.append(func.args.vararg.arg)
    if func.args.kwarg is not None:
        names.append(func.args.kwarg.arg)
    if is_method and names and names[0] in ("self", "cls"):
        names = names[1:]
    return names


def _section_block(lines, header):
    """Lines under `header:` until the next section header (or end)."""
    try:
        start = next(
            i for i, line in enumerate(lines) if line.strip() == header
        )
    except StopIteration:
        return None
    block = []
    for line in lines[start + 1:]:
        if line.strip() in _SECTIONS:
            break
        block.append(line)
    return block


def _check_callable(path, node, endpoint, is_method):
    doc = ast.get_docstring(node)
    if doc is None:
        return [(str(path), node.lineno, endpoint, "missing docstring")]
    hits = []
    lines = doc.splitlines()
    if not lines or not lines[0].strip():
        hits.append((str(path), node.lineno, endpoint, "missing summary line"))
    params = _params(node, is_method)
    if params:
        block = _section_block(lines, "Args:")
        if block is None:
            hits.append(
                (str(path), node.lineno, endpoint, "missing Args: section")
            )
        else:
            missing = [
                name for name in params
                if not any(
                    stripped == name or stripped.startswith(name + ":")
                    or stripped.startswith(name + " (")
                    for stripped in (b.strip() for b in block)
                )
            ]
            if missing:
                hits.append((
                    str(path), node.lineno, endpoint,
                    f"undocumented params: {', '.join(missing)}",
                ))
    if _returns_value(node) and _section_block(lines, "Returns:") is None:
        hits.append(
            (str(path), node.lineno, endpoint, "missing Returns: section")
        )
    if _raises(node) and _section_block(lines, "Raises:") is None:
        hits.append(
            (str(path), node.lineno, endpoint, "missing Raises: section")
        )
    return hits


def _endpoints(tree):
    """(node, endpoint, is_method) for public classes and callables."""
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            if not node.name.startswith("_"):
                yield node, node.name, False
            for child in node.body:
                if isinstance(child, _FUNCTION_TYPES) and not child.name.startswith("_"):
                    yield child, f"{node.name}.{child.name}", True
        elif isinstance(node, _FUNCTION_TYPES) and not node.name.startswith("_"):
            yield node, node.name, False


def scan_file(path):
    """[(file, lineno, endpoint, reason)] for docstring gaps in one file."""
    path = Path(path)
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return []
    hits = []
    for node, endpoint, is_method in _endpoints(tree):
        if isinstance(node, ast.ClassDef):
            doc = ast.get_docstring(node)
            if doc is None:
                hits.append(
                    (str(path), node.lineno, endpoint, "missing docstring")
                )
            elif not doc.splitlines() or not doc.splitlines()[0].strip():
                hits.append(
                    (str(path), node.lineno, endpoint, "missing summary line")
                )
        else:
            hits.extend(_check_callable(path, node, endpoint, is_method))
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
    roots = argv[1:] or enforced_files()
    hits = scan(roots)
    for path, lineno, endpoint, reason in hits:
        print(f"{path}:{lineno}: {endpoint}: {reason}")
    return 1 if hits else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
