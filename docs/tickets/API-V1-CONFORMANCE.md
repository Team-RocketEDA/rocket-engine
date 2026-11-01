# API-V1-CONFORMANCE: Prove v1 consumers/providers and installed workflows before deployment

*Status: Ready · Design: ADR-014 · Created: 2026-11-01*

Depends: API-V1-CORE, API-V1-EDITORS, TESTBENCH-COMPONENT, API-V1-TOOLS, API-V1-CLIENTS, CANVAS-CST. Design fixtures currently prove contract shape only, never provider/tool behavior.

Gate: types/help regenerate unchanged; every real serialized response/result/error/event validates canonical schema; all fixtures/unknown/null/empty/unsupported cases pass. Meet execution C01-C17 matrix, editor/testbench scoped scenarios, source save and working/pinned ref behavior, cross-transport one-runtime identity, atomic CAS/rollback, admission saturation and retry, shared coalescing, independent concurrency/gated workflows, cancel completion race, disconnect/restart survivors/no auto-run, ordered event cursor expiry/resync and complete I28 drift probes. Run installed representative digital/analog/photonic/mixed fixtures with native tools and known-good/known-bad mutations. Verify current migration passes both consumer and provider conformance against SAME artifact.

Check canonical canvas.toml file/migration/default templates/inline knobs/authored HDL isolation; generated downstream HDL and imported hard macro models correctly distinguished. Verify every package/tool marked ready really passes its qualified inputs and all required deployment profiles. No full readiness claim on Python import, process exit0, GDS existence, fixture-only wiring or schema-only checks. Preserve <=3000-line source-module boundary and current one-runtime policy. Document remaining blocked capabilities with precise remedy and scope.
