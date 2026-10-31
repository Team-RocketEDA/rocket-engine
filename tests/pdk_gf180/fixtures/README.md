# PDK-GF180 lane fixtures

## inv_pair.py — inverter-class CMOS proof fixture (lane-authored)

No PDK-shipped inverter was usable as a proof fixture:

- The wrapper's standard-cell libraries (`gf180mcu_fd_sc_mcu7t5v0` /
  `gf180mcu_fd_sc_mcu9t5v0`, 249 cells each incl. inverters) are git
  submodules that are **not initialized** in the provisioned source
  (empty dirs; network fetch required), so no stdcell GDS resolves.
- The fixed GDS that *does* ship (`gf180mcu/gds/`: BJTs + efuse) is
  not CMOS-logic shaped.

So the lane builds its own minimal inverter from PDK primitives:

- Devices: `nfet` / `pfet` parametric cells from
  `gf180mcu/cells/fet.py` (upstream, Apache-2.0), `grw=0`.
- Interconnect/taps/n-well: lane-drawn (see the module docstring for
  the single-layer routing rationale).

Upstream source + license: https://github.com/gdsfactory/gf180mcu,
Apache License 2.0 (`LICENSE` at the repo root). No upstream files
are vendored here; the script imports the provisioned package.
