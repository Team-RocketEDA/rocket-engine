"""Composition root (B9): the Engine wires core modules for adapters.

Adapters construct against this, never against services directly. The
root owns no domain logic: it routes cataloged names (see
`interfaces.vocabulary`) to live module state. Operations queue through
the project service with revision gating and envelope-id idempotency;
only wired queries read state, the rest honestly report unwired. Tool
execution still queues only — runners arrive with the deck/tool slices.
"""

import io
import uuid

from ruamel.yaml import YAML

from .execution.service import ExecutionService
from .interfaces.vocabulary import OPERATIONS, QUERIES
from .library.catalog import Catalog
from .project.errors import ProjectError
from .project.service import ProjectService

_WIRED_QUERIES = frozenset({"get_project_snapshot"})


class Engine:
    def __init__(self, project_id, actor, catalog_root="."):
        self._project_id = project_id
        self._project = ProjectService(project_id, actor)
        self._execution = ExecutionService(project_id)
        self._catalog = Catalog(catalog_root)
        self._yaml = YAML(typ="safe")

    def snapshot(self):
        return self._project.snapshot()

    def submit(self, command):
        envelope = command.get("project_id")
        if envelope != self._project_id:
            raise ProjectError(
                "cross_project_denied",
                f"Bound to {self._project_id}, got {envelope}.",
            )
        name = command.get("operation")
        arguments = dict(command.get("arguments") or {})
        if name in _WIRED_QUERIES:
            return self._project.snapshot()
        if name in QUERIES or name not in OPERATIONS:
            raise ProjectError(
                "unsupported_operation", f"Operation not wired yet: {name}."
            )
        buf = io.StringIO()
        self._yaml.dump({"operation": name, "arguments": arguments}, buf)
        request_id = command.get("request_id") or uuid.uuid4().hex
        return self._project.submit(
            buf.getvalue(),
            str(request_id),
            expected_revision=arguments.get("expected_revision"),
        )
