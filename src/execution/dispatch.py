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
    """Parse one op-call line (batch/REPL path) via `parse_op_tokens`."""
    try:
        tokens = shlex.split(text)
    except ValueError as exc:
        raise UsageError(
            "invalid_command", f"Cannot parse op call: {exc}."
        ) from exc
    return parse_op_tokens(tokens)


class OpDispatcher:
    """Route validated op calls to the engine port."""

    def __init__(self, engine, project_id="default", actor="cli"):
        self._engine = engine
        self._project_id = project_id
        self._actor = actor

    @property
    def project_id(self):
        return self._project_id

    @property
    def actor(self):
        return self._actor

    def execute(self, operation, arguments, request_id=None):
        _check_name(operation)
        command = {
            "project_id": self._project_id,
            "operation": operation,
            "arguments": dict(arguments),
            "request_id": request_id or uuid.uuid4().hex,
        }
        if operation in QUERIES:
            return self._engine.submit(command)
        return self._engine.run(command)

    def execute_line(self, line, request_id=None):
        operation, arguments = parse_op_call(line)
        return operation, self.execute(
            operation, arguments, request_id=request_id
        )
