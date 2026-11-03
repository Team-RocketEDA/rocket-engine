Why: docs/tools/* dissected 21 frontends, but 7 shapes are not contract-grade yet (contract-first: no machine-checkable grammar + fixtures, no adapter). Close each gap with source-verified grammar + golden fixtures, then flip the audit row.

Items (evidence in docs/tools/):
1. openroad: SDC/SDF/STA writers uninspected (empty src/sta submodule). Fetch submodule at recorded rev, document write_sdc/write_sdf/report_* shapes.
2. cace: evidence at 2.5.6 vs pin 2.13.0. Re-verify filenames/grammars at pin.
3. openrcx: STRUCK (dead upstream, absorbed into OpenROAD src/rcx) — no standalone re-verify; SPEF grammar covered via the librelane run-dir study (docs/tools/librelane.md). Item closed by removal 2026-11-02.
4. openvaf: --dump-json is a DEAD flag (driver bails). Prove OSDI-via-dlopen reader or record reader-unavailable.
5. xschem: per-type netlist EBNF not extracted (needs real batch run); pin 7811010c not in clone history. Batch-run + re-pin before fixtures.
6. yosys_slang: slang-submodule formats unresolved; diags stdio-only. Re-verify read_slang logging against bundle Yosys 0.70.
7. xyce: .fftN/-rsf/.csd grammars unresolved. Complete or scope out.
8. cocotb + gmsh: never dissected. Document results.xml (xUnit) + .msh shapes.

Acceptance: each item leaves a machine-checkable grammar (schema/regex/field table) + good/bad fixtures; audit rows updated; no adapter staffed on prose.

## Verdict (Wave-2, 2026-11-03) — Ready, remainder to Wave-3

Six owned flow-lane adapters pinned via tests/test_shapes_owned.py
(flat rule/severity/message shapes, escape codes, 6 passed).
Remainder (openroad rows, cace pin, openvaf, xschem EBNF,
yosys_slang, xyce, cocotb+gmsh) carries to the Wave-3 surface
lane with the sibling slices.
