"""Engine ops mixin: Wired query handlers (events, apig, jobs, layers, logs)."""

from ..execution.apig_pool import stored_completion_from_events
from ..execution.errors import ExecutionError
from ..project.errors import ProjectError


class _QueryMixin:
    """Wired query handlers (events, apig, jobs, layers, logs)."""

    def _query_events_since(self, arguments):
        """Serve the wired get_events_since query (cursor + resync)."""
        cursor = arguments.get("cursor", 0)
        if not isinstance(cursor, int) or isinstance(cursor, bool):
            raise ProjectError(
                "invalid_command", f"Cursor must be an int, got {cursor!r}."
            )
        demand = arguments.get("require_contiguous_from")
        if (
            demand is not None
            and (not isinstance(demand, int) or isinstance(demand, bool))
        ):
            raise ProjectError(
                "invalid_command",
                f"require_contiguous_from must be an int, got {demand!r}.",
            )
        events = self._project.events_since(
            cursor, require_contiguous_from=demand
        )
        return {
            "project_id": self._project_id,
            "events": events,
            "cursor": self._project.snapshot()["event_cursor"],
        }

    def _query_apig(self, name, arguments):
        """Route a catalogue/asset query to its Engine reader."""
        if name == "list_cells":
            return self.catalog_cells(pdk=arguments.get("pdk"))
        if name == "serve_asset":
            return self.serve_asset(
                arguments.get("pdk_id"),
                arguments.get("revision"),
                arguments.get("path"),
                engine_root=arguments.get("engine_root"),
            )
        if name == "list_assets":
            return self.list_assets(
                arguments.get("pdk_id"),
                arguments.get("revision"),
                prefix=arguments.get("prefix"),
                engine_root=arguments.get("engine_root"),
            )
        raise ProjectError("unsupported_operation", f"Operation not wired yet: {name}.")

    def _query_job(self, name, arguments):
        """Route a job-result query to its Engine reader."""
        if name == "get_job_status":
            return self.job_status(arguments.get("run_id"))
        if name == "get_check_results":
            return self.check_results(arguments.get("operation"))
        if name == "get_logs":
            return self.run_logs(
                arguments.get("run_id"),
                query=arguments.get("query"),
                offset=arguments.get("offset", 0),
                limit=arguments.get("limit", 40),
            )
        if name == "list_job_kinds":
            return self.job_kinds()
        raise ProjectError("unsupported_operation", f"Operation not wired yet: {name}.")

    def _query_completion(self, name, arguments):
        """Route a completion query to its Engine reader."""
        if name == "plan_checks":
            return self.plan_checks(arguments.get("flow"))
        if name == "get_design_completion":
            return self.design_completion(arguments.get("flow"))
        raise ProjectError("unsupported_operation", f"Operation not wired yet: {name}.")

    def _query_layer(self, name, arguments):
        """Route a layer-serving query to its Engine reader."""
        if name == "get_layer_stackup":
            return self.layer_stackup(
                arguments.get("pdk_id"),
                revision=arguments.get("revision"),
                engine_root=arguments.get("engine_root"),
            )
        if name == "get_layer_rows":
            return self.layer_rows(
                arguments.get("pdk_id"),
                preset=arguments.get("preset"),
                overrides=arguments.get("overrides"),
                active=arguments.get("active"),
                revision=arguments.get("revision"),
                engine_root=arguments.get("engine_root"),
            )
        if name == "list_layer_presets":
            return self.layer_presets()
        if name == "save_layer_preset":
            return self.layer_preset_save(
                arguments.get("pdk_id"),
                arguments.get("name"),
                arguments.get("layers"),
                render_layers=arguments.get("render_layers"),
                flip=arguments.get("flip", False),
                active=arguments.get("active"),
                overwrite=arguments.get("overwrite", False),
                revision=arguments.get("revision"),
                engine_root=arguments.get("engine_root"),
            )
        if name == "delete_layer_preset":
            return self.layer_preset_delete(arguments.get("name"))
        if name == "apply_layer_preset":
            return self.layer_preset_apply(
                arguments.get("pdk_id"),
                arguments.get("name"),
                revision=arguments.get("revision"),
                engine_root=arguments.get("engine_root"),
            )
        raise ProjectError("unsupported_operation", f"Operation not wired yet: {name}.")

    def _logs_page(self, arguments):
        from ..composition import _LOG_PAGE_MAX  # deferred: breaks the ops<->composition cycle
        run_id = arguments.get("run_id")
        self._execution.status(run_id)  # unknown runs raise unknown_run
        lines = self._logs.get(run_id, "").splitlines()
        numbered = [(index + 1, line) for index, line in enumerate(lines)]
        query = arguments.get("query")
        if query:
            numbered = [(n, line) for n, line in numbered if query.lower() in line.lower()]
        try:
            offset = max(0, int(arguments.get("offset", 0)))
        except (TypeError, ValueError):
            raise ProjectError(
                "invalid_command",
                f"get_logs offset must be an int, got {arguments.get('offset')!r}.",
            ) from None
        try:
            limit = max(1, min(int(arguments.get("limit", 40)), _LOG_PAGE_MAX))
        except (TypeError, ValueError):
            raise ProjectError(
                "invalid_command", f"get_logs limit must be an int, got {arguments.get('limit')!r}."
            ) from None
        page = numbered[offset : offset + limit]
        return {
            "run_id": run_id,
            "total_lines": len(lines),
            "matched": len(numbered),
            "offset": offset,
            "lines": [f"{n}: {line}" for n, line in page],
            "more": offset + limit < len(numbered),
        }

    def _stored_completion(self, run_id):
        """Stored completion for a finished run, without executing.

        In-memory verdicts answer first; across a reboot the
        ledger's run event answers instead. Runs that never
        finished (or never ran) answer None.
        """
        try:
            status = self._execution.status(run_id)
        except ExecutionError:
            status = None
        if (
            status is not None
            and status.get("state") in ("completed", "cancelled")
            and status.get("verdict") is not None
        ):
            pending = self._run_jobs.get(run_id, {})
            return {
                "run_id": run_id,
                "state": status["state"],
                "verdict": status["verdict"],
                "operation": pending.get("operation"),
            }
        return stored_completion_from_events(
            self._project.events_since(0), run_id
        )
