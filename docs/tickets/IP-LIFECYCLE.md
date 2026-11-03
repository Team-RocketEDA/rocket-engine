Problem: no ip_search/ip_get/ip_register/ip_instantiate/ip_promote anywhere in vocabulary, composition, or src. Only place_cell exists (ops/submit.py:253-272) — narrower, unversioned, no linkage.
Expected-per: suggested-api.md:287-295 (§9 bootstrap), :301-307 (§10 table). Audit MC-04.
Ruling: RULING-01 — IP blocks are prebuilt HIERARCHICAL schematic blocks, KiCad-catalogue model (buck converters, digital chips), each shipping schematic symbol AND footprint/cell LINKED. "Instantiate" = place with linkage intact. INVARIANT: prebuilt IP is PER-PDK (each PDK strictly owns its blocks; digital MAY generalize case-by-case, default per-PDK). Distinguish PDK library cells (flat) and user hierarchy (bottom-up).
Fix: implement the five ops with per-PDK registries + symbol/footprint linkage; formalize the per-PDK invariant in behavior-invariants.yaml.

## Agent verdict (ip lane, 2026-11-03)

Landed, TDD RED->GREEN (owned-set failures -> green;
`tests/project` + wire suites: 171 passed, 1 skipped;
docstring guard exit 0):

- `src/project/ip/lifecycle.py` — IpBlock entities ({pdk,
  name, version, symbol, cell, pin_map, scope, reason,
  promoted}): `ip_register` (duplicate -> `ip_exists`;
  `scope="shared"` needs a recorded reason, else
  `invalid_scope`), `ip_search` (PDK-scoped, missing PDK ->
  `invalid_pdk`), `ip_get` (latest version by default),
  `ip_instantiate` (Instance + IpLink placed with linkage
  intact; foreign-PDK per-PDK blocks fail, shared-scope
  digital blocks resolve cross-PDK), `ip_promote`
  (exactly one promoted version per pdk/name).
- Per-PDK invariant is enforced in code, not just docs.
- Tests: `tests/project/test_ip_lifecycle.py`.

Engine-wiring seam (NOT edited here): wire the five
`ip_search`/`ip_get`/`ip_register`/`ip_instantiate`/
`ip_promote` names through `vocabulary.py` + `composition.py`
(submit-immediate for register/instantiate/promote, queries
for search/get); the behavior-invariants.yaml formalization
rides with the surface lane.

## Agent verdict (Step 8 surface lane, 2026-11-03)

Done, TDD RED->GREEN (8 RED surface failures -> green; catalogue
contract 9 RED -> green; suites: 25 IP + 32 contracts green):

- `ip_instantiate` / `ip_promote` are OPERATIONS (vocabulary,
  _CRUD_OPERATIONS, _EDITOR_OPS) riding submit-immediate through
  `_submit_editor` to new `ProjectService` verbs, which admit
  through the standard editor mutation (revision gate, idempotent
  replay, I28 pins) down to the lifecycle lane. Cross-PDK
  instantiate of a per-PDK block is refused loudly
  (`unknown_ip`/`pdk_mismatch` tolerance, matching the lane
  tests); promoting an unknown version fails `unknown_ip`.
  MCP/HTTP/CLI inherit via Engine.submit composition.
- `behavior-invariants.yaml` (repo root) formalizes RULING-01:
  per-PDK ownership, shared-scope exception, IpLink linkage.
- `src/project/ip/blocks.py::resolve_block_ref` resolves
  (pdk, name[, version]) into `<root>/<pdk>/<entry>/` with the
  `rocket/meta.yaml` contract verified at runtime against the
  in-package copy of `contracts/v1/schemas/ip-entry.schema.json`
  (byte-sync test pins the copy to the single source; bundle
  manifest + generated TS/Python artifacts updated).
- Catalogue rules for all future entries: closed top-level
  meta (name+version required, slug folders), name/version
  agreement, entry_repo/ requires upstream provenance; registry
  names stay free-text, catalogue resolution requires slugs.
- Forced the first REFACTOR-SERVICE slice: IP verbs moved to
  `src/project/ip/verbs.py::_IpMixin` (service.py 3046 -> 2941,
  back under the 3000-line guard); api_spec resolves their
  contract text via _SERVICE_DOC_HOME, handlers stay bound on
  ProjectService. Regenerated docs/api-*, docs/contract.json,
  contracts/generated via their --write paths; all freshness
  gates pass.
- Known pre-existing failures (not Step 8, attributed on
  pristine tree): docstring guard (15 hits in untouched
  adapters), completion thermal-gate test, both unrelated.
