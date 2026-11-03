# connectgraph (engine own code) — connectivity findings (run_connectivity/run_erc)

Version provenance: own code, versioned with the engine
(`src/workflows/connectgraph.py`, `src/workflows/connectgraph_emit.py`,
`src/adapters/connectivity/__init__.py`). No subprocess, no tool
to pin: read this code, don't transcribe a vendor manual.

## Report inventory

In-process only: `execute` extracts the graph, emits the
requested netlists, and collects ERC findings
(`connectivity:109-154`). Native output is `{exit_code: 0,
operation, findings, netlists, nets, net_count,
instance_count, skipped, log}`. `parse` normalizes findings
into violations; netlists plus the net table ride
`measurements` (`connectivity:156-196`). Every net name flows
from the shared `Connectivity.net_name` authority.

## Grammar

Findings are records, not text (`connectivity:175-196`):

```ebnf
{rule, severity, message, net?, net_id?}
```

Policy differs by operation over the same findings
(`connectivity:24-25`): `run_connectivity` warns on
unconnected pins (`CONNECTIVITY_POLICY`), `run_erc`
escalates them to errors (`ERC_POLICY`); shorts fail
either way. Parsed result: `{total, violations[],
measurements{netlists, nets, net_count, instance_count,
skipped}}`.

## Exit states

- No exit path to read: `exit_code` is always 0; read the
  verdict, never the exit path (`connectivity:44-45`).
- Malformed schematic: `invalid_command` from `prepare_netlist_structs`
  (`connectivity:125-131`). Output with no findings list:
  `runner_unavailable` (`connectivity:170-174`).

## Version sensitivity

Stable while the finding-record shape holds; policy maps are
the contract. Net-naming changes would rekey every finding.

## Out of scope

Netlist language grammars downstream (spice/verilog/vhdl emit
is covered by the emitter modules, not the check finding).

## Fixtures

- `tests/workflows/fixtures/connect_graph_demo.json` (+
  `.spice`/`.verilog`/`.vhdl` goldens).
- Mutated direction: shorted-net / unconnected-pin variants
  transcribed in coverage map cells `cov-a04-connectivity`,
  `cov-a04-erc`, `cov-m09-erc` (`coverage/map.json`).
