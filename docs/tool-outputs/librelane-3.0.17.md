# librelane 3.0.17 — run-dir machine files (run_digital_flow)

Version provenance: LibreLane `3.0.17` pin
(`scripts/provision_toolchain.sh:77` `LIBRELANE_PIN="3.0.17"`,
clone `64ef8080` per `docs/tools/librelane.md:10-16`); adapter
`src/adapters/digital_flow/__init__.py:1-22`,
machine readout `src/adapters/digital_flow/state.py`.
Canned natives are fixture run-dir trees
(`tests/adapters/test_digital_flow.py:212-280`), not live runs:
`librelane` is absent on this host (loud skip, BLOCKED-needs-host).

## Report inventory

One mode: Classic flow as a subprocess
(`digital_flow:678-694`): stage the project RTL into `design/`,
run `librelane <config> --tag <tag> --pdk <pdk> --overwrite`
(`--pdk-root`/`--scl` when named), then read
`design/runs/<tag>/` step dirs. Per step dir
(`librelane.md:22-29`): `config.json` / `state_in.json`
(input echo, provenance), `state_out.json` (views paths +
metrics dict), `metrics.json` / `metrics.csv` (flat scalar
table, header `Metric,Value`), `runtime.txt` (elapsed,
informational only), plus tool-native logs/reports/`.odb`/`.gds`.

## Grammar

`state_out.json`: `State.dumps` shape — views are paths keyed by
`DesignFormat`, metrics are scalars (`librelane.md:33-40`).
`metrics.csv`:

```ebnf
"Metric,Value" NL { KEY "," SCALAR NL }
```

`metrics.json`: flat `{name: value}` (`librelane.md:41-45`).
Key names are dynamic per step — the adapter never hardcodes a
full list; it looks up documented families case-insensitively
(`state.py:21-30`) and fails loud listing the keys seen when
none match (key drift = upstream step change).

Verdict keys consumed (fixture-pinned, live run confirms):

| Gate | Keys | Fail iff |
|---|---|---|
| D22 STA | `timing__setup__ws`, `timing__hold__ws`, `timing__setup__tns`, `timing__hold__tns` (+ `wns_*`/`tns_*` aliases; OpenROAD family `timing__setup\|hold__{tns,ws,wns}` per `docs/tools/openroad.md:63`) | min < 0 |
| D25 DRC | `drc__violations`, `drc_total`, `violations` | total > 0 |
| D26 LVS | `lvs__match`, `lvs_match`, `match` (1/0, true/false, match/mismatch) | falsy |
| D27 equiv | `equiv__equivalent`, `equivalent`, `equiv_pass`, `equiv__proven` | falsy |

D11 passes on staged config + pinned version; D12 on synth
artifacts with no `ERROR:` line; D24 on a non-empty `.gds`;
other gates on matched step + artifact evidence
(`digital_flow:218-290`).

## Exit states

- Nonzero exit: first failing gate fails, evidence-free
  downstream gates `not_run` (`digital_flow:379-438`).
- Timeout: SIGKILLs the process tree, reports
  `digital_flow_timeout` with partial evidence.
- Missing machine files on a gated step: gate fails naming
  `state_out.json/metrics.csv` — never scraped text, never
  silent (`state.py:232-256`).
- `force` list bypasses named gates as warnings, never silent.
- Unpinned binary: `missing_dependency` with the PROV remedy.

## Version sensitivity

Stable: run-dir layout, `state_out.json` views+metrics split,
`Metric,Value` header. Drift-prone: step-dir names (matched by
lowercase substring, loud on miss), metric key names (loud on
miss). LibreLane revision equals the pin (no drift window).

## Out of scope

STA `.rpt` text until `sta` lands (TOOL-OUTPUTS wave 4; audit
keeps STA-text as residue); tool-native free text inside step
logs (bounded tails, evidence only); `runtime.txt` elapsed.

## Fixtures

- `tests/adapters/fixtures/digital_flow/counter.v` (clean).
- `tests/adapters/fixtures/digital_flow/broken.v` (D12 death).
- Fake trees + stub `librelane` in
  `tests/adapters/test_digital_flow.py:34-105,212-280` (ok /
  partial / synthfail / sta_fail / drc_dirty / lvs_fail, each
  with machine states).
