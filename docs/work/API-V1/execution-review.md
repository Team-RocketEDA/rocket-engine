# Engine v1 execution contract review

Review date: 2026-11-01. Scope: admission, scheduling, concurrency, run control,
recovery, discovery and the contract migration. This is design evidence and a
required acceptance matrix; it is not a claim that these behaviors are implemented
or verified. The canonical v1 contract and its adoption ADR resolve the API shape.

## Existing decisions that remain binding

- [ADR-011](../../adr/011-one-runtime-durable-admission-and-client-neutral-operations.md):
  one EngineRuntime owns the ledger, scheduler, admission, coalescing and events.
  Valid accepted requests are durably recorded before acknowledgement and dispatch
  immediately when capacity and dependencies permit. FIFO is a burst buffer and
  recovery mechanism. A second `run_job` start handshake is unnecessary.
- [ADR-008](../../adr/008-per-entity-cas.md): edits use per-entity compare-and-swap.
  Different-entity edits can both commit; same-entity races conflict explicitly.
  The global project revision remains the snapshot, event and coalescing cursor.
- [ADR-004](../../adr/004-engine-side-op-gates.md): hard prerequisites and verdict
  gates are engine-owned. Hard prerequisite failures cannot be overridden.
- [REPLAY](../../tickets/REPLAY.md): a replay command for finished runs was
  explicitly decided against. A fresh submission can consume retained pinned
  inputs when the user wants another execution. I28 requires ingredient retention
  and reproducibility, not a dedicated replay API.
- [REPLAY-SAFE](../../tickets/REPLAY-SAFE.md): startup reports unfinished survivors
  and executes none automatically. Resume/discard is explicit. Repeatedly
  interrupted content is quarantined according to the recorded poison rules.
- [I28 and related invariants](../../../../PRD/tools-research/behavior-invariants.yaml):
  project state, authored views, source/model closure, technology, tool versions,
  decks, seeds and resolved settings consumed by a run are pinned ingredients.
  Regenerated native output bytes need not be identical; verdicts, findings and
  measurements must be reproducible under the stated comparison rules.

## Minimal method responsibilities

`describe` reads the contract registry and returns method/operation descriptions,
schemas, accepted target scopes and views, side effects and capability readiness.
It does not instantiate another engine or execute project imports.

`query` reads project state, catalogs, hierarchy, runs, findings, logs and artifacts
with explicit source/container arguments, stable cursors and a reported revision.

`edit` applies typed design transactions atomically. It checks entity versions,
validates all changes before commit, advances the project revision once and emits
durable attributed events. Retrying the same request returns its stored outcome.

`run` owns execution lifecycle: start, cancel, explicit survivor resume and discard.
Run control belongs here rather than in design edits. Completed runs have no
dedicated replay action.

`script` provides Python/library execution while reusing normal admission, run
receipts, worker isolation, event and evidence schemas. Project mutations pass
through the editor transaction boundary. Mutating scripts never share execution
merely because their source text matches.

`watch` delivers ordered cursor-based events including project revisions, run
progress, findings, script output and admission pause/resume information. Expired
cursors fail explicitly and identify how to obtain a fresh snapshot.

## Admission and scheduling semantics

### Durable acknowledgement and responsive controls

An admitted receipt identifies the request, project, run, pinned snapshot and event
cursor. The request and its identity mapping are durable before that receipt is
sent. A disconnect after acknowledgement does not discard the request. A caller
can query the original request ID to recover the associated run and receipt.

Capacity exhaustion before admission returns a typed retryable refusal with
`admitted: false`. Clients pause their submissions and retain the original request
ID and payload. Capacity signals are advisory: a race can consume the final slot
between observing availability and submitting. The admission result is decisive.
Once capacity returns, an unchanged retry admits at most once.

Read/discovery/event delivery and run control remain responsive while solver
admission is saturated. Cancellation cannot require an additional heavy-job slot.
Short editor commits use a project writer lane and do not wait behind a long
solver. Solvers consume immutable snapshots; an editor commit cannot change a
running operation's later inputs.

### Coalescing and request identity

Request idempotency and run coalescing are separate mechanisms. Reusing a request
ID with identical content returns the original outcome. Reusing it with different
content fails with `request_conflict`.

Equivalent in-flight observational runs can share execution only when their project,
global revision, target, normalized operation/options, deck and pinned inputs match.
Every caller's request ID maps to the shared run ID. An intervening mutation,
different arguments or an explicit fresh execution creates separate work. Completed
results are fetched by identity rather than treated as newly coalesced execution.
Mutating scripts and editor transactions are not collapsed by content similarity.

Do not overload one `force` flag: bypassing coalescing, overriding an allowed verdict
gate and overriding poison quarantine express different intentions. None permits
bypassing hard prerequisites, revision conflicts, invalid input or unavailable
required ingredients.

### State, verdict and cancellation

Execution state and verification verdict are distinct. Successful tool completion
does not imply a passing DRC, LVS, simulation or formal result. Unsupported or
missing stages cannot silently become PASS. A cancellation/completion race produces
one truthful outcome, retains partial evidence and records the lifecycle in the
ledger. Cancellation requests must be attributable even when the worker completes
before cancellation takes effect.

Startup reconciliation retains admitted identity and pinned inputs. It reports
never-started and interrupted survivors without executing them. Explicit resume
uses the retained ingredients and reports drift or unavailable dependencies rather
than silently substituting the current project head. The existing policy offers
one explicit resume for ambiguous interruption and quarantines a content key after
two interruptions; a further resume requires explicit quarantine override.

### Error contract

Every transport preserves a shared error code, friendly message, structured
details, retryability, admission status and correlation identifiers. Optional retry
timing belongs in structured data. Suggested code families include malformed
request, unknown operation/resource, unsupported target, unavailable capability,
revision/request conflict, full admission, ingredient drift, failed prerequisite,
quarantined execution and expired event cursor. The canonical contract owns the
final spelling.

HTTP adapters map malformed requests to 400, missing resources to 404, state or
revision conflicts to 409, semantically invalid requests to 422 and temporary
admission exhaustion to 503 with `Retry-After`. Transport success codes never replace
the run's explicit state and verification verdict.

## Reconciliations required during adoption

| Existing surface | Required reconciliation |
|---|---|
| ADR-003 and contributor contract make docstrings authoritative | Adopt the canonical v1 schema through an explicit superseding ADR and update contributor rules. Keep current v0 generated documents stable until their migration; never hand-edit generated payload shapes. |
| Older handlers and contributor wording describe global `expected_revision` gating | Implement per-entity CAS for edits while retaining the global snapshot/event cursor. |
| Generated help declares `api_help`, `api_info`, `api_search` unwired | Implement v1 discovery from the canonical registry with accurate readiness rather than listing names as working endpoints. |
| MCP server documents inline submit and builds an Engine for help introspection | Route all clients to the one runtime, return prompt admission receipts and load help metadata without creating state owners. |
| Older batch paths require `run_job` pumping | Start dispatch after admission without a client round trip. |
| MCP-CONTRACT ticket says cancellation has no ledger event | Supersede that clause: cancellation intent and outcome require durable attributed lifecycle evidence. |
| I28 uses the old `canvas.cst` filename | Rename the active contract to `canvas.toml` through the schema migration; historical run ingredients retain their original recorded filename and bytes. |
| Ticket headers disagree with the board | Treat the script-driven board as the status index and inspect implementation/evidence independently. A Done label does not prove current conformance. |

The board was inspected read-only using `python3 scripts/sprint.py list`. It marks
SEAM-COSIM, COALESCE-I33, REPLAY-SAFE and API-GENERALIZE Done even where the ticket
document header still says Backlog or Ready. No board entries were changed by this
review.

## Required contract migration acceptance matrix

All entries below are required proofs, not results from this review.

| ID | Scenario | Required observable behavior |
|---|---|---|
| C01 | Every method request/result/error, empty collection and omitted/null case | Canonical schemas validate supported payloads and reject unknown semantic fields; examples are schema-valid. |
| C02 | Generate frontend, MCP, HTTP and framed-stdio consumers | Types, transport validators, help and fixtures derive from the same canonical artifact without independently maintained payload copies. |
| C03 | Discover installed and declared capabilities | Every method/operation has descriptions, schemas, scopes, side effects, readiness and actionable reasons; discovery constructs no second engine and executes no project source. |
| C04 | Frontend and MCP inspect/mutate/submit concurrently | One runtime, project state, admission state, run identity mapping, coalescer and event order are observed by both. |
| C05 | Two edits touch different entities; two edits race on one entity | Distinct entities both commit; exactly one same-entity writer wins and the loser receives the entity plus expected/actual versions. |
| C06 | Final change in an atomic edit is invalid | No partial files, revision advance or committed mutation event; errors identify the invalid change. |
| C07 | Admission saturates and then frees a slot | Refusal is retryable and not admitted; pause/resume is visible; retrying unchanged request identity admits exactly once. |
| C08 | Client disconnects after durable acknowledgement | The request/run association and pinned snapshot remain queryable and no accepted work is silently lost. |
| C09 | Five identical in-flight observational submissions | One execution, five recorded request identities and one shared run ID. |
| C10 | Identical operation after an intervening edit, changed arguments or explicit fresh execution | Separate executions; mutating scripts never coalesce by content. |
| C11 | Independent operations and a dependency-gated workflow | Independent work overlaps within resource limits; dependents obey engine-owned prerequisites and verdict gates; no start-pumping handshake is needed. |
| C12 | Heavy admission saturated during edits, discovery and cancellation | Control/read/event paths and short editor commits remain responsive; cancellation needs no new heavy-job slot. |
| C13 | Cancel races queued work, running work and just-completed work | One truthful terminal outcome, attributable lifecycle events, worker-tree termination where needed and retained partial artifacts. Exit zero alone never yields PASS. |
| C14 | Runtime is killed with acknowledged unfinished work and restarted | Zero automatic reexecution; complete survivor report; explicit resume/discard; repeated interruption enforces quarantine. |
| C15 | A consumed source/model/deck/profile/config/tool ingredient changes | The original consumed revision remains pinned or drift is reported by field; current state is never silently substituted. |
| C16 | Watch reconnects, repeats a cursor or requests an expired cursor | Ordered, deduplicable delivery with stable identifiers; explicit cursor-expired response and documented snapshot/resubscribe path. |
| C17 | v0 consumer runs during v1 migration | Existing behavior remains stable until an explicit migration adapter/version switch; breaking differences are documented and provider/consumer conformance passes. |

