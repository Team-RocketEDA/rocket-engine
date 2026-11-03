# NGSPICE-LIVE: Live ngspice/netgen proofs where the binaries exist

*Status: Done · Depends: SIM-SKY130, EXTRACT-SKY130 · Size: S · Roadmap: orch-build-mvp*

## Why

Wave 3 proved the parse paths against verbatim recorded output
(ngspice-47 corner log with Vref 1.210323; netgen match/mismatch
reports) and both adapters fail loud without their binaries — but
no ngspice or netgen binary exists in this sandbox (absent from
oss-cad-suite, nix, PATH), so the bandgap DC live test, the RC
live test, and the LVS live paths are implemented yet
skip-guarded, and 3 scenarios fail environmentally. A proof that
has never executed its tool is a promise, not a proof. The demo
machine (or B10 provisioning) must supply both binaries, and this
ticket turns the skips green there.

## What

- Provision ngspice + netgen on the demo/CI machine (B10-owned
  list; record versions).
- Run the skip-guarded live tests with both binaries present:
  bandgap DC Vref in DR-005 [1.176, 1.224], RC divider, LVS
  pass/fail paths — all green, none skipped.
- Scenario gate green on tools PATH with a registered sky130a
  store (ROCKETEDA_HOME) — the 5 environmental failures to zero.

## Acceptance

- Full suite on tools PATH shows the ngspice/LVS live tests
  passing (not skipped); scenarios all-PASS with store + tools.
- Versions + install recipe recorded in the demo runbook.

## Field notes (2026-10-30)

- User machine now has ngspice 42 (`/usr/bin/ngspice`) and real
  LVS Netgen 1.5.326 (`~/tools/bin/netgen`, opencircuitdesign
  source build) — the "no binaries" premise above is stale for
  that machine; the sandbox still lacks them.
- Impostor trap, caught live: the `netgen` apt package is the
  Schoeberl mesh generator (same name). `resolve_netgen()` in
  `src/adapters/lvs_netgen/` now denylists its banner markers;
  promote to a strict allowlist here once the real banner is
  verified in the proof environment.
- The `-help` identity probe prints Tk noise to stderr on the
  real binary but exits fast; re-verify probe choice against the
  installed binary when running the live proofs.

## Closing notes (2026-10-30, tools PATH + live store)

- ngspice/LVS files (`test_ngspice`, `test_extract_sky130`)
  live-green inside a 96 passed / 1 skipped combined run —
  the single skip is the inverted missing-binary test
  (correctly skipping because ngspice IS present). Bandgap
  DC, RC divider, LVS pass/fail paths: all executed, none
  environmentally skipped.
- Scenarios 26/0; gate 4/4 (44/0/0). Versions recorded:
  ngspice-42 (`/usr/bin`, KLU solver), Netgen 1.5.326
  (`~/tools/bin`, opencircuitdesign source build) —
  runbook + provision-plan table.
- Residual (non-blocking): promote the netgen banner
  denylist to a strict allowlist; refresh the runbook's
  unprovisioned-baseline transcript.
