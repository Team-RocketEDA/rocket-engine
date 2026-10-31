"""PHOTONIC-WIRE lane: register the proven photonic solvers on an Engine.

Circulax (time-domain transient circuit sim) serves run_optical
behind deck.tool `circulax` as the second tool — sax stays first,
so the default never moves. Meow (EME mode/field solving with
two-resolution convergence evidence) serves run_em behind
deck.tool `meow` as the only tool. FDTD/FEM stay out: proposed,
not proven, so no other deck tool is registered here.

This helper is the executable form of the composition.py wiring
patch (see docs/work/PHOTONIC-WIRE/report.md): it performs the
same solver registrations the patch bakes into Engine.__init__,
plus the same SOLVER_DEPS detection rows the patch adds to
interfaces/setup.py, so dispatch and capabilities reporting are
provable on an unpatched tree. Post-patch it is an idempotent
re-registration of identical keys.

Generalization law: the adapters consume project specs (circuit
YAML in, transient out; device YAML in, S-params plus
convergence out). The RC/EME smokes qualify the installs; this
lane generalizes them and never hardcodes their values.
"""

from ..interfaces.setup import SOLVER_DEPS

PHOTONIC_TOOLS = {"run_optical": "circulax", "run_em": "meow"}

# Detection rows mirroring the setup.py patch: each cites the
# solver's own import probe, the way the sax row cites sax. Deeper
# pip-transitive deps stay out — a solver present but broken fails
# loud at run time, never as a misreported capability.
PHOTONIC_DEPS = {
    ("run_optical", "circulax"): {"python": ["circulax"]},
    ("run_em", "meow"): {"python": ["meow"]},
}


def wire_photonics(engine, *, runner=None):
    """Register the circulax and meow solvers on an Engine.

    Circulax joins run_optical after sax (the default is the
    first registered, so sax keeps it); meow opens run_em.
    Detection rows land in SOLVER_DEPS only where the static
    table has none, so an integrator-patched tree keeps its own
    rows and capabilities reporting never raises unknown_solver
    for a wired lane.

    Args:
        engine: Engine to wire (composition root with
            register_solver).
        runner: Optional isolated runner handed to both
            adapters; direct subprocess when None.

    Returns:
        Mapping of operation to deck-tool key registered
        ({"run_optical": "circulax", "run_em": "meow"}).

    Raises:
        ModuleNotFoundError: If the same-ticket adapter modules
            (adapters.circulax.adapter, adapters.meow.adapter)
            are not importable — the lane is missing, never
            faked.

    Caution: Mutates the shared SOLVER_DEPS map (additive rows
        only, never overwrites) and the engine's solver registry
        — call once per Engine; repeats re-register identically.
    """
    from ..adapters.circulax.adapter import CirculaxAdapter
    from ..adapters.meow.adapter import MeowAdapter

    for key, spec in PHOTONIC_DEPS.items():
        SOLVER_DEPS.setdefault(key, dict(spec))
    engine.register_solver("run_optical", CirculaxAdapter(runner=runner),
                           tool="circulax")
    engine.register_solver("run_em", MeowAdapter(runner=runner), tool="meow")
    return dict(PHOTONIC_TOOLS)
