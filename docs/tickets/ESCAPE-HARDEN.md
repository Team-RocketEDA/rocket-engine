Problem batch (adapters bypassing their blessed structured escapes):
1. synth_yosys emits only `tee stat` + write_verilog, scrapes stat text (audit mandates write_json; rejects pyosys). MC-37.
2. syntax runs `slang --lint-only`, scrapes file:line:col + summary (audit mandates pyslang + --ast-json). MC-37.
3. hdl_sim parses FATAL/ERROR lines only, no $dumpfile/VCD; cosim-digital has no VCD/pywellen refs (cosim analog wrdata+markers already pinned-compliant). MC-37.
4. drc_kl deck-mode bbox via generic float scraping (:104-110) — pin to lyrdb value grammar. MC-44.
5. Violation/measurement conformance: drc/drc_kl omit severity/message; extract_magic omits `total`; measurements dict-vs-list split; bare PASS rows in synth/timing/gdsfactory (need value/target/margin/status). MC-36.
Expected-per: audit KEEP rows :36,38,49; ports.py:54-72 contract; API-V1-ADAPTERS:49-50. Tighten ports.py to "measurements: list, possibly empty" before normalizers.
