# PROV phase 1 report — to-GDS toolchain slice

Lane: PROV (phase 1 only). Ticket: `docs/tickets/PROV.md`.
Branch: GREEN-the-tests. Date: 2026-10-31.

## Scope

Phase 1 (this lane): oss-cad-suite pin assert on ambient, LibreLane
supported-distribution install per upstream docs, OpenSTA install,
version asserts everywhere, loud remedies where install is
impossible. Delivered as new files plus `wiring.patch` (tracked
files untouched by this lane).

Phase 2 (rest of the PRD/tech-stack matrix — analog, physical,
HDL, formal extras, FPGA, photonic profiles, EM, thermal, plus
per-profile Python locks) is out of scope for this lane. The
ticket stays open until Phase 2 lands.

## Pins (single source: `scripts/provision_toolchain.sh`)

- oss-cad-suite `20261025` (tag `2026-10-25`): ambient
  `VERSION` inspected; tarball URL pattern confirmed against
  upstream release conventions.
- yosys banner `Yosys 0.70*`: ambient `yosys -V` reports
  `Yosys 0.70+219 (git sha1 5053d0e26, ...)`.
- sby banner `SBY v0.70*`: ambient `sby --version` reports
  `SBY v0.70-9-g79fc9ed`.
- LibreLane `3.0.17` (commit
  `64ef80802d3d189b476636d2a6b17888c03304ee`): latest stable
  tag on the upstream releases page; AppImage asset name per
  the upstream install docs.
- OpenSTA (short `857316f`, full hash
  `857316ff001b2a8dbbdc5996944d08a6d38c87ab`): commit verified
  upstream; same STA revision the LibreLane closure documents
  in `tool_versions.txt`.
- CUDD (OpenSTA dep) `3.0.0`: OpenSTA README prerequisites.

Upstream methods (standing rule — most-correct per tool docs;
full URLs also in `scripts/provision_toolchain.sh`):
- oss-cad-suite pinned tarball (YosysHQ oss-cad-suite-build
  releases page).
- LibreLane AppImage install docs (librelane.readthedocs.io,
  stable/installation/appimage_installation/
  installation_linux.html); Nix alternate under
  stable/installation/nix_installation/.
- OpenSTA CMake source build (The-OpenROAD-Project/OpenSTA
  README, "Build from source").

GTKWave is EXCLUDED from engine provisioning by the headless rule
(display-side, RocketIDE concern) — recorded in the provisioner,
the catalogue patch, and here; never installed.

## Files shipped (new, untracked)

- `scripts/provision_toolchain.sh` — the provisioner. `--check-only`
  asserts ambient (no writes, no network); `--install` installs
  what is missing (retry + resume, one fast network preflight so
  air-gapped runs degrade at once) then re-asserts. Exit 0 with
  `PROV-PHASE1: OK (4/4 ...)` only when yosys + sby + librelane +
  opensta all assert; otherwise exit 1 with `PROV-PHASE1:
  DEGRADED` plus `REMEDY <tool>: <cause>. next: <fix>. see:
  <url>` lines. Writes `$TOOLS_DIR/prov-phase1.env` on
  install/OK as the consumer contract (DIGITAL-FLOW/TIMING-STA
  source it for `OSS_CAD_SUITE_DIR`, `LIBRELANE_APPIMAGE`,
  `OPENSTA_PREFIX`). Honors `TOOLS_DIR`, `OSS_CAD_SUITE_DIR`,
  `PROV_OFFLINE=1`.
- `tests/test_prov_toolchain.py` — hermetic suite: stub-PATH
  OK/mismatch/missing matrices, offline + unreachable-network
  degradation (never fake-green), check-only purity (no writes),
  upstream-doc cites, retry/resume pins, GTKWave exclusion, live
  verdict smoke, report + patch guards.
- `tests/installed/test_toolchain_pins.py` — B10 gate suite: real
  host version asserts, pins parsed from the provisioner (no
  drift). Absent tool: loud skip on dev (names remedy + gate
  command), hard fail with `PROV_GATE=1`. Wrong version always
  fails.
- `docs/work/PROV/wiring.patch` — the exact patch (below).
- `docs/work/PROV/report.md` — this file.

## Honest verification log (sandbox, 2026-10-31)

- RED: 23 failed before the provisioner existed (provisioner +
  report + patch absent).
- GREEN after implementation: 22 passed, 2 skipped
  (`tests/test_prov_toolchain.py` 18 passed;
  `tests/installed/test_toolchain_pins.py` 4 passed + 2 loud
  skips for absent librelane/opensta, each naming its remedy).
- Live `provision_toolchain.sh --check-only`: bundle `20261025`
  + yosys + sby asserted; librelane/opensta `REMEDY` lines;
  `PROV-PHASE1: DEGRADED (missing: librelane opensta)`, exit 1.
- Installed vs remedied: oss-cad-suite/yosys/sby INSTALLED
  (ambient, version-asserted). LibreLane + OpenSTA REMEDIED, not
  installed: the sandbox proxy is throttled (~42 B/s observed)
  and 502s some hosts, so multi-GB downloads and full git
  clones are infeasible here (nix absent too; docker present
  but cannot pull usefully). The install paths are
  code-reviewed, timeout-guarded, and fail loud; the first
  networked `--install` run is the live proof (gate host).
- Byte-verified through the proxy (1-byte range probes +
  716-byte `tool_versions.txt` from release `3.0.17`): the
  AppImage URL, the oss-cad-suite tarball URL, and the release
  asset all exist; the downloaded `tool_versions.txt` names
  `opensta ... 857316ff001b2a8dbbdc5996944d08a6d38c87ab`,
  exactly this lane's `OPENSTA_PIN`. The commit page for that
  SHA also resolves upstream.
- Install-path caveats (open, stated): non-interactive
  `librelane --smoke-test` inside the AppImage is NOT asserted
  (upstream documents interactive entry); DIGITAL-FLOW owns the
  flow-level proof. `sta -version` with `--version` fallback
  covers the version probe; the pin file is the authoritative
  assert. `git checkout` has a `git fetch origin <sha>`
  fallback for detached pins.
- Patch verification (scratch tree at `/tmp/prov-verify`, HEAD +
  new files + patch): `git apply --check` clean; patched
  `install.sh --check-only` exits 0 with the provisioner verdict
  appended; patched catalogue loads, validates, covers all
  install.sh probes, and keeps existing setup-test invariants
  (fresh-machine states, magic-flip isolation); `bash -n` clean.

## Integrator steps

1. `git apply --check docs/work/PROV/wiring.patch` (must be clean).
2. `git apply docs/work/PROV/wiring.patch` (touches ONLY
   `scripts/install.sh` + `src/interfaces/setup_catalogue.yaml`).
3. `bash scripts/install.sh --check-only` — expect exit 0 with
   the `PROV-PHASE1:` verdict appended (DEGRADED + remedies in
   sandbox is correct, not a failure).
4. `.venv/bin/python -m pytest tests/test_prov_toolchain.py
   tests/installed/test_toolchain_pins.py tests/interfaces/test_setup.py
   tests/test_demo_path.py -q` — all green (2 loud skips in
   sandbox).
5. `scripts/install.sh --install` on a networked Ubuntu 24.04
   host, then `PROV_GATE=1 .venv/bin/python -m pytest
   tests/installed -q` — the B10 gate proof (expect 4/4 OK).
6. Consumer lanes (DIGITAL-FLOW/TIMING-STA): source
   `$TOOLS_DIR/prov-phase1.env`; missing distribution/binary
   must surface `missing_dependency` with the catalogue remedy.

## Exact patch

`docs/work/PROV/wiring.patch` (89 lines). HEAD-hook design note:
the install.sh hook is deliberately non-fatal (venv/PDK bootstrap
never breaks on toolchain state); enforcement lives in the loud
verdict + `tests/installed` (strict under `PROV_GATE=1`). A
`--strict` fatal mode is Phase-2 material, not added here.
Sandbox fast path: `PROV_OFFLINE=1 scripts/install.sh --install`
skips the network preflight.
