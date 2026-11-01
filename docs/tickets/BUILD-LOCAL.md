# BUILD-LOCAL: repo-local toolchain + super-repo build plan

*Status: Ready · Depends: PROV · Size: M ·
Roadmap: B10 follow-through (no-pollution default, RocketEDA bundle)*

## Why

Today the toolchain installs to `~/tools` and the PDK store to
`~/.local/share/rocketeda` — outside the repo, polluting the
machine by default. The future is a RocketEDA super-repo
(submodules: rocket-engine, rocket-fuel, UI) whose build script
collects and bundles everything from the install directory, plus
a Docker recipe. That future needs the engine install to be
hermetic-by-default: every write lands inside the repo (or the
super-repo build root), overridable outward only by explicit
env. This ticket is the staged path from today's `$HOME`
defaults to that world. It also turns the provisioner's
per-tool `install_<tool>` functions into the backend for the
Vivado-style modular install screen (ENGINE-SETUP).

## What

- Stage 1 (prove, no default change): verify a fully repo-local
  install works today via env only —
  `TOOLS_DIR=$ROOT/.tools`,
  `ROCKETEDA_HOME=$ROOT/.stores/rocketeda` — through
  `--install` + `--check-only` + setup probes; add
  `.tools/` + `.stores/` to .gitignore; document the
  layout. Elmer stays the known exception (sudo apt is
  system-wide by nature — loud remedy, Docker bakes it).
- Stage 2 (flip the default): provisioner `TOOLS_DIR`
  defaults to `$ROOT/.tools`; engine `ROCKETEDA_HOME`
  defaults to `$ROOT/.stores/rocketeda`. Explicit env
  still wins. Migration note for existing `~/tools`
  users (live bundles keep working via
  `TOOLS_DIR=~/tools`). All prov/setup tests go through
  the new default hermetically.
- Stage 3 (install-screen backend): provisioner gains
  `--only <tool>` + `--list-tools` and a machine-readable
  verdict (one line per tool: id, state, version, path,
  remedy), so ENGINE-SETUP can drive per-tool install /
  status without parsing prose. setup_catalogue mirrors
  the tool list; no second source of install truth.
  Per-row provision prerequisites (shown BEFORE the user
  ticks — the honest-checkbox rule):
  - oss-cad-suite: network + ~1GB disk; fetch tarball.
  - librelane: network + ~2GB disk; fetch AppImage.
  - opensta: network + build prereqs (git cmake make g++
    swig bison flex tcl eigen) + ~30min build.
  - magic/netgen/xschem: network + build prereqs (git
    make gcc tclsh wish) + ~10min builds each.
  - klayout: network + dpkg-deb; host Qt runtime libs
    (banner check proves liveness, else remedy toward
    apt).
  - ngspice: network + build prereqs (make gcc bison
    flex) + ~15min build.
  - xyce: network + heavy build prereqs (cmake g++
    gfortran ...) + Trilinos first: HOURS. Warn loudly.
  - cace/devsim: uv + engine venv + network; pip into
    the venv (lockfile update rides a lane commit).
  - pymeep: network + ~3GB disk; miniforge bootstrap
    once, then conda-forge env. A user conda override
    skips the bootstrap (assert-only path).
  - openems: network + build prereqs (cmake hdf5 vtk
    boost fparser tinyxml) + CSXCAD first: LONG.
  - elmer: sudo + network (apt PPA). No-sudo hosts get
    the remedy, never a silent skip.
  - palace: NO ROW ACTION (unsourced) — visible,
    disabled, with the reason.
  - bwrap: usually ambient; else apt (document, no
    provisioner build).
- Stage 3b (PATH flag backend — DONE): `--print-path`
  emits the marker-guarded block
  (`# >>> rocketeda toolchain >>>` ... `export PATH=...`
  ... `# <<< rocketeda toolchain <<<`) listing only
  existing provisioned bin dirs (AppImage dir excluded:
  no binaries). The installer flag appends this block to
  the shell rc ONCE (marker check first); the engine
  never edits the shell itself. Re-run after
  provisioning more tools.
- Stage 4 (super-repo build contract, RocketEDA repo):
  define the bundle layout (`engine/`, `fuel/`,
  `ui/dist/`, `tools/`, `stores/`) and a `build.sh` that
  collects from each submodule's install directory;
  DOCKER-DEPLOY consumes the same layout for the
  one-container judging recipe. Engine-side work here is
  only the layout doc + a `scripts/collect.sh` that
  stages the engine's shippable outputs.

## Out of scope

- The actual RocketEDA super-repo + submodules (owner:
  integration repo, not this one).
- The Docker image build (DOCKER-DEPLOY).
- The install-screen UI itself (ENGINE-SETUP consumes
  stage 3; RocketIDE renders it).

## Acceptance

- Fresh clone + `scripts/install.sh --install` writes
  nothing outside the repo except via explicit env, and
  `--check-only` is green-or-loud-remedy from the
  repo-local root.
- `provision_toolchain.sh --only klayout --install`
  provisions exactly one tool; `--list-tools` enumerates
  the matrix for the setup menu.
- Super-repo layout doc exists and names every collected
  path.
