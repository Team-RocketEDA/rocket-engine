"""Console lifecycle: open/status/reset/close on the shared envelope.

Identity plus generation, per the BWRAP-STUDY ruling: the console
is a plain python console on trusted-local user permissions, every
cell runs in a confined worker, and where bwrap is unprovable the
surface still records generations and approvals but admits
nothing. This module owns the recording half only — identity,
generation rotation, workspace binding — and never spawns a
worker, never touches the runner, and never changes sandbox
behavior.

Scoping decision (CONSOLE-LIFECYCLE): `stdio_console` keeps its
local-panel REPL protocol (`submit`/`history`/`reset` over stdio);
the Engine-side lifecycle operations (`python_open`,
`python_execute`, `python_reset`) travel as shared-envelope
command texts rendered here, so the adapt lane wires the three
operations through `console_envelope`/`parse_console_envelope`
without inventing a second envelope shape. The operations
themselves are vocabulary/composition wiring (adapt lane); this
module pins the envelope contract they must speak.

Seam: `session_for` exposes the underlying `ConsoleSession` to the
worker lane (`CellRunner.admit_cell`) and to tests; Engine wiring
calls `open_console`/`reset_console` and never reaches past them.
"""

import uuid

from ruamel.yaml import YAML

from ..errors import ExecutionError
from ..routing.calls import admission_envelope
from .apply_session import ConsoleSession

#: Lifecycle operations converging on the shared envelope. The
#: Engine does not wire them yet (adapt lane); the envelope shape
#: here is the contract that wiring must speak.
CONSOLE_OPERATIONS = frozenset(
    {"python_open", "python_execute", "python_reset"}
)

_yaml = YAML(typ="safe")


def console_envelope(operation, arguments):
    """Render one console lifecycle command on the shared envelope.

    The text uses the identical YAML dumper the Engine uses for
    every admission, so equal calls admit with equal identity and
    console history replays as command scripts by construction.

    Args:
        operation: Console lifecycle operation (python_open,
            python_execute, python_reset).
        arguments: Operation arguments mapping.

    Returns:
        Envelope command text for the call.

    Raises:
        ExecutionError: invalid_command for an operation outside
            the console lifecycle set or unserializable arguments.
    """
    if operation not in CONSOLE_OPERATIONS:
        raise ExecutionError(
            "invalid_command",
            f"Not a console lifecycle operation: {operation!r}.",
        )
    if not isinstance(arguments, dict):
        raise ExecutionError(
            "invalid_command",
            f"Envelope needs mapping arguments, got {arguments!r}.",
        )
    try:
        return admission_envelope(operation, arguments)
    except ExecutionError as exc:
        raise ExecutionError("invalid_command", str(exc)) from exc


def parse_console_envelope(text):
    """Parse one console envelope back to operation + arguments.

    Args:
        text: Envelope command text from `console_envelope`.

    Returns:
        Mapping with operation and arguments.

    Raises:
        ExecutionError: invalid_command for unparsable text, a
            non-mapping envelope, or an operation outside the
            console lifecycle set.
    """
    if not isinstance(text, str) or not text.strip():
        raise ExecutionError(
            "invalid_command", "Console envelope must be text."
        )
    try:
        document = _yaml.load(text)
    except Exception as exc:
        raise ExecutionError(
            "invalid_command",
            f"Console envelope does not parse: {exc}.",
        ) from exc
    if not isinstance(document, dict):
        raise ExecutionError(
            "invalid_command",
            f"Console envelope must be a mapping, got {document!r}.",
        )
    operation = document.get("operation")
    arguments = document.get("arguments")
    if operation not in CONSOLE_OPERATIONS or not isinstance(
        arguments, dict
    ):
        raise ExecutionError(
            "invalid_command",
            f"Not a console lifecycle envelope: {document!r}.",
        )
    return {"operation": operation, "arguments": dict(arguments)}


class ConsoleLifecycle:
    """Console identity + generation registry (lifecycle only).

    `open_console` mints one console per call — or reuses the live
    handle when the same workspace root opens again (single
    console per panel). `reset_console` retires the generation and
    kills every outstanding approval through the session; live
    workers are cancel territory, never reset. Nothing here
    executes: admission and execution stay in the worker lane.

    Args:
        None.
    """

    def __init__(self):
        self._consoles = {}
        self._roots = {}

    def open_console(self, project_id, actor, workspace_root=None):
        """Open a console, reusing the live one for its workspace.

        Args:
            project_id: Project the console approves cells for.
            actor: Actor recorded on approvals.
            workspace_root: Panel workspace binding; one live
                handle per root, unbound when omitted.

        Returns:
            Opening with console_id, project_id, generation, and
                the workspace_root binding (None when unbound).
        """
        if workspace_root is not None:
            live = self._roots.get(str(workspace_root))
            if live is not None and live in self._consoles:
                record = self._consoles[live]
                return self._describe(record)
        console_id = uuid.uuid4().hex
        session = ConsoleSession(project_id, actor)
        record = {
            "console_id": console_id,
            "project_id": project_id,
            "actor": actor,
            "workspace_root": (
                None if workspace_root is None
                else str(workspace_root)
            ),
            "session": session,
        }
        self._consoles[console_id] = record
        if record["workspace_root"] is not None:
            self._roots[record["workspace_root"]] = console_id
        return self._describe(record)

    def status(self, console_id):
        """Read one console's lifecycle state (never executes).

        Args:
            console_id: Console from `open_console`.

        Returns:
            Status with console_id, project_id, generation, and
                the workspace_root binding.

        Raises:
            ExecutionError: unknown_console for an id never
                opened or already closed.
        """
        return self._describe(self._record(console_id))

    def session_for(self, console_id):
        """Return the live session for worker-lane admission.

        Worker-lane seam: `CellRunner.admit_cell` binds through
        the session; Engine wiring never reaches past
        `open_console`/`reset_console`.

        Args:
            console_id: Console from `open_console`.

        Returns:
            Live `ConsoleSession` for the console.

        Raises:
            ExecutionError: unknown_console for an id never
                opened or already closed.
        """
        return self._record(console_id)["session"]

    def reset_console(self, console_id):
        """Retire the generation; kill every outstanding approval.

        Args:
            console_id: Console from `open_console`.

        Returns:
            Mapping with the console_id and the fresh generation.

        Raises:
            ExecutionError: unknown_console for an id never
                opened or already closed.
        """
        record = self._record(console_id)
        outcome = record["session"].reset()
        return {
            "console_id": console_id,
            "generation": outcome["generation"],
        }

    def close_console(self, console_id):
        """Close a console and release its workspace binding.

        Args:
            console_id: Console from `open_console`.

        Returns:
            Closing with console_id and closed True.

        Raises:
            ExecutionError: unknown_console for an id never
                opened or already closed.
        """
        record = self._record(console_id)
        del self._consoles[console_id]
        root = record["workspace_root"]
        if root is not None and self._roots.get(root) == console_id:
            del self._roots[root]
        return {"console_id": console_id, "closed": True}

    def _record(self, console_id):
        try:
            return self._consoles[console_id]
        except KeyError:
            raise ExecutionError(
                "unknown_console", f"Unknown console: {console_id!r}."
            ) from None

    @staticmethod
    def _describe(record):
        return {
            "console_id": record["console_id"],
            "project_id": record["project_id"],
            "generation": record["session"].generation,
            "workspace_root": record["workspace_root"],
        }
