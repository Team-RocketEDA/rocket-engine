# I29-SERVING: own verbatim PDK serving end to end with PRD-name aliases

*Status: Ready · Depends: none · Size: M · Roadmap: design serving (MVP track) · Parent: CANVAS-CST (Step 6c)*

## Why

Today the frontend renders bundled `spectrum`/`waveformSignals` fixtures and
handwritten scalar DTOs because the engine does not serve PDK knowledge
itself. The invariant is that the engine is FULLY capable of serving its PDKs
at every granularity — metadata, cells, layers, timing, models, bulk — so any
consumer (IDE, MCP agent) renders from engine data alone, no fixture
knowledge baked into clients.

Verbatim is non-negotiable: liberty/models/cells are served as the PDK ships
them. PRD-name aliases ride alongside the canonical names so humans and
agents query by the names the PRD uses while the wire always carries the
PDK's own identifiers. This is what makes the IDE a presentation layer over
engine truth.

## What

- Engine-owned serving endpoints over the existing ports covering PDK
  metadata/cells/layers/timing/models at bulk and fine granularity.
- Verbatim PDK payloads + PRD-name aliases on the same records.
- Frontend gap doc updated from "handwritten DTOs + fixtures" to engine
  schemas driven by the serving contract.

## Acceptance

- Serving tests over stdio/HTTP assert verbatim fields plus alias lookup for
  the pinned PDK set (tests pin).
- Any PDK served verbatim round-trips: bulk list → cell record → timing/
  model payload, no fixture source in the path.
- Contract + api_spec regen if surfaces change; suite green.

## Delivery verdict (I29-OWNER + I29-SERVING merged, 2026-11-02)

DELIVERED at the module + inbound-port layer (TDD RED→GREEN, 6 new
tests in `tests/test_apig_aliases_paging.py`; neighboring files
`test_apig_assets.py`, `test_apig_integration.py`,
`test_apig_catalog/pool/submit.py` stay green — 192 passed,
14 pre-existing skips).

- PRD aliases: `list_pdk_assets`/`get_pdk_asset` in
  `src/interfaces/apig_assets.py` wrap the canonical functions
  with identical payloads (`PRD_ALIASES` pins the pair).
- Caps/paging (MC-43): `serve_asset(..., max_bytes=...)` refuses
  over-cap with `too_large` (default 4 MiB cap); `list_assets(...,
  limit, cursor)` pages with an opaque `next_cursor` following
  the v1 Page convention (`limit=None` returns the whole set, so
  existing callers are unaffected).
- Transport: canonical names round-trip end to end through the
  one inbound port every gateway shares (`adapters.api.submit` →
  `Engine.submit`): bulk list → cell serve, verbatim bytes +
  matching sha256, no fixture in the path.
- No contract/api_spec regen: no Engine surface changed (only
  module-level functions), so the frozen `contracts/v1` and the
  api_spec AST seams are untouched.

Seams for other lanes (NOT done here — out of owned set):

- Adapt lane: catalog `list_pdk_assets`/`get_pdk_asset` in
  `interfaces/vocabulary.py` + `composition.py` wiring
  (`Engine.list_pdk_assets/get_pdk_asset`,
  `QUERY_ENGINE_METHODS`, `_APIG_QUERIES`, `_query_apig`),
  re-export the aliases in `interfaces/__init__.py`, thread
  `limit`/`cursor`/`max_bytes` through the Engine methods, and
  update the stale "No size cap" caution on
  `Engine.serve_asset`. `test_prd_alias_wiring_seam_documented`
  pins this gap and tells the adapt lane exactly what flips it
  green.
- Docs lane: flip the "planned (I29)" prose to shipped in the
  invariants / suggested-api / frontend-tooling-spec docs.

BLOCKED-needs-host: none. This slice is pure Python; no
binary-gated acceptance applies.
