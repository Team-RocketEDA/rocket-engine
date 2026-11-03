"""Wave-3 editor seam: shared admission helpers plus Engine dispatch.

Service-side endpoint methods stay thin: every Wave-3 mutation
rides the wire envelope through editor_mutation, every computed
read serves through editor_read. Receipts carry I28 closure pins
via pin_receipt. The Engine-side _EditorMixin (query dispatch)
lives here too, so both sides of the seam share one module.
"""

from ..interfaces.errors import ContractError
from ..interfaces.refs import pin_closure
from ..project.errors import ProjectError


def editor_value_error(func):
    """Run editor logic, mapping value errors to ProjectError.

    Args:
        func: Zero-argument callable running the domain op.

    Returns:
        Whatever the domain op returns.

    Raises:
        ProjectError: invalid_command (or the carried code).
    """
    try:
        return func()
    except ValueError as exc:
        raise ProjectError(
            getattr(exc, "code", "invalid_command"), str(exc)
        ) from exc


def pin_receipt(service, receipt):
    """Attach the I28 closure pin to one editor receipt.

    Entity ids carried by the receipt pin their live revisions;
    unresolvable names are skipped, never guessed. Prior partial
    pins (template, profile) are preserved and folded in.

    Args:
        service: ProjectService handle to read through.
        receipt: Editor receipt mapping (mutated in place).

    Returns:
        The same receipt with an i28 closure pin.
    """
    from ..project.edit import cas as _cas

    revisions = {}
    prior = {}
    if isinstance(receipt, dict):
        prior = receipt.get("i28") or {}
        for key in (
            "entity", "sheet", "instance", "binding",
            "symbol", "cell", "ip", "testbench", "shape",
        ):
            candidate = receipt.get(key)
            if not isinstance(candidate, str):
                continue
            try:
                revisions[candidate] = _cas.read_entity_revision(
                    service, candidate)
            except Exception:  # noqa: BLE001 — names skip
                continue
    receipt["i28"] = pin_closure(
        service.snapshot()["current_revision"], entities=revisions,
        template=prior.get("template"),
        profile=prior.get("profile"))
    return receipt


def editor_mutation(service, operation, request_id, command_text,
                    expected_revision, run, describe):
    """Admit one Wave-3 editor op through the wire envelope.

    Inner envelopes derive from the outer request id, so a
    retried envelope replays the verbs that already landed
    instead of minting duplicates.

    Args:
        service: ProjectService handle to write through.
        operation: Editor operation name for the event data.
        request_id: Client envelope id for idempotent replay.
        command_text: YAML command text for identity comparison.
        expected_revision: Revision the writer read.
        run: Callable (store, inner_id, inner_text, live)
            returning the domain receipt.
        describe: Callable (receipt) -> diff summary text.

    Returns:
        Mutation mapping with the pinned receipt, revision
        transition, actor, events, cursor, and request id.

    Raises:
        ProjectError: request_conflict, revision_conflict,
            or the domain refusal code.
    """
    def _run(store):
        return pin_receipt(service, editor_value_error(
            lambda: run(
                store, f"{request_id}:{operation}",
                f"{command_text}\n#inner {operation}",
                service.snapshot()["current_revision"])))
    return service._wire_mutation(
        operation, request_id, command_text,
        expected_revision, _run, describe)


def editor_read(service, operation, func):
    """Serve one Wave-3 computed read with revision and I28.

    Args:
        service: ProjectService handle to read through.
        operation: Read name for the entity-store seam tag.
        func: Callable (store) returning the result mapping.

    Returns:
        Result mapping plus head revision and I28 pin.

    Raises:
        ProjectError: The domain refusal code.
    """
    store = service._entity_store(f"read:{operation}")
    try:
        result = func(store)
    except ContractError as exc:
        raise ProjectError(exc.code, str(exc)) from exc
    return {
        **result,
        "current_revision": service.snapshot()["current_revision"],
        "i28": pin_closure(service.snapshot()["current_revision"]),
    }


#: Wave-3 computed reads served through ProjectService verbs.
_COMPUTED_READS = frozenset({
    "read_entity_revision", "connection_graph", "net_occurrences",
    "xprobe", "resolve_pin", "plot_export", "erc_check",
    "write_netlist", "update_netlist", "check_capability",
    "describe_testbench",
})


class _EditorMixin:
    """Wave-3 editor/testbench query dispatch (Engine side)."""

    def _query_editor(self, name, arguments):
        """Serve one Wave-3 editor/testbench read query.

        Generic entity reads ride the component seams; computed
        reports delegate to the matching ProjectService verb.

        Args:
            name: Wave-3 read query name.
            arguments: Query arguments mapping.

        Returns:
            Read mapping with head revision and I28 pin.

        Raises:
            ProjectError: invalid_command for missing arguments
                or the domain refusal code.
        """
        project = self._project
        if name == "read_entity_revision":
            if "entity" not in arguments:
                raise ProjectError(
                    "invalid_command",
                    "read_entity_revision needs an entity.",
                )
            return project.entity_revision(arguments["entity"])
        if name in ("connection_graph", "net_occurrences"):
            return project.graph_report(
                sheet=arguments.get("sheet"),
                net=arguments.get("net"),
                net_pins=arguments.get("net_pins"))
        if name in ("xprobe", "resolve_pin"):
            for key in ("instance", "pin"):
                if key not in arguments:
                    raise ProjectError(
                        "invalid_command",
                        f"{name} needs {key}.",
                    )
            return project.probe_report(
                arguments["instance"], arguments["pin"],
                net_pins=arguments.get("net_pins"))
        if name == "plot_export":
            return project.plot_report(
                format=arguments.get("format", "svg"),
                sheet=arguments.get("sheet"))
        if name == "erc_check":
            return project.erc_report(
                severities=arguments.get("severities"),
                pin_conflict=arguments.get("pin_conflict"),
                net_pins=arguments.get("net_pins"))
        if name in ("write_netlist", "update_netlist"):
            if "language" not in arguments:
                raise ProjectError(
                    "invalid_command",
                    f"{name} needs a language.",
                )
            return project.netlist_report(
                arguments["language"],
                sheet=arguments.get("sheet"),
                title=arguments.get("title", "top"),
                net_pins=arguments.get("net_pins"),
                prior_text=arguments.get("prior_text"),
                adopted=arguments.get("adopted", False))
        if name == "check_capability":
            for key in ("profile", "operation"):
                if key not in arguments:
                    raise ProjectError(
                        "invalid_command",
                        f"check_capability needs {key}.",
                    )
            return project.capability_report(
                arguments["profile"], arguments["operation"],
                bindings=arguments.get("bindings"))
        if name == "describe_testbench":
            if "testbench" not in arguments:
                raise ProjectError(
                    "invalid_command",
                    "describe_testbench needs a testbench.",
                )
            return project.testbench_report(
                arguments["testbench"])
        return self._query_entities(name, arguments)

    def _query_entities(self, name, arguments):
        """Serve Wave-3 reads through the component seams.

        Args:
            name: Wave-3 entity read query name.
            arguments: Query arguments mapping.

        Returns:
            Entity data with head revision and I28 pin.

        Raises:
            ProjectError: invalid_command for missing arguments
                or the seam refusal code.
        """
        from ..interfaces.refs import pin_closure as _pin

        project = self._project
        head = project.snapshot()["current_revision"]

        def _wrap(payload):
            """Attach head revision and I28 pin to one payload.

            Args:
                payload: Read payload mapping.

            Returns:
                Payload with current_revision and i28 pin.
            """
            return {
                **payload, "current_revision": head,
                "i28": _pin(head),
            }

        if name == "list_sheets":
            return _wrap(project.entities_with("Sheet"))
        if name == "get_sheet":
            if "entity" not in arguments:
                raise ProjectError(
                    "invalid_command",
                    "get_sheet needs an entity.",
                )
            return _wrap(project.get_component(
                arguments["entity"], "Sheet"))
        if name == "get_instance":
            if "entity" not in arguments:
                raise ProjectError(
                    "invalid_command",
                    "get_instance needs an entity.",
                )
            return _wrap(project.get_component(
                arguments["entity"], "Instance"))
        if name == "instances_on_sheet":
            if "sheet" not in arguments:
                raise ProjectError(
                    "invalid_command",
                    "instances_on_sheet needs a sheet.",
                )
            sheet = arguments["sheet"]
            found = []
            for entity in project.entities_with(
                    "Instance")["entities"]:
                data = project.get_component(
                    entity, "Instance")["data"]
                if isinstance(data, dict) and data.get(
                        "sheet") == sheet:
                    found.append(entity)
            return _wrap({"sheet": sheet, "instances": found})
        if name == "list_symbols":
            return _wrap(project.entities_with("Symbol"))
        if name == "get_symbol":
            if "entity" not in arguments:
                raise ProjectError(
                    "invalid_command",
                    "get_symbol needs an entity.",
                )
            return _wrap(project.get_component(
                arguments["entity"], "Symbol"))
        if name == "get_cell":
            if "entity" not in arguments:
                raise ProjectError(
                    "invalid_command",
                    "get_cell needs an entity.",
                )
            return _wrap(project.get_component(
                arguments["entity"], "Cell"))
        if name == "list_layers":
            try:
                doc = project.read_doc("layers/bindings.yaml")
            except ProjectError as exc:
                if exc.code == "unknown_document":
                    raise ProjectError(
                        "invalid_command",
                        "No bindings saved yet: run bind_layers.",
                    ) from exc
                raise
            return _wrap({"bindings_path": doc["path"],
                          "content": doc["content"]})
        if name == "list_testbenches":
            return _wrap(project.entities_with("Testbench"))
        if name == "ip_search":
            if "pdk" not in arguments:
                raise ProjectError(
                    "invalid_command",
                    "ip_search needs a pdk.",
                )
            wanted = arguments.get("name_filter")
            found = []
            for entity in project.entities_with(
                    "IpBlock")["entities"]:
                data = project.get_component(
                    entity, "IpBlock")["data"]
                if not isinstance(data, dict):
                    continue
                if data.get("pdk") != arguments["pdk"]:
                    continue
                if wanted and wanted not in data.get("name", ""):
                    continue
                item = dict(data)
                item["id"] = entity
                found.append(item)
            found.sort(key=lambda item: item.get("version", ""))
            return _wrap({"pdk": arguments["pdk"],
                          "blocks": found})
        if name == "ip_get":
            for key in ("pdk", "name"):
                if key not in arguments:
                    raise ProjectError(
                        "invalid_command",
                        f"ip_get needs {key}.",
                    )
            return _wrap(self._select_ip(
                arguments["pdk"], arguments["name"],
                arguments.get("version")))
        raise ProjectError(
            "unsupported_operation", f"Operation not wired yet: {name}.")

    def _select_ip(self, pdk, name, version):
        """Select one registered IP block, latest when unpinned.

        Args:
            pdk: Owning PDK id (shared blocks qualify too).
            name: Block name within the registry.
            version: Revision label, or None for the greatest.

        Returns:
            Full block mapping with id.

        Raises:
            ProjectError: unknown_ip when no block matches.
        """
        project = self._project
        candidates = []
        for entity in project.entities_with("IpBlock")["entities"]:
            data = project.get_component(entity, "IpBlock")["data"]
            if not isinstance(data, dict):
                continue
            if data.get("name") != name:
                continue
            if data.get("pdk") != pdk and data.get(
                    "scope") != "shared":
                continue
            item = dict(data)
            item["id"] = entity
            candidates.append(item)
        if version is not None:
            for item in candidates:
                if item.get("version") == version:
                    return item
        elif candidates:
            return sorted(
                candidates, key=lambda item: item.get(
                    "version", ""))[-1]
        raise ProjectError(
            "unknown_ip", f"No such IP block: {pdk}/{name}.")
