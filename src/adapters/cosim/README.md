# Coupled mixed-signal co-simulation adapter

CosimAdapter serves run_cosim. It runs an ngspice transient, samples the analog output into a digital bitstream, passes that stream to the Icarus HDL adapter, and evaluates the combined analog and digital checks.

The job supplies its analog sources, digital bench, and loop settings. PDK model references resolve through the PDK store; an invalid or changed model fails preflight. Model-free behavioral jobs can omit the PDK reference.

The verdict comes from parsed measurements and digital findings, not the tool exit code. Missing samples or tool failures remain failures or NOT_RUN with a reason. The adapter currently composes its digital half through HdlSimAdapter.

See the [SEAM-COSIM report](../../../docs/work/SEAM-COSIM/report.md) for qualification evidence and known limits.
