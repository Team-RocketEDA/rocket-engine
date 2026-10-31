# WIRE-PLACE lane report — Wire/junction entities + connect ops

Ticket: `docs/tickets/WIRE-PLACE.md` · Branch: GREEN-the-tests ·
No commits, no pushes (integrator commits).

Verify lane (HEAD `cf9a5d0`): re-ran the standalone suite RED→GREEN,
confirmed the full-suite 1-failure note, and regenerated the wiring
patch against the drifted tree (same added lines, fresh context).

## Files added (new files only — zero edits to existing files)

- `src/interfaces/wireplace.py` — Wire/Junction/Net component schemas +
  validators, ops `place_wire`/`place_junction`/`connect_endpoint`/
  `move_wire`/`split_wire`/`delete_wire`/`delete_junction`/
  `materialize_nets` (each exactly one attributed store transaction),
  `world_schematic` extraction glue, `collect_wire_erc` findings.
  Stdlib + `.errors` only at import time; CONNECT-GRAPH extraction is a
  function-local import inside `materialize_nets` (default, injectable).
- `tests/interfaces/test_wireplace.py` — schema validation, all wire/
  junction ops, and ERC through `FakeEntityStore` (in-memory stand-in
  for the requested ENGINE-ECS seam; also imported by the nets file).
- `tests/interfaces/test_wireplace_nets.py` — extraction glue, stable
  Net materialization, SPICE/raw-IR name parity, junction taps,
  crossing isolation, prune, and the place→wire→verdict→rewind loop.
- `tests/interfaces/test_wireplace_wiring.py` — 4 post-patch
  integration tests the integrator runs AFTER applying the wiring
  patch below (skip until then in a minimal env; the MCP probe fails
  pre-patch in a full env — that is the suite's expected 1 failure —
  and the submit round-trip additionally needs the ENGINE-ECS store).
- `docs/work/WIRE-PLACE/wiring.patch` — the integrator patch as a
  file (byte-identical to the embedded diff below).
- `docs/work/WIRE-PLACE/report.md` — this file.

Naming note: the lane rule asks for `test_<ticket>_<name>.py`, but the
ticket stem `WIRE-PLACE` is not an importable module name, so this lane
follows the CELL-LINK precedent (`test_wireplace*.py`,
`src/interfaces/wireplace.py` — the ticket's own suggested module).

## Contract implemented (ticket clause → behavior)

- Wire entity (segments, layer, endpoints) + Junction entity (explicit
  dots, never accidental crossings) — `Wire` holds integer polylines, a
  layer, and exactly `[a, b]` endpoints with xy pinned to the polyline
  ends; `Junction` holds xy + layer. Joins happen only at shared
  endpoints, T-taps, or referenced junctions; crossing interiors never
  connect (tested: two crossing wires extract as two nets).
- Ops `place_wire`, `connect_endpoint`, `move_wire`, `split_wire`,
  `delete_wire` as durable attributed revisions through the entity
  store — every op runs as exactly one `transact` (one revision, one
  description, actor on every event). `place_junction`/
  `delete_junction`/`materialize_nets` complete the surface the ticket
  implies (dots must be creatable; nets must materialize). No-ops
  (same ref, zero move, unchanged world) return a None-revision receipt
  and write nothing.
- Endpoints reference pin/port/junction/net entity IDs (ENGINE-ECS);
  dangling endpoints allowed transiently, flagged by ERC, never
  silently dropped — null refs are legal and yield
  `wire.dangling_endpoint` warnings; refs to deleted entities yield
  `wire.unknown_ref` errors; spans whose xy no longer meets a
  pin/junction target yield `wire.stale_geometry` warnings; junctions
  touching nothing yield `wire.orphan_junction` warnings. Deleting a
  referenced junction is refused (`junction_in_use`). Wire/self refs
  are rejected at edit time (`invalid_ref`).
- Nets derived from CONNECT-GRAPH extraction, then materialized as Net
  entities with stable IDs under the shared `net_name()` authority —
  `world_schematic` feeds stored wires + caller pins/labels/ports into
  `prepare_netlist_structs` (always rebuilt, never cached); groups
  sharing a canonical name merge into one Net keyed by that name, so a
  repeat materialization returns identical IDs (tested) and the
  raw-IR/SPICE emitter names match the stored Nets exactly (tested).
  Net-ref endpoints tap by name via synthesized labels; vanished names
  prune in the same revision; stale refs land in `unresolved`.
- Agent loop shape place → wire → simulate → verdict, all durable, all
  rewindable — every op returns ledger-grade receipts
  (revision + events); the suite proves place → wire → materialize →
  ERC verdict → rewind removes wire + net cleanly.

Error codes (`ContractError`): `invalid_wire`, `invalid_junction`,
`invalid_net`, `invalid_pin`, `invalid_label`, `invalid_port`,
`invalid_cell`, `invalid_endpoint`, `invalid_geometry`,
`invalid_split`, `invalid_ref`, `invalid_actor`, `invalid_policy`,
`unknown_wire`, `unknown_junction`, `unknown_ref`,
`junction_in_use`, `extraction_failed`. The patch maps them 1:1 onto
`ProjectError` so transports keep stable codes.

## ENGINE-ECS exact interface request (its module is not on disk)

No entity-store code was found in-tree (`create_entity`, `entity_store`,
`component_changed` have zero hits in `src/`), so this lane ships no
storage: every op takes a `store` serving the seam below. The
ENGINE-ECS lane implements it durably (projected over docs/ledger per
its ticket) and exposes it at `ProjectService._entities`; the wiring
patch reads only that attribute. `FakeEntityStore` in
`tests/interfaces/test_wireplace.py` is the executable reference.

Reads (return deep copies; unknown entity/component → `LookupError`):

- `components_of(entity) -> {component: value}`
- `get_component(entity, component) -> value`
- `entities_with(component, predicate=None) -> [id]` in ID order.

Writes (each its own revision; `transact` is the only writer the wire
ops use — one op, one revision, all-or-nothing on any failure):

- `create_entity(actor, description) -> {"id", "revision"}` (engine-provisioned IDs only)
- `set_component(actor, entity, component, value, description) -> {"revision"}`
- `attach_component(actor, entity, component, value, description) -> {"revision"}`
- `detach_component(actor, entity, component, description) -> {"revision"}`
- `delete_entity(actor, entity, description) -> {"revision"}`
- `transact(actor, description, calls) -> {"revision", "aliases", "events"}`
  where each call is `{"verb", "args", "alias"?}` with verbs mirroring
  the five writers above (same arg names, minus actor/description);
  `{"alias": name}` values resolve — at any depth — to IDs created
  earlier in the same transaction; unknown verbs/aliases fail the whole
  transaction. Events: `component_changed` per set/attach/detach
  `{event, entity, component, revision, actor}`, `entity_created` /
  `entity_deleted` `{event, entity, revision, actor}`.
- `events_since(cursor) -> [...]` over the transact events.

Wire ops never call the single writers (the fake still implements them;
one test uses `delete_entity` to simulate target removal). Store
revisions are the store's internal counter; the ledger revision stays
the durable head — patch responses carry both.

Late coordination note (read-only survey, no peer files touched): the
ENGINE-ECS lane's WIP appeared on disk (`src/interfaces/
engine_ecs_store.py`, `docs/work/ENGINE-ECS/wiring.patch`) after this
lane's seam was fixed. Its verb *names* match this seam exactly, but
the shapes diverge: verbs are `ProjectService` methods with per-verb
admission (`request_id`, `expected_revision`, actor from the service —
no actor/description params), errors are `EcsError`/`ProjectError`
codes (not `LookupError`), and there is no multi-verb `transact`
(their `EntityStore` class is a standalone double, not a bound store).
Reconciliation for the integrator (no WIRE-PLACE rewrite needed): bind
a ~50-line adapter implementing this seam over the peer's
`ProjectService` verbs — reads delegate with `unknown_entity`/
`unknown_component` mapped to `LookupError`, `transact` runs calls
sequentially with alias threading (one logical op; physically one
ledger revision per verb until/unless the peer adds a batch verb) —
and point the patch's `_entity_store()` at the adapter instead of
`self._entities`. Caveat: the peer `wiring.patch` itself is stale at
HEAD `cf9a5d0` (its service.py hunk fails dry-run), so its owner must
regenerate it first; re-verify this lane's patch dry-run at apply
time on the shared tree.

## RED → GREEN evidence

Toolchain: `/tmp/wireplace-venv` (scratch, pytest + ruamel + mcp from
the index) with a `site-packages/rocket_engine -> src` symlink. Repo
`.venv` untouched, no `uv sync`.

RED (module temporarily moved aside; restored byte-identical after):

    mv src/interfaces/wireplace.py /tmp/wireplace_hidden_red.py
    /tmp/wireplace-venv/bin/python -m pytest tests/interfaces/test_wireplace.py \
      tests/interfaces/test_wireplace_nets.py tests/interfaces/test_wireplace_wiring.py -q
    # 2 errors during collection — both behavior files fail with
    # ModuleNotFoundError: No module named 'rocket_engine.interfaces.wireplace'
    mv /tmp/wireplace_hidden_red.py src/interfaces/wireplace.py

GREEN (module restored; first run green, no module fixes needed):

    # same three-file command, minimal env (no mcp):
    # 49 passed, 4 skipped in 0.08s (skips = wiring tests awaiting the patch)

Expected unwired RED in a full env (this lane's full-suite 1 failure):

    /tmp/wireplace-venv/bin/pip install "mcp>=1.0,<3"   # scratch env only
    # same three-file command:
    # 1 failed, 49 passed, 3 skipped
    # FAILED test_mcp_tool_describes_wire_operations — describe_tool
    # reports "Declared query `place_wire`; no handler wired yet."
    # pre-patch. By design: it asserts the wired state and turns green
    # only after the integrator applies the patch below. Without mcp
    # installed the same probe skips instead of failing.

Named neighbors (never the full suite):

    /tmp/wireplace-venv/bin/python -m pytest tests/interfaces/test_references.py \
      tests/test_docstrings.py tests/test_no_cloud.py \
      tests/workflows/test_connect_graph_extract.py \
      tests/workflows/test_connect_graph_emit.py -q
    # 34 passed (docstring gate scans the new module too)
    /tmp/wireplace-venv/bin/python scripts/check_docstrings.py
    # clean (exit 0)
    /tmp/wireplace-venv/bin/python scripts/check_docstrings.py \
      <patched copies of wireplace.py, service.py, composition.py, __init__.py, vocabulary.py>
    # clean (exit 0)

Style: no line over 100 chars in new files, the patch file, or
patch-added lines.

## Wiring patch for the integrator (exact unified diff)

Also shipped as `docs/work/WIRE-PLACE/wiring.patch` (byte-identical
to the block below; prefer the file). Regenerated three times as the
tree moved: RUN-PARAMS, then APIG `place_cell`/`apig_assets`, and now
— for HEAD `cf9a5d0` — settings-store imports, `write_settings` in
the CRUD set, and the `_submit_crud` extraction. Each prior version
failed dry-run on the new bytes and was discarded (one intermediate
regen was also discarded after verification caught it carrying peer
reversions). This regen reuses the prior patch's added lines verbatim
— machine-checked identical per file, single `-` line unchanged (the
composition comment rewrap) — with fresh hunk context only.

Apply with `patch -p1 < docs/work/WIRE-PLACE/wiring.patch` from the
repo root, AFTER the ENGINE-ECS patch (see the seam note above for the
`_entities` reconciliation); order with other CRUD lanes does not
matter otherwise. MCP exposure is automatic: `describe_tool` serves
`ProjectService.<op>` summaries and `McpTransport` routes through
`Engine.submit` — no server.py change.

Verified: `git apply --check` and `patch -p1 --dry-run` clean with
zero offsets on the current tree (HEAD `cf9a5d0`, clean working tree
apart from untracked lane files), all four files `py_compile`,
`check_docstrings.py` clean on the patched copies, every added line
≤100 chars, `/tmp/wp_verify_patch.py` green on a /tmp patched-tree
copy (service admission incl. replay/revision-gate/noop/materialize/
ContractError mapping, missing-store honest failure on all 8 ops,
Engine routing for all 8 ops + arg gate, api_spec wired + schemas +
help for all 8, MCP describe for all 8), and the new wiring tests run
against the patched tree copy
(3 passed, 1 skipped — round-trip awaits the ENGINE-ECS store).

```diff
--- a/src/interfaces/__init__.py
+++ b/src/interfaces/__init__.py
@@ -27,6 +27,21 @@
     parse_run_request,
     validate_run_request,
 )
+from .wireplace import (
+    collect_wire_erc,
+    connect_endpoint,
+    delete_junction,
+    delete_wire,
+    materialize_nets,
+    move_wire,
+    place_junction,
+    place_wire,
+    split_wire,
+    validate_junction,
+    validate_net,
+    validate_wire,
+    world_schematic,
+)
 
 __all__ = [
     "NETLIST_TYPES",
@@ -41,17 +56,30 @@
     "asset_manifest",
     "check_connection",
     "collect_erc",
+    "collect_wire_erc",
+    "connect_endpoint",
+    "delete_junction",
+    "delete_wire",
     "freeze_run_request",
     "list_assets",
     "match_cell_filters",
+    "materialize_nets",
+    "move_wire",
     "parse_run_request",
+    "place_junction",
+    "place_wire",
     "resolve_cell",
     "resolve_link",
     "resolve_pin",
     "resolve_reference",
     "resolve_run",
     "serve_asset",
+    "split_wire",
     "validate_celllink",
     "validate_document",
+    "validate_junction",
+    "validate_net",
     "validate_run_request",
+    "validate_wire",
+    "world_schematic",
 ]
--- a/src/interfaces/vocabulary.py
+++ b/src/interfaces/vocabulary.py
@@ -13,6 +13,8 @@
         "run_view_sync", "run_job",
         "create_project", "write_doc", "delete_doc", "apply_mutations",
         "rewind", "place_cell", "write_settings",
+        "place_wire", "place_junction", "connect_endpoint", "move_wire",
+        "split_wire", "delete_wire", "delete_junction", "materialize_nets",
     }
 )
 QUERIES = frozenset(
--- a/src/composition.py
+++ b/src/composition.py
@@ -164,7 +164,9 @@
 # CRUD mutations + rewind execute immediately inside submit()
 # (run_job precedent): revision gate + idempotency + event logging,
 # no queue, no solver. Engine.run delegates them back to submit so
-# the CLI `run` path shares the one implementation.
+# the CLI `run` path shares the one implementation. Wire ops
+# (WIRE-PLACE) ride the same immediate path once the ENGINE-ECS
+# store lands; without it they report unsupported.
 _CRUD_OPERATIONS = frozenset(
     {
         "create_project",
@@ -173,6 +175,14 @@
         "apply_mutations",
         "rewind",
         "write_settings",
+        "place_wire",
+        "place_junction",
+        "connect_endpoint",
+        "move_wire",
+        "split_wire",
+        "delete_wire",
+        "delete_junction",
+        "materialize_nets",
     }
 )
 
@@ -610,6 +620,119 @@
                 command_text,
                 expected_revision=arguments.get("expected_revision"),
             )
+        if name == "place_wire":
+            for key in ("segments", "layer", "endpoints"):
+                if key not in arguments:
+                    raise ProjectError(
+                        "invalid_command",
+                        f"place_wire needs a {key} argument.",
+                    )
+            return self._project.place_wire(
+                arguments["segments"],
+                arguments["layer"],
+                arguments["endpoints"],
+                request_id,
+                command_text,
+                expected_revision=arguments.get("expected_revision"),
+            )
+        if name == "place_junction":
+            for key in ("xy", "layer"):
+                if key not in arguments:
+                    raise ProjectError(
+                        "invalid_command",
+                        f"place_junction needs a {key} argument.",
+                    )
+            return self._project.place_junction(
+                arguments["xy"],
+                arguments["layer"],
+                request_id,
+                command_text,
+                expected_revision=arguments.get("expected_revision"),
+            )
+        if name == "connect_endpoint":
+            for key in ("wire_id", "end", "ref"):
+                if key not in arguments:
+                    raise ProjectError(
+                        "invalid_command",
+                        f"connect_endpoint needs a {key} argument.",
+                    )
+            return self._project.connect_endpoint(
+                arguments["wire_id"],
+                arguments["end"],
+                arguments["ref"],
+                request_id,
+                command_text,
+                expected_revision=arguments.get("expected_revision"),
+            )
+        if name == "move_wire":
+            for key in ("wire_id", "dx", "dy"):
+                if key not in arguments:
+                    raise ProjectError(
+                        "invalid_command",
+                        f"move_wire needs a {key} argument.",
+                    )
+            return self._project.move_wire(
+                arguments["wire_id"],
+                arguments["dx"],
+                arguments["dy"],
+                request_id,
+                command_text,
+                expected_revision=arguments.get("expected_revision"),
+            )
+        if name == "split_wire":
+            for key in ("wire_id", "at"):
+                if key not in arguments:
+                    raise ProjectError(
+                        "invalid_command",
+                        f"split_wire needs a {key} argument.",
+                    )
+            return self._project.split_wire(
+                arguments["wire_id"],
+                arguments["at"],
+                request_id,
+                command_text,
+                expected_revision=arguments.get("expected_revision"),
+            )
+        if name == "delete_wire":
+            if "wire_id" not in arguments:
+                raise ProjectError(
+                    "invalid_command",
+                    "delete_wire needs a wire_id argument.",
+                )
+            return self._project.delete_wire(
+                arguments["wire_id"],
+                request_id,
+                command_text,
+                expected_revision=arguments.get("expected_revision"),
+            )
+        if name == "delete_junction":
+            if "junction_id" not in arguments:
+                raise ProjectError(
+                    "invalid_command",
+                    "delete_junction needs a junction_id argument.",
+                )
+            return self._project.delete_junction(
+                arguments["junction_id"],
+                request_id,
+                command_text,
+                expected_revision=arguments.get("expected_revision"),
+            )
+        if name == "materialize_nets":
+            if "pins" not in arguments:
+                raise ProjectError(
+                    "invalid_command",
+                    "materialize_nets needs a pins argument.",
+                )
+            return self._project.materialize_nets(
+                arguments["pins"],
+                request_id,
+                command_text,
+                labels=arguments.get("labels"),
+                ports=arguments.get("ports"),
+                cell=arguments.get("cell", "top"),
+                named_refs=arguments.get("named_refs"),
+                expected_revision=arguments.get("expected_revision"),
+            )
         if "mutations" not in arguments:
             raise ProjectError(
                 "invalid_command",
--- a/src/project/service.py
+++ b/src/project/service.py
@@ -42,6 +42,8 @@
 from ruamel.yaml import YAML
 
 from ..interfaces import settings_store
+from ..interfaces import wireplace
+from ..interfaces.errors import ContractError
 from ..interfaces.paths import join_contained, to_unix
 from .errors import ProjectError
 
@@ -1948,6 +1950,449 @@
         self._persist_after_mutation()
         return response
 
+    def _entity_store(self):
+        """Return the ENGINE-ECS entity store, or fail loudly without it.
+
+        WIRE-PLACE/ENGINE-ECS seam: the ENGINE-ECS patch owns the
+        durable store and exposes it at `self._entities`; until
+        that patch lands every wire op reports unsupported instead
+        of inventing storage here.
+
+        Returns:
+            Entity store serving the wireplace seam.
+
+        Raises:
+            ProjectError: unsupported_operation when the
+                ENGINE-ECS patch is not applied.
+        """
+        store = getattr(self, "_entities", None)
+        if store is None:
+            raise ProjectError(
+                "unsupported_operation",
+                "Wire ops need the ENGINE-ECS entity store, which is "
+                "not wired yet.",
+            )
+        return store
+
+    def _wire_mutation(self, operation, request_id, command_text,
+                       expected_revision, run, describe):
+        """Admit one wire op through the ledger admission machinery.
+
+        A resubmitted envelope returns its stored response; a new
+        envelope gates its expected_revision, snapshots the
+        previous head, runs the one-revision entity transact,
+        captures the new head, advances, and logs. A noop receipt
+        returns the head unadvanced with an empty event list.
+
+        Args:
+            operation: Wire operation name for the event data.
+            request_id: Client envelope id for idempotent replay.
+            command_text: YAML command text for identity comparison.
+            expected_revision: Revision the writer read.
+            run: Callable (store) -> wireplace receipt.
+            describe: Callable (receipt) -> diff summary text.
+
+        Returns:
+            Mutation mapping with the entity receipt, revision
+            transition, actor, diff summary, rewind handle,
+            appended event, cursor, and request id — or the
+            unadvanced noop mapping when the receipt is a noop.
+
+        Raises:
+            ProjectError: request_conflict for a reused id with
+                new text; revision_conflict for a stale head;
+                unsupported_operation without the ENGINE-ECS
+                store; the wire contract code (unknown_wire,
+                unknown_ref, ...) for a refused op.
+        """
+        self._refresh_durable()
+        replay = self._check_replay(request_id, command_text)
+        if replay is not None:
+            return replay
+        self._gate_revision(expected_revision)
+        store = self._entity_store()
+        previous = self._current_revision
+        self._ensure_snapshot(previous)
+        try:
+            receipt = run(store)
+        except ContractError as exc:
+            raise ProjectError(exc.code, str(exc)) from exc
+        if receipt.get("noop"):
+            response = {
+                "project_id": self._project_id,
+                "previous_revision": previous,
+                "current_revision": previous,
+                "revision_transition": {"from": previous, "to": previous},
+                "actor": self._actor,
+                "diff_summary": f"{operation} changed nothing",
+                "rewind_handle": {
+                    "project_id": self._project_id,
+                    "revision": previous,
+                    "request_id": request_id,
+                },
+                "noop": True,
+                "receipt": receipt,
+                "events": [],
+                "event_cursor": self._cursor(),
+                "request_id": request_id,
+            }
+            self._requests[request_id] = (command_text, response)
+            self._persist_after_mutation()
+            return response
+        advanced = _advance_revision(previous)
+        self._capture_snapshot(advanced)
+        self._current_revision = advanced
+        diff = describe(receipt)
+        record = self._append_event(
+            operation,
+            request_id,
+            {
+                "revision": self._current_revision,
+                "operation": operation,
+                "diff_summary": diff,
+                "receipt": receipt,
+            },
+        )
+        response = {
+            "project_id": self._project_id,
+            "previous_revision": previous,
+            "current_revision": self._current_revision,
+            "revision_transition": {
+                "from": previous,
+                "to": self._current_revision,
+            },
+            "actor": self._actor,
+            "diff_summary": diff,
+            "rewind_handle": {
+                "project_id": self._project_id,
+                "revision": previous,
+                "request_id": request_id,
+            },
+            "receipt": receipt,
+            "events": [record],
+            "event_cursor": self._cursor(),
+            "request_id": request_id,
+        }
+        self._requests[request_id] = (command_text, response)
+        self._persist_after_mutation()
+        return response
+
+    def place_wire(self, segments, layer, endpoints, request_id,
+                   command_text, expected_revision=None):
+        """Place one wire: gate, transact, advance, log.
+
+        A resubmitted envelope returns its stored response without
+        advancing; a new envelope gates its expected_revision, and
+        only an accepted placement advances the revision and
+        appends the place_wire event carrying the entity receipt.
+
+        Args:
+            segments: Non-empty list of integer polylines.
+            layer: Layer name for every segment.
+            endpoints: [a, b] endpoint mappings; each ref is a
+                pin/port/junction/net entity ID or null when
+                dangling.
+            request_id: Client envelope id; resubmitting the
+                identical text returns the identical response
+                without advancing.
+            command_text: YAML command text for identity comparison.
+            expected_revision: Revision the writer read.
+
+        Returns:
+            Mutation mapping with the wire receipt, revision
+            transition, new head, actor, diff summary, rewind
+            handle, the appended event, cursor, and request id.
+
+        Raises:
+            ProjectError: request_conflict for a reused id with
+                new text; revision_conflict for a stale head;
+                unknown_ref for a ref naming no entity;
+                invalid_ref for a wire ref; invalid_wire for a
+                malformed wire; unsupported_operation without the
+                ENGINE-ECS entity store.
+
+        Caution: Every accepted placement advances the revision —
+            a second writer at the old head fails instead of
+            merging.
+        """
+        return self._wire_mutation(
+            "place_wire", request_id, command_text, expected_revision,
+            lambda store: wireplace.place_wire(
+                store, self._actor, segments, layer, endpoints
+            ),
+            lambda receipt: f"placed wire {receipt['wire']} on {layer}",
+        )
+
+    def place_junction(self, xy, layer, request_id, command_text,
+                       expected_revision=None):
+        """Place one junction dot: gate, transact, advance, log.
+
+        Args:
+            xy: Integer [x, y] dot position.
+            layer: Layer name for the dot.
+            request_id: Client envelope id for idempotent replay.
+            command_text: YAML command text for identity comparison.
+            expected_revision: Revision the writer read.
+
+        Returns:
+            Mutation mapping with the junction receipt, revision
+            transition, new head, actor, diff summary, rewind
+            handle, the appended event, cursor, and request id.
+
+        Raises:
+            ProjectError: request_conflict for a reused id with
+                new text; revision_conflict for a stale head;
+                invalid_junction for a malformed dot;
+                unsupported_operation without the ENGINE-ECS
+                entity store.
+
+        Caution: Every accepted placement advances the revision —
+            a second writer at the old head fails instead of
+            merging.
+        """
+        return self._wire_mutation(
+            "place_junction", request_id, command_text, expected_revision,
+            lambda store: wireplace.place_junction(
+                store, self._actor, xy, layer
+            ),
+            lambda receipt: f"placed junction {receipt['junction']}",
+        )
+
+    def connect_endpoint(self, wire_id, end, ref, request_id,
+                         command_text, expected_revision=None):
+        """Point one wire endpoint at a new terminus: gate, run, log.
+
+        Geometry never moves — only the ref changes — and a
+        no-change call returns the head unadvanced with an empty
+        event list instead of logging a phantom revision.
+
+        Args:
+            wire_id: Wire entity to rewire.
+            end: "a" or "b" selecting the endpoint.
+            ref: Pin/port/junction/net entity ID, or null to
+                dangle the endpoint.
+            request_id: Client envelope id for idempotent replay.
+            command_text: YAML command text for identity comparison.
+            expected_revision: Revision the writer read.
+
+        Returns:
+            Mutation mapping with the connect receipt, revision
+            transition, actor, diff summary, rewind handle, the
+            appended event, cursor, and request id — or the
+            unadvanced noop mapping when the ref is already set.
+
+        Raises:
+            ProjectError: request_conflict for a reused id with
+                new text; revision_conflict for a stale head;
+                unknown_wire for a missing wire; invalid_endpoint
+                for a bad selector; unknown_ref for a missing
+                entity; invalid_ref for a wire/self ref;
+                unsupported_operation without the ENGINE-ECS
+                entity store.
+        """
+        return self._wire_mutation(
+            "connect_endpoint", request_id, command_text,
+            expected_revision,
+            lambda store: wireplace.connect_endpoint(
+                store, self._actor, wire_id, end, ref
+            ),
+            lambda receipt: (
+                f"connected wire {wire_id} end {end} to {ref!r}"
+            ),
+        )
+
+    def move_wire(self, wire_id, dx, dy, request_id, command_text,
+                  expected_revision=None):
+        """Translate one wire: gate, transact, advance, log.
+
+        Refs survive the move; a zero move returns the head
+        unadvanced with an empty event list.
+
+        Args:
+            wire_id: Wire entity to move.
+            dx: Integer x translation.
+            dy: Integer y translation.
+            request_id: Client envelope id for idempotent replay.
+            command_text: YAML command text for identity comparison.
+            expected_revision: Revision the writer read.
+
+        Returns:
+            Mutation mapping with the move receipt, revision
+            transition, actor, diff summary, rewind handle, the
+            appended event, cursor, and request id — or the
+            unadvanced noop mapping for a zero move.
+
+        Raises:
+            ProjectError: request_conflict for a reused id with
+                new text; revision_conflict for a stale head;
+                unknown_wire for a missing wire; invalid_geometry
+                for non-integer deltas; unsupported_operation
+                without the ENGINE-ECS entity store.
+        """
+        return self._wire_mutation(
+            "move_wire", request_id, command_text, expected_revision,
+            lambda store: wireplace.move_wire(
+                store, self._actor, wire_id, dx, dy
+            ),
+            lambda receipt: f"moved wire {wire_id} by ({dx}, {dy})",
+        )
+
+    def split_wire(self, wire_id, at, request_id, command_text,
+                   expected_revision=None):
+        """Split one wire at an interior point: gate, run, log.
+
+        The junction dot, the head rewrite, and the new tail wire
+        land in one revision under one event.
+
+        Args:
+            wire_id: Wire entity to split.
+            at: Integer [x, y] point on the polyline interior.
+            request_id: Client envelope id for idempotent replay.
+            command_text: YAML command text for identity comparison.
+            expected_revision: Revision the writer read.
+
+        Returns:
+            Mutation mapping with the split receipt (wire,
+            junction, new_wire), revision transition, new head,
+            actor, diff summary, rewind handle, the appended
+            event, cursor, and request id.
+
+        Raises:
+            ProjectError: request_conflict for a reused id with
+                new text; revision_conflict for a stale head;
+                unknown_wire for a missing wire; invalid_split for
+                a point off the interior or a multi-polyline wire;
+                unsupported_operation without the ENGINE-ECS
+                entity store.
+        """
+        return self._wire_mutation(
+            "split_wire", request_id, command_text, expected_revision,
+            lambda store: wireplace.split_wire(
+                store, self._actor, wire_id, at
+            ),
+            lambda receipt: (
+                f"split wire {wire_id} at {at} "
+                f"(junction {receipt['junction']}, "
+                f"tail {receipt['new_wire']})"
+            ),
+        )
+
+    def delete_wire(self, wire_id, request_id, command_text,
+                    expected_revision=None):
+        """Delete one wire: gate, remove, advance, log.
+
+        Referenced junctions persist; Net entities rematerialize
+        on the next materialize_nets call.
+
+        Args:
+            wire_id: Wire entity to delete.
+            request_id: Client envelope id for idempotent replay.
+            command_text: YAML command text for identity comparison.
+            expected_revision: Revision the writer read.
+
+        Returns:
+            Mutation mapping with the delete receipt, revision
+            transition, new head, actor, diff summary, rewind
+            handle, the appended event, cursor, and request id.
+
+        Raises:
+            ProjectError: request_conflict for a reused id with
+                new text; revision_conflict for a stale head;
+                unknown_wire for a missing wire;
+                unsupported_operation without the ENGINE-ECS
+                entity store.
+        """
+        return self._wire_mutation(
+            "delete_wire", request_id, command_text, expected_revision,
+            lambda store: wireplace.delete_wire(
+                store, self._actor, wire_id
+            ),
+            lambda receipt: f"deleted wire {wire_id}",
+        )
+
+    def delete_junction(self, junction_id, request_id, command_text,
+                        expected_revision=None):
+        """Delete one unreferenced junction: gate, remove, log.
+
+        Args:
+            junction_id: Junction entity to delete.
+            request_id: Client envelope id for idempotent replay.
+            command_text: YAML command text for identity comparison.
+            expected_revision: Revision the writer read.
+
+        Returns:
+            Mutation mapping with the delete receipt, revision
+            transition, new head, actor, diff summary, rewind
+            handle, the appended event, cursor, and request id.
+
+        Raises:
+            ProjectError: request_conflict for a reused id with
+                new text; revision_conflict for a stale head;
+                unknown_junction for a missing junction;
+                junction_in_use naming the referencing wires;
+                unsupported_operation without the ENGINE-ECS
+                entity store.
+        """
+        return self._wire_mutation(
+            "delete_junction", request_id, command_text,
+            expected_revision,
+            lambda store: wireplace.delete_junction(
+                store, self._actor, junction_id
+            ),
+            lambda receipt: f"deleted junction {junction_id}",
+        )
+
+    def materialize_nets(self, pins, request_id, command_text,
+                         labels=None, ports=None, cell="top",
+                         named_refs=None, expected_revision=None):
+        """Extract connectivity, upsert Net entities: gate, run, log.
+
+        Extraction always rebuilds from the stored wires; Nets
+        keyed by canonical name are created or refreshed, vanished
+        names pruned, all in one revision. An unchanged world
+        returns the head unadvanced with an empty event list.
+
+        Args:
+            pins: Caller pin records [{entity, instance, pin, xy}].
+            request_id: Client envelope id for idempotent replay.
+            command_text: YAML command text for identity comparison.
+            labels: Caller label records [{name, xy}].
+            ports: Caller port records [{name, direction}].
+            cell: Top cell name.
+            named_refs: {entity ID: net name} for port-style refs.
+            expected_revision: Revision the writer read.
+
+        Returns:
+            Mutation mapping with the materialize receipt (nets,
+            created/updated/pruned, unresolved), revision
+            transition, actor, diff summary, rewind handle, the
+            appended event, cursor, and request id — or the
+            unadvanced noop mapping when every Net matches.
+
+        Raises:
+            ProjectError: request_conflict for a reused id with
+                new text; revision_conflict for a stale head;
+                invalid_pin / invalid_label / invalid_port /
+                invalid_cell / invalid_ref for malformed inputs;
+                extraction_failed when extraction refuses the
+                world; unsupported_operation without the
+                ENGINE-ECS entity store.
+        """
+        return self._wire_mutation(
+            "materialize_nets", request_id, command_text,
+            expected_revision,
+            lambda store: wireplace.materialize_nets(
+                store, self._actor, pins, labels=labels or (),
+                ports=ports or (), cell=cell, named_refs=named_refs,
+            ),
+            lambda receipt: (
+                f"materialized {len(receipt['nets'])} nets "
+                f"({len(receipt['created'])} created, "
+                f"{len(receipt['updated'])} updated, "
+                f"{len(receipt['pruned'])} pruned)"
+            ),
+        )
+
     def rewind(self, target_revision, request_id, command_text,
                expected_revision=None):
         """Restore managed bytes to a prior revision under a new head.
```

Post-patch verification (integrator, full env):

    patch -p1 < docs/work/WIRE-PLACE/wiring.patch
    python scripts/api_spec.py --write && git diff --stat docs/   # expect 3 regenerated files
    python scripts/contract.py --write && git diff --stat docs/
    python -m pytest tests/interfaces/test_wireplace.py \
      tests/interfaces/test_wireplace_nets.py \
      tests/interfaces/test_wireplace_wiring.py -q               # expect 53 passed, 0 skipped
      # (needs ENGINE-ECS patch first; without it the submit round-trip skips)
    # then the full suite + gate per ticket acceptance.

## Anything refused, with reasons

- No edits to any existing file: ownership allows creates only; all
  wiring is the patch above. (Regens handled every tree collision —
  never a tree touch.)
- No full-suite run: the scratch env lacks optional deps (klayout) so
  a scratch full-suite run cannot go green; the project `.venv` is
  off-limits. Ran only the new tests plus the named neighbors above.
  The suite's single expected failure from this lane pre-patch is the
  MCP wiring probe (proven above by installing mcp into the scratch
  env: `1 failed, 49 passed, 3 skipped`).
- No `api_spec`/`contract` regen run: both rewrite tracked `docs/*`
  files, which I may not edit; the exact commands are above, and the
  /tmp patched-tree copy proves regen inputs render (wired=True,
  schemas, and help for all 8 ops).
- No parallel entity store: ENGINE-ECS is not on disk, so durability
  rides its seam (specified above) with an in-memory fake confined to
  the tests; the patch reports `unsupported_operation` until the
  ENGINE-ECS patch provides `ProjectService._entities`.
- No `run_erc` operation: wire ERC is collected via
  `collect_wire_erc` and the materialize receipt; wiring the unwired
  `run_erc` solver op belongs to the ERC/CONNECT-GRAPH lanes.
- No use of repo `.venv` or `uv sync`: all runs used the
  `/tmp/wireplace-venv` scratch env.
- Known seam risk (documented, not hidden): if the ledger snapshot
  capture fails after the entity transact commits, the entity head
  runs ahead of the ledger head; same failure class as a mid-mutation
  doc-write fault, owned by the ENGINE-ECS durable projection to
  reconcile.

## Integrator note (merged after ENGINE-ECS da00acd)

The shipped patch was generated for pre-ECS HEAD and drifted on
three files after the ENGINE-ECS commit, so the integrator
hand-merged it instead of force-applying:

- `__init__.py` hunk applied verbatim (`--include`); vocabulary,
  composition (`_submit_crud` tail), and service hunks re-placed
  by hand with patch-identical added lines.
- `_entity_store()` binds a `_WireEntityStore` adapter over the
  landed ENGINE-ECS verbs (reads map unknown/invalid codes to
  `LookupError`; `transact` runs sequentially with alias
  threading, one ledger revision per verb, inner envelopes
  derived from the outer request id, live-head revision gating).
- Two fixes found during live verification: the outer
  `_wire_mutation` advance chains from the post-transact head
  (advancing from the pre-transact head forked revisions
  backwards), and the adapter passes the live head into every
  inner verb (`_gate_revision` never accepts None past init).
- `wiring.patch` was refreshed to the exact merged bytes (diff
  of the four wiring files against da00acd); the report's inline
  diff above is the pre-ECS original. Live: 53/53 wire tests
  (round-trip included), 8-op probe green, 176-file gate green,
  api_spec/contract/docstrings fresh.
