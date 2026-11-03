"""Engine ops mixin: Submit-immediate admission paths (CRUD, place-cell, pyexec)."""

import uuid
from ..interfaces.yaml_dump import dump_yaml_text
from ..library.errors import LibraryError
from ..project.errors import ProjectError


class _SubmitMixin:
    """Submit-immediate admission paths (CRUD, place-cell, pyexec)."""

    def _submit_crud(self, name, arguments, command):
        """Execute one CRUD/rewind mutation immediately (no queue)."""
        command_text = dump_yaml_text(
            {"operation": name, "arguments": arguments}
        )
        request_id = str(command.get("request_id") or uuid.uuid4().hex)
        if name == "create_project":
            if "new_project_id" not in arguments:
                raise ProjectError(
                    "invalid_command",
                    "create_project needs a new_project_id argument.",
                )
            return self._project.create_project(
                arguments["new_project_id"], request_id, command_text
            )
        if name == "write_doc":
            if "path" not in arguments or "content" not in arguments:
                raise ProjectError(
                    "invalid_command",
                    "write_doc needs path and content arguments.",
                )
            return self._project.write_doc(
                arguments["path"],
                arguments["content"],
                request_id,
                command_text,
                expected_revision=arguments.get("expected_revision"),
            )
        if name == "delete_doc":
            if "path" not in arguments:
                raise ProjectError(
                    "invalid_command", "delete_doc needs a path argument."
                )
            return self._project.delete_doc(
                arguments["path"],
                request_id,
                command_text,
                expected_revision=arguments.get("expected_revision"),
            )
        if name == "rewind":
            if "target_revision" not in arguments:
                raise ProjectError(
                    "invalid_command",
                    "rewind needs a target_revision argument.",
                )
            return self._project.rewind(
                arguments["target_revision"],
                request_id,
                command_text,
                expected_revision=arguments.get("expected_revision"),
            )
        if name == "write_settings":
            if "kind" not in arguments or "settings" not in arguments:
                raise ProjectError(
                    "invalid_command",
                    "write_settings needs kind and settings arguments.",
                )
            return self._project.write_settings(
                arguments["kind"],
                arguments["settings"],
                request_id,
                command_text,
                expected_revision=arguments.get("expected_revision"),
            )
        if name == "create_entity":
            return self._project.create_entity(
                request_id,
                command_text,
                kind=arguments.get("kind", ""),
                components=arguments.get("components"),
                expected_revision=arguments.get("expected_revision"),
            )
        if name in ("set_component", "attach_component"):
            if (
                "entity" not in arguments
                or "component" not in arguments
                or "data" not in arguments
            ):
                raise ProjectError(
                    "invalid_command",
                    f"{name} needs entity, component, and data arguments.",
                )
            method = getattr(self._project, name)
            return method(
                arguments["entity"],
                arguments["component"],
                arguments["data"],
                request_id,
                command_text,
                expected_revision=arguments.get("expected_revision"),
                expected_entity_revision=arguments.get(
                    "expected_entity_revision"
                ),
            )
        if name == "detach_component":
            if "entity" not in arguments or "component" not in arguments:
                raise ProjectError(
                    "invalid_command",
                    "detach_component needs entity and component arguments.",
                )
            return self._project.detach_component(
                arguments["entity"],
                arguments["component"],
                request_id,
                command_text,
                expected_revision=arguments.get("expected_revision"),
                expected_entity_revision=arguments.get(
                    "expected_entity_revision"
                ),
            )
        if name == "delete_entity":
            if "entity" not in arguments:
                raise ProjectError(
                    "invalid_command",
                    "delete_entity needs an entity argument.",
                )
            return self._project.delete_entity(
                arguments["entity"],
                request_id,
                command_text,
                expected_revision=arguments.get("expected_revision"),
                expected_entity_revision=arguments.get(
                    "expected_entity_revision"
                ),
            )
        if name == "place_wire":
            for key in ("segments", "layer", "endpoints"):
                if key not in arguments:
                    raise ProjectError(
                        "invalid_command",
                        f"place_wire needs a {key} argument.",
                    )
            return self._project.place_wire(
                arguments["segments"],
                arguments["layer"],
                arguments["endpoints"],
                request_id,
                command_text,
                expected_revision=arguments.get("expected_revision"),
            )
        if name == "place_junction":
            for key in ("xy", "layer"):
                if key not in arguments:
                    raise ProjectError(
                        "invalid_command",
                        f"place_junction needs a {key} argument.",
                    )
            return self._project.place_junction(
                arguments["xy"],
                arguments["layer"],
                request_id,
                command_text,
                expected_revision=arguments.get("expected_revision"),
            )
        if name == "connect_endpoint":
            for key in ("wire_id", "end", "ref"):
                if key not in arguments:
                    raise ProjectError(
                        "invalid_command",
                        f"connect_endpoint needs a {key} argument.",
                    )
            return self._project.connect_endpoint(
                arguments["wire_id"],
                arguments["end"],
                arguments["ref"],
                request_id,
                command_text,
                expected_revision=arguments.get("expected_revision"),
            )
        if name == "move_wire":
            for key in ("wire_id", "dx", "dy"):
                if key not in arguments:
                    raise ProjectError(
                        "invalid_command",
                        f"move_wire needs a {key} argument.",
                    )
            return self._project.move_wire(
                arguments["wire_id"],
                arguments["dx"],
                arguments["dy"],
                request_id,
                command_text,
                expected_revision=arguments.get("expected_revision"),
            )
        if name == "split_wire":
            for key in ("wire_id", "at"):
                if key not in arguments:
                    raise ProjectError(
                        "invalid_command",
                        f"split_wire needs a {key} argument.",
                    )
            return self._project.split_wire(
                arguments["wire_id"],
                arguments["at"],
                request_id,
                command_text,
                expected_revision=arguments.get("expected_revision"),
            )
        if name == "delete_wire":
            if "wire_id" not in arguments:
                raise ProjectError(
                    "invalid_command",
                    "delete_wire needs a wire_id argument.",
                )
            return self._project.delete_wire(
                arguments["wire_id"],
                request_id,
                command_text,
                expected_revision=arguments.get("expected_revision"),
            )
        if name == "delete_junction":
            if "junction_id" not in arguments:
                raise ProjectError(
                    "invalid_command",
                    "delete_junction needs a junction_id argument.",
                )
            return self._project.delete_junction(
                arguments["junction_id"],
                request_id,
                command_text,
                expected_revision=arguments.get("expected_revision"),
            )
        if name == "materialize_nets":
            if "pins" not in arguments:
                raise ProjectError(
                    "invalid_command",
                    "materialize_nets needs a pins argument.",
                )
            return self._project.materialize_nets(
                arguments["pins"],
                request_id,
                command_text,
                labels=arguments.get("labels"),
                ports=arguments.get("ports"),
                cell=arguments.get("cell", "top"),
                named_refs=arguments.get("named_refs"),
                expected_revision=arguments.get("expected_revision"),
            )
        if "mutations" not in arguments:
            raise ProjectError(
                "invalid_command",
                "apply_mutations needs a mutations argument.",
            )
        return self._project.apply_mutations(
            arguments["mutations"],
            request_id,
            command_text,
            expected_revision=arguments.get("expected_revision"),
        )

    def _submit_place_cell(self, arguments, command):
        """Place a catalogue cell immediately (no queue, no solver).

        Args:
            arguments: place_cell arguments (cell plus the
                optional pdk, instance_id, params, connections,
                path_prefix, and expected_revision).
            command: Envelope carrying request_id.

        Returns:
            Mutation mapping for the placed instance.

        Raises:
            ProjectError: invalid_command for a missing cell, or
                the catalogue codes (unknown_cell,
                ambiguous_cell, unknown_param,
                incompatible_port, instance_exists) for a bad
                placement.
        """
        if "cell" not in arguments:
            raise ProjectError(
                "invalid_command", "place_cell needs a cell argument."
            )
        request_id = str(command.get("request_id") or uuid.uuid4().hex)
        try:
            return self._cells.place_cell(
                self._project,
                arguments["cell"],
                request_id,
                expected_revision=arguments.get("expected_revision"),
                pdk=arguments.get("pdk"),
                instance_id=arguments.get("instance_id"),
                params=arguments.get("params"),
                connections=arguments.get("connections"),
                path_prefix=arguments.get("path_prefix", "components"),
            )
        except LibraryError as exc:
            raise ProjectError(exc.code, str(exc)) from exc

    def _submit_pyexec(self, arguments, command):
        """Admit a python_execute request: gate, then open an approval.

        Shape validation runs before the revision gate so malformed
        requests fail before anything is persisted or queued; the
        gated submit then advances the revision and appends
        job_queued like every other operation. The ack run_id IS
        the execution id: approval admits it, run_job executes it.

        Args:
            arguments: python_execute arguments (mode plus lines
                or path, timeout_s, artifacts, expected_revision).
            command: Envelope carrying request_id.

        Returns:
            Admission mapping with the ack fields plus
                execution_id, approval_id, and pending_approval
                state. No run exists until the UI route approves.

        Raises:
            ProjectError: revision_conflict for a stale
                expected_revision, request_conflict for a reused
                envelope id with new text.
            ExecutionError: invalid_command/invalid_cell/empty_cell
                for malformed requests, path_escape/invalid_path/
                cell_unreadable for bad project files.
        """
        self._pyexec.validate_request(
            arguments.get("mode"),
            lines=arguments.get("lines"),
            path=arguments.get("path"),
            artifacts=arguments.get("artifacts", ()),
            timeout_s=arguments.get("timeout_s"),
        )
        command_text = dump_yaml_text(
            {"operation": "python_execute", "arguments": arguments})
        request_id = command.get("request_id") or uuid.uuid4().hex
        ack = self._project.submit(
            command_text,
            str(request_id),
            expected_revision=arguments.get("expected_revision"),
        )
        handle = self._pyexec.request_execution(
            arguments["mode"],
            lines=arguments.get("lines"),
            path=arguments.get("path"),
            request_id=str(request_id),
            run_id=ack["run_id"],
            expected_revision=arguments.get("expected_revision"),
            artifacts=arguments.get("artifacts", ()),
            timeout_s=arguments.get("timeout_s"),
        )
        self._run_jobs.setdefault(
            ack["run_id"],
            {
                "operation": "python_execute",
                "arguments": dict(arguments),
                "snapshot_id": ack["snapshot_id"],
                "request_id": str(request_id),
            },
        )
        return {**ack, **handle, "state": "pending_approval"}
