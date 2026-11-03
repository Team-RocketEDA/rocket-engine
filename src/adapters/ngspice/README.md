# ngspice adapter

`run_spice` behind the ToolAdapter port (SIM-SKY130).

Job: `sources` (netlists, `.end` lines stripped), `measurements`
(`name`/`expr`/`min`/`max`/`unit`), `analyses` (default `op`),
`options` (default `wnflag=1`), `params` (`.param` lines),
`corner` (default `tt`), `temp_c` (default 27), optional `pdk`
(`id`/`revision`/`model_rel`/`engine_root`, resolved through the
PDK store so a wrong rev fails loudly before any sim).

Staging: `ngspice_deck.spice` (preamble + bodies + generated
`.control` with `let`/`print meas_*`) plus `.spiceinit`
(neutral base lines plus the lane profile extras, see
`../profile.py` and `docs/pdk/<lane>/profile.yaml`). Runs
`ngspice -b -o ngspice.log ngspice_deck.spice`.

Simulator needs are profile-driven (PDK-PROFILE pattern): the
default model relpath and `.spiceinit` extras come from the PDK
lane profile, never from adapter special-cases. An explicit
`model_rel` in the job pin always wins; a PDK with no sim
profile and no explicit `model_rel` fails loudly
(`invalid_command`, never a guessed relpath).

Parse: `meas_* = value` lines evaluated against bounds (SAX
`measurements` shape); a sim yielding no values synthesizes
`sim_fail` violations carrying ngspice's own error text. The
verdict always comes from parsed output, never the exit code.
