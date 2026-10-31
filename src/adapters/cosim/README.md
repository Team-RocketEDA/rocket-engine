# adapters/cosim — coupled mixed-signal co-simulation solver

`run_cosim` behind the `ToolAdapter` port (SEAM-COSIM): preflight
refuses the wrong operation, missing halves, bad loop config,
control-carrying analog bodies, bad PDK pins, and unresolvable
tools; execute runs a single-threaded ngspice transient, samples
the bitstream node mid-period, streams the live bits into the
digital bench as `cosim_bits.txt`, and runs that under icarus via
`HdlSimAdapter`; parse judges the JOINT verdict (SNDR gate plus
RTL ones-density/counts/golden-model checks).

Rules reuse the halves' native names: quantitative misses are
`measurement`, digital native violations pass through, valueless
halves synthesize `sim_fail`. The verdict always comes from parsed
output, never the exit code. Quantitative helpers (`rfft_power`,
`sndr_bits`, `sample_bits`, `settled_stats`) are stdlib-only —
the SNDR estimator replicates sim/snr.py including its guard
quirk, verified to 0.01 dB against the recorded 40.2 dB vector.

Tiers are project inputs, not fixtures: the tier-1 behavioral
body and the PEX macro plus wrapper both arrive as
`analog_sources` with their loop config. No Engine registration
yet — see `docs/work/SEAM-COSIM/wiring.patch` (integrator
applies; the VALIDATE-M seam tests update in the same step via
`docs/work/SEAM-COSIM/seam-tests.patch`).
