"""Engine ops mixin: Wired query handlers (events, apig, jobs, layers, logs)."""

from ..execution.apig.pool import stored_completion_from_events
from ..execution.errors import ExecutionError
from ..execution.python_exec import PythonExecService
from ..project.errors import ProjectError
from ..project.service import ProjectService

#: Severity order for ledger-backed findings pages, mirroring the
#: execution record's errors-first paging.
_SEVERITY_RANK = {"error": 0, "warning": 1}


def completion_event_for(events, run_id):
    """Latest run event naming one run, or None.

    Args:
        events: Ledger events in seq order.
        run_id: Run to find.

    Returns:
        The latest run_completed/run_failed event data for the
            run, or None when the run never finished.
    """
    found = None
    for event in events or ():
        if event.get("event") not in ("run_completed", "run_failed"):
            continue
        if (event.get("data") or {}).get("run_id") == run_id:
            found = event.get("data") or {}
    return found


def findings_page_for(data, limit=50, cursor=None):
    """Page ledger-stored findings like the execution record does.

    Args:
        data: Completion event data with findings,
            findings_truncated, and a verdict carrying the full
            finding_counts.
        limit: Maximum findings in this page.
        cursor: Opaque position from a previous page, if any.

    Returns:
        Finding page with total counts, findings, next cursor,
            and truncation flag.
    """
    stored = list(data.get("findings") or [])
    ordered = sorted(
        stored,
        key=lambda f: _SEVERITY_RANK.get(f.get("severity"), 2),
    )
    counts = dict((data.get("verdict") or {}).get("finding_counts") or {})
    if not counts:
        for finding in ordered:
            severity = finding.get("severity", "unknown")
            counts[severity] = counts.get(severity, 0) + 1
    start = int(cursor) if cursor else 0
    page = ordered[start : start + limit]
    remaining = len(ordered) - (start + len(page))
    return {
        "total_counts": counts,
        "findings": page,
        "next_cursor": str(start + len(page)) if remaining > 0 else None,
        "truncated": bool(data.get("findings_truncated")) or remaining > 0,
    }


class _QueryMixin:
    """Wired query handlers (events, apig, jobs, layers, logs)."""

    def _describe_op(self, name):
        """Resolve one cataloged name to its live serving handler.

        The live twin of the MCP server's describe_tool over engine
        objects, so api_search/api_info/api_help report the same
        summaries the generated docs and MCP descriptions serve.

        Args:
            name: Cataloged operation or query name.

        Returns:
            (kind, wired, summary, handlers) with the handler
                refs in generated-spec form.
        """
        from ..composition import (
            ENGINE_OP_METHODS,
            QUERY_ENGINE_METHODS,
            QUERY_METHODS,
            _CRUD_OPERATIONS,
        )
        from ..interfaces.vocabulary import OPERATIONS

        solvers = self._solvers.get(name) or {}
        if solvers:
            adapter = next(iter(solvers.values()))
            cls = type(adapter)
            doc = cls.__doc__ or ""
            summary = doc.splitlines()[0].strip() if doc.splitlines() else ""
            return (
                "operation", True, summary,
                [f"{cls.__module__}.{cls.__qualname__}"],
            )
        if name == "run_job":
            from ..composition import Engine as _Engine

            return (
                "operation", True,
                (_Engine._run_queued.__doc__ or "").splitlines()[0].strip(),
                [
                    "rocket_engine.composition.Engine.run",
                    "rocket_engine.composition.Engine._run_queued",
                ],
            )
        if name == "python_execute":
            return (
                "operation", True,
                (PythonExecService.request_execution.__doc__ or ""
                 ).splitlines()[0].strip(),
                [
                    "rocket_engine.composition.Engine.submit",
                    "rocket_engine.execution.python_exec."
                    "PythonExecService.request_execution",
                ],
            )
        if name in _CRUD_OPERATIONS and hasattr(ProjectService, name):
            target = getattr(ProjectService, name)
            doc = target.__doc__ or ""
            summary = doc.splitlines()[0].strip() if doc.splitlines() else ""
            return (
                "operation", True, summary,
                [f"rocket_engine.project.service.ProjectService.{name}"],
            )
        method = QUERY_METHODS.get(name)
        if method is not None:
            target = getattr(ProjectService, method)
            doc = target.__doc__ or ""
            summary = doc.splitlines()[0].strip() if doc.splitlines() else ""
            return (
                "query", True, summary,
                [f"rocket_engine.project.service.ProjectService.{method}"],
            )
        emethod = QUERY_ENGINE_METHODS.get(name)
        if emethod is not None:
            from ..composition import Engine as _Engine

            target = getattr(_Engine, emethod)
            doc = target.__doc__ or ""
            summary = doc.splitlines()[0].strip() if doc.splitlines() else ""
            return (
                "query", True, summary,
                [f"rocket_engine.composition.Engine.{emethod}"],
            )
        kind = "operation" if name in OPERATIONS else "query"
        return (
            kind, False,
            f"Declared {kind} `{name}`; no handler wired yet.", [],
        )

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

    def _ledger_findings(self, run_id, limit=50, cursor=None):
        """Findings page from the ledger, after a reboot.

        In-memory verdicts answer first; across a reboot the
        completion event answers instead. Runs that never
        finished (or never ran) answer unknown_run.

        Args:
            run_id: Run whose findings to read.
            limit: Maximum findings in this page.
            cursor: Opaque position from a previous page, if any.

        Returns:
            Finding page for the run.

        Raises:
            ExecutionError: unknown_run for an id with no
                completion event.
        """
        data = completion_event_for(self._project.events_since(0), run_id)
        if data is None:
            raise ExecutionError("unknown_run", f"Unknown run: {run_id}.")
        return findings_page_for(data, limit=limit, cursor=cursor)

    def _ledger_logs_page(self, arguments):
        """Log page from the ledger excerpt, after a reboot.

        Serves the stored tail with true trailing line numbers;
        the unrecoverable head reads as an excerpt, flagged so.

        Args:
            arguments: run_logs arguments with run_id, query,
                offset, and limit.

        Returns:
            Page mapping with numbered lines, totals, a more
                flag, and excerpt True.

        Raises:
            ExecutionError: unknown_run for an id with no
                completion event.
        """
        from ..composition import _LOG_PAGE_MAX  # deferred: breaks the ops<->composition cycle
        run_id = arguments.get("run_id")
        data = completion_event_for(self._project.events_since(0), run_id)
        if data is None:
            raise ExecutionError("unknown_run", f"Unknown run: {run_id}.")
        excerpt = (data.get("log_excerpt") or "").splitlines()
        total = data.get("log_lines") or len(excerpt)
        base = total - len(excerpt)
        numbered = [
            (base + index + 1, line) for index, line in enumerate(excerpt)
        ]
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
            "total_lines": total,
            "matched": len(numbered),
            "offset": offset,
            "lines": [f"{n}: {line}" for n, line in page],
            "more": offset + limit < len(numbered),
            "excerpt": True,
        }

    def _logs_page(self, arguments):
        from ..composition import _LOG_PAGE_MAX  # deferred: breaks the ops<->composition cycle
        run_id = arguments.get("run_id")
        try:
            self._execution.status(run_id)  # unknown runs raise unknown_run
        except ExecutionError:
            return self._ledger_logs_page(arguments)
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
