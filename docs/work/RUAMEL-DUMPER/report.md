# RUAMEL-DUMPER lane report — fresh dumpers for Engine/ProjectService YAML writes

Ticket: `docs/tickets/RUAMEL-DUMPER.md` · Branch: GREEN-the-tests.

NOTE: the lane agent errored (runtime approval-capacity failure) before
filing a report, so the integrator reconstructed this record from the
landed RED-first sources + tests and verified the wiring live. One
wiring-test expectation was corrected (see below); no lane behavior
was invented.

## Failure mode (from CONSOLE-ROUTE)

A failed ruamel `YAML(typ="safe").dump` poisons that dumper
instance: every later dump through it emits empty text instead of
raising. Engine/ProjectService wrote through long-lived shared
dumpers, so one failed write could silently hollow all later
writes (and collapse ledger idempotency identities onto "").

## Files added (new files only)

- `src/interfaces/yaml_dump.py` — `dump_yaml_text(data)`:
  one YAML text through a fresh dumper per call.
- `tests/interfaces/test_yaml_dump.py` — unit pin: byte-equality
  with a direct fresh dump, poison isolation, never-empty,
  round-trip, distinct identities.
- `tests/interfaces/test_yaml_dump_wiring.py` — integrator-run
  wiring proofs: skip loudly while `self._yaml.dump` remains in
  composition source, run real Engine submissions after.
- `docs/work/RUAMEL-DUMPER/wiring.patch` + this report.

## Wiring (integrator-applied, recorded in wiring.patch)

`src/composition.py` only:

- All 4 `self._yaml.dump` sites (submit admission, CRUD
  immediate, python_execute admission, findings verdict) dump
  through `dump_yaml_text` instead.
- Removed the shared `self._yaml` instance plus the now-unused
  `import io` / `from ruamel.yaml import YAML` (verified:
  instance was dumps-only, no other `io.`/`YAML(`/`_yaml`
  users in the module, no test references `engine._yaml`).
- `src/project/service.py`: NO change — its writer already
  dumps per call (`_dump_yaml` builds a fresh dumper), and it
  keeps `self._yaml` for loads only. Same for
  `src/interfaces/settings_store.py` (fresh per call).

## Integrator test correction

`test_engine_happy_path_bytes_unchanged` expected the stored
command text to equal a fresh dump of the caller-supplied
arguments — but RUN-PARAMS `_apply_run_request` freezes
`request` to all defaults on EVERY submit before the identity
dump (pre-existing behavior, unchanged by this lane). The test
now builds the expectation from the admitted arguments
(`validate_run_request(None)` for the frozen knobs). Intent
preserved: wiring must not alter happy-path bytes.

Style note (verified, not a defect): this tree's ruamel 0.19.1
`typ="safe"` emits flow style for shallow mappings and block
style once a deeper nested mapping is present — deterministic
per content, identical pre/post patch for identical input
(shared vs fresh instances share version + config).

## Suite + gates (integrator-measured)

- Lane: 9/9 pass (5 unit + 4 wiring, wiring flipped skip→pass).
- Wide neighbor net (submit-path blast radius): engine_run,
  contract, coalesce ×2, project, execution, cli, mcp_server,
  mcp_live — 346 passed, 45 skipped (live/env-gated).
- Gates: api_spec, check_contract, docstrings, no_cloud green;
  check_docstrings + check_no_cloud clean; 100-col holds.
- Regen: api_spec --write + contract --write moved ZERO docs
  (no adapter/docstring surface changed) — verified clean tree
  besides wiring.
