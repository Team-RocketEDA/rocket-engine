# Environment split: sandbox vs user host

*Wave-0 record (cleanup plan step 1). Probe: `scripts/probe_wave0.py`
(44 checks; exit 0 = all runnable-here required checks pass).*

Both sites share the filesystem (`~/tools`, PDKs, repo, `.venv`).
They differ in kernel/build powers:

| Capability | Agent sandbox | User host terminal |
|---|---|---|
| EDA binaries (oss-cad-suite incl. eqy/mcy/verilator/ghdl/slang-diag-json, magic, netgen, ngspice, xschem, klayout 0.30.12, ElmerSolver) | yes | yes |
| Venv groups (photonic, layout, hdl, analog) | yes (`UV_CACHE_DIR=/tmp/uv-cache`; host cache copied on flakes) | yes (`install.sh` / `uv sync`) |
| pymeep env (`import meep`; set `MPLCONFIGDIR=/tmp`) | yes | yes |
| PDKs (`~/.local/share/pdk/sky130A/B`) | yes (read) | yes |
| make/gcc/swig source builds | yes | yes |
| LibreLane AppImage runs (needs `/dev/fuse`) | NO | yes |
| bwrap/userns sandbox tests | NO | yes |
| `~/tools` writes | NO | yes |

## Standing assignments

- Fixture-recording LibreLane runs (DIGITAL-FLOW-URANIUM, DEMO-PATH):
  user host. Agents write the run scripts; user executes; agents
  consume the recorded run dirs.
- Provision builds + `--install` verification (PROV-UPSTREAM-RECIPE,
  trio unparking): user host.
- Sandbox/console tests (BWRAP-STUDY evidence, CONSOLE-LIFECYCLE
  sandbox paths): user host.
- Everything else (code, unit/integration tests, adapter runs against
  present binaries): either site; probe-green here is sufficient.

## Wave-0 pins (all in `uv.lock`)

sax, circulax, meow-sim, gdsfactory (+kfactory transitive), pyslang,
pywellen, vlsirtools 7.0.0, amaranth, cace 2.13.0, devsim 2.11.2.
cace/devsim moved from provision-script pip installs into the
`analog` group (`==` pins matching `provision_toolchain.sh`) so
`uv sync` no longer prunes them; the provision pip lines are now
redundant-but-harmless (same versions).
