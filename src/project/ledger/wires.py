"""Wire/junction ECS seam and wire-mutation admission."""

import copy

from ...interfaces.errors import ContractError
from ..errors import ProjectError

from .shared import _advance_revision

class _WireEntityStore:
    """WIRE-PLACE seam over the ENGINE-ECS ProjectService verbs.

    The wire ops take a store serving the seam in
    docs/work/WIRE-PLACE/report.md: reads return deep copies and
    raise LookupError for missing entities/components, and
    transact threads aliases through one call list. ENGINE-ECS
    landed as per-verb service methods with admission envelopes
    instead of a bound store, so this adapter binds those verbs
    to the seam: reads delegate with unknown/invalid entity and
    component codes mapped to LookupError, and transact runs its
    calls sequentially with alias resolution, one ledger
    revision per verb.

    Inner envelopes derive deterministically from the outer wire
    request id, so a retried envelope replays the verbs that
    already landed instead of minting duplicates. Sequential, not
    atomic: a mid-transact refusal leaves the earlier verbs
    applied (wire ops pre-validate, so a refusal after the first
    verb implies a concurrent writer, and the outer revision gate
    already serialized this op against those).
    """

    _READS = ("components_of", "get_component", "entities_with")
    _WRITES = (
        "create_entity", "set_component", "attach_component",
        "detach_component", "delete_entity",
    )
    _LOOKUP_CODES = frozenset({
        "unknown_entity", "unknown_component",
        "invalid_entity", "invalid_component",
    })

    def __init__(self, service, request_id):
        self._service = service
        self._request_id = request_id
        self._seq = 0

    def _envelope(self, verb):
        self._seq += 1
        sub_id = f"{self._request_id}:wire-ecs:{self._seq}"
        return sub_id, f"{verb} {sub_id}"

    def _lookup(self, entity, component=None):
        if component is None:
            return LookupError(f"Unknown entity: {entity!r}.")
        return LookupError(
            f"Unknown component {component!r} on {entity!r}."
        )

    def components_of(self, entity):
        """Return a deep copy of one entity's component mapping.

        Args:
            entity: Entity id to inspect.

        Returns:
            Mapping of component name to payload copy.

        Raises:
            LookupError: Unknown or malformed entity id.
        """
        try:
            names = self._service.components_of(entity)["components"]
        except ProjectError as exc:
            if exc.code in self._LOOKUP_CODES:
                raise self._lookup(entity) from None
            raise
        return {
            name: self.get_component(entity, name) for name in names
        }

    def get_component(self, entity, component):
        """Return a deep copy of one component payload.

        Args:
            entity: Entity id holding the component.
            component: Component name to read.

        Returns:
            Deep copy of the component payload.

        Raises:
            LookupError: Unknown or malformed entity id or
                component name.
        """
        try:
            data = self._service.get_component(
                entity, component
            )["data"]
        except ProjectError as exc:
            if exc.code in self._LOOKUP_CODES:
                raise self._lookup(entity, component) from None
            raise
        return copy.deepcopy(data)

    def entities_with(self, component, predicate=None):
        """List holder ids in id order, filtered by a callable.

        Args:
            component: Component name holders must carry.
            predicate: Callable over the payload copy, or None
                for no filtering.

        Returns:
            Sorted holder entity ids.
        """
        found = []
        for entity in self._service.entities_with(
            component
        )["entities"]:
            if predicate is None:
                found.append(entity)
            elif predicate(self.get_component(entity, component)):
                found.append(entity)
        return found

    def create_entity(self, actor, description):
        """Mint one entity; return its id and the new head.

        Args:
            actor: Attribution (the service actor applies).
            description: Human note (carried on inner envelopes).

        Returns:
            Mapping with the minted id and the new head revision.
        """
        del actor, description
        request_id, command_text = self._envelope("create_entity")
        response = self._service.create_entity(
            request_id, command_text,
            expected_revision=self._service._current_revision,
        )
        return {
            "id": response["entity"],
            "revision": response["current_revision"],
        }

    def set_component(self, actor, entity, component, value,
                      description):
        """Overwrite one component; refuse a missing target.

        Args:
            actor: Attribution (the service actor applies).
            entity: Entity id holding the component.
            component: Component name to overwrite.
            value: JSON payload to store.
            description: Human note (carried on inner envelopes).

        Returns:
            Mapping with the new head revision.

        Raises:
            ProjectError: unknown_entity or unknown_component
                for a missing target.
        """
        del actor, description
        try:
            names = self._service.components_of(entity)["components"]
        except ProjectError as exc:
            if exc.code in self._LOOKUP_CODES:
                raise ProjectError(
                    "unknown_entity",
                    f"Unknown entity: {entity!r}.",
                ) from None
            raise
        if component not in names:
            raise ProjectError(
                "unknown_component",
                f"Unknown component {component!r} on {entity!r}.",
            )
        request_id, command_text = self._envelope("set_component")
        response = self._service.set_component(
            entity, component, value, request_id, command_text,
            expected_revision=self._service._current_revision,
        )
        return {"revision": response["current_revision"]}

    def attach_component(self, actor, entity, component, value,
                         description):
        """Attach one new component to its entity.

        Args:
            actor: Attribution (the service actor applies).
            entity: Entity id gaining the component.
            component: Component name to attach.
            value: JSON payload to store.
            description: Human note (carried on inner envelopes).

        Returns:
            Mapping with the new head revision.

        Raises:
            ProjectError: component_exists for a duplicate;
                unknown_entity for a missing entity.
        """
        del actor, description
        request_id, command_text = self._envelope(
            "attach_component"
        )
        response = self._service.attach_component(
            entity, component, value, request_id, command_text,
            expected_revision=self._service._current_revision,
        )
        return {"revision": response["current_revision"]}

    def detach_component(self, actor, entity, component, description):
        """Detach one component from its entity.

        Args:
            actor: Attribution (the service actor applies).
            entity: Entity id losing the component.
            component: Component name to detach.
            description: Human note (carried on inner envelopes).

        Returns:
            Mapping with the new head revision.

        Raises:
            ProjectError: unknown_entity or unknown_component
                for a missing target.
        """
        del actor, description
        request_id, command_text = self._envelope(
            "detach_component"
        )
        response = self._service.detach_component(
            entity, component, request_id, command_text,
            expected_revision=self._service._current_revision,
        )
        return {"revision": response["current_revision"]}

    def delete_entity(self, actor, entity, description):
        """Delete one entity and its projected record.

        Args:
            actor: Attribution (the service actor applies).
            entity: Entity id to delete.
            description: Human note (carried on inner envelopes).

        Returns:
            Mapping with the new head revision.

        Raises:
            ProjectError: unknown_entity for a missing entity.
        """
        del actor, description
        request_id, command_text = self._envelope("delete_entity")
        response = self._service.delete_entity(
            entity, request_id, command_text,
            expected_revision=self._service._current_revision,
        )
        return {"revision": response["current_revision"]}

    def _resolve(self, node, aliases):
        if isinstance(node, dict) and set(node) == {"alias"}:
            try:
                return aliases[node["alias"]]
            except KeyError:
                raise ProjectError(
                    "invalid_command",
                    f"Unknown transact alias: {node['alias']!r}.",
                ) from None
        if isinstance(node, dict):
            return {
                key: self._resolve(val, aliases)
                for key, val in node.items()
            }
        if isinstance(node, list):
            return [self._resolve(val, aliases) for val in node]
        return node

    def transact(self, actor, description, calls):
        """Run calls sequentially with alias threading.

        Each call is {"verb", "args"?, "alias"?}; {"alias": name}
        values resolve at any depth to ids created earlier in the
        same call list.

        Args:
            actor: Attribution stamped on the seam events.
            description: Human note for the call list.
            calls: Verb calls with optional args and aliases.

        Returns:
            Mapping with the new head, the alias map, and the
            stamped seam events.

        Raises:
            ProjectError: invalid_command for an unknown verb,
                alias, or missing arg; the ECS refusal code
                (unknown_entity, component_exists, ...) for a
                refused verb.
        """
        aliases = {}
        events = []
        for call in calls:
            verb = call["verb"]
            try:
                args = self._resolve(
                    dict(call.get("args", {})), aliases
                )
            except KeyError as exc:
                raise ProjectError(
                    "invalid_command",
                    f"Malformed transact call: {call!r}.",
                ) from exc
            need = {
                "create_entity": (),
                "set_component": ("entity", "component", "value"),
                "attach_component": ("entity", "component", "value"),
                "detach_component": ("entity", "component"),
                "delete_entity": ("entity",),
            }
            if verb not in need:
                raise ProjectError(
                    "invalid_command",
                    f"Unknown transact verb: {verb!r}.",
                )
            missing = [k for k in need[verb] if k not in args]
            if missing:
                raise ProjectError(
                    "invalid_command",
                    f"transact {verb} misses {missing!r}.",
                )
            if verb == "create_entity":
                made = self.create_entity(actor, description)
                events.append({
                    "event": "entity_created",
                    "entity": made["id"],
                })
                if "alias" in call:
                    aliases[call["alias"]] = made["id"]
            elif verb in ("set_component", "attach_component"):
                method = getattr(self, verb)
                method(
                    actor, args["entity"], args["component"],
                    args["value"], description,
                )
                events.append({
                    "event": "component_changed",
                    "entity": args["entity"],
                    "component": args["component"],
                })
            elif verb == "detach_component":
                self.detach_component(
                    actor, args["entity"], args["component"],
                    description,
                )
                events.append({
                    "event": "component_changed",
                    "entity": args["entity"],
                    "component": args["component"],
                })
            else:
                self.delete_entity(
                    actor, args["entity"], description
                )
                events.append({
                    "event": "entity_deleted",
                    "entity": args["entity"],
                })
        revision = self._service._current_revision
        for event in events:
            event["revision"] = revision
            event["actor"] = actor
        return {
            "revision": revision,
            "aliases": aliases,
            "events": events,
        }

    def events_since(self, cursor):
        """List entity events past a ledger sequence cursor.

        Args:
            cursor: Ledger sequence; only later events return.

        Returns:
            Seam-shaped entity events in ledger order.
        """
        self._service._refresh_durable()
        found = []
        for record in self._service._events:
            if record["seq"] <= cursor:
                continue
            if record["event"] not in (
                "entity_created", "component_changed",
                "entity_deleted",
            ):
                continue
            data = record.get("data", {})
            event = {
                "event": record["event"],
                "entity": data.get("entity"),
                "revision": data.get("revision"),
                "actor": record.get("actor"),
            }
            if "component" in data:
                event["component"] = data["component"]
            found.append(event)
        return found


class _WireMixin:
    """Wire-mutation admission for ProjectService."""

    def _entity_store(self, request_id):
        """Return the ENGINE-ECS entity store seam for one wire op.

        WIRE-PLACE/ENGINE-ECS seam: ENGINE-ECS owns the durable
        store as per-verb service methods, so this binds the
        _WireEntityStore adapter over those verbs for the given
        outer request id (inner envelopes derive from it).

        Args:
            request_id: Outer wire envelope id; inner ECS
                envelopes derive deterministically from it.

        Returns:
            Entity store serving the wireplace seam.

        Raises:
            ProjectError: unsupported_operation when the
                ENGINE-ECS verbs are not present.
        """
        for name in (
            _WireEntityStore._READS + _WireEntityStore._WRITES
        ):
            if not callable(getattr(self, name, None)):
                raise ProjectError(
                    "unsupported_operation",
                    "Wire ops need the ENGINE-ECS entity store, "
                    "which is not wired yet.",
                )
        return _WireEntityStore(self, request_id)

    def _wire_mutation(self, operation, request_id, command_text,
                       expected_revision, run, describe):
        """Admit one wire op through the ledger admission machinery.

        A resubmitted envelope returns its stored response; a new
        envelope gates its expected_revision, snapshots the
        previous head, runs the entity transact (one ledger
        revision per verb), then advances once more for the wire
        event and logs. A noop receipt returns the head
        unadvanced with an empty event list.

        Args:
            operation: Wire operation name for the event data.
            request_id: Client envelope id for idempotent replay.
            command_text: YAML command text for identity comparison.
            expected_revision: Revision the writer read.
            run: Callable (store) -> wireplace receipt.
            describe: Callable (receipt) -> diff summary text.

        Returns:
            Mutation mapping with the entity receipt, revision
            transition, actor, diff summary, rewind handle,
            appended event, cursor, and request id — or the
            unadvanced noop mapping when the receipt is a noop.

        Raises:
            ProjectError: request_conflict for a reused id with
                new text; revision_conflict for a stale head;
                unsupported_operation without the ENGINE-ECS
                store; the wire contract code (unknown_wire,
                unknown_ref, ...) for a refused op.
        """
        self._refresh_durable()
        replay = self._check_replay(request_id, command_text)
        if replay is not None:
            return replay
        self._gate_revision(expected_revision)
        store = self._entity_store(request_id)
        previous = self._current_revision
        self._ensure_snapshot(previous)
        try:
            receipt = run(store)
        except ContractError as exc:
            raise ProjectError(exc.code, str(exc)) from exc
        if receipt.get("noop"):
            response = {
                "project_id": self._project_id,
                "previous_revision": previous,
                "current_revision": previous,
                "revision_transition": {"from": previous, "to": previous},
                "actor": self._actor,
                "diff_summary": f"{operation} changed nothing",
                "rewind_handle": {
                    "project_id": self._project_id,
                    "revision": previous,
                    "request_id": request_id,
                },
                "noop": True,
                "receipt": receipt,
                "events": [],
                "event_cursor": self._cursor(),
                "request_id": request_id,
            }
            self._requests[request_id] = (command_text, response)
            self._persist_after_mutation()
            return response
        # Chain from the live head: the transact's verbs already
        # advanced past `previous`, so advancing from `previous`
        # would fork the revision line backwards.
        advanced = _advance_revision(self._current_revision)
        self._capture_snapshot(advanced)
        self._current_revision = advanced
        diff = describe(receipt)
        record = self._append_event(
            operation,
            request_id,
            {
                "revision": self._current_revision,
                "operation": operation,
                "diff_summary": diff,
                "receipt": receipt,
            },
        )
        response = {
            "project_id": self._project_id,
            "previous_revision": previous,
            "current_revision": self._current_revision,
            "revision_transition": {
                "from": previous,
                "to": self._current_revision,
            },
            "actor": self._actor,
            "diff_summary": diff,
            "rewind_handle": {
                "project_id": self._project_id,
                "revision": previous,
                "request_id": request_id,
            },
            "receipt": receipt,
            "events": [record],
            "event_cursor": self._cursor(),
            "request_id": request_id,
        }
        self._requests[request_id] = (command_text, response)
        self._persist_after_mutation()
        return response
