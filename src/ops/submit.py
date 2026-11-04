"""Engine ops mixin: Submit-immediate admission paths (CRUD, editors, place-cell, pyexec)."""

import hashlib
import uuid
from ..execution.console.lifecycle import console_envelope
from ..interfaces.yaml_dump import dump_yaml_text
from ..library.errors import LibraryError
from ..project.errors import ProjectError


#: Wave-3 editor operation -> required argument names.
_EDITOR_OPS = {
    "apply_transaction": ("changes",),
    "create_shape": ("shape_type", "layer", "data"),
    "create_sheet": ("name",),
    "place_instance": ("sheet", "symbol", "x", "y"),
    "bind_block": ("parent_sheet", "child_sheet", "instance"),
    "create_symbol": ("name", "pins"),
    "create_cell": ("name", "ports"),
    "map_pins": ("symbol", "cell", "pin_map"),
    "ip_register": ("pdk", "name", "version", "symbol", "cell"),
    "ip_instantiate": ("pdk", "name", "sheet", "x", "y"),
    "ip_promote": ("pdk", "name", "version"),
    "bind_layers": ("profile", "layers"),
    "annotate": (),
    "create_testbench": ("name", "kind", "targets"),
    "regenerate_testbench": ("testbench",),
}


class _SubmitMixin:
    """Submit-immediate admission paths (CRUD, editors, place-cell, pyexec)."""

    def _submit_crud(self, name, arguments, command):
        """Execute one CRUD/rewind/editor mutation immediately (no queue)."""
        if name in _EDITOR_OPS:
            return self._submit_editor(name, arguments, command)
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

    def _submit_editor(self, name, arguments, command):
        """Execute one Wave-3 editor/testbench op immediately.

        Required arguments are refused loudly before anything is
        admitted; the ProjectService verb owns revision gating,
        idempotent replay, and I28 pins.

        Args:
            name: Wave-3 editor operation name.
            arguments: Operation arguments mapping.
            command: Envelope carrying request_id.

        Returns:
            Mutation mapping for the editor verb.

        Raises:
            ProjectError: invalid_command for missing arguments.
        """
        missing = [
            key for key in _EDITOR_OPS[name] if key not in arguments
        ]
        if missing:
            raise ProjectError(
                "invalid_command",
                f"{name} needs {', '.join(sorted(missing))}.",
            )
        request_id = str(command.get("request_id") or uuid.uuid4().hex)
        command_text = dump_yaml_text(
            {"operation": name, "arguments": arguments}
        )
        head = arguments.get("expected_revision")
        project = self._project
        if name == "apply_transaction":
            return project.apply_transaction(
                arguments["changes"], request_id, command_text,
                expected_revision=head)
        if name == "create_shape":
            return project.create_shape(
                arguments["shape_type"], arguments["layer"],
                arguments["data"], request_id, command_text,
                units=arguments.get("units", "nm"),
                profile=arguments.get("profile"),
                anchor=arguments.get("anchor"),
                expected_revision=head)
        if name == "create_sheet":
            return project.create_sheet(
                arguments["name"], request_id, command_text,
                title=arguments.get("title", ""),
                expected_revision=head)
        if name == "place_instance":
            return project.place_instance(
                arguments["sheet"], arguments["symbol"],
                arguments["x"], arguments["y"], request_id,
                command_text,
                rotation=arguments.get("rotation", 0),
                mirror=arguments.get("mirror", False),
                properties=arguments.get("properties"),
                ref=arguments.get("ref", ""),
                expected_revision=head)
        if name == "bind_block":
            return project.bind_block(
                arguments["parent_sheet"],
                arguments["child_sheet"], arguments["instance"],
                request_id, command_text,
                expected_revision=head)
        if name == "create_symbol":
            return project.create_symbol(
                arguments["name"], arguments["pins"], request_id,
                command_text, graphics=arguments.get("graphics"),
                properties=arguments.get("properties"),
                expected_revision=head)
        if name == "create_cell":
            return project.create_cell(
                arguments["name"], arguments["ports"], request_id,
                command_text,
                properties=arguments.get("properties"),
                expected_revision=head)
        if name == "map_pins":
            return project.map_pins(
                arguments["symbol"], arguments["cell"],
                arguments["pin_map"], request_id, command_text,
                expected_revision=head)
        if name == "ip_register":
            return project.ip_register(
                arguments["pdk"], arguments["name"],
                arguments["version"], arguments["symbol"],
                arguments["cell"], request_id, command_text,
                pin_map=arguments.get("pin_map"),
                scope=arguments.get("scope", "pdk"),
                reason=arguments.get("reason", ""),
                expected_revision=head)
        if name == "ip_instantiate":
            return project.ip_instantiate(
                arguments["pdk"], arguments["name"],
                arguments["sheet"], arguments["x"],
                arguments["y"], request_id, command_text,
                version=arguments.get("version"),
                rotation=arguments.get("rotation", 0),
                mirror=arguments.get("mirror", False),
                properties=arguments.get("properties"),
                expected_revision=head)
        if name == "ip_promote":
            return project.ip_promote(
                arguments["pdk"], arguments["name"],
                arguments["version"], request_id, command_text,
                expected_revision=head)
        if name == "bind_layers":
            return project.bind_layers(
                arguments["profile"], arguments["layers"],
                request_id, command_text,
                source=arguments.get("source", "profile"),
                version=arguments.get("version", "unknown"),
                expected_revision=head)
        if name == "annotate":
            return project.annotate(
                request_id, command_text,
                prefixes=arguments.get("prefixes"),
                sheet=arguments.get("sheet"),
                expected_revision=head)
        if name == "create_testbench":
            return project.create_testbench(
                arguments["name"], arguments["kind"],
                arguments["targets"], request_id, command_text,
                probes=arguments.get("probes"),
                harness=arguments.get("harness"),
                template=arguments.get("template"),
                expected_revision=head)
        return project.regenerate_testbench(
            arguments["testbench"], request_id, command_text,
            expected_revision=head)

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

    def apply_batch(self, batch):
        """Land one apply-context batch as a single transaction.

        The session compiler turns staged sink intents into entity
        changes; they submit through one ``apply_transaction`` on
        the live head, so a console batch is atomic exactly like an
        editor batch. The request id derives from the batch
        envelope, so replaying the same batch is idempotent
        (same receipt, no new revision) while a reused id with
        different arguments conflicts loudly instead of landing
        twice.

        Args:
            batch: Emitted batch with label and intents.

        Returns:
            Receipt with the batch label, the new head revision,
            landed kinds, declared-unlanded entries, and the
            request id.

        Raises:
            ProjectError: invalid_command for a malformed batch
                or an unknown sink kind, revision_conflict for a
                head that moved under the batch, request_conflict
                for a reused id with different arguments.
        """
        from ..execution.pyexec.apply_context import compile_batch

        label = batch.get("label", "")
        intents = batch.get("intents", ())
        envelope = batch.get("envelope") or dump_yaml_text(
            {"operation": "apply_batch", "arguments": batch}
        )
        compiled = compile_batch(batch)
        request_id = "apply-" + hashlib.sha256(
            envelope.encode("utf-8")).hexdigest()[:32]
        command_text = dump_yaml_text(
            {"operation": "apply_batch",
             "arguments": {"label": label, "intents": intents}}
        )
        head = self._project.snapshot()["current_revision"]
        landed = self._project.apply_transaction(
            compiled["changes"], request_id, command_text,
            expected_revision=head)
        return {
            "ok": True,
            "operation": "apply_batch",
            "project_id": self._project_id,
            "label": label,
            "revision": landed["current_revision"],
            "previous_revision": landed.get("previous_revision"),
            "landed": compiled["landed"],
            "unlanded": compiled["unlanded"],
            "applied": len(compiled["changes"]),
            "request_id": request_id,
        }

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

    def _submit_console(self, name, arguments, command):
        """Admit one console lifecycle op on the shared envelope.

        Identity comes from the rendered console envelope, so
        console history replays as command scripts by
        construction. Consoles are Engine-memory and
        workspace-bound — no ledger admission, no revision gate.
        ExecutionError from the lifecycle (unknown_console)
        passes through unwrapped, like python_execute refusals.

        Args:
            name: python_open or python_reset.
            arguments: Lifecycle arguments (workspace_root for
                open, console_id for reset).
            command: Envelope carrying request_id.

        Returns:
            Opening (open) or fresh generation (reset) plus
            the request_id.

        Raises:
            ProjectError: invalid_command for an unknown console
                operation name.
        """
        if name not in ("python_open", "python_reset"):
            raise ProjectError(
                "invalid_command",
                f"Not a console lifecycle operation: {name!r}.",
            )
        command_text = console_envelope(name, dict(arguments))
        request_id = str(command.get("request_id") or uuid.uuid4().hex)
        if name == "python_open":
            out = self.open_console(
                workspace_root=arguments.get("workspace_root"))
        else:
            out = self.reset_console(
                console_id=arguments.get("console_id"))
        return {**out, "request_id": request_id,
                "command_text": command_text}
