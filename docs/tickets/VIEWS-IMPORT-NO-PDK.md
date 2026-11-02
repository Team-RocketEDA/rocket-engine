# VIEWS-IMPORT-NO-PDK: generate_views import_gds never activates a PDK

*Status: Backlog · Depends: none · Size: XS*

## Why

Importing the `photonic_matmul` 2x2 unit GDS (`generate_views`,
`recipe: import_gds`) FAILs loudly but wrongly:

```
unreadable_source: Cannot import GDS .../mzi_unit.gds: No active PDK.
Import and activate a PDK, or activate the generic PDK with
`gf.gpdk.PDK.activate()`.
```

Root cause: the views adapter stages `doc=None` for `import_gds`
(`src/adapters/gdsfactory/adapter.py`, import branch), and the
staged driver (`src/adapters/gdsfactory/_driver.py::_activate`)
returns early on `doc is None` without activating anything — while
`build_cells`/`export_*` always go through PDK activation. So the one
recipe that reads designer-produced (non-registry) GDS is the one
recipe that cannot run at all. The design and GDS are proven good by
independent evidence (KLayout readback roundtrip in project tests,
engine `run_drc` PASS on the same file); this FAIL is engine-side,
not design-side.

## What

- On the import path, activate a PDK before `gf.import_gds` (generic
  PDK at minimum; project PDK via `cspdk_path`/pin context where the
  adapter already carries it — pick one, never a silent default
  that changes build/export behavior).
- No contract regen (driver behavior, not schema); add an adapter
  test importing a real GDS with no view spec, plus one with the
  vendored cspdk tree.

## Acceptance

- `generate_views`/`import_gds` on a valid GDS returns mappings
  (plus pin fallback as today) instead of `unreadable_source`.
- `build_cells`/`export_gds`/`export_oasis` behavior unchanged;
  affected adapter suite green.

## Verdict (2026-11-03, landed)

Done, no contract regen (driver behavior, not schema). RED:
`tests/adapters/test_views_import_pdk.py` staged a real import_gds
job (`doc=None`, no view spec) over the vendored si340 waveguide GDS
and got the ticket's exact failure (`unsupported_format` envelope:
"No active PDK..."). GREEN: `_activate` in
`src/adapters/gdsfactory/_driver.py` now activates on the import
path — the carried `cspdk_path` tree wins where the adapter staged
it (active PDK `cornerstone_si340`), otherwise the generic PDK keeps
the read independent of build/export PDK selection. The shared cspdk
activation was factored into `_activate_cspdk` with byte-identical
build/export behavior. Both new tests pass (generic import reports
`active_pdk: generic` with 1 mapping; cspdk-tree import reports
`cornerstone_si340` plus `cspdk_version`). `adapter.py` needed no
change (it already stages `cspdk_path` into the job JSON).
`tests/adapters/test_generate_views.py`: 26 passed, 1 skipped; the 2
live-cspdk failures (`mzi` vs `mzi_...mmi_hash` component naming) are
pre-existing on the untouched base (re-ran with the fix reverted —
same 2 failures), i.e. environmental cspdk naming drift, not this
change.
