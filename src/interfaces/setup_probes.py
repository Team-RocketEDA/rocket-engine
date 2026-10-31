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

    Args:
        names: Importable module names to probe, in order.

    Returns:
        (found, missing) pair: found maps each installed module to
            its distribution version, missing lists the rest in
            probe order.
    """
    found, missing = {}, []
    for name in names:
        try:
            spec = importlib.util.find_spec(name)
        except (ImportError, ValueError):
            spec = None
        if spec is None or spec.loader is None:
            missing.append(name)
            continue
        try:
            found[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            missing.append(name)
    return found, missing
