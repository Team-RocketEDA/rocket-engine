Problem batch (adapters bypassing their blessed structured escapes):
1. synth_yosys emits only `tee stat` + write_verilog, scrapes stat text (audit mandates write_json; rejects pyosys). MC-37.
2. syntax runs `slang --lint-only`, scrapes file:line:col + summary (audit mandates pyslang + --ast-json). MC-37.
3. hdl_sim parses FATAL/ERROR lines only, no $dumpfile/VCD; cosim-digital has no VCD/pywellen refs (cosim analog wrdata+markers already pinned-compliant). MC-37.
4. drc_kl deck-mode bbox via generic float scraping (:104-110) — pin to lyrdb value grammar. MC-44.
5. Violation/measurement conformance: drc/drc_kl omit severity/message; extract_magic omits `total`; measurements dict-vs-list split; bare PASS rows in synth/timing/gdsfactory (need value/target/margin/status). MC-36.
Expected-per: audit KEEP rows :36,38,49; ports.py:54-72 contract; API-V1-ADAPTERS:49-50. Tighten ports.py to "measurements: list, possibly empty" before normalizers.

## Verdict (Wave-2, 2026-11-03) — Ready, remainder to Wave-3

Structured escapes + shape conformance pinned for the six owned
flow-lane adapters (same shapes suite). drc_kl bbox grammar,
extract total, and cross-adapter conformance carry to Wave-3.

## Verdict (Wave-3, 2026-11-03) — Remainder confirmed out of lane

Verified this wave: the remainder needs parse-behavior changes
(drc_kl deck-mode bbox grammar pinning, extract `total`,
severity/message conformance in `parse()`), which this lane is
forbidden to make (normalizers ONLY, no behavior change). The
landed normalizers compensate without touching behavior:
klayout synthetic-mode violations without messages fall back to
rule-plus-geometry, and every severity-less violation fails as
an error finding. Carrying the parse-side remainder unchanged.
