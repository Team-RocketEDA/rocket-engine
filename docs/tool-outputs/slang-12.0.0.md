# slang 12.0.0 — lint diagnostics (run_syntax)

Version provenance: verified against slang 12.0.0 per
`src/adapters/syntax/__init__.py:1-13`. Grammar transcribed from
the adapter's diagnostic and summary regexes; canned outputs in
`tests/test_coverage_wave1.py` are transcribed, not live runs.

## Report inventory

One mode: `slang --lint-only -Wextra` over the sources
(`syntax:121-153`). Native output is `{exit_code, stdout, stderr,
sources}`; diagnostics are parsed from stdout + stderr combined,
plus the Build summary line (`syntax:155-202`).

## Grammar

Diagnostic (`syntax:28`):

```ebnf
FILE ":" LINE ":" COL ": " ("error"|"warning") ": " MESSAGE
```

`MESSAGE` may carry a trailing rule tag `[` `-W` NAME `]`
(`syntax:29`); untagged diagnostics parse under rule `syntax`.
Summary (`syntax:30`):

```ebnf
"Build " ("succeeded"|"failed") ": " INT " errors, " INT " warnings"
```

Errors are FAIL, warnings never fail (`syntax:34-38`). Parsed
result: `{total, violations[]}` with rule, severity, message, and
file/line/col.

## Exit states

- Exit code is trustworthy here (0 clean, 1 errors) but the
  verdict still comes from parsed output (`syntax:6-9`).
- A failed build with no parsed error diagnostics synthesizes
  one error rather than going clean (`syntax:193-201`).
- Output with no Build summary line: `runner_unavailable`
  (`syntax:187-191`) — unparseable never parses as clean.
- Timeout: `runner_unavailable` (`syntax:230-239`).

## Version sensitivity

Stable: `file:line:col: severity:` shape, Build summary line.
Incidental: diagnostic message wording and `-W` tag names across
slang releases; flag spelling beyond `-Wextra`.

## Out of scope

Elaboration effects (that is `yosys_slang`/synthesis scope);
warning policy (warnings never fail, by contract).

## Fixtures

- `tests/adapters/fixtures/syntax/counter.v` (clean).
- `tests/adapters/fixtures/syntax/counter_broken.v` (error).
- `tests/adapters/fixtures/syntax/trunc.v` (truncation probe).
- `tests/adapters/fixtures/hdl/` (shared HDL corpus, incl.
  picorv32-class sources).
