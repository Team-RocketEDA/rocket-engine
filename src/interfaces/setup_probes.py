"""Shadow-proof Python-tool probes for the setup surface.

`detect_python` answers "is this tool module genuinely installed"
without false-readying on import shadows: a bare `find_spec` hit is
not enough, because an empty namespace directory on `sys.path` (a
stray dir, a partial uninstall, a foreign residue like the observed
`/tmp/gdsfactory/`) yields a loader-less namespace spec that the old
probe counted as installed and then stamped `found: True` when the
version lookup missed. This probe requires both a real loader and
installed distribution metadata before reporting found.
"""

import importlib.metadata
import importlib.util


def detect_python(names):
    """Split module names into found versions and missing names.

    A module counts as found only when it resolves to a spec with a
    real loader (namespace shadows carry `loader=None`) and its
    distribution metadata answers a version. Anything else — no
    spec, a loader-less spec, an unresolvable spec, or no installed
    distribution — reports missing, never a bare `True`.

    The distribution is resolved through the top-level mapping,
    not by assuming the names match: the `meow` module ships as
    the `meow-sim` distribution, and only the mapping knows that.
    Dotted names look up their top-level parent; when the mapping
    is silent (a dist-info without top_level records), a direct
    version lookup under the module name is the fallback, so the
    rule stays loader-plus-version either way.

    Args:
        names: Importable module names to probe, in order.

    Returns:
        (found, missing) pair: found maps each installed module to
            its distribution version, missing lists the rest in
            probe order.
    """
    try:
        provided = importlib.metadata.packages_distributions()
    except Exception:
        provided = {}
    found, missing = {}, []
    for name in names:
        try:
            spec = importlib.util.find_spec(name)
        except (ImportError, ValueError):
            spec = None
        if spec is None or spec.loader is None:
            missing.append(name)
            continue
        candidates = list(provided.get(name.partition(".")[0]) or [])
        if name not in candidates:
            candidates.append(name)
        for candidate in candidates:
            try:
                found[name] = importlib.metadata.version(candidate)
                break
            except importlib.metadata.PackageNotFoundError:
                continue
        else:
            missing.append(name)
    return found, missing
