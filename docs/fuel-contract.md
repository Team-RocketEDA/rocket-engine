# Fuel contract: pin, handshake, and recipe (FUEL-CONTRACT, engine side)

Fuel's `mcp-stub` is a mock engine with its own shapes; left alone
it becomes a fantasy engine fuel codes against. This contract is the
codesign seam (`docs/prd-feedforward.md` F13): the engine
publishes versioned truth, the stub pins to it, and skew fails
loudly. Ticket stays in Doing until fuel lands its side.

## The three files

| File | Owner | Rule |
|---|---|---|
| `docs/contract.json` | generated (`scripts/contract.py --write`) | never hand-edit; freshness-pinned by `tests/test_contract.py` |
| `scripts/check_contract.py` | engine source, stdlib-only | reference it from fuel; never fork a copy |
| `docs/fuel-contract.md` | this file, hand-written | prose + recipe; field lists live in the artifact |

`docs/contract.json` carries the API-GEN-B schemas (`operations`,
`queries` — byte-identical to `scripts/api_spec.py` output), the
`envelopes` (submit/ack/completion/ledger shapes probed from live
engine behavior with a fake solver, no tools), and `stub_overlap`
(the overlap map plus known gaps). Regenerate after any docstring,
envelope, or overlap-tuple change:

```sh
cd rocket-engine
.venv/bin/python scripts/contract.py --write
.venv/bin/python scripts/contract.py --check   # exit 0 when current
```

## Version and pin

- `contract_version` names the tooling line:
  `rocketeda/tooling/v<major>.<minor>` from the engine release
  (today `rocketeda/tooling/v0.0` at engine `0.0.1`).
- `schema_sha256` pins the exact checkable bits: schemas,
  envelopes, and overlap `(tool, side, field, ref)` tuples.
  Mapping notes, `known_gaps`, and `fuel_owned` are explanatory
  prose and do not invalidate pins.
- The stub records both in `mcp-stub/contract.pin`:

```json
{"contract_version": "rocketeda/tooling/v0.0", "schema_sha256": "<64 hex>"}
```

Handshake: the drift check compares the pin against the live
engine contract. Either half skewed is a stale stub — exit 1
naming expected vs found, never a silent pass. A missing pin
warns loudly but stays exit 0 (shapes checked, version open).

GAP ids are never reused or renumbered; fuel automation may key
on them.

## Request/run id plumbing (the audit join)

Fuel mints the request id; the engine mints run ids; both logs
carry both ids so `rocket_fuel/.rocket/audit.jsonl` and the engine
`events.yaml` join on `(request_id, run_id)`.

Submit envelope (`Engine.submit`): `project_id`, `operation`,
`arguments` (carries `expected_revision` for ops), `request_id`
— all four required by contract. The engine defaults `request_id`
and `arguments` when absent (ad-hoc callers), but fuel MUST always
send both: the request id is the idempotency key (resubmit the
identical envelope → identical ack) and the cross-phase join key.

Phase 1 `submit(op)` → ack `{request_id, project_id, run_id,
snapshot_id, state: queued, current_revision, event_cursor}` plus
a `job_queued` ledger event carrying `(request_id, run_id)`.
Phase 2 `submit(run_job, {request_id})` → completion `{run_id,
state: completed, verdict, operation}` plus a `run_completed`
(PASS/FAIL) or `run_failed` (NOT_RUN) event carrying
`(request_id, run_id, verdict)`.

Fuel's audit entry for every engine tool call MUST log the
`request_id` it sent and the `run_id`(s) it got back, keyed by its
own `sessionID`/`callID`. Engine-side every event already carries
`actor` (fuel uses `rocket-fuel`), `request_id`, and `run_id`.

Known duality (GAP-3): on GREEN-the-tests the submit-ack `run_id`
(queue id) DIFFERS from the `run_job` completion `run_id`
(execution id) — join across phases by `request_id`, and never
assume the two run ids are equal. `merge/fuel-mcp` decides the
ack `run_id` IS the execution id with `run_job` accepting `run_id`
or `request_id`; that lands with the PR3-MERGE integration, and
this contract will say so when it does.

## Overlap map (tool level; fields authoritative in the artifact)

Today both sides agree on exactly one field with shared meaning:
`run_id` names the execution id. Five mappings pin it across
`run_job` / `get_job_status` / `get_logs` (request + response).
Everything else real-but-unmatched is a documented gap, and
stub-only workflow tools are fuel-owned — see
`docs/contract.json` `stub_overlap` for the normative text:

- GAP-1 request_id carriage (stub takes kind/hypothesis, not the
  admission id) · GAP-2 job queries unwired engine-side (shared
  shapes pinned, not same-name wiring) · GAP-3 ack/completion
  run_id duality · GAP-4 error shapes unconverged · GAP-5
  constraints ownership (caller targets).
- Fuel-owned (no engine counterpart, never drift-checked):
  `get_constraints`, `get_status`, `propose_revision`,
  `apply_revision`, `propose_constraint_change`, `ip_search`,
  `ip_get`, `ip_register`.

To extend the overlap, add a mapping tuple in
`scripts/contract.py` `STUB_OVERLAP` and regenerate — the checker
reads the map from the artifact, never its own copy.

## Recipe: fuel-side stub pinning (exact commands)

Assumes sibling checkouts (`rocket-engine/` and `rocket_fuel/`
side by side); otherwise pass `--engine-root` / `--stub-root`
explicitly. The checker needs only Python 3.12+, no venv.

1. Drift-check the current stub (from either repo):

```sh
cd rocket_fuel && python3 ../rocket-engine/scripts/check_contract.py
cd rocket-engine && .venv/bin/python scripts/check_contract.py
```

Green looks like this (warning until step 2 lands the pin):

```text
contract OK: 5 mappings green against rocketeda/tooling/v0.0 (schema 2b9bc4068222…)
WARNING: stub is not pinned (no contract.pin beside mcp-stub) — drift shapes checked, version not pinned. Pin per docs/fuel-contract.md recipe.
```

2. Write the pin from the live engine contract (never hand-type
   the hash):

```sh
cd rocket_fuel
python3 -c "import json; d=json.load(open('../rocket-engine/docs/contract.json')); json.dump({'contract_version': d['contract_version'], 'schema_sha256': d['schema_sha256']}, open('mcp-stub/contract.pin', 'w'), indent=2)"
git add mcp-stub/contract.pin && git commit -m "chore(stub): pin engine <contract_version>"
```

3. Re-verify — the warning becomes a pin line, still exit 0:

```sh
python3 ../rocket-engine/scripts/check_contract.py
```

```text
contract OK: 5 mappings green against rocketeda/tooling/v0.0 (schema 2b9bc4068222…)
pin OK: mcp-stub/contract.pin matches engine contract
```

4. On an engine bump (fuel maintainer): pull the engine,
   re-run step 1, re-run step 2 (the hash changed → old pin
   fails `stale pin` naming expected vs found), commit the pin.

5. On a drift failure: the message names the skewed field, the
   tool, and the side (`stub 'get_logs' lost argument 'run_id'`
   vs `engine '…' is gone`). Stub-side rename → fix the stub or
   extend `STUB_OVERLAP` engine-side and re-pin; engine-side
   removal → the engine broke its contract, do not work around
   it in the stub.

6. Suggested fuel CI line (fails the build on drift or staleness):

```sh
python3 ../rocket-engine/scripts/check_contract.py
```

## Pointers

- Ticket `docs/tickets/FUEL-CONTRACT.md` (field notes, stays Doing).
- Contract source doctrine: `AGENTS.md` + ADR-003.
- Agent-path decisions already taken on `merge/fuel-mcp`
  (run_job-by-run_id, four job queries, constraints refusal):
  `docs/tickets/PR3-MERGE.md` field notes; integration pending.
