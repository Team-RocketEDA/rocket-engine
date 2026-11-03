# adapters/lvs_netgen — Netgen LVS solver

Batch LVS behind the `ToolAdapter` port: preflight refuses missing
binaries, netlists, and setup files; execute flattens both sides to
top level (netgen's one-shot `lvs` compares top circuits only) and
runs `netgen -batch lvs` with DISPLAY scrubbed; parse maps `match
uniquely` to no violations and `do not match` to named
`lvs_net_mismatch` / `lvs_device_mismatch` violations.

Verified against netgen 1.5.316 + sky130A_setup.tcl on
`sky130_fd_sc_hd__inv_2`: extracted layout matches the PDK
schematic; a single-net edit fails with the edited net named.
Netgen exits 0 on match and mismatch alike, so the verdict comes
from parsed output, never the exit code.

Status: EXTRACT-SKY130 GREEN. See `docs/probe-extract-lvs.md`.
Status: LVS-ESCAPE GREEN (net-name inventory tripwire). See
`docs/tickets/LVS-ESCAPE.md`.
There is deliberately no KLayout LVS solver: `sky130.lvs` fails on
the same known-good cell (case bug, evidence in the probe note).
