# postlayout klt translation — vendor map or loud refusal

Context: POSTLAYOUT-REAL. Real extracted PEX carries klt generic
device classes and is unsimmable as-is. Translator
`src/adapters/postlayout/translate.py`.

## Report inventory

`translate_klt_netlist(text, vendor)` maps known klt classes to
vendor models (`sky130_klt_nmos` → `sky130_fd_pr__nfet_01v8`
etc.) and returns `(translated, mapping)`; `is_klt_netlist`
detects klt markers.

## Grammar

Mapping rows: `{from, to, vendor}`. Unknown klt classes raise
`unsupported_operation` naming the device and the vendor gap —
loud refusal, never a silent sim_fail. The postlayout sim path
calls this before staging the deck.
