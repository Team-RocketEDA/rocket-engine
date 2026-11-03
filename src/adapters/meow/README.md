# MEOW eigenmode adapter

MeowAdapter serves run_em. It stages project-provided waveguide/device inputs and a simulation job, runs MEOW through its local mode-solving and SAX EME backends, and returns transmission, reflection, phase, mode, and convergence evidence.

The adapter is registered in Engine as the meow solver. Its focused qualification case is a silicon strip waveguide at 1550 nm with two modes: a matched guide transmits T=1/R=0, while an abrupt 0.5-to-1.0 μm width step lowers transmission and produces reflection. A missing dependency reports missing_dependency.

Engine code does not import the Tidy3D client or call its cloud service. The local smoke has a network-disabled check. FDTD and FEM support remain outside the proven scope. See the [MEOW-LIVE ticket](../../../docs/tickets/MEOW-LIVE.md).
