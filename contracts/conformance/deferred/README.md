# Deferred provider RED contracts

The user explicitly deferred all FPGA work off MVP and FEM/EM/field/mode/thermal/device work until after November 4. The typed contracts remain part of the common API. This explicit suite records missing provider behavior without making deferred tools a prerequisite of the default MVP test target.

Run from `rocket-engine`:

```sh
.venv/bin/python -m pytest -q contracts/conformance/deferred/test_delivery.py --tb=short
```

The tests use the current real `Engine` and public `HttpTransport`; they do not run native tools, return fake numerical data, or use skip/xfail. Task requests reuse the canonical accepted examples rather than a handwritten replacement payload shape.

## Recorded evidence

Date: 2026-11-01. Branch: `GREEN-the-tests`. RED checkpoint: `38a62d6` (root integrator checkpoint). Parent-reported baseline: `310a068`.

The valid RED command above returned **8 failed in 0.07s**:

```text
FFFFFFFF
AdapterError: Missing project_id in request.
8 failed in 0.07s
```

All eight failures reach the real public adapter, which still expects the v0 envelope. The canonical v1 envelope derives project scope from method arguments or task target rather than a top-level v0 `project_id`. This is the intended missing v1 boundary behavior. An initial local fixture-path typo was corrected before the valid RED run; setup failures are not counted as TDD evidence.

| Planned guarantee | Test | Current evidence |
|---|---|---|
| FPGA discovery exposes `off_mvp`, typed schema and non-ready state | `test_deferred_task_describes_delivery_and_schemas[implement.fpga-off_mvp]` | RED: current adapter rejects the v1 envelope. |
| EM, thermal and device discovery exposes `post_mvp` and typed schema | Same parameterized discovery test for three tasks | RED: same missing v1 boundary. |
| Deferred tasks fail before admission/native execution with typed `capability_unavailable`, explicit delivery reason and `admitted:false` | `test_deferred_task_is_refused_before_native_execution` for all four tasks | RED: current adapter cannot return this v1 response. |

This suite proves a boundary blocker only. It does not prove FPGA place/route, EM numerical behavior, thermal equations, device physics, mesh convergence or native solver correctness. Later implementation must add representative input studies, actual native profiles, known-good/known-bad cases and normalized output evidence for those capabilities.

## Why RED remains separate

`pyproject.toml` discovers the ordinary suite under `tests/`; this opt-in suite lives under `contracts/conformance/deferred/`. It has no marker-based skip or hidden xfail. The explicit command must continue to report its actual result until the provider boundary is implemented. Contract/schema fixtures can become GREEN independently; that must not be called native solver conformance.

Once v1 discovery and the release-profile refusal are implemented, these specific boundary cases may become GREEN even while deferred solvers are still unimplemented. That is correct: their guarantee is honest deferred behavior. Native physics/FPGA completion requires the separate post-MVP acceptance work, not a reinterpretation of these tests.
