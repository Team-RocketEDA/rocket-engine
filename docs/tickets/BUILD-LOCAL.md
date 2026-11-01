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
