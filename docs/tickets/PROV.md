# PROV: Provision the missing toolchain (LibreLane, OpenSTA, pin asserts)

*Status: Ready · Depends: none · Size: M ·
Roadmap: to-GDS lane (MVP track, unblocks DIGITAL-FLOW
+ TIMING-STA)*

## Why

install.sh provisions the Python env but explicitly not
the toolchain — and the probes prove it: yosys/sby ride
the ambient oss-cad-suite, but LibreLane, OpenSTA, and
OpenROAD are absent, which hard-blocks the RTL→GDS
closeout. Provisioning is a product feature (Vivado-style
setup menu renders it), not a user chore. This ticket
makes install.sh actually provision what the engine
needs, with loud remedies where it cannot.

## What

- RED-first: install.sh gains toolchain modes —
  oss-cad-suite pin assert (version-check ambient,
  refuse on drift with the remedy), LibreLane supported
  distribution install per upstream docs, OpenSTA
  install (standalone or via the LibreLane closure).
- setup_catalogue recipes turn real: every toolchain
  entry gets a working recipe or a loud
  missing_dependency remedy — `provisionable: false`
  with "no recipe yet" is no longer an accepted state
  for MVP-track tools.
- Network-flaky safe: installs retry + resume where the
  upstream supports it; sandbox/offline runs degrade to
  version-asserted ambient + loud remedy, never
  fake-green. PDK/deck provisioning stays on its
  existing --pdk-only path (out of scope here).

## Acceptance

- Fresh `install.sh --install` (or its toolchain mode)
  yields working yosys + sby + librelane + opensta with
  version asserts, or names exactly what's missing and
  how to get it; DIGITAL-FLOW/TIMING-STA lanes can
  green on the result.
- Contract + api_spec regen; full suite + gate green.
