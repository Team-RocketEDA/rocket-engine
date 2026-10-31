# PROV: B10 full-bundle provisioning — install.sh provisions the whole matrix

*Status: Ready · Depends: none · Size: L ·
Roadmap: B10 release gate (MVP track, unblocks DIGITAL-FLOW
+ TIMING-STA first)*

## Why

B10 in the PRD is one goal with one name: install.sh
provisions EVERY dependency in the tech-stack matrix —
ngspice, Icarus, LibreLane, the oss-cad-suite
distribution, all of it — pinned, version-asserted, and
rendered in the Vivado-style setup menu. There is no
separate "toolchain ticket" vs "B10": this ticket IS B10
as executed. The probes prove the gap (LibreLane,
OpenSTA, OpenROAD absent); the to-GDS closeout is just
the first consumer, so it phases first — but the ticket
stays open until the matrix is fully provisioned.

## What

- RED-first, phased. Phase 1 (current closeout
  workflow): to-GDS toolchain slice — oss-cad-suite pin
  assert on ambient, LibreLane supported-distribution
  install per upstream docs, OpenSTA install, version
  asserts everywhere, loud remedies where install is
  impossible.
- Phase 2 (remainder): every other native pack in
  PRD/tech-stack.md — analog (ngspice pin, Xyce, Xschem,
  CACE, OpenVAF), physical (Magic, Netgen, KLayout
  asserts), HDL (Verilator, Icarus, GHDL, cocotb),
  formal (oss-cad-suite contents), FPGA (nextpnr),
  photonic profiles, EM (Meep, openEMS, Palace, Gmsh),
  thermal (Elmer, DEVSIM) — plus per-profile Python
  locks. setup_catalogue recipes turn real for all of
  it; `provisionable: false` with "no recipe yet" is no
  longer an accepted state for anything in the matrix.
- GTKWave is EXCLUDED from engine provisioning by the
  headless rule (display-side, RocketIDE concern) —
  record the exclusion, never the install.
- Network-flaky safe: installs retry + resume where
  upstream supports it; offline runs degrade to
  version-asserted ambient + loud remedy, never
  fake-green. PDK/deck provisioning stays on its
  existing --pdk-only path.

## Acceptance

- Phase 1: yosys + sby + librelane + opensta working
  with version asserts (or exactly-named remedies);
  DIGITAL-FLOW/TIMING-STA lanes can green on it.
  Ticket stays Ready until Phase 2 lands.
- Full: fresh install.sh yields the whole matrix
  pinned + asserted; B10 gate (installed tests on
  Ubuntu 24.04) green.
- Contract + api_spec regen; full suite + gate green.
