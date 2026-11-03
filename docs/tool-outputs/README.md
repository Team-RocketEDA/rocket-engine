# docs/tool-outputs — pinned tool output notes (waves 1-3)

Per kept tool: report inventory, grammars, exit states, version
notes, fixture paths — everything a normalizer author needs
besides `parse()` source, without running the tool
(TOOL-OUTPUTS ticket). One note per tool keeps reviews small.

## Wave 1 — checks

- [magic-8.3.685.md](magic-8.3.685.md) — Magic DRC batch
  (total line + error-area blocks; exit 0 always).
- [klayout-0.28.16.md](klayout-0.28.16.md) — KLayout DRC,
  synthetic `TOTAL`/`VIOL` lines plus `.lyrdb` deck reports.
- [netgen-1.5.316.md](netgen-1.5.316.md) — Netgen LVS match /
  mismatch reports (TOP-level compare; impostor banner probe).
- [slang-12.0.0.md](slang-12.0.0.md) — Slang lint diagnostics
  plus the Build summary line.
- [connectgraph-engine.md](connectgraph-engine.md) — own-code
  connectivity findings (run_connectivity / run_erc policies).
- [sby-0.70.md](sby-0.70.md) — Sby status file + DONE summary
  with scoped verdicts and counterexample traces.

Determinism pins: `tests/test_coverage_wave1.py` parses the
transcribed good/bad natives twice (JSON round-trip included)
and asserts clean vs failing plus loud refusal on
verdict-less output. The coverage map replays the same
canned natives per cell (`coverage/check.py --rerun`).

## Wave 2 — sims (owned adapters)

- [icarus-14.0.md](icarus-14.0.md) — Icarus compile diagnostics
  plus vvp FATAL/ERROR assertion lines (`$error` exits 0, so the
  verdict is parsed output, never the exit code).

## Wave 3 — implementation (owned adapters)

- [librelane-3.0.17.md](librelane-3.0.17.md) — LibreLane run-dir
  layout with per-step `state_out.json`/`metrics.csv` machine
  verdicts (D22/D25/D26/D27 read machine files only).
- [yosys-0.70.md](yosys-0.70.md) — Yosys synth stat grammar plus
  ERROR/Warning diagnostics.

OpenSTA stays wave 4 (PARKED per RULING-03; STA-text grammar
residue lives in the audit, no note staffed until provision
unparks it).
