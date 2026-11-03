"""Ifdef-aware property sites plus the vacuity guard for run_formal.

Helper behind FORMAL-EDGE: :func:`property_sites` counts only the
assume/assert/cover sites that survive Verilog preprocessing
(`` `define `` lines never count, `` `ifdef``/`` `ifndef`` branches
resolve against the active defines), and :func:`guard_vacuous_pass`
refuses an sby PASS with zero checked properties as a loud
bounded-vacuous FAIL instead of a bare PASS.
"""

import re
from pathlib import Path

DEFAULT_DEFINES = frozenset({"FORMAL"})
""" pre-defined macros assumed active, matching sby ``read -formal``."""

VACUOUS_SCOPE = "bounded-vacuous"
"""Scope reported when sby PASSes with zero checked properties."""

VACUOUS_RULE = "formal_vacuous"
"""Violation rule for a vacuous (property-free) sby PASS."""

_PROP_RE = re.compile(r"\b(assert|assume|cover)\s*\(")
_DIRECTIVE_RE = re.compile(
    r"^\s*`(ifdef|ifndef|elsif|elif|else|endif|define|undef)\b\s*(\S+)?"
)
_DEFINE_ANY_RE = re.compile(r"`\s*define\b")
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_$]*$")


def property_sites(sources, defines=None):
    """Active assume/assert/cover sites by file and line.

    Comment- and preprocess-aware: ``/* */`` block comments (including
    multi-line) plus ``//`` line comments are stripped before matching,
    `` `define `` lines never count (they declare the ``assert`` macro,
    they are not proof obligations), and `` `ifdef``/`` `ifndef``/
    `` `elsif``/`` `else``/`` `endif`` branches resolve against the
    active defines so disabled properties do not inflate the count.
    `` `define``/`` `undef`` lines encountered in an active branch
    update the active set for the lines that follow. Unreadable
    sources are skipped, never fatal.

    Args:
        sources: Iterable of RTL source paths to scan.
        defines: Pre-defined macro names considered active. None
            means the sby default (FORMAL, matching ``read -formal``).

    Returns:
        (assumptions, properties) tuple: assumptions carry file plus
            line, properties add the kind (assert or cover).
    """
    active = (
        set(DEFAULT_DEFINES) if defines is None else set(defines)
    )
    assumptions, properties = [], []
    for source in sources:
        try:
            text = Path(source).read_text(
                encoding="utf-8", errors="replace"
            )
        except OSError:
            continue
        in_block = False
        stack = []
        for lineno, raw in enumerate(text.splitlines(), start=1):
            code, in_block = _strip_block(raw, in_block)
            code = code.split("//", 1)[0]
            directive = _DIRECTIVE_RE.match(code)
            if directive is not None:
                kind, arg = directive.group(1), directive.group(2)
                current = stack[-1]["active"] if stack else True
                if kind in ("ifdef", "ifndef"):
                    parent = current
                    if arg is not None and _IDENT_RE.match(arg):
                        hit = (arg in active) == (kind == "ifdef")
                    else:
                        hit = True
                    now = parent and hit
                    stack.append(
                        {"parent": parent, "taken": now, "active": now}
                    )
                elif kind in ("elsif", "elif"):
                    if stack:
                        frame = stack[-1]
                        parent = frame["parent"]
                        if not parent or frame["taken"]:
                            frame["active"] = False
                        else:
                            if arg is not None and _IDENT_RE.match(arg):
                                hit = arg in active
                            else:
                                hit = True
                            frame["active"] = hit
                            if hit:
                                frame["taken"] = True
                elif kind == "else":
                    if stack:
                        frame = stack[-1]
                        parent = frame["parent"]
                        now = parent and not frame["taken"]
                        frame["active"] = now
                        if now:
                            frame["taken"] = True
                elif kind == "endif":
                    if stack:
                        stack.pop()
                elif kind == "define":
                    if current and arg is not None:
                        name = arg.split("(", 1)[0].strip()
                        if _IDENT_RE.match(name):
                            active.add(name)
                elif kind == "undef":
                    if current and arg is not None:
                        active.discard(arg.strip())
                continue
            if stack and not stack[-1]["active"]:
                continue
            if _DEFINE_ANY_RE.search(code):
                continue
            for match in _PROP_RE.finditer(code):
                entry = {"file": str(source), "line": lineno}
                if match.group(1) == "assume":
                    assumptions.append(entry)
                else:
                    kind = match.group(1)
                    properties.append({**entry, "kind": kind})
    return assumptions, properties


def guard_vacuous_pass(properties, mode=None, depth=None):
    """Refuse an sby PASS with zero checked properties, loudly.

    A property-free PASS is a vacuous proof: sby exited 0 but nothing
    was proven. The guard converts it to a bounded-vacuous FAIL
    (error finding, scope ``bounded-vacuous``) so the engine verdict
    is FAIL, never a bare PASS.

    Args:
        properties: Property entries as returned by property_sites.
        mode: Sby mode string (bmc, prove, or cover) for the message.
        depth: Proof bound in steps for the message.

    Returns:
        None when at least one property was checked; otherwise a
            mapping with scope plus the formal_vacuous violation.

    Caution: Converts sby PASS to engine FAIL when properties is
        empty — zero-property designs cannot PASS silently.
    """
    if properties:
        return None
    where = []
    if mode is not None:
        where.append(f"mode {mode}")
    if depth is not None:
        where.append(f"depth {depth}")
    scope = ", ".join(where) if where else "sby defaults"
    message = (
        f"sby reported PASS with zero checked properties ({scope}): "
        "no active assert/cover site was found — vacuous proof refused "
        "as FAIL (scope bounded-vacuous); add a property to the sources "
        "or check `ifdef guards (FORMAL is assumed defined)."
    )
    return {
        "scope": VACUOUS_SCOPE,
        "violation": {
            "rule": VACUOUS_RULE,
            "severity": "error",
            "message": message,
        },
    }


def _strip_block(line, in_block):
    """Remove /* */ spans from one line, threading the block state."""
    out = []
    pos = 0
    while True:
        if in_block:
            end = line.find("*/", pos)
            if end == -1:
                return "".join(out), True
            pos = end + 2
            in_block = False
            continue
        start = line.find("/*", pos)
        if start == -1:
            out.append(line[pos:])
            return "".join(out), False
        end = line.find("*/", start + 2)
        out.append(line[pos:start])
        if end == -1:
            return "".join(out), True
        pos = end + 2
