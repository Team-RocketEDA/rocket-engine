Problem: Engine.cancel_job exists (src/composition.py:941-961) and worker cancel flags exist (python_exec.py:215-216,581-587), but cancel_job is absent from vocabulary OPERATIONS, so MCP rejects it as unsupported_operation and CLI OpDispatcher gates it out. Unreachable on every transport.
Expected-per: tooling-operations.yaml:307-309, frontend-tooling-spec.md:129, python-console-spec.md:32 (console interrupt via cancel_job(run_id)).
Actual-per: method exists, zero wire paths (audit MC-01, comms F3, core F4).
Fix: add cancel_job to vocabulary + submit dispatch + all transports; extend cancel beyond pyexec runs (tree kill per MC-28). Smallest high-value fix; TDD RED->GREEN with a cancel-mid-run test.
