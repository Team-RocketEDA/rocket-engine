# Provision Sources: where every matrix tool comes from

*Generated: 2026-11-01 | Method: /deep-research, official docs first |
Rule: no bespoke installs — every recipe below follows the
upstream-documented method, pinned. install.sh encodes this
file; this file cites the docs.*

## Bundle rule

One pinned oss-cad-suite tarball covers the whole digital
frontend. Everything else follows its own upstream docs.
The engine bundles what the matrix needs and uses what it
needs; display-side tools ride along but are never engine
deps.

## 1. oss-cad-suite (digital frontend bundle)

- Source: https://github.com/YosysHQ/oss-cad-suite-build/releases
- Method (documented): download the pinned dated tarball,
  extract, `source environment` (or prepend `bin/` to PATH).
  URL scheme:
  `.../releases/download/<TAG>/oss-cad-suite-linux-x64-<STAMP>.tgz`
  (e.g. tag `2026-10-02`, stamp `20261002).
- Covers from the matrix: yosys (+abc), sby, nextpnr-*
  (ice40/ecp5/generic/machxo2/nexus/himbaechel), iverilog
  + vvp, verilator, ghdl, slang, eqy, mcy, SMT solvers
  (z3, boolector, bitwuzla, yices, cvc4, cvc5), cocotb.
  Also ships gtkwave/surfer — display-side, ignored by
  the engine per the headless rule.
- Evidence: local 20261025 enumerated, 155 binaries.
  Authoritative: repo `default/rules/` lists exactly
  cocotb, eqy, formal, ghdl, iverilog, nextpnr,
  programmers, pyhdl, python, resources, solvers,
  utils, verilator, waveformviewers, yosys.
- Explicitly NOT in the suite (verified three ways:
  local enumeration, rules manifest, third-party
  build plan): **opensta, openroad, magic, netgen,
  klayout**. Any claim otherwise refers to a different
  bundle or an unreleased nightly — re-verify before
  trusting.
- install.sh: `--toolchain` fetches the pinned tarball
  (pin in provision_toolchain.sh), asserts versions of
  yosys/sby/iverilog/verilator/ghdl/nextpnr, exports
  the bin dir via prov-phase1.env.

## 2. OpenSTA (standalone STA)

- Source: https://github.com/parallaxsw/OpenSTA (official;
  The-OpenROAD-Project fork is a mirror). Docs:
  https://opensta.readthedocs.io/
- Method (documented, README "Build from source"):
  `git clone`, `mkdir build`, `cmake ..` (with
  `-DCMAKE_INSTALL_PREFIX=<tools>`), `make`, `make install`.
  Deps: cmake, gcc, tcl8.6, swig, bison, flex, eigen3,
  cudd 3.0.0 (required), zlib/tclreadline optional.
- License flag: **GPLv3** (Parallax dual-license). Relevant
  to the pending MIT-vs-GPL decision — record, don't solve.
- install.sh: source-build recipe with the dep table
  asserted up front; `sta` version-asserted after install.
- Pinned (single source: `scripts/provision_toolchain.sh`):
  OpenSTA `857316ff001b2a8dbbdc5996944d08a6d38c87ab`
  (short `857316f`), CUDD `3.0.0`. Parity: the LibreLane
  `tool_versions.txt` (release 3.0.17, verified 2026-11-03)
  names the same OpenSTA revision. Recipe cross-checked
  against the live OpenSTA README ("Build from source") at
  provision time.

## 3. LibreLane (RTL-to-GDS flow driver)

- Source: https://github.com/librelane/librelane (successor
  to OpenLane). Docs: https://librelane.readthedocs.io/
- Methods (documented, README Installation):
  1. **Nix (recommended)**: flake pins nix-eda 6.11.0
     (the real tool closure: openroad, opensta, magic,
     yosys, klayout, …) + ciel (PDK manager, `~/.ciel`
     root) + custom openroad/opensta/magic builds.
  2. Docker (works incl. Windows; `--dockerized` flag).
  3. `pip install librelane` = **Python-only, bring your
     own compiled utilities, explicitly unsupported**.
     The PyPI package is flow infrastructure, NOT tools.
- CLI shape: `python3 -m librelane --pdk-root <root>
  <config>`, e.g. `--pdk-root $HOME/.ciel`.
- install.sh strategy (DECIDED: AppImage route — the
  script is the truth, this doc follows it): fetch the
  pinned `librelane-devshell-x86_64.AppImage` +
  `tool_versions.txt` from the GitHub release into the
  app-owned tools dir; assert via LIBRELANE_PIN plus
  `librelane --version` inside the devshell. Rationale:
  the AppImage is a self-contained devshell (full tool
  closure in one file, no root, no clone); the Nix
  route needs the determinate installer (sudo) plus an
  interactive nix-shell, which is hostile to headless
  engine subprocess invocation. Nix stays a documented
  alternate for users who already run it. pip route
  rejected unless the full closure is provisioned
  separately (that just rebuilds nix-eda by hand).
  PDK side: ciel (`~/.ciel`) volumes, see PDK
  section.

## 4. OpenROAD (place & route)

- Primary route: the LibreLane nix-eda closure above
  (openroad 2.x w/ llvm18 per the flake) — no separate
  install when LibreLane is provisioned.
- Standalone alternative (documented upstream, not yet
  verified here): OpenROAD-flow-scripts or the OpenROAD
  CMake superbuild. Confidence: medium — confirm from
  The-OpenROAD-Project docs before encoding.

## 5. Magic + Netgen (extraction, LVS)

- Source: https://github.com/RTimothyEdwards/magic (+
  netgen sibling), docs http://opencircuitdesign.com/magic/
  (Download/Compile/Install pages).
- Method (documented): `git clone`, `./configure
  --prefix=<tools>` (+ `--enable-cairo-offscreen` for
  headless), `make -j$(nproc)`, `make install`. Needs
  Tcl/Tk + X11 + cairo dev libs. Netgen follows the same
  autotools pattern from the same author.
- install.sh: source-build recipe; apt `magic` rejected
  (stale) per project guideline.

## 6. KLayout (batch DRC, layout API)

- Source: https://www.klayout.de/build.html (official
  builds), `pip install klayout` wheel for the Python API.
- Method: pip wheel primary for engine use (batch DRC
  via `klayout.db` needs no desktop); desktop build or
  `apt install klayout` where a `klayout` binary is
  required. Pin the wheel version in the lock.
- install.sh: pip route into the layout group + binary
  probe with remedy.

## 7. ngspice (SPICE)

- Source: https://ngspice.sourceforge.io/download.html,
  INSTALL file + manual ch. 32 (compile), git mirror
  github.com/ngspice/ngspice.
- Method (documented): source tarball (`ngspice-*.tar.gz`)
  + `./configure`, `make`, `make install` (needs bison,
  flex, X11 dev); or distro package where fresh enough.
  No Linux binaries from upstream.
- install.sh: prefer source build pinned to a rework
  release (≥42); accept distro ngspice only if the
  version assert passes, else remedy.

## 8. Xyce (parallel SPICE)

- Source: https://xyce.sandia.gov/ (building guide),
  github.com/Xyce/Xyce.
- Method (documented): build Trilinos from source first
  (required, version-matched), then Xyce via autotools
  (primary) or CMake (INSTALL.md). Binary installers
  exist for Windows/Mac/RedHat only — Ubuntu builds
  from source. Heavy; MPI optional for parallel.
  GitHub checkouts lack ./configure: run ./bootstrap
  first (needs autoconf+automake+libtool) — verbatim
  building guide. ShyLU is Parallel-Xyce-only; our
  serial build omits it (Trilinos 17 breaks otherwise).
  gtest TPL off (TriBITS' own documented escape).
- install.sh: source-build recipe, long-timeout lane;
  serial-first, MPI as an option.
- Pinned (single source: `scripts/provision_toolchain.sh`):
  Xyce `Release-7.10.0` (https://github.com/Xyce/Xyce),
  Trilinos `trilinos-release-17-2-1`
  (https://github.com/trilinos/Trilinos). Recipe
  cross-checked against the live Xyce building guide
  (https://xyce.sandia.gov/) at provision time: Trilinos
  first (serial, MPI OFF, ShyLU OFF, gtest TPL OFF), then
  `./bootstrap` for GitHub checkouts, then the Xyce
  autotools build against the Trilinos prefix.

## 9. Xschem + CACE (schematic, characterization)

- Xschem: https://github.com/StefanSchippers/xschem —
  `git clone`, `./configure`, `make`, `make install`
  (X11 + Tcl-Tk). Manual documents the same.
- CACE: https://github.com/efabless/cace — Nix or
  Python-only (`pip install cace`, bring your own
  xschem/magic/netgen/ngspice). Same shape as LibreLane.
- install.sh: xschem source build; CACE via pip once
  its tool deps are provisioned (or Nix, shared with
  the LibreLane decision).

## 10. Meep (FDTD)

- Source: https://meep.readthedocs.io/en/latest/Installation/
- Method (documented): **conda-forge `pymeep` is the
  maintained route** (`conda create -n mp -c conda-forge
  pymeep`). `apt install python3-meep` is stale (1.3, no
  Python interface) — rejected. Source build documented
  but heavy (autotools + MPI + HDF5 + SWIG).
- install.sh: miniforge bootstrap + pinned pymeep env,
  or document the conda prerequisite loudly. No apt
  fallback (known-broken for our use).

## 11. openEMS (EC-FDTD)

- Source: https://docs.openEMS.de/ (python/install),
  github.com/thliebig/openEMS + CSXCAD.
- Method (documented): build CSXCAD C++ + Python ext
  first, then openEMS C++ + Python ext. Upstream
  Debian/Ubuntu minimum, verbatim: build-essential
  cmake git libhdf5-dev libboost-all-dev
  libtinyxml-dev zlib1g-dev. Proven extras on this
  host: libfparser-dev + libcgal-dev (both demanded
  by actual CSXCAD configure errors). VTK/Qt are
  AppCSXCAD-GUI-only — headless build skips them.
  An `apt install openems` exists on Ubuntu (medium
  confidence, version unknown — verify before
  trusting).
- install.sh: source-build recipe per the manual;
  probe apt as a fast path only if version-asserted.
- Pinned (single source: `scripts/provision_toolchain.sh`):
  openEMS `v0.37.0` (https://github.com/thliebig/openEMS),
  CSXCAD `v0.7.0` (https://github.com/thliebig/CSXCAD).
  Recipe cross-checked against https://docs.openEMS.de/
  (python/install) at provision time: CSXCAD C++/Python
  ext first, then the openEMS C++/Python ext against the
  CSXCAD prefix.

## 12. Palace (full-wave FEM)

- Status: **not yet sourced** — no fetch performed.
  Upstream is awslabs Palace with a documented
  superbuild. Action: fetch awslabs.github.io/palace
  install docs before encoding. Do not guess.

## 13. Elmer (thermal/FEM)

- Route: `apt install elmerfem-csc` via the CSC PPA on
  Ubuntu (one 2026-08 Ubuntu 24.04 report; gdsfactory
  gplugins assumes ElmerSolver/ElmerGrid on PATH).
  Confidence: medium — confirm against elmerfem.org
  docs before encoding.

## 14. DEVSIM (TCAD)

- Route: `pip install devsim` (binary wheels; also a
  gdsfactory gplugins target). Confidence: medium-high
  (PyPI-published, widely used) — confirm version pin
  from pypi.org/project/devsim before encoding.

## Engine path pointing

Provisioned tools land under one tools root; engine
resolution order stays: explicit job `tool_dir` →
provisioned root (sourced from `prov-phase1.env`) →
ambient PATH (version-asserted, warns on drift) →
loud `missing_dependency` naming the PROV remedy.
setup_catalogue recipes mirror this file one-to-one;
any recipe without a section here is a lie.

## Correction log

- 2026-11-01: opensta is NOT in oss-cad-suite 20261025
  (local enumeration 155 binaries + upstream rules
  manifest + third-party build plan agree). STANDALONE
  build required (§2).
- 2026-11-01: `pip install librelane` is flow infra
  only (README: "bring your own compiled utilities,
  unsupported"). NIX closure is the documented route (§3).
- 2026-11-01: local hunt found no librelane/opensta/
  openroad/nix installs (PATH, /usr/local, /opt,
  dpkg, pip). If they exist elsewhere on the dev
  machine, point PROV at them instead of reinstalling.
