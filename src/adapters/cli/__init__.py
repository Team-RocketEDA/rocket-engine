"""CLI inbound adapter: argv parsing + result formatting over dispatch.

`rocket-engine` (this module via `python -m rocket_engine`): bare
args drop into the interactive REPL; `run <op> [key=value ...]`
runs one op; `--batch FILE`/`-` batch-executes op lines; `--json`
gives stable machine output. Op text parses through the one parser
of record (`execution.dispatch`); this adapter never parses op
calls itself, never calls another adapter, and holds no rules.

Exits: 0 execution-ok EVEN when the verdict is FAIL (verdicts live
in the payload, never in exit codes); 1 engine error; 2 usage
error (unknown op/args). Batch aggregates: any usage error -> 2,
else any engine error -> 1, else 0.
"""

import json
import sys

from ...composition import Engine
from ...execution.dispatch import OpDispatcher, parse_op_call, parse_op_tokens
from ...execution.errors import UsageError
from ..errors import AdapterError

__all__ = ["EXIT_ENGINE_ERROR", "EXIT_OK", "EXIT_USAGE", "USAGE", "main"]

EXIT_OK = 0
EXIT_ENGINE_ERROR = 1
EXIT_USAGE = 2

USAGE = """usage: rocket-engine [--project ID] [--actor NAME] [--request-id ID] [--json] [--batch FILE|-] [run <op> [key=value ...]]

No args drops into the interactive REPL (one op call per line,
blank lines and `#` comments skipped, `quit` to leave). `run`
executes one op call; `--batch` executes every op-call line of a
file (`-` reads stdin). `--json` prints stable machine envelopes.
`--request-id` stamps a caller id on a single `run` (batch and
REPL lines always mint their own, so repeats stay distinct).
Op calls are `<operation> [key=value ...]` with YAML-scalar values
(`benches=[ac,tran]`, `deck={tool: klayout}`); quote values with
spaces. Every call — queries and operations alike — goes through
submit, the one admission path.

Exits: 0 execution-ok (even when the verdict is FAIL — read the
payload); 1 engine error; 2 usage error (unknown op/args).
"""


def _split_flag(token, name):
    prefix = f"--{name}="
    if token.startswith(prefix):
        return token[len(prefix):]
    return None


def _parse_argv(argv):
    options = {"json": False, "batch": None, "project": "default",
               "actor": "cli", "request_id": None, "help": False}
    rest = []
    i = 0
    while i < len(argv):
        token = argv[i]
        if token == "--json":
            options["json"] = True
        elif token in ("--help", "-h"):
            options["help"] = True
        elif token == "--batch":
            i += 1
            if i >= len(argv):
                raise UsageError(
                    "invalid_command", "`--batch` needs a FILE (`-` for stdin).")
            options["batch"] = argv[i]
        elif token == "--project":
            i += 1
            if i >= len(argv):
                raise UsageError("invalid_command", "`--project` needs an ID.")
            options["project"] = argv[i]
        elif token == "--actor":
            i += 1
            if i >= len(argv):
                raise UsageError("invalid_command", "`--actor` needs a NAME.")
            options["actor"] = argv[i]
        elif token == "--request-id":
            i += 1
            if i >= len(argv):
                raise UsageError(
                    "invalid_command", "`--request-id` needs an ID.")
            options["request_id"] = argv[i]
        elif _split_flag(token, "batch") is not None:
            options["batch"] = _split_flag(token, "batch")
        elif _split_flag(token, "project") is not None:
            options["project"] = _split_flag(token, "project")
        elif _split_flag(token, "actor") is not None:
            options["actor"] = _split_flag(token, "actor")
        elif _split_flag(token, "request-id") is not None:
            options["request_id"] = _split_flag(token, "request-id")
        elif token == "--":
            rest.extend(argv[i + 1:])
            break
        elif token.startswith("-"):
            raise UsageError("invalid_command", f"Unknown flag: {token}.")
        else:
            rest.extend(argv[i:])
            break
        i += 1
    return options, rest


def _envelope(operation, ok, payload):
    body = {"operation": operation, "ok": ok}
    body["result" if ok else "error"] = payload
    return json.dumps(body, sort_keys=True, default=str)


def _human_summary(operation, result):
    if isinstance(result, dict):
        verdict = result.get("verdict")
        if isinstance(verdict, dict) and "status" in verdict:
            line = f"{operation}: {verdict['status']}"
            if result.get("run_id"):
                line += f" (run {result['run_id']})"
            return line
        return f"{operation}: ok"
    return f"{operation}: {result}"


def _emit_result(operation, result, as_json, stdout):
    if as_json:
        stdout.write(_envelope(operation, True, result) + "\n")
    else:
        stdout.write(_human_summary(operation, result) + "\n")


def _emit_error(operation, exc, as_json, stdout, stderr):
    code = getattr(exc, "code", None) or "internal_error"
    message = str(exc) or code
    if as_json:
        stdout.write(
            _envelope(operation, False, {"code": code, "message": message}) + "\n"
        )
    else:
        stderr.write(f"error [{code}]: {message}\n")
        if isinstance(exc, UsageError):
            stderr.write(USAGE)


def _classify(exc):
    if isinstance(exc, UsageError):
        return EXIT_USAGE
    return EXIT_ENGINE_ERROR


def _run_single(dispatch, options, op_tokens, stdout, stderr):
    if not op_tokens:
        _emit_error(None, UsageError("invalid_command", "`run` needs an operation."),
                    options["json"], stdout, stderr)
        return EXIT_USAGE
    try:
        operation, arguments = parse_op_tokens(op_tokens)
    except UsageError as exc:
        _emit_error(op_tokens[0], exc, options["json"], stdout, stderr)
        return EXIT_USAGE
    try:
        result = dispatch.execute(operation, arguments,
                                  request_id=options["request_id"])
    except Exception as exc:  # engine errors stay data, never tracebacks
        _emit_error(operation, exc, options["json"], stdout, stderr)
        return _classify(exc)
    _emit_result(operation, result, options["json"], stdout)
    return EXIT_OK


def _iter_batch_lines(source, stdin):
    if source == "-":
        return stdin.read().splitlines()
    try:
        with open(source, encoding="utf-8") as handle:
            return handle.read().splitlines()
    except OSError as exc:
        raise AdapterError(
            "batch_unreadable", f"Cannot read batch file {source}: {exc}."
        ) from exc


def _run_batch(dispatch, options, source, stdin, stdout, stderr):
    try:
        lines = _iter_batch_lines(source, stdin)
    except Exception as exc:
        _emit_error(None, exc, options["json"], stdout, stderr)
        return _classify(exc)
    worst = EXIT_OK
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        try:
            operation, result = dispatch.execute_line(stripped)
        except UsageError as exc:
            _emit_error(stripped.split()[0] if stripped.split() else None,
                        exc, options["json"], stdout, stderr)
            worst = max(worst, EXIT_USAGE)
            continue
        except Exception as exc:
            # execute_line parsed this line already; re-parse only to
            # label the envelope — it cannot fail here.
            operation = parse_op_call(stripped)[0]
            _emit_error(operation, exc, options["json"], stdout, stderr)
            worst = max(worst, EXIT_ENGINE_ERROR)
            continue
        _emit_result(operation, result, options["json"], stdout)
    return worst


def _run_repl(dispatch, options, stdin, stdout, stderr):
    interactive = stdin.isatty() if hasattr(stdin, "isatty") else False
    if interactive:
        stdout.write("rocket> ")
        stdout.flush()
    while True:
        line = stdin.readline()
        if line == "":
            break
        stripped = line.strip()
        if interactive:
            stdout.write("rocket> ")
            stdout.flush()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped in ("exit", "quit"):
            break
        if stripped == "help":
            stdout.write(USAGE)
            continue
        try:
            operation, result = dispatch.execute_line(stripped)
        except UsageError as exc:
            _emit_error(stripped.split()[0] if stripped.split() else None,
                        exc, options["json"], stdout, stderr)
            continue
        except Exception as exc:
            operation = parse_op_call(stripped)[0]
            _emit_error(operation, exc, options["json"], stdout, stderr)
            continue
        _emit_result(operation, result, options["json"], stdout)
    return EXIT_OK


def main(argv=None, engine=None, stdin=None, stdout=None, stderr=None):
    """Run the CLI; return the process exit code (never raise for use).

    Bare args drop into the REPL, `run` executes one op, `--batch`
    executes op lines; usage and engine failures become exit codes,
    never tracebacks.

    Args:
        argv: Argument vector without the program name; defaults to
            sys.argv[1:].
        engine: Engine to dispatch against; constructed from
            --project/--actor when omitted.
        stdin: Input stream for the REPL and `--batch -`.
        stdout: Stream for results and machine envelopes.
        stderr: Stream for human-readable errors plus usage.

    Returns:
        Process exit code: 0 execution-ok (even when the verdict
        is FAIL), 1 engine error, 2 usage error.

    Caution: Exit zero is not PASS — the verdict lives in the
        payload; read it, never the exit code.
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    stdin = sys.stdin if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout
    stderr = sys.stderr if stderr is None else stderr
    try:
        options, rest = _parse_argv(argv)
    except UsageError as exc:
        _emit_error(None, exc, False, stdout, stderr)
        return EXIT_USAGE
    if options["help"]:
        stdout.write(USAGE)
        return EXIT_OK
    if options["batch"] is not None and rest[:1] == ["run"]:
        _emit_error(None, UsageError("invalid_command",
                                     "Cannot combine `run` with `--batch`."),
                    options["json"], stdout, stderr)
        return EXIT_USAGE
    if engine is None:
        engine = Engine(options["project"], actor=options["actor"])
    dispatch = OpDispatcher(engine, project_id=options["project"],
                            actor=options["actor"])
    if rest[:1] == ["run"]:
        return _run_single(dispatch, options, rest[1:], stdout, stderr)
    if rest:
        _emit_error(None, UsageError("invalid_command",
                                     f"Unknown command: {rest[0]} (want `run`)."),
                    options["json"], stdout, stderr)
        return EXIT_USAGE
    if options["batch"] is not None:
        return _run_batch(dispatch, options, options["batch"], stdin,
                          stdout, stderr)
    return _run_repl(dispatch, options, stdin, stdout, stderr)


if __name__ == "__main__":
    raise SystemExit(main())
