# postlayout adapter

`run_post_layout` behind the ToolAdapter port (POSTLAYOUT).

Job: `extracted_netlist` (simmed first body) + `testbench`
(optional second body), `extraction_provenance`
(`extraction_run_id`/`netlist_sha256`, freshness-verified —
stale records refuse loudly, never sim a schematic as
extracted), `measurements` (`name`/`expr`/`min`/`max`/`unit`,
bounds judge POST), `schematic_run_id` (`run_id` alias) plus
`schematic_measurements` or a `runs` resolver for the pre
side, optional `waveforms` (`name`/`expr` dumped via wrdata),
`analyses` (default `op`), `options` (default `wnflag=1`),
`params`, `corner` (default `tt`), `temp_c` (default 27),
optional `pdk` (`id`/`revision`/`model_rel`/`engine_root`,
resolved through the PDK store).

Staging: `postlayout_deck.spice` (preamble + bodies + generated
`.control` with `let`/`print meas_*` plus `wrdata`) and
`.spiceinit` (`ngbehavior=hsa`). Runs
`ngspice -b -o postlayout.log postlayout_deck.spice`.

Parse: `meas_* = value` lines evaluated against bounds (SAX
`measurements` shape) joined with schematic pre values into a
`comparison` table (`pre`/`post`/`delta`/`rel` per row; deltas
never gate the verdict); missing values synthesize `sim_fail`
violations carrying ngspice's own error text. The verdict
always comes from parsed output, never the exit code.
