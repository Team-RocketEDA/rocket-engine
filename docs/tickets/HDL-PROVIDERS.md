Problem batch (MVP multi-provider tasks at partial coverage):
1. simulate.hdl at 1/4: icarus only; add verilator (--xml-only/VCD escapes) + ghdl (pyGHDL). MC-20.
2. generate.views/netlist + export.design: staff xschem (pinned determinism case exists) + vlsirtools providers. NOTE: catalog kfactory provider entries need re-scope per RULING-07 demotion (kfactory internal).
3. characterize.circuit: cace provider (native bindings; re-verify at pin 2.13.0 — evidence at 2.5.6).
4. check.lvs klayout path + check.layout_xor mode (API-V1-ADAPTERS:57 assigns layout_xor to drc_kl but no XOR mode exists).
5. synthesize.hdl ghdl/amaranth frontends (pin amaranth first — unpinned).
Split per provider at staffing time. Dump-first + fixtures each.
