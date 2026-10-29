# Scenario gate: PATH contract (SCENARIO-PATH)

`scripts/scenarios.py` runs every `scenarios/*.yaml` through the real
Engine. Live steps shell out to foundry/EDA tools, so the gate
declares the toolchain it needs instead of flipping on ambient PATH.

## The contract: dev-PATH

Run the gate with oss-cad-suite on PATH:

```sh
export PATH="$HOME/tools/oss-cad-suite/bin:$PATH"
uv run --locked python scripts/scenarios.py scenarios/
```

`scripts/demo.sh` and `docs/demo-runbook.md` set this up; CI must too.

## Backend → tool table

| run_live backend | PATH binaries | Provided by |
|---|---|---|
| `magic` (default when omitted) | `magic` | system install |
| `klayout`, `klayout_sky130`, `klayout_mzi` | `klayout` | system install |
| `hdl`, `hdl_serv`, `hdl_picorv32`, `hdl_sdm` | `iverilog`, `vvp` | oss-cad-suite |
| `ngspice_bandgap`, `ngspice_sdtop` | `ngspice` | NGSPICE-LIVE (not provisioned here) |
| `extract_lvs_sky130` | `magic`, `netgen` | system + NGSPICE-LIVE (`netgen` missing here) |
| `sax_mzi` | none (needs the `sax` python module) | `uv sync --group photonic` |

Fake-track scenarios (`dispatch_fake`, no `run_live`) need no tools.

Sky130 scenarios additionally need a registered PDK store:
`ROCKETEDA_HOME` pointing at a store with the sky130 entry, plus the
`fixtures/upstream/*` trees from `scripts/fetch_fixtures.py`.

## Failure semantics

- **Startup preflight** (`required_path_tools` / `preflight_path_tools`
  in `scripts/scenarios.py`): a scenario whose binaries are missing
  from PATH fails before step 1 with one line per tool:

  `startup: missing_dependency: iverilog not on PATH (scenario gate
  needs dev-PATH with oss-cad-suite; see scenarios/README.md)`

  Missing tools never surface as mid-run `NOT_RUN` verdicts.
- **NOT_RUN with a reason**: when a tool is present but the run still
  cannot proceed (e.g. magic cannot load the requested tech), the
  `assert_verdict` mismatch line inlines the verdict reason:
  `verdict NOT_RUN (missing_dependency: Cannot load magic tech:
  bogus-tech.), want PASS`.

`ngspice`, `netgen`, and `sax` are unprovisionable in this sandbox
(no network route for their installs); scenarios needing them fail
environmentally naming the tool. That gap is owned by backlog ticket
`docs/tickets/NGSPICE-LIVE.md`, not this gate.
