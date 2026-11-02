"""Op dispatch: the inbound port shared by CLI, console, and MCP.

One catalog (`interfaces.vocabulary`), one parser of record. Op-call
text — `run_drc tech=scmos timeout_s=30` — parses here into a
validated (operation, arguments) pair; the CLI adapter, batch files,
the REPL, and console-history replay all compile through
`parse_op_call`/`parse_op_tokens` and `OpDispatcher`, so one syntax
is tested once. MCP validates names against the same catalog for
its structured calls. Names in OPERATIONS execute via `engine.run`;
names in QUERIES read via `engine.submit`. Unknown names and
malformed args raise UsageError (the caller maps it to a usage
exit); engine failures propagate untouched so callers report them
honestly. This module imports no adapter and no engine: the engine
arrives as a duck-typed port (`run`/`submit`).
"""

import shlex
import uuid

from ruamel.yaml import YAML

from ..interfaces.vocabulary import OPERATIONS, QUERIES
from .errors import UsageError

__all__ = ["OpDispatcher", "parse_op_call", "parse_op_tokens"]

_yaml = YAML(typ="safe")


def _parse_value(text):
    try:
        return _yaml.load(text)
    except Exception:
        return text


def _check_name(name):
    if name not in OPERATIONS and name not in QUERIES:
        raise UsageError("unsupported_operation", f"Unknown operation: {name}.")


def parse_op_tokens(tokens):
    """Validate pre-split op-call tokens (argv path, no re-splitting).

    First token is the operation, the rest are `key=value` pairs with
    YAML-scalar values (`benches=[ac,tran]`, `deck={tool: klayout}`).
    Unparseable values pass through as raw strings: the CLI owns
    lexical shape, the engine owns semantic validation.

    Args:
        tokens: Pre-split op call; first token is the operation,
            the rest are `key=value` pairs.

    Returns:
        (operation, arguments) pair with YAML-scalar values.

    Raises:
        UsageError: invalid_command for an empty call or a
            malformed argument, unsupported_operation for an
            unknown operation.
    """
    tokens = list(tokens)
    if not tokens:
        raise UsageError("invalid_command", "Empty op call.")
    name = tokens[0]
    _check_name(name)
    arguments = {}
    for token in tokens[1:]:
        key, sep, value_text = token.partition("=")
        if not sep or not key or not value_text:
            raise UsageError(
                "invalid_command",
                f"Malformed argument (want key=value): {token}.",
            )
        arguments[key] = _parse_value(value_text)
    return name, arguments


def parse_op_call(text):
    """Parse one op-call line (batch/REPL path) via `parse_op_tokens`.

    Args:
        text: One op-call line, shell-split before validation.

    Returns:
        (operation, arguments) pair with YAML-scalar values.

    Raises:
        UsageError: invalid_command when the line cannot be split
            or an argument is malformed, unsupported_operation
            for an unknown operation.
    """
    try:
        tokens = shlex.split(text)
    except ValueError as exc:
        raise UsageError(
            "invalid_command", f"Cannot parse op call: {exc}."
        ) from exc
    return parse_op_tokens(tokens)


class OpDispatcher:
    """Route validated op calls to the engine port.

    Args:
        engine: Duck-typed engine port (`run`/`submit`).
        project_id: Project id stamped on every command.
        actor: Actor stamped on every command.
    """

    def __init__(self, engine, project_id="default", actor="cli"):
        self._engine = engine
        self._project_id = project_id
        self._actor = actor

    @property
    def project_id(self):
        """Project id stamped on every dispatched command.

        Returns:
            Bound project id.
        """
        return self._project_id

    @property
    def actor(self):
        """Actor stamped on every dispatched command.

        Returns:
            Bound actor name.
        """
        return self._actor

    def execute(self, operation, arguments, request_id=None):
        """Route one validated op call to the engine port.

        Every call — operations and queries alike — goes through
        `engine.submit`, the one admission path (ledger, revision
        gate, idempotency). Like the MCP server's project binding,
        an operation missing expected_revision is filled from the
        bound engine's current head, so interactive callers admit
        against what they see; an explicit revision always wins,
        and read queries pass through untouched (tier-1 reads never
        carry admission data). Engine failures propagate untouched
        so callers report them honestly.

        Args:
            operation: Cataloged operation or query name.
            arguments: Operation arguments (deck.tool selects the
                solver for runs).
            request_id: Envelope id; generated when omitted.

        Returns:
            Engine result for the operation or query.

        Raises:
            UsageError: unsupported_operation for an unknown name.
        """
        _check_name(operation)
        stamped = dict(arguments)
        if operation not in QUERIES and "expected_revision" not in stamped:
            head = self._current_head()
            if head is not None:
                stamped["expected_revision"] = head
        command = {
            "project_id": self._project_id,
            "operation": operation,
            "arguments": stamped,
            "request_id": request_id or uuid.uuid4().hex,
        }
        return self._engine.submit(command)

    def _current_head(self):
        """Bound engine's head revision, or None when unknowable.

        Duck-typed engines without a snapshot read simply leave
        the call unstamped — the engine then enforces its own gate.

        Returns:
            Current revision string, or None.
        """
        snapshot = getattr(self._engine, "snapshot", None)
        if not callable(snapshot):
            return None
        try:
            return snapshot().get("current_revision")
        except Exception:
            return None

    def execute_line(self, line, request_id=None):
        """Parse one op-call line and route it to the engine port.

        Args:
            line: One op-call line (`operation [key=value ...]`).
            request_id: Envelope id; generated when omitted.

        Returns:
            (operation, result) pair for the routed call.

        Raises:
            UsageError: invalid_command for a malformed line,
                unsupported_operation for an unknown name.
        """
        operation, arguments = parse_op_call(line)
        return operation, self.execute(
            operation, arguments, request_id=request_id
        )
