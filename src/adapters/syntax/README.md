# adapters/syntax — Slang syntax solver

`run_syntax` behind the `ToolAdapter` port: preflight refuses the
wrong operation, bad timeouts/flags, missing sources, and unresolvable
tools; execute runs `slang --lint-only -Wextra`; parse normalizes
`file:line:col:` diagnostics plus the Build summary into
`{total, violations[]}` with file/line/col locations and rule flags.

Verified against slang 12.0.0 on counter fixtures
(`tests/adapters/fixtures/syntax/`). Errors fail, warnings never do,
and a failed build with no parsed diagnostics reports a synthesized
error rather than going clean.

Tool resolution is PATH plus an explicit job `tool_dir`; where the
tools live is B10 scope. No Engine registration yet (deploy-time
config, like the sim adapter).
