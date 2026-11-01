# execution — run lifecycle, isolation, and verdicts

`execution/` provides run-state services and execution helpers used by the engine composition root. It covers admission/backpressure, solver process isolation, the Python execution approval surface, normalized evidence, and verdict evaluation. It contains no UI code and owns no solver-specific parsing.

## Main pieces

- `service.py`: in-memory run and approval records, cancellation state, evidence/findings access, and verdict evaluation. Run records live for the lifetime of the `Engine` instance.
- `apig_pool.py`, `coalesce.py`, and `block_runs_scope.py`: bounded dispatch, duplicate-submit coalescing, and block-scoped run input handling.
- `runner.py`: subprocess helpers and `BwrapRunner` for OS-level tool isolation when the host supports the required sandbox.
- `replay_safe.py`: reports interrupted runs after restart and requires an explicit resume or discard decision; it does not silently re-execute survivors.
- `python_exec.py` and `console.py`: project-script/console request handling and approval-binding semantics. `python_execute` requests admission; the caller cannot approve its own code.
- `dispatch.py`: shared operation-call parsing and dispatch used by the CLI and console paths.

## Run flow

`Engine.submit` validates and admits a solver operation, captures its project context, dispatches the selected adapter, and normally returns the completed result inline. `run_job` is available for deferred work, pool draining, batch pumping, and idempotent retrieval of an admitted run's completion. The two surfaces share the same run IDs and verdict rules.

Solver adapters return structured findings, measurements, and artifacts. The engine evaluates those results into `PASS`, `FAIL`, `NOT_RUN`, or `UNSUPPORTED`; a zero process exit does not establish `PASS`. Missing isolation support disables isolated work instead of falling back to an unrestricted host process.

## Persistence boundary

The project ledger can persist when `engine_root` is configured, but `ExecutionService` run state and captured logs are in-memory per engine instance. The MCP launcher can write completed run evidence under the bound project's `results/engine-runs/`. These are separate lifecycles; do not assume every queue item or log survives an engine restart.

## Routing

- Project revisions/events → [`project/`](../project/README.md).
- Result and command records → [`interfaces/`](../interfaces/README.md).
- Tool invocation and parsing → [`adapters/`](../adapters/README.md).
- Process ordering and the fully-verified gate → [`workflows/`](../workflows/README.md).
- Isolation and console contracts → [Python console spec](../../../PRD/tools-research/python-console-spec.md).
