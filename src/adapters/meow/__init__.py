"""Meow EME smoke: smallest honest strip-waveguide S-matrix.

A 500x220nm Si strip on SiO2 at 1550nm, 2 modes solved with
meow's tidy3d FDE backend and cascaded over a 10um cell with
meow's SAX EME backend. Verified against meow 0.15.0 over
tidy3d 2.10.0: the matched guide transmits T=1.0/R=0.0, while
an abrupt 0.5->1.0um width step drops the fundamental to
T=0.877/R=0.0009 — the good-vs-bad signal. Solver imports stay
lazy so bare envs fail loud (`missing_dependency`), never
fake-green. Engine code never imports the tidy3d client: its
version is read from installed metadata, and the smoke path
runs with the network amputated (see the locality test). A
full `deck.tool: meow` Engine adapter is follow-up, out of
scope.
"""

from importlib import metadata as _metadata

from ..errors import AdapterError

MEOW_PIN = "0.15.0"
TIDY3D_PIN = "2.10.0"

WL_UM = 1.55
CELL_UM = 10.0
NUM_MODES = 2
SI_HEIGHT_UM = 0.22
X_HALF_UM = 2.0
Y_HALF_UM = 2.0
NX = 61
NY = 41


def meow_version():
    """Proven solver version, observable per run (uv.lock pin)."""
    try:
        import meow
    except ImportError as exc:
        raise AdapterError(
            "missing_dependency",
            f"meow is not importable: {exc} "
            "(uv sync --group photonic).",
        ) from exc
    return getattr(meow, "__version__", "unknown")


def tidy3d_version():
    """FDE backend version, read from metadata (never a client import)."""
    try:
        return _metadata.version("tidy3d")
    except _metadata.PackageNotFoundError as exc:
        raise AdapterError(
            "missing_dependency",
            f"tidy3d is not installed: {exc} "
            "(uv sync --group photonic).",
        ) from exc


def run_eme_smoke(*, widths_um=(0.5,), wl_um=WL_UM, cell_length_um=CELL_UM,
                  num_modes=NUM_MODES):
    """Run the EME smoke live; return the fundamental S-parameters.

    Returns `{meow_version, tidy3d_version, wl_um, widths_um[],
    cell_length_um, num_modes, neff_re[], neff_im[], transmission,
    reflection, s21_phase_rad, ports}` — plain floats, JSON-friendly.
    `transmission`/`reflection` are |S21|^2/|S11|^2 of the
    fundamental; `neff_*` is the input guide's modal basis.
    Raises `missing_dependency` where meow is uninstalled,
    `invalid_command` on bad parameters.
    """
    try:
        widths = [float(w) for w in widths_um]
    except (TypeError, ValueError) as exc:
        raise AdapterError(
            "invalid_command",
            f"EME smoke needs a list of widths in um, got {widths_um!r}.",
        ) from exc
    if not widths or any(not w > 0 for w in widths):
        raise AdapterError(
            "invalid_command",
            f"EME smoke needs positive widths in um, got {widths_um!r}.",
        )
    if not wl_um > 0 or not cell_length_um > 0:
        raise AdapterError(
            "invalid_command",
            f"EME smoke needs positive wl/cell_length, got wl_um={wl_um!r} "
            f"cell_length_um={cell_length_um!r}.",
        )
    if not isinstance(num_modes, int) or num_modes < 1:
        raise AdapterError(
            "invalid_command", f"EME smoke needs num_modes >= 1, got {num_modes!r}."
        )
    try:
        import numpy as np

        from meow import MATERIALS, CrossSection, Environment, Mesh2D, Rectangle
        from meow.eme import compute_s_matrix
        from meow.fde.tidy3d import compute_modes_tidy3d
        from meow.structures import Structure2D
    except ImportError as exc:
        raise AdapterError(
            "missing_dependency",
            f"meow is not importable: {exc} "
            "(uv sync --group photonic).",
        ) from exc
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

    molten = [
        compute_modes_tidy3d(_strip(width), num_modes=num_modes)
        for width in widths
    ]
    s_dense, port_map = compute_s_matrix(
        molten, cell_lengths=[cell_length_um] * len(widths)
    )
    matrix = np.asarray(s_dense, dtype=complex)
    i_in = port_map["left@0"]
    i_out = port_map["right@0"]
    s21 = matrix[i_out, i_in]
    s11 = matrix[i_in, i_in]
    return {
        "meow_version": meow_version(),
        "tidy3d_version": tidy3d_version(),
        "wl_um": wl_um,
        "widths_um": widths,
        "cell_length_um": cell_length_um,
        "num_modes": num_modes,
        "neff_re": [float(np.real(mode.neff)) for mode in molten[0]],
        "neff_im": [float(np.imag(mode.neff)) for mode in molten[0]],
        "transmission": float(abs(s21) ** 2),
        "reflection": float(abs(s11) ** 2),
        "s21_phase_rad": float(np.angle(s21)),
        "ports": dict(port_map),
    }
