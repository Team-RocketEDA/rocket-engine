"""Staged meow EME driver: job JSON in, framed result envelope on stdout.

The adapter copies this file into the run workdir next to
`meow_job.json` and executes `python meow_driver.py meow_job.json`.
The envelope is framed between ROCKETEDA-ENVELOPE-BEGIN/END marker
lines; solver warnings may share stdout — the adapter extracts the
frame and logs the rest, never fatal.

Cross-sections are built from the project spec (`doc` widths_um /
wl_um / cell_length_um): nothing is hardcoded — widths, wavelength,
cell length, and both mode counts ride the job. Each device solves
twice (base then refined modes) so the envelope always carries
two-resolution convergence evidence. The mesh, materials, and strip
stack mirror the MEOW-LIVE smoke exactly (500x220nm Si on SiO2,
2.0um half-window, 61x41 grid). Mode solving uses meow's tidy3d FDE
backend — the local CPU eigensolver proven in the smoke (no
`tidy3d.web` import anywhere on this path). FDTD/FEM stay out:
proposed, not proven.

Envelope: `{"ok": true, "meow_version, "tidy3d_version, "result":
{wl_um, widths_um[], cell_length_um, base, refined, convergence,
ports}}` or `{"ok": false, "error": {code, message, token,
line}}`. Exit 0 on sim success, 2 on a malformed device, 3 when
meow is not importable. Anything else explodes with a traceback
and exit 1, which parse() reports as runner_unavailable rather
than mistaking a tool crash for physics.
"""

import json
import re
import sys

_QUOTED_RE = re.compile(r"""['\"]([^'\"]+)['\"]""")
_TOKEN_KEYS = ("widths_um", "wl_um", "cell_length_um", "modes", "device")

X_HALF_UM = 2.0
Y_HALF_UM = 2.0
NX = 61
NY = 41
SI_HEIGHT_UM = 0.22

_ENVELOPE_BEGIN = "ROCKETEDA-ENVELOPE-BEGIN"
_ENVELOPE_END = "ROCKETEDA-ENVELOPE-END"


def _token(doc, message):
    names = list(_TOKEN_KEYS) + [str(doc.get("device") or "")]
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


def _emit(payload):
    """Print one marker-framed JSON envelope on stdout.

    Marker literals mirror src/adapters/meow/_envelope.py — this
    file stages standalone, so change both or neither.
    """
    print(_ENVELOPE_BEGIN)
    print(json.dumps(payload))
    print(_ENVELOPE_END)


def _fail(code, message, token, line):
    _emit(
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


def main(argv):
    """Run one staged meow EME solve: job JSON in, envelope on stdout.

    Args:
        argv: Argument vector; argv[1] is the staged job JSON path.

    Returns:
        Process exit code: 0 on sim success, 2 on a malformed
            device, 3 when meow is not importable.

    Raises:
        ValueError: Bad device geometry (raised and caught inside
            main into the invalid_device envelope — never escapes).
    """
    with open(argv[1], encoding="utf-8") as handle:
        job = json.load(handle)
    text = job.get("text", "")
    doc = job["doc"]
    try:
        import numpy as np

        import meow
        from meow import MATERIALS, CrossSection, Environment, Mesh2D, Rectangle
        from meow.eme import compute_s_matrix
        from meow.fde.tidy3d import compute_modes_tidy3d
        from meow.structures import Structure2D
    except ImportError as exc:
        _fail(
            "missing_dependency",
            f"meow is not importable: {exc} "
            "(uv sync).",
            None,
            None,
        )
        return 3
    try:
        widths = [float(w) for w in doc["widths_um"]]
        wl_um = float(doc["wl_um"])
        cell_um = float(doc["cell_length_um"])
        if not widths or any(not w > 0 for w in widths):
            raise ValueError(f"widths_um must be positive: {widths!r}.")
        if not wl_um > 0 or not cell_um > 0:
            raise ValueError("wl_um/cell_length_um must be positive.")
        env = Environment(wl=wl_um)
        mesh = Mesh2D(
            x=np.linspace(-X_HALF_UM, X_HALF_UM, NX),
            y=np.linspace(-Y_HALF_UM, Y_HALF_UM, NY),
        )
        silicon = MATERIALS["silicon"]
        oxide = MATERIALS["silicon_oxide"]

        def _strip(width):
            return CrossSection(
                structures=[
                    Structure2D(
                        material=oxide,
                        geometry=Rectangle(
                            x_min=-X_HALF_UM, x_max=X_HALF_UM,
                            y_min=-Y_HALF_UM, y_max=0.0,
                        ),
                    ),
                    Structure2D(
                        material=silicon,
                        geometry=Rectangle(
                            x_min=-width / 2, x_max=width / 2,
                            y_min=0.0, y_max=SI_HEIGHT_UM,
                        ),
                    ),
                ],
                mesh=mesh,
                env=env,
            )

        def _solve(num_modes):
            molten = [
                compute_modes_tidy3d(_strip(width), num_modes=num_modes)
                for width in widths
            ]
            dense, port_map = compute_s_matrix(
                molten, cell_lengths=[cell_um] * len(widths)
            )
            matrix = np.asarray(dense, dtype=complex)
            s21 = matrix[port_map["right@0"], port_map["left@0"]]
            s11 = matrix[port_map["left@0"], port_map["left@0"]]
            return {
                "num_modes": num_modes,
                "neff_re": [float(np.real(m.neff)) for m in molten[0]],
                "neff_im": [float(np.imag(m.neff)) for m in molten[0]],
                "transmission": float(abs(s21) ** 2),
                "reflection": float(abs(s11) ** 2),
                "s21_phase_rad": float(np.angle(s21)),
            }, dict(port_map)

        modes = doc["modes"]
        base, ports = _solve(int(modes["base"]))
        refined, _ = _solve(int(modes["refined"]))
    except (ValueError, KeyError, TypeError) as exc:
        message = f"{type(exc).__name__}: {exc}"
        token = _token(doc, message)
        _fail("invalid_device", message, token, _find_line(text, token))
        return 2
    try:
        from importlib import metadata as _metadata

        tidy3d_version = _metadata.version("tidy3d")
    except Exception:
        tidy3d_version = "unknown"
    _emit(
        {
            "ok": True,
            "meow_version": getattr(meow, "__version__", "unknown"),
            "tidy3d_version": tidy3d_version,
            "result": {
                "wl_um": wl_um,
                "widths_um": widths,
                "cell_length_um": cell_um,
                "base": base,
                "refined": refined,
                "convergence": {
                    "dT": abs(
                        refined["transmission"] - base["transmission"]
                    ),
                    "dR": abs(
                        refined["reflection"] - base["reflection"]
                    ),
                    "dneff": abs(
                        refined["neff_re"][0] - base["neff_re"][0]
                    ),
                },
                "ports": ports,
            },
        }
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
