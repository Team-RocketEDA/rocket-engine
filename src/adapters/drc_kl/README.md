# adapters/drc_kl — KLayout DRC solver

Batch DRC behind the `ToolAdapter` port: preflight refuses missing
binaries, GDS files, and insane rules; execute renders a pya check
script from the rule table and runs `klayout -b -r`; parse normalizes
VIOL/TOTAL lines into `{total, violations[]}` with rule text + bbox_um.

Verified against KLayout 0.28.16 on synthetic GDS fixtures
(`tests/adapters/fixtures/drc_kl/`). KLayout exits 0 even on failure,
so the verdict comes from parsed output, never the exit code.

Status: I14 GREEN on synthetic rules. sky130A decks stay gated on the
deck-source decision (PROV); the Ruby DSL needs a driver macro for
batch (see `docs/probe-klayout-drc.md`).
