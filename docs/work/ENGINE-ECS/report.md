# ENGINE-ECS lane report — entity store + component CRUD + addressing + events

Ticket: `docs/tickets/ENGINE-ECS.md` · Branch: GREEN-the-tests · No commits, no pushes (integrator commits).

Verify lane: the untracked substrate was audited RED→GREEN standalone, the wiring
patch was found drifted against HEAD on all three files and rebased with
byte-identical additions, and the rebased patch was verified live in a
throwaway patched copy (50/50, regen clean, 92 + 1 pre-existing skip).

## Files added (new files only — zero edits to existing files)

- `src/interfaces/engine_ecs_store.py` (1466 lines) — the store: engine-minted
  entity ids, `entity.component` canonical addressing, `entities/<id>.json`
  storage projection over docs, `component_changed(entity, component, revision)`
  events, miniplex-shape world snapshot, `components_of` / `entities_with`
  filters, read-only backfill for current docs. Stdlib + `json` only (leaf
  module, no new deps, no package-internal imports — no import cycle).
  Name note: the ticket suggests `engineecs_store.py`; the lane rule
  (ticket-prefixed new files) wins, so `engine_ecs_store.py`.
- `tests/test_engine_ecs_store.py` (600 lines, 39 tests) — unit suite loading the
  module by path; all passing standalone.
- `tests/test_engine_ecs_wiring.py` (354 lines, 11 tests) — post-patch
  integration tests the integrator runs AFTER applying the wiring patch below
  (skip until then; proven 11/11 in a patched throwaway copy).
- `docs/work/ENGINE-ECS/wiring.patch` (945 lines, refreshed this lane) — the
  exact wiring patch (`git diff` bytes from a scratch copy rebased onto HEAD
  `cf9a5d0`; `git apply --check` clean on the real tree, fresh-export apply
  byte-identical). Summarized below, not inlined, so the bytes stay exact.
- `docs/work/ENGINE-ECS/report.md` — this file.

## Contract implemented (ticket clause → behavior)

- Entities + components JSON, engine-provisioned IDs only — `create_entity`
  mints `ent-<12hex>` and takes no id argument (asserted via signature);
  `mint_entity_id` skips taken ids; callers can never supply or squat on ids.
- Ops `create_entity` / `get_component` / `set_component` / `attach_component` /
  `detach_component` / `delete_entity` — full lifecycle in `EntityStore` and in
  the `ProjectService` wiring; set upserts, attach refuses duplicates
  (`component_exists`), detach/get refuse missing (`unknown_component`),
  everything on a missing entity fails (`unknown_entity`).
- `entity.component` canonical addressing; doc paths as the documented storage
  projection, no second identity system — `entity_doc_path` /
  `entity_from_doc_path` are inverses (`entities/<id>.json`); ids and component
  names never contain dots so `parse_address` / `format_address` are
  unambiguous; every mutation response carries the id, the address, AND the
  doc path; `read_doc`/`list_docs` show the same bytes (drift tests).
- `component_changed(entity, component, revision)` ledger/event emission —
  set/attach/detach append `component_changed` (detaches add `detached: True`);
  create/delete append `entity_created` / `entity_deleted`; all through the
  admission machinery (revision gate, idempotent request ids, one revision +
  one event, atomic persist, rewind snapshots).
- Miniplex-shape world snapshot query — `world_snapshot` /
  `get_world_snapshot` return `{project_id, current_revision, entities:
  [{id, kind, components}]}` sorted by id; each entry maps one-to-one onto a
  miniplex entity (`{id, ...components}`), so mirrors load it directly.
- Filter queries `components_of` / `entities_with` — sorted component names;
  holder ids with an exact-match predicate over top-level component fields
  (nets-of-block, pins-of-net become filters; non-dict payloads never match a
  mapping predicate; `invalid_predicate` for non-mappings).
- Existing CRUD keeps working; backfill without breaking revisions —
  `entities/` docs are plain documents (`read_doc`/`list_docs`/`write_doc`
  untouched); `backfill_entities` is a pure read projecting non-entity docs as
  read-only `doc-<sha1>` virtual entities (kind `backfilled-doc`, one `doc`
  component with `{path, bytes}`) — world snapshots and `doc` filters include
  them, reads serve them, mutations refuse them (`backfill_readonly`), and no
  backfill call advances any revision (asserted).
- Acceptance flow — block entity → attach sources → wire pin-id references →
  event stream shows each change → world snapshot mirrors it (unit + wiring
  tests); agent and human edits share the verbs (one Engine surface, MCP
  tools auto-derived).

## TDD gates: RED → GREEN evidence

Scratch env (no `.venv` use, no `uv sync`, no network): `/tmp/ecs-scratch-venv`
(pytest only) plus read-only `PYTHONPATH` shims — a `rocket_engine` symlink to
the tree's `src/` and private copies of lock-pinned deps from the local uv
cache (ruamel-yaml 0.19.1, ruamel-yaml-string 0.1.1, mcp 2.3.0 + tree; anyio
4.15.1 runs without sniffio, which anyio treats as optional). Commands run
from `rocket-engine/` unless noted:

- RED: unit test copied to `/tmp/ecs-red/tests/` with no `src/` beside it →
  `FileNotFoundError: .../ecs-red/src/interfaces/engine_ecs_store.py`,
  1 collection error (module missing).
- GREEN (real tree, unpatched): `pytest tests/test_engine_ecs_store.py -q` →
  `39 passed`. No substrate bugs found; no fixes needed.
- Wiring file pre-patch (real tree): `11 skipped`
  (`needs ENGINE-ECS wiring patch`, reason shown via `-rs`).
- Wiring-absent proof independent of deps: `vocabulary.py` loaded by path
  (stdlib-only) carries 0 of the 9 ECS names pre-patch.
- Rebase check: the prior 950-line patch failed `git apply --check` on ALL
  three files against HEAD (`composition.py:71`, `vocabulary.py:13`,
  `service.py:41` — settings-store, write_settings, layer-serving, and
  python_execute drift). Rebased in `/tmp/ecs-port` (`git archive HEAD` +
  substrate): every added line carried over byte-identical (extracted from the
  old hunks by script with unique-anchor assertions); only the
  `Engine.submit` Raises clause was rewrapped onto its new context, and the
  mutation dispatch moved with the code into `_submit_crud` (same shape,
  identical lines). New patch: 945 lines, 12 hunks, `git apply --check`
  clean, and applying it to a fresh HEAD export yields files byte-identical
  (`cmp`) to the verified copy — zero fuzz, exact.
- Patched copy live (`/tmp/ecs-port` + shims): unit + wiring →
  `50 passed` (includes the MCP tool-definitions test).
- Patched + regenned copy gate: unit + wiring +
  `tests/project/test_crud_api.py` + `tests/test_api_spec.py` +
  `tests/test_contract.py` + `tests/test_check_contract.py` +
  `tests/test_docstrings.py` → `92 passed, 1 skipped` (the skip is
  pre-existing/environmental: `no fuel checkout beside the engine`).
- Regen in the patched copy: api_spec `--check` stale (3 files) → `--write` →
  `--check` exit 0; contract `--check` stale → `--write` → `--check` exit 0;
  new names present in `docs/engine-api.md`, `docs/api-schema.json`,
  `docs/api-help.json`, `docs/contract.json`; no `STUB_OVERLAP` additions
  (new engine names have no stub counterpart yet, which the contract
  tolerates).
- Docstring gate: `check_docstrings.py` exit 0 on the new module (real tree)
  and on all three patched files (patched copy).
- 100-col: zero long lines in the new module/tests and in every added patch
  line (one 103-col line at patched `service.py:708` is pre-existing HEAD
  context, not an addition).
- Real tree untouched: `git status` shows only `??` entries (this lane's
  files plus peers' lanes, none of them touched).

## Integrator runbook (verified in a throwaway copy — see evidence)

The wiring persists entities as `entities/<id>.json` documents through the
existing admission machinery, so the ledger law holds for free: revision gate,
idempotent request ids, one revision + event per accepted mutation, atomic
persist, rewind snapshots, and MCP / api_spec / contract derivation from
`ProjectService` docstrings (CRUD ops and `QUERY_METHODS` queries document
from `ProjectService.<name>`; MCP resolves the same way). No `service.py`
admission changes beyond additive methods; no `__init__.py` export.

1. `git apply --check docs/work/ENGINE-ECS/wiring.patch` (must print nothing),
   then `git apply docs/work/ENGINE-ECS/wiring.patch`.
2. Reinstall so `rocket_engine.interfaces.engine_ecs_store` resolves, then
   regen: `python scripts/api_spec.py --write && python scripts/contract.py
   --write` (both report stale before, fresh after — no `STUB_OVERLAP`
   additions: new engine names have no stub counterpart yet, which the
   contract tolerates).
3. Run: `.venv/bin/python -m pytest tests/test_engine_ecs_store.py
   tests/test_engine_ecs_wiring.py tests/project/test_crud_api.py
   tests/test_api_spec.py tests/test_contract.py tests/test_check_contract.py
   tests/test_docstrings.py -q` → all green (92 passed + 1 pre-existing skip
   in the copy).

Evidence: built the rebased patch in `/tmp/ecs-port` (throwaway HEAD export,
real tree untouched) with a `rocket_engine` symlink + lock-pinned dep-copy
`PYTHONPATH` shims under scratch pytest (no reinstall, no `.venv`, no
`uv sync`): 39 unit + 11 wiring green live; api_spec and contract both went
stale → `--write` → `--check` exit 0, with the new names present in
`docs/engine-api.md`, `docs/api-schema.json`, `docs/api-help.json`, and
`docs/contract.json`; gate suites 92 passed + 1 pre-existing skip; docstring
gate exit 0 on all touched files; fresh-export apply byte-identical. Scratch
copies left under `/tmp` for review, out of the deliverable.

## Wiring patch summary (exact bytes in `wiring.patch`)

`src/interfaces/vocabulary.py` (+4): OPERATIONS gains `create_entity`,
`set_component`, `attach_component`, `detach_component`, `delete_entity`;
QUERIES gains `get_component`, `components_of`, `entities_with`,
`get_world_snapshot`.

`src/composition.py` (+98/−1): `QUERY_METHODS` maps the four reads
(`get_world_snapshot` → `world_snapshot`); `_CRUD_OPERATIONS` gains the five
writes (immediate, CRUD precedent); `Engine.submit` dispatches the reads with
argument checks (after `get_resolved_config`) and routes the writes through
`_submit_crud` (after `write_settings`, before the `apply_mutations` tail);
the `submit` docstring Raises covers the new codes.

`src/project/service.py` (+753): imports `engine_ecs_store`; private seams
`_entity_records`, `_backfill_records`, `_find_backfill`,
`_read_backfill_component`, `_read_entity_record`, `_store_entity_record`,
`_ecs_response`; reads `get_component`, `components_of`, `entities_with`,
`world_snapshot` (pure reads, revision untouched); mutations `create_entity`,
`set_component`, `attach_component`, `detach_component`, `delete_entity` with
full admission (replay check → validate → revision gate → snapshot → store →
capture → advance → `entity_created` / `component_changed` / `entity_deleted`
→ CRUD-shaped response → persist, with rollback on snapshot failure).
`EcsError` codes surface through `ProjectError` unchanged (`unknown_entity`,
`unknown_component`, `component_exists`, `backfill_readonly`,
`invalid_entity`, `invalid_component`, `invalid_data`, `invalid_predicate`,
`invalid_document`, …).

## Refusals / constraints honored

- No existing file edited in the real tree (verified: `git status` shows only
  `??` entries; all wiring delivered as the patch above).
- `tests/pdk_*/` and `docs/pdk/*/` untouched; `ASAP7-DRC-DECK` files and all
  peer-lane untracked files untouched; full suite never run (only the new
  tests plus the named neighbors above).
- No `.venv` use at all (not even the interpreter), no `uv sync`, no installs
  into the repo (scratch venv + read-only `PYTHONPATH` shims; no extra deps —
  the module is stdlib + `json`).
- Nothing committed, nothing pushed.
- Nothing in the ticket was refused: every clause above is implemented,
  tested, and regen-verified.
