# Demo runbook: one-command engine proof

DEMO-PATH deliverable. Provisions, proves, and reports the engine on
the demo machine in a single command. Expected output below was
recorded from a fresh-shell run on 2026-10-30 (see Transcript).

## Machine

- Host: demo machine (x86-64, Ubuntu/Pop!_OS 24.04, Python 3.12, uv)
- Toolchain: `$HOME/tools/oss-cad-suite/bin` on PATH + ambient
  magic, KLayout, bwrap. Recorded versions:
  - magic 8.3.685, KLayout 0.28.16, bwrap 0.11.0
  - Icarus Verilog 14.0 (devel s20260301), Verilator 5.053 devel,
    slang 12.0.0, Yosys 0.70+219, GHDL 7.0.0-dev, SBY v0.70-9
- PDK source: `$HOME/.local/share/pdk/sky130A` (open_pdks build
  `5f09001e4b975ba35d27d99a10ecdf45054a9bd5` = `commit.open_pdks`
  in its `.config/nodeinfo.json`; 15007 files adopted)
- Engine store: `/tmp/rocketeda-demo` (the default
  `~/.local/share/rocketeda` works too — export `ROCKETEDA_HOME`
  only to override)
- NOT on this machine (no network to provision): ngspice, netgen,
  sax — owned by NGSPICE-LIVE; every blocked item below names them

## The single command

From a fresh shell in `rocket-engine/`:

```sh
export PATH="$HOME/tools/oss-cad-suite/bin:$HOME/tools/bin:$PATH"
export ROCKETEDA_HOME=/tmp/rocketeda-demo
scripts/demo.sh
```

(`$HOME/tools/bin` carries user-built tools such as the
opencircuitdesign netgen; harmless when absent.)

This runs four stages — install (venv + locked sync + engine +
PDK register + tool probe), fetch (fixture license gate),
scenarios (all MVP flows), gate (correctness report) — and exits 0
iff all four pass.

Offline note: the transcript below was recorded in an offline
sandbox, so the proof shell also exported
`UV_CACHE_DIR=/tmp/uv-cache UV_OFFLINE=1` (provisioning from a
warm cache copy; no PyPI route). On a networked machine omit those
two variables. The bwrap probe line below (`No permissions to create a
new namespace`) is a sandbox artifact too — presence is still
detected correctly.

## Expected output

Note (2026-10-30, post-transcript): ngspice-42 and Netgen 1.5.326
have since been provisioned on the demo machine, so a fresh run
executes the analog/mixed/LVS paths live instead of blocking.
The transcript below is the unprovisioned baseline; NGSPICE-LIVE
owns the re-proof. Until then, expect MORE live results, never
fewer — anything newly failing is a real bug, not a gap.

Stages install and fetch PASS. Scenarios and gate report the
env-blocked items honestly (cause + next step, no tracebacks):

- digital: PASS (serv + picorv32 good, all mutants caught, icarus)
- analog: FAIL:blocked-env (ngspice not on PATH → NGSPICE-LIVE)
- photonic: FAIL:blocked-env (optical side needs sax → B10-owned
  tooling; layout side passes live on KLayout + cspdk MZI)
- mixed: FAIL:blocked-env (sdm_rx digital side passes on icarus;
  sd_top needs ngspice → NGSPICE-LIVE)
- layout: magic DRC + KLayout DRC + sky130A KLayout DRC pass live;
  LVS needs netgen (→ NGSPICE-LIVE)

Overall exit code: 1 until NGSPICE-LIVE provisions ngspice, netgen,
and sax — that is the recorded expectation, not a failure of the
procedure: every line below either passed or names its cause and
next step.

## Transcript

Recorded 2026-10-30, fresh shell (`env -i` + login PATH), exit 1:

```text
================================================================
demo stage: install
================================================================
==> venv + locked sync
Using CPython 3.12.14
Creating virtual environment at: .venv
Activate with: source .venv/bin/activate
Resolved 190 packages in 1ms
warning: Failed to hardlink files; falling back to full copy. This may lead to degraded performance.
         If the cache and target directories are on different filesystems, hardlinking may not be supported.
         If this is intentional, set `export UV_LINK_MODE=copy` or use `--link-mode=copy` to suppress this warning.
Installed 42 packages in 164ms
 + annotated-doc==0.0.5
 + annotated-types==0.8.0
 + anyio==4.15.1
 + attrs==26.1.0
 + certifi==2026.10.23
 + cffi==2.1.1
 + click==8.5.0
 + coverage==7.17.0
 + cryptography==50.0.2
 + fastapi==0.162.0
 + h11==0.16.0
 + httpcore==1.0.9
 + httpcore2==2.16.0
 + httpx==0.28.1
 + httpx2==2.16.0
 + idna==3.20
 + iniconfig==2.3.1
 + jsonschema==4.26.0
 + jsonschema-specifications==2025.9.1
 + mcp==2.3.0
 + mcp-types==2.3.0
 + opentelemetry-api==1.45.1
 + packaging==26.3
 + pluggy==1.7.0
 + pycparser==3.12
 + pydantic==2.13.5
 + pydantic-core==2.46.5
 + pygments==2.21.0
 + pyjwt==2.15.1
 + pytest==9.2.0
 + pytest-cov==7.1.0
 + python-multipart==0.0.32
 + referencing==0.37.0
 + rocket-engine==0.0.1 (from file:///home/alrida-ismail/github/rocketEDA/rocket-engine)
 + rpds-py==2026.9.1
 + ruamel-yaml==0.19.1
 + sse-starlette==3.6.0
 + starlette==1.10.0
 + truststore==0.10.5
 + typing-extensions==4.16.0
 + typing-inspection==0.4.4
 + uvicorn==0.54.0
==> engine import check
ok
==> PDK register
pdk sky130a@5f09001e4b975ba35d27d99a10ecdf45054a9bd5: already registered, reverified (15007 files, /tmp/rocketeda-demo/pdks/sky130a/5f09001e4b975ba35d27d99a10ecdf45054a9bd5)
==> tool capability probe (engine = batch-capable only)
TOOL       STATE     VERSION
bwrap      present   No permissions to create a new namespace [/home/alrida-ismail/tools/oss-cad-suite/bin/bwrap]
magic      present   8.3.685 [/usr/local/bin/magic]
klayout    present   KLayout 0.28.16 [/usr/bin/klayout]
iverilog   present   Icarus Verilog version 14.0 (devel) (s20260301-670-g2b8d42dc0-dirty) [/home/alrida-ismail/tools/oss-cad-suite/bin/iverilog]
vvp        present   Icarus Verilog runtime version 14.0 (devel) (s20260301-670-g2b8d42dc0-di [/home/alrida-ismail/tools/oss-cad-suite/bin/vvp]
verilator  present   Verilator 5.053 devel rev v5.052-586-g1838b6ed0 (mod) [/home/alrida-ismail/tools/oss-cad-suite/bin/verilator]
slang      present   slang version 12.0.0+545f88b2e [/home/alrida-ismail/tools/oss-cad-suite/bin/slang]
yosys      present   Yosys 0.70+219 (git sha1 5053d0e26, Release, Clang /usr/bin/clang++ 21.1 [/home/alrida-ismail/tools/oss-cad-suite/bin/yosys]
ghdl       present   GHDL 7.0.0-dev (6.0.0.r554.ga977191e7.dirty) [Dunoon edition] [/home/alrida-ismail/tools/oss-cad-suite/bin/ghdl]
sby        present   SBY v0.70-9-g79fc9ed [/home/alrida-ismail/tools/oss-cad-suite/bin/sby]
ngspice    absent    -
netgen     absent    -
pins: B10-owned (tests/installed asserts them when B10 lands).
demo stage install: PASS
================================================================
demo stage: fetch
================================================================
demo stage fetch: PASS
================================================================
demo stage: scenarios
================================================================
PASS drc fake-adapter fail path
PASS drc live fail on known-bad cell
PASS drc live klayout fail on known-bad cell
PASS drc live klayout pass on known-good cell
PASS drc live pass on known-good cell
PASS drc sky130 fail on known-bad cell
PASS drc sky130 pass on known-good cell
PASS hdl live fail on known-bad bench
PASS hdl live pass on known-good bench
PASS sdm_rx live fail on truncation mutant
PASS sdm_rx live pass on documented registers + PEX vector
PASS klayout mzi fail on sliver mutant
PASS klayout mzi pass on cspdk reference GDS
FAIL lvs sky130 fail on mismatched netlist
  - step 2 (run_live): netgen not on PATH (see docs/tickets/NGSPICE-LIVE.md)
FAIL lvs sky130 pass on known-good cell
  - step 2 (run_live): netgen not on PATH (see docs/tickets/NGSPICE-LIVE.md)
FAIL ngspice bandgap fail on sizing mutant
  - step 2 (run_live): ngspice not on PATH
FAIL ngspice bandgap pass on recorded snapshot netlist
  - step 2 (run_live): ngspice not on PATH
FAIL ngspice sd_top fail on sizing mutant
  - step 2 (run_live): ngspice not on PATH (see docs/tickets/NGSPICE-LIVE.md)
FAIL ngspice sd_top pass on PEX integrator DC
  - step 2 (run_live): ngspice not on PATH (see docs/tickets/NGSPICE-LIVE.md)
PASS picorv32 live fail on truncation mutant
PASS picorv32 live pass on vendor test_ez
FAIL sax mzi fail on geometry mutant
  - step 2 (run_live): sax not installed, uv sync (B10-owned tooling)
FAIL sax mzi pass on balanced circuit
  - step 2 (run_live): sax not installed, uv sync (B10-owned tooling)
PASS serv live fail on truncation mutant
PASS serv live pass on hello firmware
PASS stale revision rejected without effects
18 passed, 8 failed
demo stage scenarios: FAIL
next: each FAIL line above names its cause; env-blocked items cite their ticket
================================================================
demo stage: gate
================================================================
GATE FAIL: 1/4 flows green (28 pass, 0 fail, 16 quarantined)
  analog: FAIL:blocked-env
  digital: PASS
  mixed: FAIL:blocked-env
  photonic: FAIL:blocked-env
report: /home/alrida-ismail/github/rocketEDA/rocket-engine/tmp/correctness/report.json
demo stage gate: FAIL
next: open tmp/correctness/report.md: quarantines cite refs, failures link artifacts
================================================================
demo: 2 passed, 2 failed (install/fetch/scenarios/gate)
demo: FAIL — see docs/demo-runbook.md for the expected transcript
```

## Known-failure modes (cause → next step)

| Symptom | Cause | Next step |
|---|---|---|
| `uv not on PATH` | uv missing | install uv, retry install stage |
| `PDK source is not a directory` | PDK_SOURCE wrong | set PDK_SOURCE to the sky130A tree |
| `no engine interpreter` | venv step failed/skipped | run `scripts/install.sh --install` |
| `not vendored under` | fixture tree missing | run `scripts/fetch_fixtures.py` (needs network) |
| `ngspice not on PATH` | no ngspice binary | NGSPICE-LIVE (provision + rerun) |
| `netgen not on PATH` | no netgen binary | NGSPICE-LIVE (provision + rerun) |
| `sax not installed` | core venv missing solver deps | `uv sync` (needs network) |
| `sky130 PDK not registered` | store empty/wrong HOME | run `scripts/install.sh --pdk-only`, check ROCKETEDA_HOME |
| `quarantined ... blocked-env` | tool/store absent for that case | per-case ref (NGSPICE-LIVE / B10-owned tooling) |

## Re-running after a wipe

`/tmp` does not survive reboot. After a reboot, re-run the single
command: `--install` re-registers the PDK from the (persistent)
`$HOME/.local/share/pdk/sky130A` source, then proves as above.
Expect the PDK adoption (12 GB copy + hash) to take several minutes
on the first run only; later runs re-verify instead of copying.

## Docker flow (DOCKER-DEPLOY, one-command judging recipe)

Build once on a networked host, then every judging run is a
single `docker run` plus a browser tab. The PDK rides named
volumes, never image layers; the plain-HTTP adapter stays
NO-AUTH on `127.0.0.1:8000` only, and `--network=host` keeps
that loopback bind the trust boundary (never publish the port
to untrusted networks — auth'd HTTPS is the later path).

```sh
# One-time: bake the locked engine + pinned toolchain.
docker build -t rocketeda:judging .
docker images --digests rocketeda:judging  # record the digest, repin BASE_IMAGE

# One-time: stage the PDK source where the first run adopts it.
docker volume create edata-pdk
docker volume create edata-store
docker run --rm -v edata-pdk:/pdk \
  -v "$HOME/.local/share/pdk/sky130A:/src:ro" \
  docker.io/library/python:3.12-slim-bookworm \
  cp -a /src/. /pdk/sky130A/

# The single command: adopt (first run) + prove (every run).
docker run --rm --network=host \
  -v edata-pdk:/pdk:ro -v edata-store:/stores/rocketeda \
  -e PDK_SOURCE=/pdk/sky130A \
  rocketeda:judging

# Then open http://127.0.0.1:8000 in a browser (GET /health
# is the liveness probe) and read the demo gate verdict from
# the container log: `demo: 4 passed, 0 failed`.
```

Image-size and digest notes: record `docker images` SIZE plus
the `repo@sha256:<digest>` here at judging-build time (this
checkout host has no daemon route, so the fresh-machine
build + run stays BLOCKED-needs-host, qualified by
recipe-review only). Rebuilds are reproducible from `uv.lock`
plus the provisioner pins plus the repinned base digest.

Known Docker failure modes: `permission denied on the socket`
means the Docker daemon is unreachable (start it, retry);
`PDK source is not a directory` means `PDK_SOURCE` misses the
volume path (check the `-v` flags); `offline` from the
provisioner layer means the build host has no registry route
(retry networked — the layer is never faked green).
