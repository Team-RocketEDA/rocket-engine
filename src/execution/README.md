# execution — the live Python environment + job lifecycle

## Responsibility (PRD)

This module houses the **live Python execution environment the IDE
uses as its terminal**. Every "Run" in RocketIDE's Python panel — and
every MCP `python_execute` call — executes here, in a prepared,
locked-profile, OS-isolated worker with the project/PDK/IP/tool
proxies prebound. The terminal UI lives in RocketIDE; the interpreter,
sandbox, lifecycle, and authority it talks to live here.

Four parts, one owner:

- **workers/** — the live env: prepared UV profiles, fresh worker per
  execution (console cell or tool job), scoped credentials, Bubblewrap
  namespaces + seccomp + cgroup, confirmed process-tree termination.
- **queue/** — admission, queueing, dispatch, cancellation races.
- **evidence/** — immutable input locks, artifact manifests, freshness.
- **evaluator/** — verdicts (PASS/FAIL/NOT_RUN/UNSUPPORTED), bounded
  summaries with cursors, executable-closure approval gate.

PRD sources:
[frontend-tooling-spec §3–§4](../PRD/tools-research/frontend-tooling-spec.md),
[python-console-spec](../PRD/tools-research/python-console-spec.md)
(worker lifecycle, isolation, approval binding),
[suggested-api §11](../PRD/tools-research/suggested-api.md) (evidence).
Blueprint B4; console UX surface (B8) lands here later, not as a new
module.

## Inputs

- Admitted jobs from `project/`; tool results from
  `adapters/<solver>/`; human approvals from the trusted UI route.

## Outputs

- Live execution (terminal output, effects, child runs), evidence
  manifests, verdicts, cancellation outcomes. Unavailable sandbox
  disables admission — never host fallback.

## Boundaries

Owns: the live env, dispatch, isolation, evidence, evaluation. Must
not own: solver CLIs, check planning, transport protocols, any UI.

## Routing

- Evidence/record shapes → `../interfaces/README.md`.
- State and events → `../project/README.md`.
- Which stages exist → `../workflows/README.md`.
- Which tool runs a job → `../adapters/README.md`.

## Status

GREEN (slice 2): `service.py` (in-memory dispatch, evidence,
evaluation, approvals), `errors.py` (`ExecutionError`). Real workers,
live console env, and persistence arrive in later slices.
Invariants I08–I11, I22 proven, plus I15, I17, I18 via
`console.py` (real binding semantics; execution itself still
in-memory). `runner.py` (`BwrapRunner`) confines solver subprocesses
in userns sandboxes (I16 mechanics; net isolation re-proven on
target). Tests: `tests/execution/` (22 passed). I23, I24 await the
real worker substrate.
