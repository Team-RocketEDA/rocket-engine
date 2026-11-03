# Scenario gate

Run the scenario harness against the real Engine composition. Fake-track scenarios use a canned adapter result; live scenarios invoke the named EDA tools on representative project fixtures. Missing native tools fail in startup preflight before a scenario begins.

## Setup and run

Use the supported repository setup and tool provisioners:

1. Run scripts/install.sh --install for the locked Python 3.12 engine environment.
2. Run scripts/provision_toolchain.sh --check-only and follow its remedies for the native tools needed by the selected scenarios.
3. Put the provisioned binaries on the scenario process PATH, and set ROCKETEDA_HOME to a store with the required PDK when a scenario uses a foundry deck.
4. Fetch the documented upstream fixtures when needed with scripts/fetch_fixtures.py.

The scenario command is:

```sh
.venv/bin/python scripts/scenarios.py scenarios/
```

The harness accepts --json and -q. See [demo-runbook.md](../docs/demo-runbook.md), [provision-plan.md](../docs/provision-plan.md), and [fixture provenance](../fixtures/upstream/).

## Scenario tool requirements

| Scenario/backend | Requirement |
|---|---|
| dispatch_fake | No external tool |
| magic | Magic on PATH |
| klayout, klayout_sky130, klayout_mzi | KLayout on PATH |
| hdl, hdl_serv, hdl_picorv32, hdl_sdm | iverilog and vvp on PATH |
| ngspice_bandgap, ngspice_sdtop | ngspice on PATH |
| extract_lvs_sky130 | Magic and Netgen on PATH |
| sax_mzi | SAX available in the engine Python environment |

Sky130 scenarios also require the relevant PDK revision registered in the engine store and the upstream fixtures described by the scenario. The scenario runner reports the missing item and its remedy rather than substituting another deck or tool.

The base install currently selects the base and development Python dependency groups. Optional solver groups such as photonic are declared in pyproject.toml but are not selected by scripts/install.sh yet. A base install alone therefore does not qualify sax_mzi; use a supported, already-provisioned environment for that lane until profile installation is added to the repository installer. Do not hand-edit the sealed .venv.

## Verdict behavior

- Missing required PATH binaries fail before step 1 with missing_dependency and name the required tool.
- If a present tool cannot run the requested technology, the scenario reports its NOT_RUN reason.
- Exit-zero tool results still pass through the adapter parser and engine evaluator; tool exit status is not treated as a PASS verdict.

For the declared fixture matrix and per-scenario assertions, read the YAML files in this directory and scripts/scenarios.py.
