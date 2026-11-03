# netgen 1.5.316 — LVS batch report (run_lvs)

Version provenance: verified against netgen 1.5.316 +
`sky130A_setup.tcl` per `src/adapters/lvs_netgen/__init__.py:1-11`.
Report grammar transcribed from the adapter's match/mismatch
regexes; canned reports in `tests/test_coverage_wave1.py` are
transcribed, not live runs.

## Report inventory

One mode: `netgen -batch lvs <layout> <schematic> <setup>
<report>` over TOP-level circuits (`lvs_netgen:351-416`). Both
sides are flattened to top level first (leaf-cell normalization:
the single `.subckt` wrapper is dropped; a library needs `cell`
to select its block — `lvs_netgen:72-140`). Native output is
`{exit_code, stdout, stderr, report_file, report_text, ...}`; the
verdict is read from `report_text`, falling back to the report
file, then stdout (`lvs_netgen:444-453`).

## Grammar

Match (`lvs_netgen:63`):

```ebnf
"Circuits match uniquely." | "Netlists match uniquely."
```

Mismatch (`lvs_netgen:64-69`): either `Netlists do not match.` or
`*** MISMATCH ***`, followed by net lines `Net: <name>` (plus bare
`(no matching net)` markers) before `DEVICE mismatches:`, and
`Instance: <name>` (plus `(no matching instance)` markers) after
it (`lvs_netgen:219-262`). Parsed result: `{match, total,
violations[]}` with `lvs_net_mismatch` / `lvs_device_mismatch`
rules at severity error.

## Exit states

- Netgen exits 0 on match and mismatch alike (`lvs_netgen:7-8`);
  the verdict always comes from parsed output, never the exit
  code.
- PATH presence is NOT enough: the `netgen` apt package is the
  Schoeberl mesh generator — same name, different tool. The
  banner probe (`-help` + denylist, `lvs_netgen:154-197`)
  rejects impostors as `missing_dependency`; PATH resolution
  alone never admits.
- No report file produced: `runner_unavailable`
  (`lvs_netgen:403-407`). Output with no verdict:
  `runner_unavailable` (`lvs_netgen:453-455`) — never a guess.
- Batch runs with `DISPLAY` scrubbed (Tk init fails against an
  unreachable display — `lvs_netgen:142-151`).

## Version sensitivity

Stable: match/mismatch verdict lines, `Net:`/`Instance:`
markers. Incidental: surrounding log chatter; setup-file
(`sky130A_setup.tcl`) contents are PDK-owned.

## Out of scope

`.spice` netlist language; setup-Tcl authoring; hierarchical
(non-flattened) compare — the adapter always flattens first.

## Fixtures

- `tests/mutate/fixtures/lvs_inv/layout.spice` (layout side).
- `tests/mutate/fixtures/lvs_inv/schematic.spice` (reference side).
- Mutated direction: net-swap transcription recorded in the
  coverage map cell `cov-d26-lvs` (`coverage/map.json`).
