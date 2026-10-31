# Fixture provenance: mzi_ref.gds

- File: `mzi_ref.gds` (13,564 bytes, md5 `3e23eda5739108c69c1f7f5c60bd6b58`)
- Upstream source: `tests/gds_ref_si340/mzi.gds` in
  https://github.com/gdsfactory/cspdk @
  `3323b17b4d75c852ed2372d7d13239408cca0eb1` (cspdk 2.1.0) —
  byte-identical to the repo's `fixtures/upstream/cspdk` vendored copy.
- License: MIT (upstream `LICENSE`, (c) 2024 gdsfactory).
- What it is: the PDK's own regression reference for the si340
  strip C-band MZI — 16 polygons on GDS 3/0, top cell `mzi_*`.
  The lane DRC proof (`test_drc.py`) runs the engine KLayout batch
  check against it (expect 0 violations).
