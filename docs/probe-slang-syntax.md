# Slang lint probe (run_syntax input, 2026-10-28)

Syntax-check path beside Icarus elaboration. Tool: slang 12.0.0 from
oss-cad-suite (dev convenience at `~/tools/oss-cad-suite`; PATH
placement is B10 scope). Reused the HDL counter fixtures.

## Verified protocol

`slang --lint-only [-Wextra] sources...`:

| Case | Exit | Output |
|---|---|---|
| clean | 0 | `Build succeeded: 0 errors, 0 warnings` |
| syntax error | 1 | `file:line:col: error: msg` + source context + caret, then `Build failed: 1 error, 0 warnings` |
| `-Wextra` truncation | 0 | `file:line:col: warning: msg [-Wrule]`, then `Build succeeded: 0 errors, 1 warning` |

Notes:

- Default warnings are sparse (unused signal and bare truncation both
  silent); `-Wextra` enables useful ones like `-Wwidth-trunc` with the
  rule flag inline. The adapter should default to `-Wextra`: warnings
  never fail the verdict, and the rule flags feed AI review.
- Diagnostics carry file, line, AND column — the full engine-api
  diagnostic shape `{file, line, col, severity, rule, message}`.
- The summary line (`Build ...: N errors, M warnings`) cross-checks
  parsed counts. Exit code is trustworthy here (1 on errors, 0
  otherwise) but the adapter still parses: exit zero plus zero parsed
  errors is PASS; any parsed error is FAIL.
- Parse only lines matching `^(.+?):(\d+):(\d+):\s*(error|warning):`;
  skip source-context and caret lines.

## Adapter sketch (next: SyntaxAdapter RED)

- `preflight`: slang on PATH (or job `tool_dir`), sources exist.
- `execute`: `slang --lint-only -Wextra sources...`, capture streams.
- `parse`: diagnostics → error/warning violations with file/line/col
  + rule flag; summary line cross-check; total = diagnostic count.
- Fixtures: reuse `tests/adapters/fixtures/hdl/` counter set plus a
  `-Wextra` warning case (`trunc.v` pattern).
- Skip guard: tests skip where slang is absent, same as the sim
  adapter. No Engine registration until the finding-shape unification
  below lands (file/line/col locations must survive `run()`).
