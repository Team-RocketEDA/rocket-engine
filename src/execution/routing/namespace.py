"""Host-side console namespace over ProjectService verbs."""

import uuid

from ...library.errors import LibraryError
from ...project.errors import ProjectError
from .calls import admission_envelope


class ConsoleNamespace:
    """Host-side console namespace: tier-2 verbs through admission.

    One thin wrapper per tier-2 verb, named identically to the
    CRUD/MCP verbs and calling the matching ProjectService verb
    with the same call shape the Engine uses (verb arguments, then
    the envelope id plus identity text, revision bound by keyword).
    Every wrapper mints an envelope id when the caller omits one,
    builds the admission identity text over its arguments, and
    lets admission judge: stale revisions conflict, resubmits
    replay, and accepted mutations advance once with one
    actor-attributed ledger record. ECS and wire verbs fail loudly
    until their peer patches land; place_cell needs a catalogue.

    Args:
        project: Project port serving the public admission verbs
            (ProjectService serves).
        catalog: Component catalogue place_cell resolves through,
            or None when cell placement stays unwired.
    """

    def __init__(self, project, catalog=None):
        self._project = project
        self._catalog = catalog

    def _admit(self, verb, arguments, request_id, expected_revision):
        """Envelope id plus identity text for one verb call."""
        rid = request_id or uuid.uuid4().hex
        payload = dict(arguments)
        if expected_revision is not None:
            payload["expected_revision"] = expected_revision
        return rid, admission_envelope(verb, payload)

    def _wired(self, verb, owner):
        """One ECS/wire project verb, or loud pre-patch refusal."""
        method = getattr(self._project, verb, None)
        if method is None:
            raise ProjectError(
                "unsupported_operation",
                f"Console tier-2 verb {verb!r} needs the {owner} "
                "wiring, which is not applied yet.",
            )
        return method

    def write_doc(self, path, content, request_id=None,
                  expected_revision=None):
        """Write one document through admission.

        Args:
            path: Document path to create or overwrite.
            content: UTF-8 text to store.
            request_id: Client envelope id; resubmitting the
                identical call returns the identical response
                without advancing.
            expected_revision: Revision the writer read.

        Returns:
            Mutation mapping with path, revision transition, new
                head, actor, diff summary, rewind handle, the
                appended record, cursor, and request id.

        Raises:
            ProjectError: request_conflict for a reused id with
                new arguments; invalid_path or path_escape for a
                bad path; invalid_command for non-text content;
                revision_conflict for a stale head.

        Caution: Every accepted write advances the head — a
            second writer at the old head fails instead of
            merging.
        """
        rid, text = self._admit(
            "write_doc", {"path": path, "content": content},
            request_id, expected_revision,
        )
        return self._project.write_doc(
            path, content, rid, text,
            expected_revision=expected_revision,
        )

    def delete_doc(self, path, request_id=None, expected_revision=None):
        """Delete one document through admission.

        Args:
            path: Document path to delete.
            request_id: Client envelope id for idempotent replay.
            expected_revision: Revision the writer read.

        Returns:
            Mutation mapping with path, revision transition, new
                head, actor, diff summary, rewind handle, the
                appended record, cursor, and request id.

        Raises:
            ProjectError: request_conflict for a reused id with
                new arguments; invalid_path or path_escape for a
                bad path; unknown_document for a missing document;
                revision_conflict for a stale head.

        Caution: Deleting advances the head like any mutation —
            stale writers fail instead of merging.
        """
        rid, text = self._admit(
            "delete_doc", {"path": path}, request_id,
            expected_revision,
        )
        return self._project.delete_doc(
            path, rid, text, expected_revision=expected_revision
        )

    def apply_mutations(self, mutations, request_id=None,
                        expected_revision=None):
        """Apply a batch atomically under one new head.

        Args:
            mutations: Non-empty list of write/delete mappings.
            request_id: Client envelope id for idempotent replay.
            expected_revision: Revision the writer read.

        Returns:
            Mutation mapping with revision transition, new head,
                actor, joined diff summary, rewind handle, the
                single appended record, per-mutation results,
                cursor, and request id.

        Raises:
            ProjectError: request_conflict for a reused id with
                new arguments; invalid_command for a malformed
                batch; unknown_document for a delete of a missing
                document; revision_conflict for a stale head.

        Caution: All-or-nothing means one head for the whole
            batch — a half-landed batch is a bug, never a state.
        """
        rid, text = self._admit(
            "apply_mutations", {"mutations": mutations}, request_id,
            expected_revision,
        )
        return self._project.apply_mutations(
            mutations, rid, text, expected_revision=expected_revision
        )

    def place_cell(self, cell, request_id=None, expected_revision=None,
                   pdk=None, instance_id=None, params=None,
                   connections=None):
        """Place a catalogue cell through batch admission.

        Args:
            cell: Catalogue cell name.
            request_id: Client envelope id for idempotent replay.
            expected_revision: Revision the writer read.
            pdk: PDK label disambiguating same-named cells.
            instance_id: Instance name; derived when omitted.
            params: Override values for the cell defaults.
            connections: Connection mappings over cell ports.

        Returns:
            Mutation mapping with the revision transition, new
                head, actor, record, and request id.

        Raises:
            ProjectError: unsupported_operation without a
                catalogue; unknown_cell, ambiguous_cell,
                unknown_param, incompatible_port, or
                instance_exists for a bad placement (catalogue
                codes surface unchanged); revision_conflict for
                a stale head; request_conflict for a reused id
                with new arguments.
        """
        if self._catalog is None:
            raise ProjectError(
                "unsupported_operation",
                "place_cell needs a catalogue; this namespace was "
                "built without one.",
            )
        try:
            return self._catalog.place_cell(
                self._project, cell, request_id or uuid.uuid4().hex,
                expected_revision=expected_revision, pdk=pdk,
                instance_id=instance_id, params=params,
                connections=connections,
            )
        except LibraryError as exc:
            raise ProjectError(exc.code, str(exc)) from exc

    def create_entity(self, kind="", components=None, request_id=None,
                      expected_revision=None):
        """Create one entity with an engine-minted id.

        Args:
            kind: Kind label carried beside the components.
            components: Optional initial component mapping.
            request_id: Client envelope id for idempotent replay.
            expected_revision: Revision the writer read.

        Returns:
            Mutation mapping with the minted entity, kind, storage
                path, revision transition, new head, actor, diff
                summary, rewind handle, the entity_created record,
                cursor, and request id.

        Raises:
            ProjectError: unsupported_operation until the
                ENGINE-ECS wiring lands; request_conflict for a
                reused id with new arguments; invalid_kind,
                invalid_component, or invalid_data for malformed
                parts; revision_conflict for a stale head.

        Caution: Every accepted create advances the head — a
            second writer at the old head fails instead of
            merging.
        """
        arguments = {"kind": kind}
        if components is not None:
            arguments["components"] = components
        rid, text = self._admit(
            "create_entity", arguments, request_id, expected_revision
        )
        return self._wired("create_entity", "ENGINE-ECS")(
            rid, text, kind=kind, components=components,
            expected_revision=expected_revision,
        )

    def set_component(self, entity, component, data, request_id=None,
                      expected_revision=None,
                      expected_entity_revision=None):
        """Upsert one component payload through admission.

        Args:
            entity: Entity id holding the component.
            component: Component name to write.
            data: JSON payload to store.
            request_id: Client envelope id for idempotent replay.
            expected_revision: Revision the writer read.
            expected_entity_revision: Entity revision the writer
                read (ENTITY-CAS).

        Returns:
            Mutation mapping with entity, component, canonical
                address, storage path, revision transition, new
                head, actor, diff summary, rewind handle, the
                component_changed record, cursor, and request id.

        Raises:
            ProjectError: unsupported_operation until the
                ENGINE-ECS wiring lands; unknown_entity for a
                missing entity; backfill_readonly for a
                backfilled id; revision_conflict for a stale
                head; request_conflict for a reused id with new
                arguments.

        Caution: Every accepted write advances the head — a
            second writer at the old head fails instead of
            merging.
        """
        arguments = {"entity": entity, "component": component, "data": data}
        if expected_entity_revision is not None:
            arguments["expected_entity_revision"] = expected_entity_revision
        rid, text = self._admit(
            "set_component", arguments, request_id, expected_revision,
        )
        return self._wired("set_component", "ENGINE-ECS")(
            entity, component, data, rid, text,
            expected_revision=expected_revision,
            expected_entity_revision=expected_entity_revision,
        )

    def attach_component(self, entity, component, data, request_id=None,
                         expected_revision=None,
                         expected_entity_revision=None):
        """Attach one new component through admission.

        Args:
            entity: Entity id holding the component.
            component: Component name to attach.
            data: JSON payload to store.
            request_id: Client envelope id for idempotent replay.
            expected_revision: Revision the writer read.
            expected_entity_revision: Entity revision the writer
                read (ENTITY-CAS).

        Returns:
            Mutation mapping with entity, component, canonical
                address, storage path, revision transition, new
                head, actor, diff summary, rewind handle, the
                component_changed record, cursor, and request id.

        Raises:
            ProjectError: unsupported_operation until the
                ENGINE-ECS wiring lands; component_exists when
                the component already lives on the entity;
                unknown_entity for a missing entity;
                revision_conflict for a stale head.

        Caution: Every accepted attach advances the head — a
            second writer at the old head fails instead of
            merging.
        """
        arguments = {"entity": entity, "component": component, "data": data}
        if expected_entity_revision is not None:
            arguments["expected_entity_revision"] = expected_entity_revision
        rid, text = self._admit(
            "attach_component", arguments, request_id, expected_revision,
        )
        return self._wired("attach_component", "ENGINE-ECS")(
            entity, component, data, rid, text,
            expected_revision=expected_revision,
            expected_entity_revision=expected_entity_revision,
        )

    def detach_component(self, entity, component, request_id=None,
                         expected_revision=None,
                         expected_entity_revision=None):
        """Detach one component through admission.

        Args:
            entity: Entity id holding the component.
            component: Component name to remove.
            request_id: Client envelope id for idempotent replay.
            expected_revision: Revision the writer read.
            expected_entity_revision: Entity revision the writer
                read (ENTITY-CAS).

        Returns:
            Mutation mapping with entity, component, canonical
                address, storage path, revision transition, new
                head, actor, diff summary, rewind handle, the
                component_changed record, cursor, and request id.

        Raises:
            ProjectError: unsupported_operation until the
                ENGINE-ECS wiring lands; unknown_component for a
                missing component; revision_conflict for a stale
                head; request_conflict for a reused id with new
                arguments.

        Caution: Every accepted detach advances the head — a
            second writer at the old head fails instead of
            merging.
        """
        arguments = {"entity": entity, "component": component}
        if expected_entity_revision is not None:
            arguments["expected_entity_revision"] = expected_entity_revision
        rid, text = self._admit(
            "detach_component", arguments, request_id, expected_revision,
        )
        return self._wired("detach_component", "ENGINE-ECS")(
            entity, component, rid, text,
            expected_revision=expected_revision,
            expected_entity_revision=expected_entity_revision,
        )

    def delete_entity(self, entity, request_id=None,
                      expected_revision=None,
                      expected_entity_revision=None):
        """Delete one entity through admission.

        Args:
            entity: Entity id to delete.
            request_id: Client envelope id for idempotent replay.
            expected_revision: Revision the writer read.
            expected_entity_revision: Entity revision the writer
                read (ENTITY-CAS).

        Returns:
            Mutation mapping with entity, storage path, revision
                transition, new head, actor, diff summary, rewind
                handle, the entity_deleted record, cursor, and
                request id.

        Raises:
            ProjectError: unsupported_operation until the
                ENGINE-ECS wiring lands; unknown_entity for a
                missing entity; backfill_readonly for a
                backfilled id; revision_conflict for a stale
                head.

        Caution: Deleting advances the head like any mutation —
            stale writers fail instead of merging.
        """
        arguments = {"entity": entity}
        if expected_entity_revision is not None:
            arguments["expected_entity_revision"] = expected_entity_revision
        rid, text = self._admit(
            "delete_entity", arguments, request_id, expected_revision,
        )
        return self._wired("delete_entity", "ENGINE-ECS")(
            entity, rid, text, expected_revision=expected_revision,
            expected_entity_revision=expected_entity_revision,
        )

    def place_wire(self, segments, layer, endpoints, request_id=None,
                   expected_revision=None):
        """Place one wire through admission.

        Args:
            segments: Non-empty list of integer polylines.
            layer: Layer name for every segment.
            endpoints: Exactly two endpoint mappings with xy plus
                a pin/port/junction/net id or null when dangling.
            request_id: Client envelope id for idempotent replay.
            expected_revision: Revision the writer read.

        Returns:
            Mutation mapping with the wire receipt, revision
                transition, actor, diff summary, rewind handle,
                appended record, cursor, and request id.

        Raises:
            ProjectError: unsupported_operation until the
                WIRE-PLACE wiring lands; invalid_wire for a
                malformed wire; unknown_ref for a dangling id
                naming no entity; revision_conflict for a stale
                head.

        Caution: Every accepted place advances the head — a
            second writer at the old head fails instead of
            merging.
        """
        rid, text = self._admit(
            "place_wire",
            {"segments": segments, "layer": layer,
             "endpoints": endpoints},
            request_id, expected_revision,
        )
        return self._wired("place_wire", "WIRE-PLACE")(
            segments, layer, endpoints, rid, text,
            expected_revision=expected_revision,
        )

    def place_junction(self, xy, layer, request_id=None,
                       expected_revision=None):
        """Place one junction dot through admission.

        Args:
            xy: Integer dot position.
            layer: Layer name for the dot.
            request_id: Client envelope id for idempotent replay.
            expected_revision: Revision the writer read.

        Returns:
            Mutation mapping with the junction receipt, revision
                transition, actor, diff summary, rewind handle,
                appended record, cursor, and request id.

        Raises:
            ProjectError: unsupported_operation until the
                WIRE-PLACE wiring lands; invalid_junction for a
                malformed dot; revision_conflict for a stale
                head.

        Caution: Every accepted place advances the head — a
            second writer at the old head fails instead of
            merging.
        """
        rid, text = self._admit(
            "place_junction", {"xy": xy, "layer": layer},
            request_id, expected_revision,
        )
        return self._wired("place_junction", "WIRE-PLACE")(
            xy, layer, rid, text, expected_revision=expected_revision
        )

    def connect_endpoint(self, wire_id, end, ref, request_id=None,
                         expected_revision=None):
        """Terminate one wire endpoint on an id through admission.

        Args:
            wire_id: Wire entity to connect.
            end: Endpoint selector (a or b).
            ref: Pin/port/junction/net entity id, or null to
                leave the end dangling.
            request_id: Client envelope id for idempotent replay.
            expected_revision: Revision the writer read.

        Returns:
            Mutation mapping with the connect receipt, revision
                transition, actor, diff summary, rewind handle,
                appended record, cursor, and request id.

        Raises:
            ProjectError: unsupported_operation until the
                WIRE-PLACE wiring lands; unknown_wire for a
                missing wire; unknown_ref for an id naming no
                entity; revision_conflict for a stale head.

        Caution: Every accepted connect advances the head — a
            second writer at the old head fails instead of
            merging.
        """
        rid, text = self._admit(
            "connect_endpoint",
            {"wire_id": wire_id, "end": end, "ref": ref},
            request_id, expected_revision,
        )
        return self._wired("connect_endpoint", "WIRE-PLACE")(
            wire_id, end, ref, rid, text,
            expected_revision=expected_revision,
        )

    def move_wire(self, wire_id, dx, dy, request_id=None,
                  expected_revision=None):
        """Shift one wire by a delta through admission.

        Args:
            wire_id: Wire entity to move.
            dx: Integer x shift.
            dy: Integer y shift.
            request_id: Client envelope id for idempotent replay.
            expected_revision: Revision the writer read.

        Returns:
            Mutation mapping with the move receipt, revision
                transition, actor, diff summary, rewind handle,
                appended record, cursor, and request id.

        Raises:
            ProjectError: unsupported_operation until the
                WIRE-PLACE wiring lands; unknown_wire for a
                missing wire; revision_conflict for a stale
                head.

        Caution: Every accepted move advances the head — a
            second writer at the old head fails instead of
            merging.
        """
        rid, text = self._admit(
            "move_wire", {"wire_id": wire_id, "dx": dx, "dy": dy},
            request_id, expected_revision,
        )
        return self._wired("move_wire", "WIRE-PLACE")(
            wire_id, dx, dy, rid, text,
            expected_revision=expected_revision,
        )

    def split_wire(self, wire_id, at, request_id=None,
                   expected_revision=None):
        """Split one wire at a point through admission.

        Args:
            wire_id: Wire entity to split.
            at: Integer point on the wire marking the split.
            request_id: Client envelope id for idempotent replay.
            expected_revision: Revision the writer read.

        Returns:
            Mutation mapping with the split receipt, revision
                transition, actor, diff summary, rewind handle,
                appended record, cursor, and request id.

        Raises:
            ProjectError: unsupported_operation until the
                WIRE-PLACE wiring lands; unknown_wire for a
                missing wire; invalid_split for a point off the
                wire; revision_conflict for a stale head.

        Caution: Every accepted split advances the head — a
            second writer at the old head fails instead of
            merging.
        """
        rid, text = self._admit(
            "split_wire", {"wire_id": wire_id, "at": at},
            request_id, expected_revision,
        )
        return self._wired("split_wire", "WIRE-PLACE")(
            wire_id, at, rid, text, expected_revision=expected_revision
        )

    def delete_wire(self, wire_id, request_id=None,
                    expected_revision=None):
        """Delete one wire through admission.

        Args:
            wire_id: Wire entity to delete.
            request_id: Client envelope id for idempotent replay.
            expected_revision: Revision the writer read.

        Returns:
            Mutation mapping with the delete receipt, revision
                transition, actor, diff summary, rewind handle,
                appended record, cursor, and request id.

        Raises:
            ProjectError: unsupported_operation until the
                WIRE-PLACE wiring lands; unknown_wire for a
                missing wire; revision_conflict for a stale
                head.

        Caution: Deleting advances the head like any mutation —
            stale writers fail instead of merging.
        """
        rid, text = self._admit(
            "delete_wire", {"wire_id": wire_id}, request_id,
            expected_revision,
        )
        return self._wired("delete_wire", "WIRE-PLACE")(
            wire_id, rid, text, expected_revision=expected_revision
        )

    def delete_junction(self, junction_id, request_id=None,
                        expected_revision=None):
        """Delete one junction through admission.

        Args:
            junction_id: Junction entity to delete.
            request_id: Client envelope id for idempotent replay.
            expected_revision: Revision the writer read.

        Returns:
            Mutation mapping with the delete receipt, revision
                transition, actor, diff summary, rewind handle,
                appended record, cursor, and request id.

        Raises:
            ProjectError: unsupported_operation until the
                WIRE-PLACE wiring lands; unknown_junction for a
                missing junction; junction_in_use for a dot still
                referenced; revision_conflict for a stale head.

        Caution: Deleting advances the head like any mutation —
            stale writers fail instead of merging.
        """
        rid, text = self._admit(
            "delete_junction", {"junction_id": junction_id},
            request_id, expected_revision,
        )
        return self._wired("delete_junction", "WIRE-PLACE")(
            junction_id, rid, text,
            expected_revision=expected_revision,
        )

    def materialize_nets(self, pins, request_id=None,
                         expected_revision=None, labels=None,
                         ports=None, cell="top", named_refs=None):
        """Materialize net entities through admission.

        Args:
            pins: Caller pin records mapping entities to their
                schematic triples.
            request_id: Client envelope id for idempotent replay.
            expected_revision: Revision the writer read.
            labels: Optional label records for extraction.
            ports: Optional port records for extraction.
            cell: Cell name extraction runs under.
            named_refs: Optional net-ref taps by name.

        Returns:
            Mutation mapping with the materialize receipt,
                revision transition, actor, diff summary, rewind
                handle, appended record, cursor, and request id.

        Raises:
            ProjectError: unsupported_operation until the
                WIRE-PLACE wiring lands; invalid_pin and sibling
                contract codes for malformed inputs;
                revision_conflict for a stale head.

        Caution: Every accepted materialize advances the head —
            a second writer at the old head fails instead of
            merging.
        """
        arguments = {"pins": pins, "cell": cell}
        if labels is not None:
            arguments["labels"] = labels
        if ports is not None:
            arguments["ports"] = ports
        if named_refs is not None:
            arguments["named_refs"] = named_refs
        rid, text = self._admit(
            "materialize_nets", arguments, request_id,
            expected_revision,
        )
        return self._wired("materialize_nets", "WIRE-PLACE")(
            pins, rid, text, labels=labels, ports=ports, cell=cell,
            named_refs=named_refs, expected_revision=expected_revision,
        )

    def create_project(self, new_project_id, request_id=None):
        """Create one managed project at its first head.

        New ledgers start clean, so creation binds no revision —
        the envelope id alone carries idempotency.

        Args:
            new_project_id: Slug for the project to create.
            request_id: Client envelope id; resubmitting the
                identical call returns the identical response.

        Returns:
            Creation mapping with the new project id, first head,
                actor, diff summary, revision transition, rewind
                handle, empty records, and request id.

        Raises:
            ProjectError: invalid_command without an engine root;
                invalid_project for a non-slug id;
                project_exists for a duplicate; request_conflict
                for a reused id with new arguments.
        """
        rid, text = self._admit(
            "create_project", {"new_project_id": new_project_id},
            request_id, None,
        )
        return self._project.create_project(new_project_id, rid, text)

    def rewind(self, target_revision, request_id=None,
               expected_revision=None):
        """Restore a prior head under a new head through admission.

        Args:
            target_revision: Stored head to restore.
            request_id: Client envelope id for idempotent replay.
            expected_revision: Revision the writer read.

        Returns:
            Mutation mapping with revision transition, target
                revision, new head, actor, diff summary,
                external-file report, rewind handle, the appended
                record, cursor, and request id.

        Raises:
            ProjectError: request_conflict for a reused id with
                new arguments; invalid_command for a missing
                target or a target equal to the live head;
                unknown_revision for a head with no stored
                bytes; revision_conflict for a stale head.

        Caution: Rewinding advances — the new head is not the
            target id, and stale writers fail instead of merging.
        """
        rid, text = self._admit(
            "rewind", {"target_revision": target_revision},
            request_id, expected_revision,
        )
        return self._project.rewind(
            target_revision, rid, text,
            expected_revision=expected_revision,
        )

    def write_settings(self, kind, settings, request_id=None,
                       expected_revision=None):
        """Write one settings kind through admission.

        Args:
            kind: Settings kind to replace wholesale.
            settings: Complete settings mapping at the head
                version.
            request_id: Client envelope id for idempotent replay.
            expected_revision: Revision the writer read.

        Returns:
            Mutation mapping with path, revision transition, new
                head, actor, diff summary, rewind handle, the
                appended record, cursor, request id, written
                flag, and settings version.

        Raises:
            ProjectError: request_conflict for a reused id with
                new arguments; invalid_command for an unknown
                kind or settings breaking the kind schema;
                revision_conflict for a stale head;
                future_format when the stored file is newer
                than the head.

        Caution: Every accepted write advances the head — a
            second writer at the old head fails instead of
            merging.
        """
        rid, text = self._admit(
            "write_settings", {"kind": kind, "settings": settings},
            request_id, expected_revision,
        )
        return self._project.write_settings(
            kind, settings, rid, text,
            expected_revision=expected_revision,
        )
