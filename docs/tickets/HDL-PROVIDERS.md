Problem batch (MVP multi-provider tasks at partial coverage):
1. simulate.hdl at 1/4: icarus only; add verilator (--xml-only/VCD escapes) + ghdl (pyGHDL). MC-20.
2. generate.views/netlist + export.design: staff xschem (pinned determinism case exists) + vlsirtools providers. NOTE: catalog kfactory provider entries need re-scope per RULING-07 demotion (kfactory internal).
3. characterize.circuit: cace provider (native bindings; re-verify at pin 2.13.0 — evidence at 2.5.6).
4. check.lvs klayout path + check.layout_xor mode (API-V1-ADAPTERS:57 assigns layout_xor to drc_kl but no XOR mode exists).
5. synthesize.hdl ghdl/amaranth frontends (pin amaranth first — unpinned).
Split per provider at staffing time. Dump-first + fixtures each.

## Verdict (adapt lane, 2026-11-03) — providers Done, gated

- simulate.hdl: `src/adapters/hdl_sim/verilator.py` (SARIF first,
  lint-text fallback; xml-only dead) and `hdl_sim/ghdl.py`
  (assert-line verdicts; runtime stdout vs compile stderr never
  merged). Verilator 5.053 and GHDL 7.0.0-dev live on PATH.
- generate.views/export.design: `src/adapters/vlsir/` (netlist
  emission deterministic; SimResult proto/numpy reads; sim
  execution stays subprocess). vlsir 7.0.0 grammar per note.
- characterize.circuit: `src/adapters/cace/` (CLI run, exit-code
  gate, summary.md verdicts). cace 2.13.0 imports live; the CLI
  binary is absent → BLOCKED-needs-host pinned by test.
- check.lvs klayout path + layout_xor: `src/adapters/drc/klayout.py`
  gains `KlayoutLvsAdapter` plus `run_xor_summary` (netgen stays
  reference; klayout exits 0 regardless so verdicts parse).
- synthesize.hdl ghdl/amaranth: `src/adapters/synth_yosys/ghdl.py`
  plus `amaranth.py` (generated backend Verilog; amaranth imports
  live, unpinned — pin first).
Tests: `test_hdl_providers.py`, `test_synth_providers.py`,
`test_cace.py`, `test_vlsir.py`, `test_klayout_lvs_xor.py`. Notes:
verilator-5.053, ghdl-7.0.0-dev, cace-2.13.0, vlsir-7.0.0,
klayout-lvs-xor, amaranth-unpinned. Wiring seam untouched.
