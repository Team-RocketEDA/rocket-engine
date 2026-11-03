Why: the user wants the ECS flow stated as law (change -> world
manager -> modify -> notify subscribers) and asked whether the
`esper` Python ECS library can replace our handrolled
`src/stores/ecs.py`.

Docs read (esper README + API reference, esper 3.x): MIT, pure
Python, zero dependencies; module-level functions (the World
object is gone in 3.x, named contexts switch process-global
state); integer entity IDs; `get_component`/`get_components`
queries; processors with `process()`; pub/sub is stringly-named
`dispatch_event(name, *args)` + `set_handler(name, func)` with
minimal error checking.

Verdict: do NOT wholesale-replace. esper is in-memory only — no
stable string IDs (it mints ints; the engine needs `ent-<12hex>`
for docs/ledger/rewind), no doc projection, no revision gates,
no idempotent replay, no ledger, no backfill. Adopting it as the
core would delete the durability story and add a second identity
system, which `ecs.py`'s own header forbids. Its event dispatch
is also untyped by-name, weaker than our ledger events.

Do instead, in order:

1. Split `src/stores/ecs.py` (1508 lines, 3x the 500-line module
   rule) into one-word-per-level submodules (e.g. stores/ecs/
   with addressing, records, queries, backfill separated), no
   behavior change, honesty scan kept green.
2. Add the missing half of ENGINE-ECS-FLOW: an in-process
   synchronous subscriber registry beside the ledger. Mutations
   already modify-then-append-`component_changed`; the registry
   delivers exactly that appended event to subscribers (adapters,
   watch fan-out) instead of forcing every consumer to poll.
   Same event shape, never a second invention.
3. Revisit esper only for processor-style passes behind the seam
   (if ever), never as the entity manager.

Record the flow as ENGINE-ECS-FLOW in behavior-invariants.yaml
(done with this ticket's first commit).
