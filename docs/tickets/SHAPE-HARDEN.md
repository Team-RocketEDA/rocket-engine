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

## Verdict (Wave-3, 2026-11-03) — Remainder confirmed out of lane

Verified this wave: every remainder item needs a non-owned
surface (foundry-deck grammars, submodule pins, upstream tool
flags, sibling-owned adapters). No owned file — results
normalizers are pure functions of recorded outputs and must not
invent grammars — can close them. The 11 landed normalizers map
only the verified v0 shapes; nothing prose-based was staffed.
Carrying unchanged.

## Verdict (Wave-4, 2026-11-03) — In-parse-scope remainder landed

This wave owns the parse side only (bbox grammar, extract
total, conformance); the grammar/shape items are closed from
live evidence, the rest stay BLOCKED-needs-host with loud
skips, never faked green:

- drc_kl deck-mode bbox: pinned to the observed lyrdb value
  grammar (`polygon:`/`edge-pair:`/`shape`, `;`-separated
  pairs) against KLayout 0.28.16 + sky130A@5f09001e
  (`tests/adapters/test_drc_bbox_grammar.py`).
- Binary-gated acceptances verified loud-skipping on this
  host: `test_timing_sta.py` (28 passed, 4 skipped — sta /
  liberty absent), `test_digital_flow.py` (librelane / PDK
  root / serv-fixture probes skip with remedies).
- Still out of lane (unchanged): openroad SDC/SDF/STA writers
  (empty src/sta), cace re-verify at pin 2.13.0, openvaf OSDI
  reader, xschem per-type EBNF at pin 7811010c, yosys_slang
  submodule formats, xyce .fftN/-rsf/.csd, cocotb+gmsh —
  each needs a non-owned surface (submodule, tool flag, or
  sibling adapter). No prose-based adapter was staffed.
