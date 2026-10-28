# adapters/drc — Magic DRC solver

Batch DRC behind the `ToolAdapter` port: preflight refuses unknown
techs, missing cells, and foreign operations; execute runs magic
headless (`-dnull -noconsole`) over a Tcl script; parse normalizes
stdout into `{total, violations[]}` with rule text + bbox per area.

Verified against magic 8.3.685 + scmos tech 8.2.8
(`/usr/local/lib/magic/sys/scmos.tech`). Magic exits 0 even on
failure, so the verdict comes from parsed output, never the exit code.

Status: I14 GREEN on scmos fixtures. sky130A decks stay gated on the
deck-source decision (PROV).
