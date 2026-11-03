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
