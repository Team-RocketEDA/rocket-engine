# Fixture provenance (PDK-LXT)

All fixtures derive from the pinned upstream, MIT-licensed source:

- Upstream: <https://github.com/Luxtelligence/lxt_pdk_gf.git>
- Revision: `d16db6a4882657feb1ce696c16c604ff6cb7ccfa`
  (2026-06-01, merge PR #124; package `lxt_pdk_gf` 2.0)
- License: MIT, Copyright (c) 2023-2026 Luxtelligence
  (upstream `LICENSE` file; GitHub repo "About" likewise says MIT)

## Files

- `straight_L10.gds` (2554 bytes, sha256
  `b99ddbf7fc6fb4011c7dc18a7fb1808b47e30743e9a7f27c2078bb6ae5ffe23e`)
  — THE proof fixture. Generated 2026-10-31 from the pinned upstream
  via `ltoi300.cells.straight_rwg900_cband(length=10.0).write_gds(...)`
  (run env: gdsfactory 9.51.0, sax 0.18.2, gplugins 1.4.2 source).
  Top cell `straight_rwg900_cband_L10`: 1 shape on LT_RIDGE (2/10),
  1 shape on LT_SLAB (3/10). Regeneration embeds fresh GDS
  timestamps, so tests assert structure (layers/shapes/bbox), never
  byte equality.
- `ltoi300.layers.yaml` (verbatim copy of upstream
  `ltoi300/layers.yaml` at the pinned revision; sha256
  `f15a0d340bd19906677120acecfd30ff501c438450b4dbf82fbfdeb39e8cddfb`)
  — layer reference: LT_RIDGE [2, 10], LT_SLAB [3, 10], etc.
- `standin_deck/ltoi300.stand-in.lydrc` — NOT upstream. A lane-authored,
  clearly labelled STAND-IN deck exercising the user-supplied-deck
  flow (register/resolve/hash-pin). It encodes no design rules and
  must never be mistaken for the gated upstream deck; it points at
  the access gate instead.
