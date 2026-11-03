# Build-local layout (BUILD-LOCAL)

How the engine installs hermetically and what the RocketEDA
super-repo bundle collects. See `docs/tickets/BUILD-LOCAL.md`
for the staged plan; this doc records the landed layout.

## Repo-local defaults (stages 1-2)

A fresh clone writes nothing outside the repo by default.
Every root below is overridable outward by explicit env.

| Root | Default | Override | Owned by |
|---|---|---|---|
| `TOOLS_DIR` | `$ROOT/.tools` | `TOOLS_DIR=~/tools` keeps working for existing users | `scripts/provision_toolchain.sh` |
| `OSS_CAD_SUITE_DIR` | `$TOOLS_DIR/oss-cad-suite` | explicit path wins | provisioner |
| `ROCKETEDA_HOME` | `$ROOT/.stores/rocketeda` | `ROCKETEDA_HOME=~/.local/share/rocketeda` keeps the old store | `scripts/install.sh` |

Stage 1 proved the repo-local install works via env only
(`TOOLS_DIR=$ROOT/.tools`,
`ROCKETEDA_HOME=$ROOT/.stores/rocketeda`) through `--install`
+ `--check-only` + setup probes. Stage 2 flipped the
defaults above. `.tools/` + `.stores/` are git-ignored and
never committed.

Migration: existing `~/tools` bundles keep working via
`TOOLS_DIR=~/tools` (the provisioner asserts the pin, never
the path). Existing `~/.local/share/rocketeda` stores keep
working via `ROCKETEDA_HOME=~/.local/share/rocketeda`.

Known exceptions (writes outside the repo by nature):

- elmer installs via the CSC PPA + apt (system-wide, needs
  sudo). No-sudo hosts get the loud remedy, never a silent
  skip. The Docker recipe bakes it instead.
- the PDK-SKY130GF lane links the pip `sky130` KLayout tech
  into `~/.klayout/tech` (KLayout user-tech convention, not
  an engine path). Documented, not moved.
- `src/interfaces/setup.py::prov_bin_dirs` still falls back
  to `~/tools` when `TOOLS_DIR` is unset (engine-code
  default, outside this lane's files): set `TOOLS_DIR`
  explicitly or keep the provisioner default in sync.

## Install-screen backend (stage 3)

`scripts/provision_toolchain.sh --list-tools` enumerates the
14 installable tools with the per-row prerequisites shown
BEFORE the user ticks (the honest-checkbox rule).
`--only <tool> [--check-only|--install]` scopes assert or
install to exactly one tool. Every check run emits one
`PROV-ROW` TSV line per tool (id, state, version, path,
remedy) for the ENGINE-SETUP menu; palace is unsourced and
emits `unsourced`, never a fake row.

`src/interfaces/setup_catalogue.yaml` mirrors the same tool
list one-to-one: MVP tools (oss-cad-suite bundle, librelane,
opensta, magic, netgen, klayout, ngspice, xyce, xschem,
cace), deferred packs (pymeep, openEMS, elmer, devsim;
`PROV-DEFERRED` owns their line), and the visible-disabled
palace row (`provisionable: false` with the unsourced
reason). No second source of install truth.

## Super-repo bundle layout (stage 4)

The future RocketEDA super-repo (submodules: engine, fuel,
UI) collects from each submodule's install directory with a
`build.sh` (integration-repo owned); DOCKER-DEPLOY consumes
the same layout for the one-container recipe. Engine-side,
`scripts/collect.sh` stages this repo's shippable outputs:

```text
<dest>/
  tools/         copy of TOOLS_DIR (the provisioned install
                 directory: bundle, LibreLane AppImage,
                 source-built prefixes, miniforge env)
  stores/        copy of ROCKETEDA_HOME when present (the
                 registered PDK store); skipped openly when
                 absent, never faked
  manifest.txt   layout version + collection time + tool pins
                 (parsed from the provisioner, single source)
                 + source paths
```

Usage: `scripts/collect.sh --check` verifies the sources and
prints the plan without writing; `scripts/collect.sh --dest
<dir>` stages the layout above. `tools/` is the install
directory the super-repo `build.sh` bundles; `engine/`,
`fuel/`, `ui/dist/` come from their own submodules, not from
this script.
