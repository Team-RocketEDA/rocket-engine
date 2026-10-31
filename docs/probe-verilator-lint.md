# Verilator lint probe (run_syntax alternative, 2026-10-28)

Lint path beside slang. Tool: Verilator 5.053 (oss-cad-suite dev
convenience at `~/tools/oss-cad-suite`; PATH placement is B10 scope).
Reused the HDL counter fixtures.

## Verified protocol

`verilator --lint-only --top-module <top> sources...`:

| Case | Exit | Output |
|---|---|---|
| clean | 0 | `Verilation Report` lines on stdout, nothing on stderr |
| syntax error | 1 | `%Error: file:line:col: msg` + source context + caret on stderr, then `%Error: Exiting due to 1 error(s)` |
| width truncation (default flags) | 1 | `%Warning-WIDTHTRUNC: file:line:col: msg` + context + doc-link lines on stderr, then `%Error: Exiting due to 1 warning(s)` |
| `-Wall` unused signal | 1 | `%Warning-UNUSEDSIGNAL: ...`, same trailer |

Notes:

- Warnings are fatal to the exit code: warnings-only still exits 1
  with an `%Error: Exiting due to N warning(s)` trailer. An adapter
  MUST parse text, never trust the exit code — the inverse of the
  Icarus lesson (exit 0 with failures) but the same rule.
- Error vs warning-only is decided by parsing: real errors start
  `%Error: file:...`; the warnings-only trailer says `warning(s)`.
  Parse only lines matching `^%((?:Error)|(Warning)-([A-Z0-9_]+)):
  \s*(.+?):(\d+):(\d+):`; skip context, caret, `... note:` and
  `... For warning description` lines.
- Diagnostics carry file, line, AND column — the full engine-api
  diagnostic shape `{file, line, col, severity, rule, message}`,
  with the rule inline (`WIDTHTRUNC`, `UNUSEDSIGNAL`, ...).
- Default ruleset is stricter than slang's: truncation warns without
  flags. `-Wall` adds filename/usage rules (`DECLFILENAME`,
  `UNUSEDSIGNAL`) that are noisy for lint-as-syntax-check; default
  flags are the better starting point.
- `--top-module` was passed explicitly; verilator auto-selects a top
  otherwise, which can surprise on multi-module files.

## Vs slang (`probe-slang-syntax.md`)

| | slang `--lint-only -Wextra` | verilator `--lint-only` |
|---|---|---|
| clean exit | 0 | 0 |
| warnings-only exit | 0 (trustworthy) | 1 (fatal trailer) |
| default warnings | sparse, needs `-Wextra` | truncation on by default |
| diagnostic shape | `file:line:col: severity: msg [-Wrule]` | `%Warning-RULE: file:line:col: msg` |
| speed | parse-only, fast | elaborates, slower |

Slang stays the `run_syntax` default: fast, honest exit codes, and
warnings that never fail the verdict. Verilator lint is a candidate
second solver (`deck.tool` select) for stricter elaboration-level
checks once B10 provisions it — verdict from parsed `%Error:` lines,
warnings as warning-severity violations.

## Adapter sketch (if scheduled)

- `preflight`: verilator on PATH (or job `tool_dir`), sources exist,
  top module known.
- `execute`: `verilator --lint-only --top-module <top> sources...`,
  capture streams separately (report on stdout, diagnostics stderr).
- `parse`: `%Error: file` lines → error violations; `%Warning-RULE:`
  lines → warning violations with rule; ignore the `Exiting due to`
  trailer except as a count cross-check.
- Fixtures: reuse `tests/adapters/fixtures/hdl/` counter set; the
  truncation case is a warnings-only verdict-PASS check (this is the
  case that catches exit-code trust).
