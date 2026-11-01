# PROV: B10 full-bundle provisioning — install.sh provisions the whole matrix

*Status: Ready · Depends: none · Size: L ·
Roadmap: B10 release gate (MVP track, unblocks DIGITAL-FLOW
+ TIMING-STA first)*

## Why

B10 in the PRD is one goal with one name: install.sh
provisions the MVP delivery subset of the tech-stack
matrix (PRD/tech-stack.md) — pinned, version-asserted,
and rendered in the Vivado-style setup menu. The subset
is defined by task `delivery` in
`contracts/v1/catalog/tasks.json`, not by the ticket
author's ambition: post/off-MVP packs live in
PROV-DEFERRED with RED evidence and never block the
MVP bundle claim. There is no separate "toolchain
ticket" vs "B10": this ticket IS B10 as executed. The
probes prove the gap (LibreLane, OpenSTA absent); the
to-GDS closeout is just the first consumer, so it
phases first — but the ticket stays open until the MVP
subset is fully provisioned.

## What

- RED-first, phased. Phase 1 (current closeout
  workflow): to-GDS toolchain slice — oss-cad-suite pin
  assert on ambient, LibreLane supported-distribution
  install per upstream docs, OpenSTA install, version
  asserts everywhere, loud remedies where install is
  impossible.
- Phase 2 (MVP remainder): analog (ngspice pin, Xyce,
  Xschem, CACE), physical (Magic, Netgen, KLayout
  asserts), HDL (Verilator, Icarus, GHDL, cocotb),
  formal (oss-cad-suite contents), MVP photonic
  profiles (sax, circulax, gdsfactory) — plus
  per-profile Python locks. setup_catalogue recipes
  turn real for all of it; `provisionable: false`
  with "no recipe yet" is no longer an accepted
  state for anything in the MVP subset.
- Deferred packs (PROV-DEFERRED, never gating this
  ticket): nextpnr (off_mvp), pymeep, openEMS,
  palace, gmsh (EM), elmer (thermal), devsim
  (device). OpenVAF has no recipe yet — recorded
  openly, not faked, and not MVP-gating.
- GTKWave is EXCLUDED from engine provisioning by the
  headless rule (display-side, RocketIDE concern) —
  record the exclusion, never the install.
- Network-flaky safe: installs retry + resume where
  upstream supports it; offline runs degrade to
  version-asserted ambient + loud remedy, never
  fake-green. PDK/deck provisioning stays on its
  existing --pdk-only path.
- Field note (2026-11-01): offline `uv sync` cannot
  restore the hdl/analog/layout groups in this sandbox
  (cocotb, PySpice, types-pyyaml wheels missing from
  cache) — dev+photonic restored, gate 4/4 green
  without them. Phase 2 must make group provisioning
  cache/network-tolerant (pre-seeded cache or vendored
  wheels) so a fresh host never lands group-less.

## Acceptance

- Phase 1: yosys + sby + librelane + opensta working
  with version asserts (or exactly-named remedies);
  DIGITAL-FLOW/TIMING-STA lanes can green on it.
  Ticket stays Ready until Phase 2 lands.
- Full: fresh install.sh yields the MVP subset
  pinned + asserted; B10 gate (installed tests on
  Ubuntu 24.04) green on the subset. Deferred packs
  report separately, never as MVP missing.
- Verdict split: `--check-only` gains an MVP-subset
  verdict line so B10 reads green while deferred
  packs stay missing (PROV-DEFERRED owns their line).
- Contract + api_spec regen; full suite + gate green.
