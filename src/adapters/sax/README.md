# adapters/sax — SAX photonic sim solver

`run_optical` behind the `ToolAdapter` port: preflight refuses the
wrong operation, bad timeouts, missing/extra sources, unparseable
specs, and unresolvable interpreters; execute stages the sim driver
plus a job JSON into the workdir and runs
`python sax_driver.py sax_job.json`; parse normalizes the JSON
envelope into `{total, violations[], measurements[], spectra[]}`
with file/line locations where meaningful.

Verified against sax 0.18.2 on MZI/ring fixtures
(`tests/adapters/fixtures/sax/`). The balanced MZI reproduces its
documented transmission exactly (cross 1.0, bar 0.0); the mistuned
MZI misses its target with an engine-computed margin; a malformed
circuit synthesizes an error violation naming the offender with
file + line rather than going clean. A sax-less interpreter
raises `missing_dependency`, never a fake verdict.

Tool resolution is the engine interpreter (sax arrives via the pip
`photonic` group) plus an explicit job `tool_dir` holding an
alternate python; where the tools live is B10 scope. Registered in
the Engine as `run_optical` → `sax` per F8, so `deck.tool: sax`
selects it and a missing hint falls back to it as the default.
