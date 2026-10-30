"""Staged SAX sim driver: job JSON in, result envelope JSON on stdout.

The adapter copies this file into the run workdir next to `sax_job.json`
and executes `python sax_driver.py sax_job.json`. Exactly one JSON
document is printed to stdout; sax warnings go to stderr untouched.

Envelope: `{"ok": true, "sax_version, "result": {wavelength_nm[],
transmission{"a>b": []}, ports[]}}` or `{"ok": false, "error":
{code, message, token, line}}`. Exit 0 on sim success, 2 on a
malformed circuit, 3 when sax is not importable. Anything else
explodes with a traceback and exit 1, which parse() reports as
runner_unavailable rather than mistaking a tool crash for physics.
"""

import json
import re
import sys

_QUOTED_RE = re.compile(r"""['\"]([^'\"]+)['\"]""")


def _linspace(start, stop, points):
    if points <= 1:
        return [float(start)]
    return [float(start + i * (stop - start) / (points - 1)) for i in range(points)]


def _token(doc, message):
    instances = doc.get("instances") or {}
    names = list(instances)
    names.extend(
        inst.get("component", "")
        for inst in instances.values()
        if isinstance(inst, dict)
    )
    for name in names:
        if name and re.search(r"\b" + re.escape(name) + r"\b", message):
            return name
    for match in _QUOTED_RE.finditer(message):
        return match.group(1)
    return None


def _find_line(text, token):
    if not token:
        return None
    for number, line in enumerate(text.splitlines(), 1):
        if token in line:
            return number
    return None


def _fail(code, message, token, line):
    print(
        json.dumps(
            {
                "ok": False,
                "error": {
                    "code": code,
                    "message": message,
                    "token": token,
                    "line": line,
                },
            }
        )
    )


def main(argv):
    """Run one staged SAX sim: job JSON in, envelope JSON on stdout.

    Args:
        argv: Argument vector; argv[1] is the staged job JSON path.

    Returns:
        Process exit code: 0 on sim success, 2 on a malformed
            circuit, 3 when sax is not importable.

    Raises:
        ValueError: Unknown model name (raised and caught inside
            main into the invalid_circuit envelope — never escapes).
    """
    with open(argv[1], encoding="utf-8") as handle:
        job = json.load(handle)
    text = job.get("text", "")
    doc = job["doc"]
    try:
        import sax
    except ImportError as exc:
        _fail("missing_dependency", f"sax is not importable: {exc}.", None, None)
        return 3
    try:
        bound = {}
        for inst in doc["instances"].values():
            name = inst["component"]
            if name not in bound:
                try:
                    bound[name] = getattr(sax.models, name)
                except AttributeError:
                    raise ValueError(f"Unknown model: {name!r}.") from None
        netlist = {
            "instances": doc["instances"],
            "connections": doc.get("connections") or {},
            "ports": doc["ports"],
        }
        circuit, _info = sax.circuit(netlist, models=bound)
        sweep = doc["sweep"]
        grid_nm = _linspace(sweep["start_nm"], sweep["stop_nm"], sweep["points"])
        raw = circuit(wl=[wavelength / 1000.0 for wavelength in grid_nm])
        transmission = {}
        for (left, right), values in raw.items():
            flat = values.tolist() if hasattr(values, "tolist") else list(values)
            if not isinstance(flat, list):
                flat = [flat]
            transmission[f"{left}>{right}"] = [
                float(abs(complex(value)) ** 2) for value in flat
            ]
    except (ValueError, KeyError, TypeError) as exc:
        message = f"{type(exc).__name__}: {exc}"
        token = _token(doc, message)
        _fail("invalid_circuit", message, token, _find_line(text, token))
        return 2
    print(
        json.dumps(
            {
                "ok": True,
                "sax_version": getattr(sax, "__version__", "unknown"),
                "result": {
                    "wavelength_nm": grid_nm,
                    "transmission": transmission,
                    "ports": sorted(doc["ports"]),
                },
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
