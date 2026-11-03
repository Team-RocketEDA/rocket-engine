# Tool tasks, datasets and evidence

Describe the chosen task and its exact input/output contract before execution.
Select its DUT occurrence, testbench, model/technology references, analysis
settings and profile. Keep all consumed values in the I28 snapshot. Use real
fixture/project inputs instead of a package smoke or hardcoded demo output.

DC, AC and transient are explicit analyses of the v1 `simulate.spice` task:

| Analysis | Inputs that distinguish it | Result data expected |
|---|---|---|
| `op` | Circuit/model operating conditions | Operating-point quantities/table |
| `dc` | Sweep source/parameter and values/range | Sweep axis and per-signal values |
| `ac` | Frequency range/spacing and excitation | Frequency axis and complex responses |
| `tran` | Stop time, sample/max-step policy and stimulus | Time axis and signal traces |

Noise, transfer function, pole-zero, sensitivity, distortion and qualified
harmonic balance are separately named modes with backend/model prerequisites.
PVT corners, parameter sweeps and Monte Carlo add explicit condition/sample axes;
they are not different meanings of transient. Measurements are typed values,
limits/margins and evaluation results, not text scraped by the frontend.

A digital HDL/cocotb bench runs against the selected qualified simulator.
Photonic circuit tasks can return spectra or complex S-parameter matrices;
a wavelength response does not imply a spatial heatmap. DRC/LVS return actual
violation sets and location/mapping references. Independent LVS requires an
independent reference circuit; comparing an extracted circuit with itself proves
nothing.

Consume the exact dataset/result schemas exposed by the runtime. Preserve
signal IDs, axis names/order, shape, units, complex real/imaginary representation,
condition/corner selectors, validity/missing-value metadata, chunk ordering,
convergence and provenance. Large arrays are fetched through bounded immutable
artifact/chunk references; do not truncate data silently to fit a chat reply.

The frontend renders declared traces, tables, matrices/heatmaps or markers using
these data and its own web plotting implementation. The engine does not send
HTML/JavaScript or a Python-rendered dashboard as the primary data contract.
Pure display transforms such as magnitude/phase can be selected by the renderer;
they cannot turn a missing source quantity into fabricated evidence.

Watch/query expose dataset/result revisions separately from raw logs. Stream
verbose native stdout/stderr to the output terminal and retrieve it when needed
for diagnosis; do not parse log prose as the normal task-to-task handoff. Charts
and tables retain `(run, snapshot, target, input closure, tool/model conditions)`.

An executed process and a design verdict are separate states. Read convergence,
findings, required-stage outcomes and measurements. A completed process with
missing or unsupported required evidence cannot establish PASS. On failure,
retain valid partial data and committed effects, and report the specific block.
Do not discard useful measurements because the aggregate check failed.

For a genuinely new rerun, start a fresh request using the retained pinned
inputs where appropriate. On restart, inspect survivors and explicitly
resume/discard unfinished work; never automatically replay earlier scripts.
Cancel the intended run and inspect its children; already committed effects
remain real and a shared coalesced run affects attached callers.

FPGA, field/FEM/EM/mode/device and thermal provider work is outside the November 4
MVP. Its schemas and intentionally RED acceptance cases are planning evidence,
not permission to advertise installed support or block the MVP on those solvers.
